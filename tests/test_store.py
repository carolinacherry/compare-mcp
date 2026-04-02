"""Tests for SQLite todo store."""

import pytest
from compare_mcp.store import write_todos, get_todos, update_todo


@pytest.fixture
def db_path(tmp_path):
    return str(tmp_path / "test_todos.sqlite")


async def test_write_and_read_todos(db_path):
    items = [
        {"title": "Fix memory leak", "description": "In the main loop", "severity": "high", "source_providers": ["claude", "openai"]},
        {"title": "Remove dead code", "description": "prevVisible unused", "severity": "low", "source_providers": ["openai"]},
    ]
    inserted = await write_todos(items, db_path, code_file="main.py")
    assert len(inserted) == 2
    assert inserted[0]["id"] is not None
    assert inserted[0]["status"] == "pending"

    grouped = await get_todos(db_path)
    assert len(grouped["pending"]) == 2
    assert len(grouped["done"]) == 0
    # Should be ordered by severity (high first)
    assert grouped["pending"][0]["severity"] == "high"


async def test_filter_by_code_file(db_path):
    await write_todos(
        [{"title": "Bug A", "severity": "high", "source_providers": []}],
        db_path,
        code_file="a.py",
    )
    await write_todos(
        [{"title": "Bug B", "severity": "high", "source_providers": []}],
        db_path,
        code_file="b.py",
    )

    all_todos = await get_todos(db_path)
    assert len(all_todos["pending"]) == 2

    filtered = await get_todos(db_path, code_file="a.py")
    assert len(filtered["pending"]) == 1
    assert filtered["pending"][0]["title"] == "Bug A"


async def test_update_todo_status(db_path):
    await write_todos(
        [{"title": "Fix it", "severity": "medium", "source_providers": ["claude"]}],
        db_path,
    )
    result = await update_todo(1, "done", db_path)
    assert result["status"] == "done"

    grouped = await get_todos(db_path)
    assert len(grouped["done"]) == 1
    assert len(grouped["pending"]) == 0


async def test_update_nonexistent_todo(db_path):
    result = await update_todo(999, "done", db_path)
    assert "error" in result


async def test_update_invalid_status(db_path):
    result = await update_todo(1, "invalid", db_path)
    assert "error" in result
