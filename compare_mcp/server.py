from __future__ import annotations

import logging
import sys
from typing import Any

from mcp.server.fastmcp import FastMCP

from .config import load_config, get_enabled_providers, get_provider_summary
from .diff import compute_diff
from .debate import run_debate
from .models import query_all
from .store import write_todos, get_todos, update_todo

logging.basicConfig(level=logging.INFO, stream=sys.stderr)

mcp = FastMCP("compare-mcp")


@mcp.tool()
async def compare_models() -> dict[str, Any]:
    """List all configured providers with their enabled status, type, and model. Does not expose API keys."""
    return get_provider_summary(load_config())


@mcp.tool()
async def compare_run(
    code: str,
    issue: str,
    providers: list[str] | None = None,
) -> dict[str, Any]:
    """Fan out a code review to all enabled providers (or a subset) in parallel.

    Args:
        code: The source code to review.
        issue: Description of the bug or task.
        providers: Optional list of provider names to query. Defaults to all enabled.
    """
    config = load_config()
    enabled = get_enabled_providers(config)

    if providers:
        enabled = {k: v for k, v in enabled.items() if k in providers}

    if len(enabled) < 2:
        return {
            "error": "compare requires at least 2 enabled providers",
            "enabled": list(enabled.keys()),
            "hint": "Enable more providers in ~/.compare/config.json",
        }

    max_tokens = config["compare"]["max_tokens"]
    timeout = config["compare"]["timeout_seconds"]
    results = await query_all(enabled, code, issue, max_tokens, timeout)

    if len(results) < 2:
        return {
            "error": "compare requires at least 2 successful provider responses",
            "succeeded": list(results.keys()),
            "hint": "Check provider API keys and network connectivity",
        }

    return results


@mcp.tool()
async def compare_diff(responses: dict[str, dict[str, Any]]) -> dict[str, Any]:
    """Diff provider responses: extract unique vs shared insights using fuzzy matching.

    Args:
        responses: Output from compare_run.
    """
    config = load_config()
    return compute_diff(responses, threshold=config["compare"]["dedup_threshold"])


@mcp.tool()
async def compare_debate(
    responses: dict[str, dict[str, Any]],
    rounds: int = 1,
) -> dict[str, Any]:
    """Run a debate round where each model critiques others' findings, then synthesize.

    Args:
        responses: Output from compare_run.
        rounds: Number of debate rounds (default 1).
    """
    config = load_config()
    enabled = get_enabled_providers(config)
    return await run_debate(
        responses,
        enabled,
        max_tokens=config["compare"]["max_tokens"],
        timeout=config["compare"]["timeout_seconds"],
        rounds=rounds,
    )


@mcp.tool()
async def compare_todos(
    findings: list[dict[str, Any]],
    code_file: str | None = None,
) -> dict[str, Any]:
    """Write ranked findings to the SQLite todo store.

    Args:
        findings: List of {title, description, severity, source_providers}.
        code_file: Optional file path the findings relate to.
    """
    db_path = load_config()["compare"]["db_path"]
    return {"todos": await write_todos(findings, db_path, code_file), "db_path": db_path}


@mcp.tool()
async def compare_status(code_file: str | None = None) -> dict[str, Any]:
    """Return current todos grouped by status (pending, in_progress, done).

    Args:
        code_file: Optional filter by file path.
    """
    db_path = load_config()["compare"]["db_path"]
    return {**await get_todos(db_path, code_file), "db_path": db_path}


@mcp.tool()
async def compare_todo_update(todo_id: int, status: str) -> dict[str, Any]:
    """Update a todo's status.

    Args:
        todo_id: The todo ID to update.
        status: New status — one of 'pending', 'in_progress', 'done'.
    """
    return await update_todo(todo_id, status, load_config()["compare"]["db_path"])


def main():
    mcp.run()


if __name__ == "__main__":
    main()
