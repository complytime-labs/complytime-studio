# SPDX-License-Identifier: Apache-2.0

"""Programs CRUD storage and HTTP handlers (async Postgres via asyncpg)."""

from __future__ import annotations

import json
import os
from datetime import datetime
from typing import Any, Mapping
from uuid import UUID

import asyncpg
from starlette.requests import Request
from starlette.responses import JSONResponse

ENV_POSTGRES_URL = "POSTGRES_URL"

DEFAULT_STATUS_INTAKE = "intake"
DEFAULT_VERSION = 1
DEFAULT_GREEN_PCT = 90
DEFAULT_RED_PCT = 50
ERR_INVALID_JSON_BODY = "invalid JSON body"
ERR_NAME_REQUIRED = "name is required"
ERR_FRAMEWORK_REQUIRED = "framework is required"
ERR_VERSION_REQUIRED = "version is required"

HTTP_STATUS_OK = 200
HTTP_STATUS_CREATED = 201
HTTP_STATUS_BAD_REQUEST = 400
HTTP_STATUS_NOT_FOUND = 404
HTTP_STATUS_CONFLICT = 409
HTTP_STATUS_INTERNAL_ERROR = 500

SQL_SELECT_PROGRAM_FIELDS = """\
id, name, guidance_catalog_id, framework, applicability, status,
    health, owner, description, metadata, policy_ids, environments,
    version, green_pct, red_pct, score_pct, created_at, updated_at"""

SQL_LIST_PROGRAMS = (
    "SELECT "
    + SQL_SELECT_PROGRAM_FIELDS
    + """
FROM workbench.programs
WHERE deleted_at IS NULL
ORDER BY created_at DESC"""
)

SQL_GET_PROGRAM = (
    "SELECT "
    + SQL_SELECT_PROGRAM_FIELDS
    + """
FROM workbench.programs
WHERE id = $1 AND deleted_at IS NULL"""
)

SQL_EXISTS_PROGRAM = (
    "SELECT 1 FROM workbench.programs WHERE id = $1 AND deleted_at IS NULL LIMIT 1"
)

SQL_RESOLVE_GUIDANCE_CATALOG = """SELECT target_catalog_id
    FROM public.mapping_documents
    WHERE framework = $1
    LIMIT 1"""

SQL_INSERT_PROGRAM = (
    """INSERT INTO workbench.programs (
            name, guidance_catalog_id, framework, applicability, status,
            health, owner, description, metadata, policy_ids, environments,
            version, green_pct, red_pct
        ) VALUES (
            $1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14
        ) RETURNING """
    + SQL_SELECT_PROGRAM_FIELDS
)

SQL_UPDATE_PROGRAM = (
    """UPDATE workbench.programs SET
            name = $1,
            guidance_catalog_id = $2,
            framework = $3,
            applicability = $4,
            status = $5,
            health = $6,
            owner = $7,
            description = $8,
            metadata = $9,
            policy_ids = $10,
            environments = $11,
            green_pct = $12,
            red_pct = $13,
            version = version + 1,
            updated_at = now()
        WHERE id = $14 AND version = $15 AND deleted_at IS NULL
        RETURNING """
    + SQL_SELECT_PROGRAM_FIELDS
)

SQL_SOFT_DELETE_PROGRAM = """UPDATE workbench.programs
    SET deleted_at = now(), updated_at = now()
    WHERE id = $1 AND deleted_at IS NULL
    RETURNING id"""

_pool: asyncpg.Pool | None = None


class ProgramNotFoundError(Exception):
    """No non-deleted program row for the given id."""


class ProgramVersionConflictError(Exception):
    """Optimistic concurrency: expected version did not match."""


async def get_pool() -> asyncpg.Pool:
    """Module-level singleton asyncpg pool (lazy init)."""
    global _pool
    if _pool is None:
        dsn = os.environ.get(ENV_POSTGRES_URL, "").strip()
        if not dsn:
            raise RuntimeError(f"{ENV_POSTGRES_URL} is not set")
        _pool = await asyncpg.create_pool(dsn)
    return _pool


def _datetime_to_iso(value: datetime) -> str:
    """Serialize Postgres timestamps for JSON (RFC3339-style)."""
    if value.tzinfo is None:
        return value.replace(tzinfo=datetime.UTC).isoformat().replace("+00:00", "Z")
    return value.isoformat().replace("+00:00", "Z")


