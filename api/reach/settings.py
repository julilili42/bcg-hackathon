"""Runtime settings.

Environment variables win. Locally, ``api/local.settings.json`` (the Azure Functions convention) fills
the gaps so ``uvicorn`` and ``func start`` see the same values. Secrets never live in tracked files.
"""

from __future__ import annotations

import json
import os
from functools import lru_cache
from pathlib import Path

from pydantic import BaseModel

API_DIR = Path(__file__).resolve().parents[1]
REPO_ROOT = API_DIR.parent
DEFAULT_SALT = "dev-salt-change-me"


def _load_local_settings_file() -> None:
    path = API_DIR / "local.settings.json"
    if not path.exists():
        return
    try:
        values = json.loads(path.read_text(encoding="utf-8")).get("Values", {})
    except (OSError, ValueError):
        return
    for key, value in values.items():
        if isinstance(value, str) and value and key not in os.environ:
            os.environ[key] = value


def _env(name: str, default: str = "") -> str:
    return os.environ.get(name, default)


def _flag(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


class Settings(BaseModel):
    database_url: str
    twilio_auth_token: str
    twilio_validate: bool
    anthropic_api_key: str
    claude_model: str
    claude_timeout_s: float
    reporter_salt: str
    public_base_url: str
    tts_provider: str
    azure_speech_key: str
    azure_speech_region: str
    data_dir: Path
    audio_dir: Path
    models_dir: Path
    web_dist_dir: Path
    rate_limit_max: int
    rate_limit_window_s: int
    default_domain: str
    confirm_threshold: float
    sms_confirm_threshold: float
    admin_token: str
    claude_fallbacks: bool
    demo_phone: bool

    @property
    def claude_enabled(self) -> bool:
        return bool(self.anthropic_api_key)

    @property
    def salt_is_default(self) -> bool:
        return self.reporter_salt == DEFAULT_SALT


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    _load_local_settings_file()
    data_dir = Path(_env("REACH_DATA_DIR", str(REPO_ROOT / "data")))
    return Settings(
        database_url=_env("DATABASE_URL", f"sqlite:///{data_dir / 'local.db'}"),
        twilio_auth_token=_env("TWILIO_AUTH_TOKEN"),
        twilio_validate=_flag("TWILIO_VALIDATE", True),
        anthropic_api_key=_env("ANTHROPIC_API_KEY"),
        claude_model=_env("CLAUDE_MODEL", "claude-opus-5-5"),
        claude_timeout_s=float(_env("CLAUDE_TIMEOUT_S", "4")),
        reporter_salt=_env("REPORTER_SALT", DEFAULT_SALT),
        public_base_url=_env("PUBLIC_BASE_URL").rstrip("/"),
        tts_provider=_env("TTS_PROVIDER", "auto"),
        azure_speech_key=_env("AZURE_SPEECH_KEY"),
        azure_speech_region=_env("AZURE_SPEECH_REGION"),
        data_dir=data_dir,
        audio_dir=Path(_env("REACH_AUDIO_DIR", str(REPO_ROOT / "audio"))),
        models_dir=Path(_env("REACH_MODELS_DIR", str(REPO_ROOT / "models"))),
        web_dist_dir=Path(_env("REACH_WEB_DIST", str(REPO_ROOT / "web" / "dist"))),
        rate_limit_max=int(_env("RATE_LIMIT_MAX", "20")),
        rate_limit_window_s=int(_env("RATE_LIMIT_WINDOW_S", "600")),
        default_domain=_env("DEFAULT_DOMAIN", "water"),
        confirm_threshold=float(_env("CONFIRM_THRESHOLD", "0.6")),
        sms_confirm_threshold=float(_env("SMS_CONFIRM_THRESHOLD", "0.4")),
        admin_token=_env("ADMIN_TOKEN"),
        claude_fallbacks=_flag("CLAUDE_FALLBACKS", True),
        demo_phone=_flag("DEMO_PHONE", True),
    )


def reset_settings() -> None:
    """Tests change environment variables and call this to re-read them."""
    get_settings.cache_clear()
