from __future__ import annotations

import json
import logging
from typing import Any

import aiosqlite

logger = logging.getLogger("compare_mcp.store")

SCHEMA = """
CREATE TABLE IF NOT EXISTS todos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,
    description TEXT,
    severity TEXT CHECK(severity IN ('high', 'medium', 'low')),
    source_providers TEXT,
    code_file TEXT,
    status TEXT DEFAULT 'pending' CHECK(status IN ('pending', 'in_progress', 'done')),
    created_at TEXT DEFAULT (datetime('now'))
);
"""

_initialized: set[str] = set()


async def _get_db(db_path: str) -> aiosqlite.Connection:
    db = await aiosqlite.connect(db_path)
    if db_path not in _initialized:
        await db.execute(SCHEMA)
        await db.commit()
        _initialized.add(db_path)
    return db


async def write_todos(
    items: list[dict[str, Any]],
    db_path: str,
    code_file: str | None = None,
) -> list[dict[str, Any]]:
    try:
        db = await _get_db(db_path)
    except Exception as e:
        logger.warning(f"SQLite open failed ({db_path}): {e}")
        return [{**item, "id": i + 1, "status": "pending"} for i, item in enumerate(items)]

    try:
        inserted = []
        for item in items:
            cursor = await db.execute(
                "INSERT INTO todos (title, description, severity, source_providers, code_file) "
                "VALUES (?, ?, ?, ?, ?)",
                (
                    item.get("title", ""),
                    item.get("description", ""),
                    item.get("severity", "medium"),
                    json.dumps(item.get("source_providers", [])),
                    code_file,
                ),
            )
            inserted.append({
                "id": cursor.lastrowid,
                "title": item.get("title", ""),
                "severity": item.get("severity", "medium"),
                "source_providers": item.get("source_providers", []),
                "status": "pending",
            })
        await db.commit()
        return inserted
    except Exception as e:
        logger.warning(f"SQLite write failed: {e}")
        return [{**item, "id": i + 1, "status": "pending"} for i, item in enumerate(items)]
    finally:
        await db.close()


async def get_todos(
    db_path: str,
    code_file: str | None = None,
) -> dict[str, list[dict[str, Any]]]:
    try:
        db = await _get_db(db_path)
    except Exception as e:
        logger.warning(f"SQLite open failed: {e}")
        return {"pending": [], "in_progress": [], "done": []}

    try:
        query = "SELECT id, title, description, severity, source_providers, code_file, status, created_at FROM todos"
        params: list[Any] = []
        if code_file:
            query += " WHERE code_file = ?"
            params.append(code_file)
        query += " ORDER BY CASE severity WHEN 'high' THEN 0 WHEN 'medium' THEN 1 WHEN 'low' THEN 2 END"

        cursor = await db.execute(query, params)
        rows = await cursor.fetchall()

        grouped: dict[str, list[dict[str, Any]]] = {"pending": [], "in_progress": [], "done": []}
        for row in rows:
            todo = {
                "id": row[0],
                "title": row[1],
                "description": row[2],
                "severity": row[3],
                "source_providers": json.loads(row[4]) if row[4] else [],
                "code_file": row[5],
                "status": row[6],
                "created_at": row[7],
            }
            grouped.get(todo["status"], grouped["pending"]).append(todo)

        return grouped
    finally:
        await db.close()


async def update_todo(
    todo_id: int,
    status: str,
    db_path: str,
) -> dict[str, Any]:
    if status not in ("pending", "in_progress", "done"):
        return {"error": f"invalid status: {status}. Must be pending, in_progress, or done"}

    try:
        db = await _get_db(db_path)
    except Exception as e:
        return {"error": f"SQLite open failed: {e}"}

    try:
        cursor = await db.execute(
            "UPDATE todos SET status = ? WHERE id = ?", (status, todo_id)
        )
        await db.commit()

        if cursor.rowcount == 0:
            return {"error": f"todo {todo_id} not found"}

        cursor = await db.execute(
            "SELECT id, title, severity, status FROM todos WHERE id = ?", (todo_id,)
        )
        row = await cursor.fetchone()
        return {"id": row[0], "title": row[1], "severity": row[2], "status": row[3]}
    finally:
        await db.close()
