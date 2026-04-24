from __future__ import annotations

import logging
import os
import socket
import threading
import time
from typing import Any

import oracledb
import pandas as pd

from .config import get_settings


logger = logging.getLogger("server_maximo.db")


class DatabaseManager:
    _pool = None
    _pool_failed = False
    _oracle_initialized = False
    _init_lock = threading.Lock()

    @classmethod
    def initialize_oracle_client(cls) -> None:
        settings = get_settings()
        if cls._oracle_initialized:
            return

        with cls._init_lock:
            if cls._oracle_initialized:
                return
            if settings.oracle_client_path and os.path.exists(settings.oracle_client_path):
                try:
                    oracledb.init_oracle_client(lib_dir=settings.oracle_client_path)
                    logger.info("Oracle thick mode enabled: %s", settings.oracle_client_path)
                except Exception as exc:  # noqa: BLE001
                    logger.warning("Oracle client init failed, fallback to thin mode: %s", exc)
            cls._oracle_initialized = True

    @staticmethod
    def sanitize_input(value: Any) -> str:
        if value is None:
            return ""
        text = str(value)
        dangerous_tokens = ["'", "\"", ";", "--", "/*", "*/", "xp_", "exec", "execute", "drop", "delete", "insert", "update"]
        for token in dangerous_tokens:
            text = text.replace(token, "")
        return text[:200]

    @classmethod
    def _test_connectivity(cls, timeout: int) -> bool:
        settings = get_settings()
        attempts: list[str] = []
        try:
            dsn_part = settings.db_dsn.split("/")[0]
            if ":" in dsn_part:
                host, port_str = dsn_part.rsplit(":", 1)
                port = int(port_str)
            else:
                host, port = dsn_part, 1521

            addrs = socket.getaddrinfo(host, port, socket.AF_INET, socket.SOCK_STREAM)
            if not addrs:
                return False

            seen_ips: set[str] = set()
            for addr in addrs:
                ip = addr[4][0]
                if ip in seen_ips:
                    continue
                seen_ips.add(ip)
                try:
                    with socket.create_connection((ip, port), timeout=timeout):
                        logger.info("DB TCP precheck passed (%s -> %s:%s)", settings.db_dsn, ip, port)
                        return True
                except Exception as exc:  # noqa: BLE001
                    attempts.append(f"{ip}:{port} -> {exc}")
        except Exception as exc:  # noqa: BLE001
            attempts.append(str(exc))

        if attempts:
            logger.warning("DB TCP precheck failed (%s): %s", settings.db_dsn, " | ".join(attempts))
            return False
        return False

    @classmethod
    def get_pool(cls):
        settings = get_settings()
        if cls._pool_failed:
            return None

        if cls._pool is None:
            if not settings.db_password:
                raise ValueError("缺少数据库密码，请配置 VITA_DB_PASSWORD")

            cls.initialize_oracle_client()

            if not cls._test_connectivity(timeout=settings.db_connect_timeout):
                cls._pool_failed = True
                logger.error("Database is not reachable: %s", settings.db_dsn)
                return None

            cls._pool = oracledb.create_pool(
                user=settings.db_user,
                password=settings.db_password,
                dsn=settings.db_dsn,
                min=settings.db_pool_min,
                max=settings.db_pool_max,
                increment=settings.db_pool_increment,
                getmode=oracledb.POOL_GETMODE_WAIT,
                tcp_connect_timeout=settings.db_connect_timeout,
            )
            logger.info(
                "Database pool created: min=%s max=%s dsn=%s",
                settings.db_pool_min,
                settings.db_pool_max,
                settings.db_dsn,
            )
        return cls._pool

    @classmethod
    def get_connection(cls):
        pool = cls.get_pool()
        if pool is None:
            raise ConnectionError(f"数据库连接池不可用：{get_settings().db_dsn}")
        return pool.acquire()

    @classmethod
    def check_ready(cls) -> tuple[bool, str]:
        try:
            pool = cls.get_pool()
            if pool is None:
                return False, f"数据库不可达：{get_settings().db_dsn}"
            with pool.acquire():
                return True, "正常"
        except Exception as exc:  # noqa: BLE001
            return False, str(exc)

    @classmethod
    def is_available(cls) -> bool:
        return not cls._pool_failed

    @classmethod
    def execute_query_safe(cls, sql: str, params: dict[str, Any] | None = None) -> pd.DataFrame:
        settings = get_settings()
        last_error: Exception | None = None
        for attempt in range(settings.db_max_retries):
            try:
                with cls.get_connection() as conn:
                    return pd.read_sql(sql, conn, params=params)
            except Exception as exc:  # noqa: BLE001
                last_error = exc
                logger.warning("DB query failed at attempt %s/%s: %s", attempt + 1, settings.db_max_retries, exc)
                if attempt < settings.db_max_retries - 1:
                    time.sleep(settings.db_retry_delay * (attempt + 1))
        if last_error is not None:
            raise last_error
        return pd.DataFrame()
