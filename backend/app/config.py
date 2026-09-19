"""
Central app configuration — ONE authoritative settings object.

CONFIG LOADING MECHANISM (documented here because a prior bare
`load_dotenv()` call caused a real, confirmed bug — see
docs/LIVE_DATA_STATUS.md for the full trace):

1. The .env path is resolved EXPLICITLY and deterministically as
   `<this file's directory>/../.env` — i.e. always `backend/.env`,
   regardless of the working directory `uvicorn`/`python` was launched
   from. This removes the ambiguity of bare `load_dotenv()`, whose
   default search behavior depends on python-dotenv's version and the
   caller's stack frame, and is NOT guaranteed to resolve to the same
   file when the app is started from `backend/` vs. the project root vs.
   a nested/duplicate extracted copy of the project.

2. `load_dotenv()` is called with `override=False` (the default) — this
   is intentional and matches the explicit requirement that real OS
   environment variables take precedence over `.env`. The consequence,
   which is the most likely real root cause of "`.env` has the key but
   the app doesn't see it": if `FIRMS_MAP_KEY` (or any other var here)
   already exists in the process environment BEFORE this module runs —
   from a stray shell `export`/`set`, a parent terminal profile, an IDE's
   own "envFile" setting loading a *different* file, or simply a leftover
   empty variable from an earlier session — `.env`'s value is silently
   ignored, by design, because real env vars are supposed to win. This
   is diagnosed, not silently swallowed: see `_env_var_preexisted` below
   and `python -m scripts.test_firms`.

3. `.env.example` is never read at runtime by any code path in this
   project — grep-verified, it is referenced only in documentation.

FIRMS_MAP_KEY is read here ONLY, and never logged or returned by any API
response — every diagnostic surface reports booleans/lengths, never the
value itself. Grep-verified: `grep -rn firms_map_key backend/app` only
ever shows this file, firms_fetcher.py, and firms_ingestion.py.
"""
import os
from pathlib import Path
from dataclasses import dataclass, field
from dotenv import load_dotenv

THIS_FILE = Path(__file__).resolve()
BACKEND_DIR = THIS_FILE.parent.parent          # backend/app/config.py -> backend/
ENV_PATH = BACKEND_DIR / ".env"

# Snapshot BEFORE load_dotenv() runs, so we can tell the difference between
# ".env set it" and "an OS/shell variable already had this name" — this is
# exactly the ambiguity that produces "the file has it but the app doesn't."
_PRE_EXISTING_ENV_VARS = {
    "FIRMS_MAP_KEY": "FIRMS_MAP_KEY" in os.environ,
    "FIRMS_ENABLED": "FIRMS_ENABLED" in os.environ,
    "FIRMS_ENABLE": "FIRMS_ENABLE" in os.environ,
}

_env_file_found = ENV_PATH.exists()
if _env_file_found:
    load_dotenv(dotenv_path=ENV_PATH, override=False)
else:
    # Fall back to dotenv's own search as a last resort (e.g. if someone
    # genuinely runs this from an unusual layout) — but this is now the
    # FALLBACK path, not the only path, and is reported in diagnostics.
    load_dotenv(override=False)


def _parse_bool(raw: str, default: bool) -> bool:
    if raw is None:
        return default
    return raw.strip().lower() in ("1", "true", "yes", "on")


def _read_firms_enabled() -> bool:
    """
    Canonical name is FIRMS_ENABLED. FIRMS_ENABLE (no 'D') is a real,
    observed typo in at least one real .env used with this project —
    accepted as an alias so a misspelling doesn't silently disable live
    data, but ONLY the canonical name is documented going forward, and
    diagnostics flag it if only the misspelled version is present.
    """
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
    firms_area: str = field(default_factory=lambda: os.getenv("FIRMS_AREA", "68,6,97,37"))
    firms_sources: list = field(default_factory=lambda: [
        s.strip() for s in os.getenv("FIRMS_SOURCES", "VIIRS_NOAA21_NRT,VIIRS_NOAA20_NRT").split(",") if s.strip()
    ])
    firms_sync_interval_minutes: int = field(default_factory=lambda: int(os.getenv("FIRMS_SYNC_INTERVAL_MINUTES", "15")))

    def __post_init__(self):
        origins = os.getenv("CORS_ORIGINS", "http://localhost:5173,http://localhost:5174")
        self.cors_origins = [o.strip() for o in origins.split(",")]

    @property
    def firms_configured(self) -> bool:
        return bool(self.firms_map_key)

    def diagnostic_snapshot(self) -> dict:
        """
        Every field here is SAFE TO LOG/PRINT/RETURN — no secret values,
        only booleans, lengths, and paths. Used by scripts/test_firms.py
        and the startup diagnostic log. This is the ONLY sanctioned way
        to introspect FIRMS config for debugging.
        """
        return {
            "env_file_expected_path": str(ENV_PATH),
            "env_file_found": _env_file_found,
            "firms_map_key_pre_existed_in_os_environ": _PRE_EXISTING_ENV_VARS["FIRMS_MAP_KEY"],
            "firms_enabled_pre_existed_in_os_environ": _PRE_EXISTING_ENV_VARS["FIRMS_ENABLED"],
            "firms_enable_typo_pre_existed_in_os_environ": _PRE_EXISTING_ENV_VARS["FIRMS_ENABLE"],
            "firms_enabled": self.firms_enabled,
            "firms_configured": self.firms_configured,
            "firms_map_key_length": len(self.firms_map_key),  # NEVER the key itself
            "firms_area": self.firms_area,
            "firms_sources": self.firms_sources,
            "firms_sync_interval_minutes": self.firms_sync_interval_minutes,
            "resolved_working_directory": str(Path.cwd()),
            "config_module_actual_path": str(THIS_FILE),
        }


settings = Settings()
