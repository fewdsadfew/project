from __future__ import annotations

import logging
from typing import Optional

from aiogram import Bot, F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from bot.card_sync import post_new_anketa, sync_cards
from bot.config import config
from bot.keyboards import age_kb, cooldown_reset_kb, main_menu_kb, photos_kb, review_kb
from bot.questions import QUESTIONS, TOTAL_STEPS
from bot.services import anketas as anketas_service
from bot.services import users as users_service
from bot.services.settings import get_admin_topic, increment_total_submitted
from bot.states import AnketaForm
from bot.texts import (
    ALREADY_PENDING,
    FIX_CONFIRM_SENT,
    PHOTOS_ONLY,
    SPAM_HELP_REPLY,
    STANDARDS_WARNING,
    SUBMIT_SUCCESS,
)

logger = logging.getLogger(__name__)
router = Router(name="anketa_form")


async def _safe_delete(bot: Bot, chat_id: int, message_id: int) -> None:
    try:
        await bot.delete_message(chat_id, message_id)
    except TelegramBadRequest:
        pass
    except Exception:
        logger.exception("Не удалось удалить сообщение %s в чате %s", message_id, chat_id)


async def _send_question(bot: Bot, chat_id: int, state: FSMContext) -> None:
    data = await state.get_data()
    step = data.get("step", 0)
    prev_msgs = data.get("prev_msgs", [])

    for msg_id in prev_msgs:
        await _safe_delete(bot, chat_id, msg_id)
    prev_msgs = []

    if step >= TOTAL_STEPS:
        return

    question = QUESTIONS[step]

    sticker_id: Optional[str] = None
    if step < len(config.stickers):
        sticker_id = config.stickers[step]

    if sticker_id:
        try:
            sticker_msg = await bot.send_sticker(chat_id, sticker_id)
            prev_msgs.append(sticker_msg.message_id)
        except Exception:
            logger.warning("Не удалось отправить стикер для шага %s", step)

    if question["type"] == "age":
        msg = await bot.send_message(chat_id, question["text"], reply_markup=age_kb())
    elif question["type"] == "photos":
        msg = await bot.send_message(chat_id, question["text"])
    else:
        msg = await bot.send_message(chat_id, question["text"])

    prev_msgs.append(msg.message_id)

    data["step"] = step
    data["prev_msgs"] = prev_msgs
    await state.set_data(data)


async def _start_form(bot: Bot, chat_id: int, state: FSMContext) -> None:
    await state.set_state(AnketaForm.filling)
    await state.update_data(step=0, answers={}, photos=[], prev_msgs=[])
    await _send_question(bot, chat_id, state)


async def _notify_cooldown_reset_request(bot: Bot, applicant) -> None:
    admin_chat_id, admin_topic_id = await get_admin_topic()
    if not admin_chat_id:
        return

    last = await anketas_service.get_last_for_user(applicant.id)
    remaining = await users_service.cooldown_remaining(applicant.id)

    lines = [
        "🔁 <b>Повторная попытка подачи анкеты</b>",
        f"👤 Пользователь: @{applicant.username}" if applicant.username else f"👤 ID: {applicant.id}",
        "📌 Этот человек недавно уже подавал анкету.",
    ]
    if last:
        status_ru = {
            anketas_service.STATUS_APPROVED: "✅ Одобрена",
            anketas_service.STATUS_REJECTED: "❌ Отказано",
        }.get(last["status"], last["status"])
        lines.append(f"Последняя анкета #{last['id']}: {status_ru}")
    if remaining:
        lines.append(f"⏳ Осталось ждать: {users_service.format_timedelta(remaining)}")
    lines.append("\nСбросить время ожидания, чтобы пользователь мог подать анкету снова?")

    try:
        await bot.send_message(
            admin_chat_id,
            "\n".join(lines),
            message_thread_id=admin_topic_id,
            reply_markup=cooldown_reset_kb(applicant.id),
        )
    except Exception:
        logger.exception("Не удалось отправить уведомление о повторной подаче в тему")