def _json_value(val: Any) -> Any:
    """JSON-serialize individual cell values."""
    if val is None:
        return None
    if isinstance(val, datetime):
        return _datetime_to_iso(val)
    if isinstance(val, UUID):
        return str(val)
    if isinstance(val, (bytes, bytearray)):
        return json.loads(val.decode("utf-8"))
    return val


def program_row_to_json(rec: Mapping[str, Any]) -> dict[str, Any]:
    """Map a DB row mapping to API JSON (snake_case, ISO datetimes)."""
    md = rec["metadata"]
    if md is None:
        md_json: dict[str, Any] = {}
    elif isinstance(md, dict):
        md_json = md
    else:
        md_json = {}

    return {
        "id": _json_value(rec["id"]),
        "name": rec["name"],
        "guidance_catalog_id": _json_value(rec.get("guidance_catalog_id")),
        "framework": rec["framework"],
        "applicability": list(rec["applicability"])
        if rec["applicability"] is not None
        else [],
        "status": rec["status"],
        "health": _json_value(rec.get("health")),
        "owner": _json_value(rec.get("owner")),
        "description": _json_value(rec.get("description")),
        "metadata": md_json,
        "policy_ids": list(rec["policy_ids"])
        if rec["policy_ids"] is not None
        else [],
        "environments": list(rec["environments"])
        if rec["environments"] is not None
        else [],
        "version": rec["version"],
        "green_pct": rec["green_pct"],
        "red_pct": rec["red_pct"],
        "score_pct": rec["score_pct"],
        "created_at": _json_value(rec["created_at"]),
        "updated_at": _json_value(rec["updated_at"]),
    }


async def list_programs_db(pool: asyncpg.Pool) -> list[dict[str, Any]]:
    async with pool.acquire() as conn:
        rows = await conn.fetch(SQL_LIST_PROGRAMS)
    return [program_row_to_json(dict(r)) for r in rows]


async def get_program_db(pool: asyncpg.Pool, program_id: str) -> dict[str, Any] | None:
    async with pool.acquire() as conn:
        row = await conn.fetchrow(SQL_GET_PROGRAM, program_id)
    if row is None:
        return None
    return program_row_to_json(dict(row))


async def _maybe_resolve_guidance_catalog_id(
    conn: asyncpg.Connection,
    framework: str,
    guidance_catalog_id: str | None,
) -> str | None:
    if guidance_catalog_id:
        return guidance_catalog_id
    if not framework:
        return None
    resolved = await conn.fetchval(SQL_RESOLVE_GUIDANCE_CATALOG, framework)
    if resolved:
        return str(resolved)
    return None


def _coerce_optional_str(val: Any) -> str | None:
    if val is None:
        return None
    if isinstance(val, str):
        return val
    raise ValueError("optional string fields must be strings or null")


def _coerce_string_list(val: Any) -> list[str]:
    if val is None:
        return []
    if not isinstance(val, list):
        raise ValueError("list fields must be JSON arrays")
    out: list[str] = []
    for item in val:
        if not isinstance(item, str):
            raise ValueError("list fields must contain only strings")
        out.append(item)
    return out


def _coerce_metadata(val: Any) -> dict[str, Any]:
    if val is None:
        return {}
    if isinstance(val, dict):
        return val
    raise ValueError("metadata must be a JSON object")


def _validate_create_required_fields(body: Mapping[str, Any]) -> None:
    """Cheap checks before Postgres (so validation tests need no DB pool)."""
    name = body.get("name")
    framework = body.get("framework")
    if not isinstance(name, str) or not name.strip():
        raise ValueError(ERR_NAME_REQUIRED)
    if not isinstance(framework, str) or not framework.strip():
        raise ValueError(ERR_FRAMEWORK_REQUIRED)


