"""Загрузка конфигурации бота из переменных окружения (.env на Railway/локально)."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import List

from dotenv import load_dotenv

load_dotenv()


def _env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in ("1", "true", "yes", "on")


def _split_stickers(raw: str) -> List[str]:
    return [item.strip() for item in raw.split(",") if item.strip()]


@dataclass
class Config:
    bot_token: str
    owner_id: int
    admin_contact: str
    approval_invite_link: str
    banner: str
    help_gif: str
    stickers: List[str]
    cooldown_days: int
    antispam_limit: int
    antispam_window: int
    antispam_block_minutes: int
    data_dir: Path

    @property
    def users_file(self) -> Path:
        return self.data_dir / "users.json"

    @property
    def anketas_file(self) -> Path:
        return self.data_dir / "anketas.json"

    @property
    def blacklist_file(self) -> Path:
        return self.data_dir / "blacklist.json"

    @property
    def settings_file(self) -> Path:
        return self.data_dir / "settings.json"

    @property
    def fsm_file(self) -> Path:
        return self.data_dir / "fsm_storage.json"

    @property
    def user_directory_file(self) -> Path:
        return self.data_dir / "user_directory.json"


def load_config() -> Config:
    bot_token = os.getenv("BOT_TOKEN", "").strip()
    if not bot_token:
        raise RuntimeError(
            "Переменная окружения BOT_TOKEN не задана. "
            "Добавьте её в .env (локально) или в переменные окружения Railway."
        )

    owner_raw = os.getenv("OWNER_ID", "7541580964").strip()
    try:
        owner_id = int(owner_raw)
    except ValueError as exc:
        raise RuntimeError(f"OWNER_ID должен быть числом, получено: {owner_raw!r}") from exc

    data_dir = Path(os.getenv("DATA_DIR", "data"))
    data_dir.mkdir(parents=True, exist_ok=True)

    return Config(
        bot_token=bot_token,
        owner_id=owner_id,
        admin_contact=os.getenv("ADMIN_CONTACT", "@notrightuser").strip(),
        approval_invite_link=os.getenv("APPROVAL_INVITE_LINK", "").strip(),
        banner=os.getenv("BANNER_IMAGE", "").strip(),
        help_gif=os.getenv("HELP_GIF", "").strip(),
        stickers=_split_stickers(os.getenv("QUESTION_STICKERS", "")),
        cooldown_days=int(os.getenv("COOLDOWN_DAYS", "4")),
        antispam_limit=int(os.getenv("ANTISPAM_LIMIT", "6")),
        antispam_window=int(os.getenv("ANTISPAM_WINDOW_SECONDS", "8")),
        antispam_block_minutes=int(os.getenv("ANTISPAM_BLOCK_MINUTES", "15")),
        data_dir=data_dir,
    )


config = load_config()