@router.callback_query(F.data == "submit_anketa")
async def cb_submit_anketa(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    user_id = callback.from_user.id

    active = await anketas_service.get_active_for_user(user_id, kind="regular")
    if active:
        await callback.message.answer(ALREADY_PENDING)
        return

    remaining = await users_service.cooldown_remaining(user_id)
    if remaining:
        text = (
            "⏳ Повторная подача будет доступна через "
            f"{users_service.format_timedelta(remaining)}."
        )
        await callback.message.answer(text)
        if not await users_service.was_cooldown_notice_sent(user_id):
            await _notify_cooldown_reset_request(callback.bot, callback.from_user)
            await users_service.mark_cooldown_notice_sent(user_id)
        return

    await callback.message.answer(STANDARDS_WARNING)
    await _start_form(callback.bot, callback.message.chat.id, state)


@router.message(AnketaForm.filling, F.photo)
async def handle_photo_answer(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    step = data.get("step", 0)
    if step >= TOTAL_STEPS or QUESTIONS[step]["type"] != "photos":
        return

    photos = data.get("photos", [])
    if len(photos) >= 2:
        return

    photos.append(message.photo[-1].file_id)
    data["photos"] = photos

    prev_msgs = data.get("prev_msgs", [])
    for msg_id in prev_msgs:
        await _safe_delete(message.bot, message.chat.id, msg_id)

    try:
        await message.delete()
    except Exception:
        pass

    count_text = f"📸 Получено фото: {len(photos)}/2"
    if len(photos) < 2:
        count_text += "\nМожете отправить ещё одно фото или нажать «Готово»."
    kb = photos_kb(len(photos))
    status_msg = await message.answer(count_text, reply_markup=kb)

    data["prev_msgs"] = [status_msg.message_id]
    await state.set_data(data)


@router.message(AnketaForm.filling, F.document | F.video | F.animation | F.sticker | F.voice)
async def handle_wrong_media(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    step = data.get("step", 0)
    if step < TOTAL_STEPS and QUESTIONS[step]["type"] == "photos":
        await message.answer(PHOTOS_ONLY)


@router.callback_query(AnketaForm.filling, F.data == "photos_done")
async def cb_photos_done(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    data = await state.get_data()
    photos = data.get("photos", [])
    if not photos:
        await callback.message.answer("Сначала отправьте хотя бы одно фото.")
        return

    await _finalize_anketa(callback.bot, callback.from_user, state)


@router.callback_query(AnketaForm.filling, F.data.startswith("age:"))
async def cb_age_selected(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    data = await state.get_data()
    step = data.get("step", 0)
    if step >= TOTAL_STEPS or QUESTIONS[step]["type"] != "age":
        return

    age_value = callback.data.split(":", 1)[1]
    answers = data.get("answers", {})
    answers[QUESTIONS[step]["key"]] = age_value
    data["answers"] = answers
    data["step"] = step + 1
    await state.set_data(data)

    await _send_question(callback.bot, callback.message.chat.id, state)


@router.message(AnketaForm.filling, F.text)
async def handle_text_answer(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    step = data.get("step", 0)
    if step >= TOTAL_STEPS:
        return
    if QUESTIONS[step]["type"] == "age":
        await message.answer("Пожалуйста, выберите возраст с помощью кнопок выше.")
        return
    if QUESTIONS[step]["type"] == "photos":
        await message.answer("Пожалуйста, отправьте фото (не текст) или нажмите «Готово».")
        return

    answer = message.text.strip()
    if not answer:
        await message.answer("Пожалуйста, отправьте текстовый ответ.")
        return

    answers = data.get("answers", {})
    answers[QUESTIONS[step]["key"]] = answer
    data["answers"] = answers
    data["step"] = step + 1

    try:
        await message.delete()
    except Exception:
        pass

    await state.set_data(data)
    await _send_question(message.bot, message.chat.id, state)


async def _finalize_anketa(bot: Bot, from_user, state: FSMContext) -> None:
    data = await state.get_data()
    answers = data.get("answers", {})
    photos = data.get("photos", [])
    chat_id = from_user.id

    prev_msgs = data.get("prev_msgs", [])
    for msg_id in prev_msgs:
        await _safe_delete(bot, chat_id, msg_id)

    await state.clear()

    entry = await anketas_service.create_anketa(
        user_id=from_user.id,
        username=from_user.username,
        full_name=from_user.full_name,
        answers=answers,
        photos=photos,
        kind="regular",
    )
    await users_service.set_active_anketa(from_user.id, entry["id"])
    await increment_total_submitted()

    await bot.send_message(chat_id, SUBMIT_SUCCESS, reply_markup=main_menu_kb())

    await post_new_anketa(bot, entry)


async def resolve_fix(bot: Bot, anketa_id: str, extra_note: str | None = None) -> bool:
    """Общая логика подтверждения исправления — используется и кнопкой
    «Я исправил(а)», и прямой отправкой фото/текста в личку боту.
    Возвращает True, если анкета успешно вернулась на рассмотрение."""
    result = await anketas_service.mark_fix_acknowledged(anketa_id)
    if not result["ok"]:
        return False

    entry = result["entry"]
    await sync_cards(bot, entry, review_kb(entry["id"]))

    if entry.get("dm_admin_id"):
        note = f"🔁 Пользователь подтвердил исправление по анкете #{entry['id']}."
        if extra_note:
            note += f"\n{extra_note}"
        try:
            await bot.send_message(entry["dm_admin_id"], note)
        except Exception:
            logger.warning("Не удалось уведомить админа %s об исправлении", entry["dm_admin_id"])
    return True


@router.callback_query(F.data == "fix_ack")
async def cb_fix_ack(callback: CallbackQuery) -> None:
    await callback.answer()
    user_id = callback.from_user.id
    active = await anketas_service.get_active_for_user(user_id)
    if not active or active["status"] != anketas_service.STATUS_FIX_REQUIRED:
        await callback.message.answer("Актуальная анкета, требующая исправления, не найдена.")
        return

    ok = await resolve_fix(callback.bot, active["id"])
    if not ok:
        await callback.message.answer("Не удалось обновить статус анкеты, попробуйте позже.")
        return

    await callback.message.answer(FIX_CONFIRM_SENT)


@router.callback_query(F.data == "spam_help")
async def cb_spam_help(callback: CallbackQuery, antispam_mw=None) -> None:
    await callback.answer()
    if antispam_mw is not None:
        antispam_mw.force_unblock(callback.from_user.id)
    await callback.message.answer(SPAM_HELP_REPLY)
