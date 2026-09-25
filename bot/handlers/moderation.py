from __future__ import annotations

import logging

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from bot.card_sync import sync_cards, update_dm_card, update_group_card
from bot.config import config
from bot.keyboards import fix_ack_kb, review_kb
from bot.rendering import render_admin_card
from bot.services import anketas as anketas_service
from bot.services import user_directory
from bot.services import users as users_service
from bot.services.settings import (
    get_admin_apps_topic,
    set_admin_apps_topic,
    set_admin_recruitment_open,
    set_admin_topic,
)
from bot.states import FixForm, RejectForm
from bot.texts import (
    ADMIN_RECRUITMENT_OPEN_BROADCAST,
    APPROVAL_WITH_LINK_EXTRA,
    FIX_REQUEST_EXTRA_HINT,
    NOT_IN_TOPIC,
    TOPIC_SET,
)

logger = logging.getLogger(__name__)
router = Router(name="moderation")


def _is_owner(user_id: int) -> bool:
    return user_id == config.owner_id


@router.message(Command("settopic"))
async def cmd_settopic(message: Message) -> None:
    if message.chat.type not in ("group", "supergroup"):
        return
    if not _is_owner(message.from_user.id):
        await message.reply("⚠️ Эту команду может использовать только владелец бота.")
        return

    if not message.is_topic_message or not message.message_thread_id:
        await message.reply(NOT_IN_TOPIC)
        return

    await set_admin_topic(message.chat.id, message.message_thread_id)
    await message.reply(TOPIC_SET)


@router.message(Command("set_admins"))
async def cmd_set_admins(message: Message) -> None:
    if message.chat.type not in ("group", "supergroup"):
        return
    if not _is_owner(message.from_user.id):
        await message.reply("⚠️ Эту команду может использовать только владелец бота.")
        return

    if not message.is_topic_message or not message.message_thread_id:
        await message.reply(NOT_IN_TOPIC)
        return

    await set_admin_apps_topic(message.chat.id, message.message_thread_id)
    await message.reply("✅ Эта тема установлена для заявок на младшего модератора.")


@router.message(Command("open_admin"))
async def cmd_open_admin(message: Message) -> None:
    if message.chat.type not in ("group", "supergroup"):
        return
    if not _is_owner(message.from_user.id):
        await message.reply("⚠️ Эту команду может использовать только владелец бота.")
        return

    apps_chat_id, apps_topic_id = await get_admin_apps_topic()
    if not apps_chat_id:
        await message.reply("Сначала настройте тему заявок командой /set_admins внутри нужной темы.")
        return
    if message.chat.id != apps_chat_id or message.message_thread_id != apps_topic_id:
        await message.reply(NOT_IN_TOPIC)
        return

    await set_admin_recruitment_open(True)
    await message.reply("✅ Набор на младшего модератора открыт. Рассылаю уведомление...")

    ids = await user_directory.all_known_ids()
    sent = 0
    for uid in ids:
        try:
            await message.bot.send_message(uid, ADMIN_RECRUITMENT_OPEN_BROADCAST)
            sent += 1
        except Exception:
            pass
    await message.reply(f"📨 Рассылка завершена: доставлено {sent} из {len(ids)}.")


@router.message(Command("close_admin"))
async def cmd_close_admin(message: Message) -> None:
    if message.chat.type not in ("group", "supergroup"):
        return
    if not _is_owner(message.from_user.id):
        await message.reply("⚠️ Эту команду может использовать только владелец бота.")
        return

    apps_chat_id, apps_topic_id = await get_admin_apps_topic()
    if apps_chat_id and (message.chat.id != apps_chat_id or message.message_thread_id != apps_topic_id):
        await message.reply(NOT_IN_TOPIC)
        return

    await set_admin_recruitment_open(False)
    await message.reply("🚫 Набор на младшего модератора закрыт.")


