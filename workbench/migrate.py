# SPDX-License-Identifier: Apache-2.0

"""Lightweight SQL migration runner for the workbench schema.

Mirrors the pattern used by complytime-core (advisory lock, schema_migrations
tracking table, sequential .sql files). Runs at startup before serving traffic.
"""

from __future__ import annotations

import logging
from pathlib import Path

import asyncpg

logger = logging.getLogger(__name__)

MIGRATIONS_DIR = Path(__file__).parent / "migrations"
LOCK_ID = 0x5742_4D4947  # "WB_MIG"


async def run_migrations(dsn: str) -> None:
    """Apply pending workbench migrations inside an advisory lock."""
    conn: asyncpg.Connection = await asyncpg.connect(dsn)
    try:
        await conn.execute("SELECT pg_advisory_lock($1)", LOCK_ID)

        await conn.execute("CREATE SCHEMA IF NOT EXISTS workbench")
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS workbench.schema_migrations (
                version    INTEGER PRIMARY KEY,
                filename   TEXT NOT NULL,
                applied_at TIMESTAMPTZ NOT NULL DEFAULT now()
            )
        """)

        sql_files = sorted(
            f for f in MIGRATIONS_DIR.iterdir() if f.suffix == ".sql" and not f.is_dir()
        )

        for sql_file in sql_files:
            version_str = sql_file.name.split("_", 1)[0]
            try:
                version = int(version_str)
            except ValueError:
                logger.warning("Skipping %s: cannot parse version", sql_file.name)
                continue

            exists = await conn.fetchval(
                "SELECT EXISTS("
                "SELECT 1 FROM workbench.schema_migrations WHERE version = $1"
                ")",
                version,
            )
            if exists:
                continue

            sql = sql_file.read_text(encoding="utf-8")
            logger.info("Applying workbench migration %03d: %s", version, sql_file.name)
            await conn.execute(sql)
            await conn.execute(
                "INSERT INTO workbench.schema_migrations (version, filename) "
                "VALUES ($1, $2)",
                version,
                sql_file.name,
            )

        await conn.execute("SELECT pg_advisory_unlock($1)", LOCK_ID)
    finally:
        await conn.close()
