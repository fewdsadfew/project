from __future__ import annotations

import logging

from bot.keyboards import moderation_kb
from bot.rendering import render_admin_card
from bot.services import anketas as anketas_service

logger = logging.getLogger(__name__)


async def post_new_anketa(bot, entry: dict) -> None:
    """Публикует новую анкету/заявку в соответствующую тему — обычная анкета
    и заявка на модератора расходятся по своим темам (entry['kind'])."""
    from bot.services.settings import get_admin_apps_topic, get_admin_topic

    kind = entry.get("kind", "regular")
    if kind == "admin":
        chat_id, topic_id = await get_admin_apps_topic()
    else:
        chat_id, topic_id = await get_admin_topic()

    if not chat_id:
        logger.warning(
            "Тема для заявок (kind=%s) не настроена — запись #%s не отправлена администрации",
            kind,
            entry["id"],
        )
        return

    try:
        card_msg = await bot.send_message(
            chat_id,
            render_admin_card(entry),
            message_thread_id=topic_id,
            reply_markup=moderation_kb(entry["id"]),
        )
        await anketas_service.set_admin_message(entry["id"], chat_id, card_msg.message_id)

        photos = entry.get("photos", [])
        if photos:
            if len(photos) == 1:
                await bot.send_photo(
                    chat_id,
                    photos[0],
                    message_thread_id=topic_id,
                    caption=f"🖼 Фото скина к анкете #{entry['id']}",
                    reply_to_message_id=card_msg.message_id,
                )
            else:
                from aiogram.types import InputMediaPhoto

                media = [
                    InputMediaPhoto(
                        media=photo_id,
                        caption=f"🖼 Фото скина к анкете #{entry['id']}" if i == 0 else None,
                    )
                    for i, photo_id in enumerate(photos)
                ]
                await bot.send_media_group(
                    chat_id, media, message_thread_id=topic_id, reply_to_message_id=card_msg.message_id
                )
    except Exception:
        logger.exception("Не удалось отправить запись #%s (kind=%s) в тему", entry["id"], kind)


async def update_group_card(bot, entry: dict) -> None:
    """Карточка в теме группы: без кнопок решения — только статус.
    Кнопка «Взять на рассмотрение» есть только пока анкета свободна."""
    if not entry.get("admin_chat_id") or not entry.get("admin_message_id"):
        return
    kb = moderation_kb(entry["id"]) if entry["status"] == anketas_service.STATUS_NEW else None
    try:
        await bot.edit_message_text(
            chat_id=entry["admin_chat_id"],
            message_id=entry["admin_message_id"],
            text=render_admin_card(entry),
            reply_markup=kb,
        )
    except Exception:
        logger.exception("Не удалось обновить групповую карточку анкеты #%s", entry["id"])


async def update_dm_card(bot, entry: dict, kb=None) -> None:
    """Карточка в личке админа: тут живут все кнопки принятия решения."""
    if not entry.get("dm_admin_id") or not entry.get("dm_message_id"):
        return
    try:
        await bot.edit_message_text(
            chat_id=entry["dm_admin_id"],
            message_id=entry["dm_message_id"],
            text=render_admin_card(entry),
            reply_markup=kb,
        )
    except Exception:
        logger.exception("Не удалось обновить карточку анкеты #%s в личке", entry["id"])


async def sync_cards(bot, entry: dict, dm_kb=None) -> None:
    await update_group_card(bot, entry)
    await update_dm_card(bot, entry, dm_kb)
