"""Пассивно записывает user_id/username каждого, кто взаимодействует с
ботом, в справочник (нужен для поиска по @username и рассылок)."""

from __future__ import annotations

from typing import Any, Awaitable, Callable, Dict

from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, Message, TelegramObject

from bot.services import user_directory


class UserDirectoryMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any],
    ) -> Any:
        user = data.get("event_from_user")
        if user is not None:
            try:
                await user_directory.record(user.id, user.username)
            except Exception:
                pass
        return await handler(event, data)
