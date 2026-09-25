from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from bot.questions import AGE_OPTIONS


def main_menu_kb() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="📝 Подать анкету", callback_data="submit_anketa")
    builder.button(text="🛡 Подать на пост мл. модератора", callback_data="submit_admin_app")
    builder.button(text="❓ Помощь в подаче анкеты", callback_data="show_help")
    builder.adjust(1)
    return builder.as_markup()


def age_kb() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for age in AGE_OPTIONS:
        builder.button(text=age, callback_data=f"age:{age}")
    builder.adjust(4, 3)
    return builder.as_markup()


def photos_kb(count: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    if count >= 1:
        builder.button(text="✅ Готово, отправить анкету", callback_data="photos_done")
    builder.adjust(1)
    return builder.as_markup()


def fix_ack_kb() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="✅ Я выполнил(а) требование администрации", callback_data="fix_ack")
    builder.button(text="🚨 У меня спамблок!", callback_data="spam_help")
    builder.adjust(1)
    return builder.as_markup()


def cooldown_reset_kb(user_id: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="✅ Да, сбросить", callback_data=f"cdreset_yes:{user_id}")
    builder.button(text="❌ Нет", callback_data=f"cdreset_no:{user_id}")
    builder.adjust(2)
    return builder.as_markup()


def moderation_kb(anketa_id: str) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="🔎 Взять на рассмотрение", callback_data=f"take:{anketa_id}")
    builder.adjust(1)
    return builder.as_markup()


def review_kb(anketa_id: str) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="✅ Одобрить", callback_data=f"approve:{anketa_id}")
    builder.button(text="❌ Отказать", callback_data=f"reject:{anketa_id}")
    builder.button(text="⚠️ Требуется исправление", callback_data=f"fixreq:{anketa_id}")
    builder.button(text="🔓 Освободить", callback_data=f"release:{anketa_id}")
    builder.adjust(2, 1, 1)
    return builder.as_markup()
