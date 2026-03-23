import os
from typing import Dict, Optional, Union

import psycopg
from pgvector.psycopg import register_vector
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool


def get_settings() -> Dict[str, Union[str, int]]:
    return {
        "host": os.environ["LYB_SKILL_PG_ADDRESS"],
        "port": int(os.environ.get("LYB_SKILL_PG_PORT", "5432")),
        "user": os.environ["LYB_SKILL_PG_USERNAME"],
        "password": os.environ["LYB_SKILL_PG_PASSWORD"],
        "database": os.environ["LYB_SKILL_PG_MY_PERSONAL_DATABASE"],
        "memory_user": os.environ.get("LYB_SKILL_MEMORY_USER", "LYB"),
        "service_host": os.environ.get("LYB_SKILL_MEMORY_SERVICE_HOST", "127.0.0.1"),
        "service_port": int(os.environ.get("LYB_SKILL_MEMORY_SERVICE_PORT", "8787")),
    }


def _make_conninfo() -> str:
    s = get_settings()
    return (
        f"host={s['host']} port={s['port']} user={s['user']} "
        f"password={s['password']} dbname={s['database']}"
    )


def _configure_conn(conn: psycopg.Connection) -> None:
    register_vector(conn)


_pool: Optional[ConnectionPool] = None


def _get_pool() -> ConnectionPool:
    global _pool
    if _pool is None:
        _pool = ConnectionPool(
            conninfo=_make_conninfo(),
            min_size=2,
            max_size=20,
            configure=_configure_conn,
            kwargs={"row_factory": dict_row},
            open=False,  # 延迟打开，避免 import 时建立连接
        )
        _pool.open()
    return _pool


def get_conn() -> psycopg.Connection:
    """返回池化连接的 context manager。用法与之前完全相同：with get_conn() as conn。"""
    return _get_pool().connection()
