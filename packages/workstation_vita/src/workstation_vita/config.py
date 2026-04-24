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


def _resolve_file_path(value: str) -> str:
    if not value:
        return ""
    path = Path(value)
    if path.is_absolute():
        return str(path)

    candidates = [
        PACKAGE_ROOT / path,
        PACKAGE_ROOT.parent / path,
        Path.cwd() / path,
    ]
    for candidate in candidates:
        if candidate.exists():
            return str(candidate.resolve())
    return str((PACKAGE_ROOT / path).resolve())


@dataclass(frozen=True)
class Settings:
    server_api_url: str
    server_api_token: str
    enable_batch_support: bool
    support_parallelism: int
    llm_url: str
    llm_key: str
    llm_model: str
    llm_fallback_url: str
    llm_fallback_key: str
    llm_fallback_model: str
    embedding_url: str
    rerank_url: str
    index_file: str
    id_map_file: str
    vector_top_k: int
    max_cases_limit: int
    planner_enabled: bool
    general_guide_link: str
    dingtalk_client_id: str
    dingtalk_client_secret: str
    dingtalk_robot_name: str


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings(
        server_api_url=_env("VITA_SERVER_API_URL", "http://127.0.0.1:3000").rstrip("/"),
        server_api_token=_env("VITA_SERVER_API_TOKEN", ""),
        enable_batch_support=_env("VITA_ENABLE_BATCH_SUPPORT", "true").lower() not in {"0", "false", "no"},
        support_parallelism=max(1, int(_env("VITA_SUPPORT_PARALLELISM", "3"))),
        llm_url=_env("VITA_LLM_URL", "http://10.98.12.68:8085/v1"),
        llm_key=_env("VITA_LLM_KEY", ""),
        llm_model=_env("VITA_LLM_MODEL", "GLM-4.7"),
        llm_fallback_url=_env("VITA_LLM_FALLBACK_URL", ""),
        llm_fallback_key=_env("VITA_LLM_FALLBACK_KEY", ""),
        llm_fallback_model=_env("VITA_LLM_FALLBACK_MODEL", "GLM-4.7"),
        embedding_url=_env("VITA_EMBEDDING_URL", "http://10.98.12.69:8080/embed"),
        rerank_url=_env("VITA_RERANK_URL", "http://10.98.12.69:8081/rerank"),
        index_file=_resolve_file_path(_env("VITA_INDEX_FILE", "kb_zhipu.index")),
        id_map_file=_resolve_file_path(_env("VITA_ID_MAP_FILE", "kb_zhipu_id_map.npy")),
        vector_top_k=int(_env("VITA_VECTOR_TOP_K", "50")),
        max_cases_limit=int(_env("VITA_MAX_CASES_LIMIT", "100")),
        planner_enabled=_env("VITA_PLANNER_ENABLED", "true").lower() not in {"0", "false", "no"},
        general_guide_link=_env("VITA_GENERAL_GUIDE_LINK", ""),
        dingtalk_client_id=_env("VITA_DINGTALK_CLIENT_ID", ""),
        dingtalk_client_secret=_env("VITA_DINGTALK_CLIENT_SECRET", ""),
        dingtalk_robot_name=_env("VITA_DINGTALK_ROBOT_NAME", "VITA"),
    )
