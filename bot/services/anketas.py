from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from bot.config import config
from bot.json_store import JSONStore

STATUS_NEW = "new"
STATUS_REVIEW = "review"
STATUS_FIX_REQUIRED = "fix_required"
STATUS_APPROVED = "approved"
STATUS_REJECTED = "rejected"

_DEFAULT = {"next_id": 1, "items": {}}

_store = JSONStore(config.anketas_file, _DEFAULT)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


async def create_anketa(
    user_id: int,
    username: Optional[str],
    full_name: str,
    answers: Dict[str, str],
    photos: List[str],
    kind: str = "regular",
) -> Dict[str, Any]:
    holder: Dict[str, Any] = {}

    def mutate(data: dict) -> dict:
        data.setdefault("next_id", 1)
        data.setdefault("items", {})
        anketa_id = str(data["next_id"])
        data["next_id"] += 1
        entry = {
            "id": anketa_id,
            "user_id": user_id,
            "username": username,
            "full_name": full_name,
            "answers": answers,
            "photos": photos,
            "kind": kind,
            "status": STATUS_NEW,
            "reviewer_id": None,
            "reviewer_username": None,
            "admin_chat_id": None,
            "admin_message_id": None,
            "dm_admin_id": None,
            "dm_message_id": None,
            "reject_reason": None,
            "fix_comment": None,
            "created_at": _now_iso(),
            "decided_at": None,
        }
        data["items"][anketa_id] = entry
        holder["entry"] = entry
        return data

    await _store.update(mutate)
    return holder["entry"]


async def get_anketa(anketa_id: str) -> Optional[Dict[str, Any]]:
    data = await _store.read()
    return data.get("items", {}).get(str(anketa_id))


async def get_active_for_user(user_id: int, kind: Optional[str] = None) -> Optional[Dict[str, Any]]:
    data = await _store.read()
    matches = []
    for entry in data.get("items", {}).values():
        if entry["user_id"] != user_id:
            continue
        if entry["status"] not in (STATUS_NEW, STATUS_REVIEW, STATUS_FIX_REQUIRED):
            continue
        if kind is not None and entry.get("kind", "regular") != kind:
            continue
        matches.append(entry)
    if not matches:
        return None
    # Если у пользователя одновременно есть и анкета, и заявка на модератора —
    # берём самую свежую (на практике такое пересечение редкость).
    return max(matches, key=lambda e: int(e["id"]))


async def get_last_for_user(user_id: int) -> Optional[Dict[str, Any]]:
    """Последняя (по id) анкета пользователя, независимо от статуса —
    используется, чтобы показать администрации контекст при повторной подаче."""
    data = await _store.read()
    items = [e for e in data.get("items", {}).values() if e["user_id"] == user_id]
    if not items:
        return None
    return max(items, key=lambda e: int(e["id"]))


async def get_active_reviews_for_admin(admin_id: int) -> List[Dict[str, Any]]:
    """Все анкеты, которые сейчас рассматривает этот админ (взял, но решение
    ещё не вынесено) — нужно для маршрутизации свободных сообщений в личке."""
    data = await _store.read()
    return [
        e
        for e in data.get("items", {}).values()
        if e.get("reviewer_id") == admin_id and e["status"] in (STATUS_REVIEW, STATUS_FIX_REQUIRED)
    ]


async def is_active_reviewer(user_id: int) -> bool:
    """True, если пользователь прямо сейчас что-то рассматривает — используется,
    чтобы не блокировать админа антиспамом посреди переписки с заявителем."""
    reviews = await get_active_reviews_for_admin(user_id)
    return bool(reviews)


async def set_admin_message(anketa_id: str, chat_id: int, message_id: int) -> None:
    def mutate(data: dict) -> dict:
        entry = data.get("items", {}).get(str(anketa_id))
        if entry:
            entry["admin_chat_id"] = chat_id
            entry["admin_message_id"] = message_id
        return data

    await _store.update(mutate)


async def set_dm_message(anketa_id: str, admin_id: int, message_id: int) -> None:
    def mutate(data: dict) -> dict:
        entry = data.get("items", {}).get(str(anketa_id))
        if entry:
            entry["dm_admin_id"] = admin_id
            entry["dm_message_id"] = message_id
        return data

    await _store.update(mutate)


