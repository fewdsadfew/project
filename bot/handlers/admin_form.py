"""Заявка на пост младшего модератора: отдельная анкета, отдельная тема,
включается/выключается через /open_admin и /close_admin."""

from __future__ import annotations

import logging

from aiogram import Bot, F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from bot.card_sync import post_new_anketa
from bot.keyboards import main_menu_kb
from bot.questions_admin import ADMIN_QUESTIONS, ADMIN_TOTAL_STEPS
from bot.services import anketas as anketas_service
from bot.services.settings import is_admin_recruitment_open
from bot.states import AdminForm
from bot.texts import ADMIN_APP_ALREADY_PENDING, ADMIN_APP_HEADER, ADMIN_APP_SUBMITTED, ADMIN_RECRUITMENT_CLOSED

logger = logging.getLogger(__name__)
router = Router(name="admin_form")


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

    if step >= ADMIN_TOTAL_STEPS:
        return

    question = ADMIN_QUESTIONS[step]
    msg = await bot.send_message(chat_id, question["text"])
    prev_msgs.append(msg.message_id)

    data["step"] = step
    data["prev_msgs"] = prev_msgs
    await state.set_data(data)


async def _start_form(bot: Bot, chat_id: int, state: FSMContext) -> None:
    await state.set_state(AdminForm.filling)
    await state.update_data(step=0, answers={}, prev_msgs=[])
    await bot.send_message(chat_id, ADMIN_APP_HEADER)
    await _send_question(bot, chat_id, state)


@router.callback_query(F.data == "submit_admin_app")
async def cb_submit_admin_app(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    user_id = callback.from_user.id

    if not await is_admin_recruitment_open():
        await callback.message.answer(ADMIN_RECRUITMENT_CLOSED)
        return

    active = await anketas_service.get_active_for_user(user_id, kind="admin")
    if active:
        await callback.message.answer(ADMIN_APP_ALREADY_PENDING)
        return

    await _start_form(callback.bot, callback.message.chat.id, state)


@router.message(AdminForm.filling, F.text)
async def handle_text_answer(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    step = data.get("step", 0)
    if step >= ADMIN_TOTAL_STEPS:
        return

    answer = message.text.strip()
    if not answer:
        await message.answer("Пожалуйста, отправьте текстовый ответ.")
        return

    answers = data.get("answers", {})
    answers[ADMIN_QUESTIONS[step]["key"]] = answer
    data["answers"] = answers
    data["step"] = step + 1

    try:
        await message.delete()
    except Exception:
        pass

    await state.set_data(data)

    if data["step"] >= ADMIN_TOTAL_STEPS:
        await _finalize(message.bot, message.from_user, state)
        return

    await _send_question(message.bot, message.chat.id, state)


async def _finalize(bot: Bot, from_user, state: FSMContext) -> None:
    data = await state.get_data()
    answers = data.get("answers", {})
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
        photos=[],
        kind="admin",
    )

    await bot.send_message(chat_id, ADMIN_APP_SUBMITTED, reply_markup=main_menu_kb())
    await post_new_anketa(bot, entry)
