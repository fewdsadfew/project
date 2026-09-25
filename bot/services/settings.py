from __future__ import annotations

from typing import Optional

from bot.config import config
from bot.json_store import JSONStore

_DEFAULT = {
    "admin_chat_id": None,
    "admin_topic_id": None,
    "admin_apps_chat_id": None,
    "admin_apps_topic_id": None,
    "admin_recruitment_open": False,
    "total_submitted": 0,
}

_store = JSONStore(config.settings_file, _DEFAULT)


async def get_settings() -> dict:
    data = await _store.read()
    for k, v in _DEFAULT.items():
        data.setdefault(k, v)
    return data


async def set_admin_topic(chat_id: int, topic_id: Optional[int]) -> None:
    def mutate(data: dict) -> dict:
        for k, v in _DEFAULT.items():
            data.setdefault(k, v)
        data["admin_chat_id"] = chat_id
        data["admin_topic_id"] = topic_id
        return data

    await _store.update(mutate)


async def get_admin_topic() -> tuple[Optional[int], Optional[int]]:
    data = await get_settings()
    return data.get("admin_chat_id"), data.get("admin_topic_id")


async def set_admin_apps_topic(chat_id: int, topic_id: Optional[int]) -> None:
    def mutate(data: dict) -> dict:
        for k, v in _DEFAULT.items():
            data.setdefault(k, v)
        data["admin_apps_chat_id"] = chat_id
        data["admin_apps_topic_id"] = topic_id
        return data

    await _store.update(mutate)


async def get_admin_apps_topic() -> tuple[Optional[int], Optional[int]]:
    data = await get_settings()
    return data.get("admin_apps_chat_id"), data.get("admin_apps_topic_id")


async def set_admin_recruitment_open(is_open: bool) -> None:
    def mutate(data: dict) -> dict:
        for k, v in _DEFAULT.items():
            data.setdefault(k, v)
        data["admin_recruitment_open"] = is_open
        return data

    await _store.update(mutate)


async def is_admin_recruitment_open() -> bool:
    data = await get_settings()
    return bool(data.get("admin_recruitment_open"))


async def increment_total_submitted() -> int:
    result_holder = {}

    def mutate(data: dict) -> dict:
        for k, v in _DEFAULT.items():
            data.setdefault(k, v)
        data["total_submitted"] = int(data.get("total_submitted", 0)) + 1
        result_holder["value"] = data["total_submitted"]
        return data

    await _store.update(mutate)
    return result_holder["value"]


async def get_total_submitted() -> int:
    data = await get_settings()
    return int(data.get("total_submitted", 0))
