"""
Central app configuration — ONE authoritative settings object.

CONFIG LOADING MECHANISM:
1. The .env path is resolved EXPLICITLY and deterministically as `<this file's directory>/../.env`
2. load_dotenv() is called with override=False
3. .env.example is never read at runtime
"""
import os
from pathlib import Path
from dataclasses import dataclass, field
from dotenv import load_dotenv

THIS_FILE = Path(__file__).resolve()
BACKEND_DIR = THIS_FILE.parent.parent          # backend/app/config.py -> backend/
ENV_PATH = BACKEND_DIR / ".env"

# Snapshot BEFORE load_dotenv() runs
_PRE_EXISTING_ENV_VARS = {
    "FIRMS_MAP_KEY": "FIRMS_MAP_KEY" in os.environ,
    "FIRMS_ENABLED": "FIRMS_ENABLED" in os.environ,
    "FIRMS_ENABLE": "FIRMS_ENABLE" in os.environ,
}

_env_file_found = ENV_PATH.exists()
if _env_file_found:
    load_dotenv(dotenv_path=ENV_PATH, override=False)
else:
    load_dotenv(override=False)


def _parse_bool(raw: str, default: bool) -> bool:
    if raw is None:
        return default
    return raw.strip().lower() in ("1", "true", "yes", "on")


def _read_firms_enabled() -> bool:
    canonical = os.getenv("FIRMS_ENABLED")
    if canonical is not None:
        return _parse_bool(canonical, True)
    legacy = os.getenv("FIRMS_ENABLE")
    if legacy is not None:
        return _parse_bool(legacy, True)
    return True


@dataclass
class Settings:
    database_url: str = os.getenv("DATABASE_URL", "sqlite:///./sih.db")
    anthropic_api_key: str = os.getenv("ANTHROPIC_API_KEY", "")
    cors_origins: list = None

    # --- NASA FIRMS live ingestion ---
    firms_enabled: bool = field(default_factory=_read_firms_enabled)
    firms_map_key: str = field(default_factory=lambda: os.getenv("FIRMS_MAP_KEY", os.getenv("FIRMS_API_KEY", "")).strip())
    firms_area: str = field(default_factory=lambda: os.getenv("FIRMS_AREA", "68,8,97,37"))
    
    # Updated default sources to include VIIRS_SNPP_NRT and MODIS_NRT
    firms_sources: list = field(default_factory=lambda: [
        s.strip() for s in os.getenv(
            "FIRMS_SOURCES", 
            "VIIRS_SNPP_NRT,VIIRS_NOAA20_NRT,VIIRS_NOAA21_NRT,MODIS_NRT"
        ).split(",") if s.strip()
    ])
    firms_sync_interval_minutes: int = field(default_factory=lambda: int(os.getenv("FIRMS_SYNC_INTERVAL_MINUTES", "15")))

    def __post_init__(self):
        origins = os.getenv("CORS_ORIGINS", "http://localhost:5173,http://localhost:5174")
        self.cors_origins = [o.strip() for o in origins.split(",")]

    @property
    def firms_configured(self) -> bool:
        return bool(self.firms_map_key)

    def diagnostic_snapshot(self) -> dict:
        return {
            "env_file_expected_path": str(ENV_PATH),
            "env_file_found": _env_file_found,
            "firms_map_key_pre_existed_in_os_environ": _PRE_EXISTING_ENV_VARS["FIRMS_MAP_KEY"],
            "firms_enabled_pre_existed_in_os_environ": _PRE_EXISTING_ENV_VARS["FIRMS_ENABLED"],
            "firms_enable_typo_pre_existed_in_os_environ": _PRE_EXISTING_ENV_VARS["FIRMS_ENABLE"],
            "firms_enabled": self.firms_enabled,
            "firms_configured": self.firms_configured,
            "firms_map_key_length": len(self.firms_map_key),
            "firms_area": self.firms_area,
            "firms_sources": self.firms_sources,
            "firms_sync_interval_minutes": self.firms_sync_interval_minutes,
            "resolved_working_directory": str(Path.cwd()),
            "config_module_actual_path": str(THIS_FILE),
        }


settings = Settings()