@router.callback_query(F.data.startswith("take:"))
async def cb_take(callback: CallbackQuery) -> None:
    anketa_id = callback.data.split(":", 1)[1]
    admin = callback.from_user
    result = await anketas_service.take_for_review(anketa_id, admin.id, admin.username)

    if not result["ok"]:
        if result["reason"] == "already_taken":
            reviewer = result["entry"].get("reviewer_username")
            hint = f"@{reviewer}" if reviewer else "другим администратором"
            await callback.answer(f"Анкета уже взята на рассмотрение ({hint}).", show_alert=True)
        elif result["reason"] == "not_found":
            await callback.answer("Анкета не найдена.", show_alert=True)
        else:
            await callback.answer("Не удалось взять анкету на рассмотрение.", show_alert=True)
        return

    entry = result["entry"]

    # Пытаемся открыть личку с админом — вся дальнейшая работа происходит там
    try:
        dm_msg = await callback.bot.send_message(
            admin.id, render_admin_card(entry), reply_markup=review_kb(anketa_id)
        )
    except Exception:
        # Не получилось написать в личку (админ не запускал бота) — откатываем взятие
        logger.warning("Не удалось написать админу %s в личку, откатываю взятие анкеты", admin.id)
        await anketas_service.release(anketa_id, admin.id)
        await callback.answer(
            "Не получилось открыть личку с вами. Сначала напишите боту /start в личных "
            "сообщениях, затем попробуйте взять анкету снова.",
            show_alert=True,
        )
        return

    await anketas_service.set_dm_message(anketa_id, admin.id, dm_msg.message_id)
    await callback.answer("Анкета взята на рассмотрение, дальше — в личных сообщениях.")
    await update_group_card(callback.bot, entry)

    try:
        await callback.bot.send_message(
            entry["user_id"],
            f"👮 Вашу анкету рассматривает @{admin.username or admin.id}.",
        )
    except Exception:
        logger.warning("Не удалось уведомить пользователя %s о взятии анкеты", entry["user_id"])


@router.callback_query(F.data.startswith("release:"))
async def cb_release(callback: CallbackQuery) -> None:
    anketa_id = callback.data.split(":", 1)[1]
    admin = callback.from_user
    result = await anketas_service.release(anketa_id, admin.id)

    if not result["ok"]:
        reasons = {
            "not_found": "Анкета не найдена.",
            "not_in_review": "Анкета не находится на рассмотрении.",
            "not_your_review": "Вы не рассматриваете эту анкету.",
        }
        await callback.answer(reasons.get(result["reason"], "Не удалось освободить анкету."), show_alert=True)
        return

    entry = result["entry"]
    await callback.answer("Анкета освобождена.")
    await update_group_card(callback.bot, entry)
    await update_dm_card(callback.bot, entry, None)


@router.callback_query(F.data.startswith("approve:"))
async def cb_approve(callback: CallbackQuery) -> None:
    anketa_id = callback.data.split(":", 1)[1]
    admin = callback.from_user
    result = await anketas_service.approve(anketa_id, admin.id)

    if not result["ok"]:
        reasons = {
            "not_found": "Анкета не найдена.",
            "already_decided": "По анкете уже принято решение.",
            "not_your_review": "Вы не рассматриваете эту анкету.",
        }
        await callback.answer(reasons.get(result["reason"], "Не удалось одобрить анкету."), show_alert=True)
        return

    entry = result["entry"]
    await callback.answer("Анкета одобрена.")
    await sync_cards(callback.bot, entry, None)

    kind = entry.get("kind", "regular")
    if kind != "admin":
        await users_service.start_cooldown(entry["user_id"], config.cooldown_days)

    if kind == "admin":
        approve_text = "✅ Ваша заявка на пост младшего модератора одобрена! С вами свяжется руководство."
    else:
        approve_text = "✅ Ваша анкета одобрена! Добро пожаловать."
        if config.approval_invite_link:
            approve_text += APPROVAL_WITH_LINK_EXTRA.format(link=config.approval_invite_link)

    try:
        await callback.bot.send_message(entry["user_id"], approve_text)
    except Exception:
        logger.warning("Не удалось уведомить пользователя %s об одобрении", entry["user_id"])


@router.callback_query(F.data.startswith("reject:"))
async def cb_reject_start(callback: CallbackQuery, state: FSMContext) -> None:
    anketa_id = callback.data.split(":", 1)[1]
    entry = await anketas_service.get_anketa(anketa_id)
    if not entry:
        await callback.answer("Анкета не найдена.", show_alert=True)
        return
    if entry.get("reviewer_id") != callback.from_user.id:
        await callback.answer("Вы не рассматриваете эту анкету.", show_alert=True)
        return
    if entry["status"] in (anketas_service.STATUS_APPROVED, anketas_service.STATUS_REJECTED):
        await callback.answer("По анкете уже принято решение.", show_alert=True)
        return

    await callback.answer()
    await state.set_state(RejectForm.waiting_reason)
    await state.update_data(anketa_id=anketa_id)
    await callback.message.reply("✍️ Напишите причину отказа следующим сообщением.")


