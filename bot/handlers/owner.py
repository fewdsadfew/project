from __future__ import annotations

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import Message

from bot.config import config
from bot.services import user_directory
from bot.services.blacklist import add_to_blacklist, remove_from_blacklist
from bot.services.settings import get_total_submitted
from bot.services.users import clear_cooldown

router = Router(name="owner")


def _is_owner(message: Message) -> bool:
    return message.from_user is not None and message.from_user.id == config.owner_id


@router.message(Command("setanket"))
async def cmd_setanket(message: Message) -> None:
    if not _is_owner(message):
        return
    total = await get_total_submitted()
    await message.reply(f"📊 Всего подано анкет: {total}")


def _parse_target(text: str) -> str | None:
    """Возвращает «сырой» идентификатор из аргумента команды — число или
    @username (с собакой или без)."""
    parts = text.strip().split(maxsplit=1)
    if len(parts) < 2:
        return None
    return parts[1].strip()


def _parse_user_id(text: str) -> int | None:
    target = _parse_target(text)
    if target is None or not target.lstrip("@").isdigit():
        return None
    return int(target.lstrip("@"))


async def _resolve_target(text: str) -> int | None:
    target = _parse_target(text)
    if target is None:
        return None
    return await user_directory.resolve(target)


@router.message(Command("resettime"))
async def cmd_resettime(message: Message) -> None:
    if not _is_owner(message):
        return
    user_id = _parse_user_id(message.text)
    if user_id is None:
        await message.reply("Использование: /resettime USER_ID")
        return

    await clear_cooldown(user_id)
    await message.reply(f"✅ Кулдаун для пользователя {user_id} сброшен вручную.")
    try:
        await message.bot.send_message(user_id, "✅ Администратор снял КД с вас, подавайте анкету!")
    except Exception:
        pass


async def _do_blacklist_add(message: Message, usage: str) -> None:
    if not _is_owner(message):
        return
    raw = _parse_target(message.text)
    if raw is None:
        await message.reply(usage)
        return
    user_id = await _resolve_target(message.text)
    if user_id is None:
        await message.reply(
            f"Не удалось определить ID по «{raw}» — этот пользователь ещё не писал боту. "
            "Используйте числовой Telegram ID."
        )
        return
    added = await add_to_blacklist(user_id)
    if added:
        await message.reply(f"⛔ Пользователь {user_id} добавлен в чёрный список.")
    else:
        await message.reply(f"Пользователь {user_id} уже находится в чёрном списке.")


async def _do_blacklist_remove(message: Message, usage: str) -> None:
    if not _is_owner(message):
        return
    raw = _parse_target(message.text)
    if raw is None:
        await message.reply(usage)
        return
    user_id = await _resolve_target(message.text)
    if user_id is None:
        await message.reply(
            f"Не удалось определить ID по «{raw}» — этот пользователь ещё не писал боту. "
            "Используйте числовой Telegram ID."
        )
        return
    removed = await remove_from_blacklist(user_id)
    if removed:
        await message.reply(f"✅ Пользователь {user_id} удалён из чёрного списка.")
    else:
        await message.reply(f"Пользователь {user_id} не найден в чёрном списке.")


# Telegram не распознаёт кириллические команды как "bot command entity",
# поэтому фильтруем вручную по началу текста сообщения.
@router.message(F.text.func(lambda t: t is not None and t.startswith("/чс")))
async def cmd_blacklist_add_ru(message: Message) -> None:
    await _do_blacklist_add(message, "Использование: /чс USER_ID или /чс @username")


@router.message(F.text.func(lambda t: t is not None and t.startswith("/разблокировать")))
async def cmd_blacklist_remove_ru(message: Message) -> None:
    await _do_blacklist_remove(message, "Использование: /разблокировать USER_ID или /разблокировать @username")


@router.message(Command("block"))
async def cmd_block(message: Message) -> None:
    await _do_blacklist_add(message, "Использование: /block USER_ID или /block @username")


@router.message(Command("unblock"))
async def cmd_unblock(message: Message) -> None:
    await _do_blacklist_remove(message, "Использование: /unblock USER_ID или /unblock @username")