async def create_program_db(
    pool: asyncpg.Pool, body: Mapping[str, Any]
) -> dict[str, Any]:
    name = str(body["name"])
    framework = str(body["framework"])

    applicability = _coerce_string_list(body.get("applicability"))
    policy_ids = _coerce_string_list(body.get("policy_ids"))
    environments = _coerce_string_list(body.get("environments"))

    status = body.get("status") or DEFAULT_STATUS_INTAKE
    if not isinstance(status, str):
        raise ValueError("status must be a string")

    version = body.get("version")
    if version is None:
        ver = DEFAULT_VERSION
    elif not isinstance(version, int):
        raise ValueError("version must be an integer")
    else:
        ver = DEFAULT_VERSION if version == 0 else version

    gci_raw = body.get("guidance_catalog_id")
    if gci_raw is not None and not isinstance(gci_raw, str):
        raise ValueError("guidance_catalog_id must be a string or null")
    guidance_catalog_id: str | None = gci_raw if gci_raw else None

    metadata = _coerce_metadata(body.get("metadata"))
    md_json = json.dumps(metadata) if metadata else json.dumps({})

    health = _coerce_optional_str(body.get("health"))
    owner = _coerce_optional_str(body.get("owner"))
    description = _coerce_optional_str(body.get("description"))

    green_pct = body.get("green_pct", DEFAULT_GREEN_PCT)
    red_pct = body.get("red_pct", DEFAULT_RED_PCT)
    if not isinstance(green_pct, int) or not isinstance(red_pct, int):
        raise ValueError("green_pct and red_pct must be integers")

    green = DEFAULT_GREEN_PCT if green_pct == 0 else green_pct
    red = DEFAULT_RED_PCT if red_pct == 0 else red_pct

    async with pool.acquire() as conn:
        guidance_catalog_id = await _maybe_resolve_guidance_catalog_id(
            conn, framework, guidance_catalog_id
        )
        row = await conn.fetchrow(
            SQL_INSERT_PROGRAM,
            name,
            guidance_catalog_id,
            framework,
            applicability,
            status,
            health,
            owner,
            description,
            md_json,
            policy_ids,
            environments,
            ver,
            green,
            red,
        )
    assert row is not None
    return program_row_to_json(dict(row))


async def update_program_db(
    pool: asyncpg.Pool, program_id: str, body: Mapping[str, Any]
) -> dict[str, Any]:
    if not isinstance(program_id, str) or not program_id.strip():
        raise ProgramNotFoundError

    async with pool.acquire() as conn:
        row_exists = await conn.fetchval(SQL_EXISTS_PROGRAM, program_id)
        if row_exists is None:
            raise ProgramNotFoundError

        name = body.get("name")
        framework = body.get("framework")
        if not isinstance(name, str) or not name.strip():
            raise ValueError(ERR_NAME_REQUIRED)
        if not isinstance(framework, str) or not framework.strip():
            raise ValueError(ERR_FRAMEWORK_REQUIRED)

        version = body.get("version")
        if not isinstance(version, int):
            raise ValueError(ERR_VERSION_REQUIRED)

        applicability = _coerce_string_list(body.get("applicability"))
        policy_ids = _coerce_string_list(body.get("policy_ids"))
        environments = _coerce_string_list(body.get("environments"))

        status = body.get("status")
        if not isinstance(status, str) or not status.strip():
            raise ValueError("status is required")

        gci_raw = body.get("guidance_catalog_id")
        if gci_raw is not None and not isinstance(gci_raw, str):
            raise ValueError("guidance_catalog_id must be a string or null")
        guidance_catalog_id: str | None = gci_raw if gci_raw else None

        metadata = _coerce_metadata(body.get("metadata"))
        md_json = json.dumps(metadata) if metadata else json.dumps({})

        health = _coerce_optional_str(body.get("health"))
        owner = _coerce_optional_str(body.get("owner"))
        description = _coerce_optional_str(body.get("description"))

        green_pct = body.get("green_pct")
        red_pct = body.get("red_pct")
        if not isinstance(green_pct, int) or not isinstance(red_pct, int):
            raise ValueError("green_pct and red_pct must be integers")

        row = await conn.fetchrow(
            SQL_UPDATE_PROGRAM,
            name,
            guidance_catalog_id,
            framework,
            applicability,
            status,
            health,
            owner,
            description,
            md_json,
            policy_ids,
            environments,
            green_pct,
            red_pct,
            program_id,
            version,
        )

    if row is None:
        raise ProgramVersionConflictError
    return program_row_to_json(dict(row))


async def delete_program_db(pool: asyncpg.Pool, program_id: str) -> None:
    async with pool.acquire() as conn:
        row = await conn.fetchrow(SQL_SOFT_DELETE_PROGRAM, program_id)
    if row is None:
        raise ProgramNotFoundError