@router.message(RejectForm.waiting_reason, F.text)
async def process_reject_reason(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    anketa_id = data.get("anketa_id")
    await state.clear()

    result = await anketas_service.reject(anketa_id, message.from_user.id, message.text.strip())
    if not result["ok"]:
        await message.reply("Не удалось отклонить анкету (возможно, решение уже принято).")
        return

    entry = result["entry"]
    await sync_cards(message.bot, entry, None)
    if entry.get("kind", "regular") != "admin":
        await users_service.start_cooldown(entry["user_id"], config.cooldown_days)
    await message.reply(f"Анкета #{anketa_id} отклонена.")

    reject_text = (
        "❌ Ваша заявка на пост младшего модератора отклонена."
        if entry.get("kind") == "admin"
        else "❌ Ваша анкета отклонена."
    )
    try:
        await message.bot.send_message(
            entry["user_id"],
            f"{reject_text}\n💬 Причина: {entry['reject_reason']}",
        )
    except Exception:
        logger.warning("Не удалось уведомить пользователя %s об отказе", entry["user_id"])


@router.callback_query(F.data.startswith("fixreq:"))
async def cb_fixreq_start(callback: CallbackQuery, state: FSMContext) -> None:
    anketa_id = callback.data.split(":", 1)[1]
    entry = await anketas_service.get_anketa(anketa_id)
    if not entry:
        await callback.answer("Анкета не найдена.", show_alert=True)
        return
    if entry.get("reviewer_id") != callback.from_user.id:
        await callback.answer("Вы не рассматриваете эту анкету.", show_alert=True)
        return
    if entry["status"] in (anketas_service.STATUS_APPROVED, anketas_service.STATUS_REJECTED):
        await callback.answer("По анкете уже принято решение.", show_alert=True)
        return

    await callback.answer()
    await state.set_state(FixForm.waiting_comment)
    await state.update_data(anketa_id=anketa_id)
    await callback.message.reply(
        "✍️ Напишите комментарий с тем, что нужно исправить, следующим сообщением."
    )


@router.message(FixForm.waiting_comment, F.text)
async def process_fix_comment(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    anketa_id = data.get("anketa_id")
    await state.clear()

    result = await anketas_service.request_fix(anketa_id, message.from_user.id, message.text.strip())
    if not result["ok"]:
        await message.reply("Не удалось запросить исправление (возможно, решение уже принято).")
        return

    entry = result["entry"]
    await sync_cards(message.bot, entry, review_kb(anketa_id))
    await message.reply(f"Запрошено исправление по анкете #{anketa_id}.")

    try:
        await message.bot.send_message(
            entry["user_id"],
            "⚠️ По вашей анкете требуется исправление.\n"
            f"💬 Комментарий: {entry['fix_comment']}" + FIX_REQUEST_EXTRA_HINT,
            reply_markup=fix_ack_kb(),
        )
    except Exception:
        logger.warning("Не удалось уведомить пользователя %s о необходимости исправления", entry["user_id"])


# === Сброс cooldown при повторной подаче ===

@router.callback_query(F.data.startswith("cdreset_yes:"))
async def cb_cooldown_reset_yes(callback: CallbackQuery) -> None:
    target_id = int(callback.data.split(":", 1)[1])
    admin = callback.from_user

    await users_service.clear_cooldown(target_id)
    await callback.answer("Кулдаун сброшен.")

    try:
        new_text = (callback.message.text or "") + f"\n\n✅ Кулдаун сброшен — @{admin.username or admin.id}"
        await callback.message.edit_text(new_text, reply_markup=None)
    except Exception:
        pass

    try:
        await callback.bot.send_message(
            target_id, "✅ Администратор снял КД с вас, подавайте анкету!"
        )
    except Exception:
        logger.warning("Не удалось уведомить пользователя %s о сбросе КД", target_id)


@router.callback_query(F.data.startswith("cdreset_no:"))
async def cb_cooldown_reset_no(callback: CallbackQuery) -> None:
    admin = callback.from_user
    await callback.answer("Оставлено без изменений.")
    try:
        new_text = (callback.message.text or "") + f"\n\n❌ Отклонено — @{admin.username or admin.id}"
        await callback.message.edit_text(new_text, reply_markup=None)
    except Exception:
        pass
