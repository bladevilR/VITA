from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv


PACKAGE_ROOT = Path(__file__).resolve().parents[2]
load_dotenv(PACKAGE_ROOT / ".env", override=False)


def _env(key: str, default: str = "") -> str:
    return os.getenv(key, default)


def _resolve_path(value: str) -> str:
    if not value:
        return ""
    path = Path(value)
    if path.is_absolute():
        return str(path)
    return str((PACKAGE_ROOT / path).resolve())


@dataclass(frozen=True)
class Settings:
    host: str
    port: int
    api_token: str
    db_user: str
    db_password: str
    db_dsn: str
    oracle_client_path: str
    db_pool_min: int
    db_pool_max: int
    db_pool_increment: int
    db_connect_timeout: int
    db_max_retries: int
    db_retry_delay: float
    max_cases_limit: int


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings(
        host=_env("VITA_SERVER_HOST", "0.0.0.0"),
        port=int(_env("VITA_SERVER_PORT", "3000")),
        api_token=_env("VITA_SERVER_API_TOKEN", ""),
        db_user=_env("VITA_DB_USER", "maxsearch"),
        db_password=_env("VITA_DB_PASSWORD", ""),
        db_dsn=_env("VITA_DB_DSN", "10.97.4.7:1521/eamprod"),
        oracle_client_path=_resolve_path(_env("VITA_ORACLE_CLIENT", "")),
        db_pool_min=int(_env("VITA_DB_POOL_MIN", "2")),
        db_pool_max=int(_env("VITA_DB_POOL_MAX", "10")),
        db_pool_increment=int(_env("VITA_DB_POOL_INCREMENT", "1")),
        db_connect_timeout=int(_env("VITA_DB_CONNECT_TIMEOUT", "8")),
        db_max_retries=int(_env("VITA_DB_MAX_RETRIES", "2")),
        db_retry_delay=float(_env("VITA_DB_RETRY_DELAY", "1.0")),
        max_cases_limit=int(_env("VITA_MAX_CASES_LIMIT", "100")),
    )