async def list_programs(request: Request) -> JSONResponse:
    try:
        pool = await get_pool()
        data = await list_programs_db(pool)
    except RuntimeError as e:
        return JSONResponse(
            {"error": str(e)}, status_code=HTTP_STATUS_INTERNAL_ERROR
        )
    except Exception:
        return JSONResponse(
            {"error": "database error"}, status_code=HTTP_STATUS_INTERNAL_ERROR
        )
    return JSONResponse(data, status_code=HTTP_STATUS_OK)


async def get_program(request: Request) -> JSONResponse:
    program_id = request.path_params["id"]
    try:
        pool = await get_pool()
        row = await get_program_db(pool, program_id)
    except RuntimeError as e:
        return JSONResponse(
            {"error": str(e)}, status_code=HTTP_STATUS_INTERNAL_ERROR
        )
    except Exception:
        return JSONResponse(
            {"error": "database error"}, status_code=HTTP_STATUS_INTERNAL_ERROR
        )
    if row is None:
        return JSONResponse({"error": "not found"}, status_code=HTTP_STATUS_NOT_FOUND)
    return JSONResponse(row, status_code=HTTP_STATUS_OK)


async def create_program(request: Request) -> JSONResponse:
    try:
        payload = await request.json()
    except json.JSONDecodeError:
        return JSONResponse(
            {"error": ERR_INVALID_JSON_BODY}, status_code=HTTP_STATUS_BAD_REQUEST
        )
    if not isinstance(payload, dict):
        return JSONResponse(
            {"error": ERR_INVALID_JSON_BODY}, status_code=HTTP_STATUS_BAD_REQUEST
        )

    try:
        _validate_create_required_fields(payload)
    except ValueError as e:
        return JSONResponse({"error": str(e)}, status_code=HTTP_STATUS_BAD_REQUEST)

    try:
        pool = await get_pool()
        created = await create_program_db(pool, payload)
    except ValueError as e:
        return JSONResponse({"error": str(e)}, status_code=HTTP_STATUS_BAD_REQUEST)
    except RuntimeError as e:
        return JSONResponse(
            {"error": str(e)}, status_code=HTTP_STATUS_INTERNAL_ERROR
        )
    except Exception:
        return JSONResponse(
            {"error": "database error"}, status_code=HTTP_STATUS_INTERNAL_ERROR
        )
    return JSONResponse(created, status_code=HTTP_STATUS_CREATED)


async def update_program(request: Request) -> JSONResponse:
    program_id = request.path_params["id"]
    try:
        payload = await request.json()
    except json.JSONDecodeError:
        return JSONResponse(
            {"error": ERR_INVALID_JSON_BODY}, status_code=HTTP_STATUS_BAD_REQUEST
        )
    if not isinstance(payload, dict):
        return JSONResponse(
            {"error": ERR_INVALID_JSON_BODY}, status_code=HTTP_STATUS_BAD_REQUEST
        )

    try:
        pool = await get_pool()
        updated = await update_program_db(pool, program_id, payload)
    except ProgramNotFoundError:
        return JSONResponse({"error": "not found"}, status_code=HTTP_STATUS_NOT_FOUND)
    except ProgramVersionConflictError:
        return JSONResponse(
            {"error": "version conflict"}, status_code=HTTP_STATUS_CONFLICT
        )
    except ValueError as e:
        return JSONResponse({"error": str(e)}, status_code=HTTP_STATUS_BAD_REQUEST)
    except RuntimeError as e:
        return JSONResponse(
            {"error": str(e)}, status_code=HTTP_STATUS_INTERNAL_ERROR
        )
    except Exception:
        return JSONResponse(
            {"error": "database error"}, status_code=HTTP_STATUS_INTERNAL_ERROR
        )
    return JSONResponse(updated, status_code=HTTP_STATUS_OK)


async def delete_program(request: Request) -> JSONResponse:
    program_id = request.path_params["id"]
    try:
        pool = await get_pool()
        await delete_program_db(pool, program_id)
    except ProgramNotFoundError:
        return JSONResponse({"error": "not found"}, status_code=HTTP_STATUS_NOT_FOUND)
    except RuntimeError as e:
        return JSONResponse(
            {"error": str(e)}, status_code=HTTP_STATUS_INTERNAL_ERROR
        )
    except Exception:
        return JSONResponse(
            {"error": "database error"}, status_code=HTTP_STATUS_INTERNAL_ERROR
        )
    return JSONResponse({"id": program_id}, status_code=HTTP_STATUS_OK)
