"""Справочник username -> user_id, собираемый пассивно из любых сообщений/
нажатий кнопок. Нужен, чтобы находить пользователя по @username (например,
для /чс, /block) и чтобы /open_admin мог разослать уведомление всем, кто
хоть раз взаимодействовал с ботом."""

from __future__ import annotations

from typing import List, Optional

from bot.config import config
from bot.json_store import JSONStore

_DEFAULT = {"by_username": {}, "all_ids": []}

_store = JSONStore(config.user_directory_file, _DEFAULT)


async def record(user_id: int, username: Optional[str]) -> None:
    def mutate(data: dict) -> dict:
        data.setdefault("by_username", {})
        data.setdefault("all_ids", [])
        if username:
            data["by_username"][username.lower()] = user_id
        if user_id not in data["all_ids"]:
            data["all_ids"].append(user_id)
        return data

    await _store.update(mutate)


async def resolve(identifier: str) -> Optional[int]:
    """identifier — @username, username без @, или числовой ID (строкой)."""
    identifier = identifier.strip().lstrip("@")
    if identifier.isdigit():
        return int(identifier)
    data = await _store.read()
    return data.get("by_username", {}).get(identifier.lower())


async def all_known_ids() -> List[int]:
    data = await _store.read()
    return list(data.get("all_ids", []))
