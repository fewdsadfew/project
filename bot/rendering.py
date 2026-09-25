from __future__ import annotations

from typing import Any, Dict

from bot.questions import QUESTION_LABELS
from bot.questions_admin import ADMIN_QUESTION_LABELS
from bot.services import anketas as anketas_service

_STATUS_LABELS = {
    anketas_service.STATUS_NEW: "Новая",
    anketas_service.STATUS_REVIEW: "🔎 На рассмотрении",
    anketas_service.STATUS_FIX_REQUIRED: "⚠️ Требуется исправление",
    anketas_service.STATUS_APPROVED: "✅ Одобрено",
    anketas_service.STATUS_REJECTED: "❌ Отказано",
}

_KIND_HEADERS = {
    "regular": ("📝 НОВАЯ АНКЕТА", "📝 АНКЕТА"),
    "admin": ("🛡 НОВАЯ ЗАЯВКА НА МЛАДШЕГО МОДЕРАТОРА", "🛡 ЗАЯВКА НА МЛАДШЕГО МОДЕРАТОРА"),
}


def _mention(username: str | None, user_id: int) -> str:
    return f"@{username}" if username else f"<a href='tg://user?id={user_id}'>без username</a>"


def _labels_for(kind: str) -> Dict[str, str]:
    return ADMIN_QUESTION_LABELS if kind == "admin" else QUESTION_LABELS


def render_admin_card(entry: Dict[str, Any]) -> str:
    kind = entry.get("kind", "regular")
    new_header, plain_header = _KIND_HEADERS.get(kind, _KIND_HEADERS["regular"])
    lines = [f"<b>{new_header if entry['status'] == anketas_service.STATUS_NEW else plain_header}</b>"]
    lines.append(f"👤 Пользователь: {_mention(entry.get('username'), entry['user_id'])}")
    lines.append(f"🆔 ID: <code>{entry['user_id']}</code>")
    lines.append("")

    answers = entry.get("answers", {})
    for key, label in _labels_for(kind).items():
        value = answers.get(key, "—")
        lines.append(f"❀ <b>{label}:</b> {value}")

    if kind == "regular":
        photos_count = len(entry.get("photos", []))
        lines.append(f"🖼 Фото скина: {photos_count} шт. (см. сообщение ниже)")
    lines.append("")

    status_label = _STATUS_LABELS.get(entry["status"], entry["status"])
    lines.append(f"📌 Статус: {status_label}")

    if entry["status"] == anketas_service.STATUS_REVIEW and entry.get("reviewer_username"):
        lines.append(f"👮 Рассматривает: {_mention(entry.get('reviewer_username'), entry['reviewer_id'])}")

    if entry["status"] == anketas_service.STATUS_REJECTED:
        lines.append(f"💬 Причина: {entry.get('reject_reason') or '—'}")
        lines.append(f"👮 Администратор: {_mention(entry.get('reviewer_username'), entry.get('reviewer_id'))}")

    if entry["status"] == anketas_service.STATUS_APPROVED:
        lines.append(f"👮 Администратор: {_mention(entry.get('reviewer_username'), entry.get('reviewer_id'))}")

    if entry["status"] == anketas_service.STATUS_FIX_REQUIRED:
        lines.append(f"💬 Комментарий: {entry.get('fix_comment') or '—'}")
        if entry.get("reviewer_username"):
            lines.append(f"👮 Рассматривает: {_mention(entry.get('reviewer_username'), entry['reviewer_id'])}")

    prefix = "anketa" if kind == "regular" else "adminapp"
    lines.append(f"\n#{prefix}_{entry['id']}")
    return "\n".join(lines)
