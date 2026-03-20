import os
from typing import Dict, Union

import psycopg
from pgvector.psycopg import register_vector
from psycopg.rows import dict_row


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


def get_conn() -> psycopg.Connection:
    settings = get_settings()
    conn = psycopg.connect(
        host=settings["host"],
        port=settings["port"],
        user=settings["user"],
        password=settings["password"],
        dbname=settings["database"],
        row_factory=dict_row,
    )
    register_vector(conn)
    return conn