async def take_for_review(anketa_id: str, admin_id: int, admin_username: Optional[str]):
    """Атомарно берёт анкету на рассмотрение. Защищает от двойного взятия."""
    result = {"ok": False, "entry": None, "reason": None}

    def mutate(data: dict) -> dict:
        entry = data.get("items", {}).get(str(anketa_id))
        if not entry:
            result["reason"] = "not_found"
            return data
        if entry["status"] not in (STATUS_NEW,):
            result["reason"] = "already_taken"
            result["entry"] = entry
            return data
        entry["status"] = STATUS_REVIEW
        entry["reviewer_id"] = admin_id
        entry["reviewer_username"] = admin_username
        result["ok"] = True
        result["entry"] = entry
        return data

    await _store.update(mutate)
    return result


async def release(anketa_id: str, admin_id: int):
    result = {"ok": False, "entry": None, "reason": None}

    def mutate(data: dict) -> dict:
        entry = data.get("items", {}).get(str(anketa_id))
        if not entry:
            result["reason"] = "not_found"
            return data
        if entry["status"] not in (STATUS_REVIEW, STATUS_FIX_REQUIRED):
            result["reason"] = "not_in_review"
            result["entry"] = entry
            return data
        if entry["reviewer_id"] != admin_id:
            result["reason"] = "not_your_review"
            result["entry"] = entry
            return data
        entry["status"] = STATUS_NEW
        entry["reviewer_id"] = None
        entry["reviewer_username"] = None
        result["ok"] = True
        result["entry"] = entry
        return data

    await _store.update(mutate)
    return result


async def approve(anketa_id: str, admin_id: int):
    result = {"ok": False, "entry": None, "reason": None}

    def mutate(data: dict) -> dict:
        entry = data.get("items", {}).get(str(anketa_id))
        if not entry:
            result["reason"] = "not_found"
            return data
        if entry["status"] in (STATUS_APPROVED, STATUS_REJECTED):
            result["reason"] = "already_decided"
            result["entry"] = entry
            return data
        if entry["reviewer_id"] != admin_id:
            result["reason"] = "not_your_review"
            result["entry"] = entry
            return data
        entry["status"] = STATUS_APPROVED
        entry["decided_at"] = _now_iso()
        result["ok"] = True
        result["entry"] = entry
        return data

    await _store.update(mutate)
    return result


async def reject(anketa_id: str, admin_id: int, reason_text: str):
    result = {"ok": False, "entry": None, "reason": None}

    def mutate(data: dict) -> dict:
        entry = data.get("items", {}).get(str(anketa_id))
        if not entry:
            result["reason"] = "not_found"
            return data
        if entry["status"] in (STATUS_APPROVED, STATUS_REJECTED):
            result["reason"] = "already_decided"
            result["entry"] = entry
            return data
        if entry["reviewer_id"] != admin_id:
            result["reason"] = "not_your_review"
            result["entry"] = entry
            return data
        entry["status"] = STATUS_REJECTED
        entry["reject_reason"] = reason_text
        entry["decided_at"] = _now_iso()
        result["ok"] = True
        result["entry"] = entry
        return data

    await _store.update(mutate)
    return result


async def request_fix(anketa_id: str, admin_id: int, comment: str):
    result = {"ok": False, "entry": None, "reason": None}

    def mutate(data: dict) -> dict:
        entry = data.get("items", {}).get(str(anketa_id))
        if not entry:
            result["reason"] = "not_found"
            return data
        if entry["status"] in (STATUS_APPROVED, STATUS_REJECTED):
            result["reason"] = "already_decided"
            result["entry"] = entry
            return data
        if entry["reviewer_id"] != admin_id:
            result["reason"] = "not_your_review"
            result["entry"] = entry
            return data
        entry["status"] = STATUS_FIX_REQUIRED
        entry["fix_comment"] = comment
        result["ok"] = True
        result["entry"] = entry
        return data

    await _store.update(mutate)
    return result


async def mark_fix_acknowledged(anketa_id: str):
    """Пользователь подтвердил исправление — анкета возвращается на рассмотрение
    тому же администратору, который запросил исправление."""
    result = {"ok": False, "entry": None, "reason": None}

    def mutate(data: dict) -> dict:
        entry = data.get("items", {}).get(str(anketa_id))
        if not entry:
            result["reason"] = "not_found"
            return data
        if entry["status"] != STATUS_FIX_REQUIRED:
            result["reason"] = "wrong_status"
            result["entry"] = entry
            return data
        entry["status"] = STATUS_REVIEW
        result["ok"] = True
        result["entry"] = entry
        return data

    await _store.update(mutate)
    return result
