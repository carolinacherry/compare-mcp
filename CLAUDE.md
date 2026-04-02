# compare-mcp

MCP server for multi-model code review inside Claude Code CLI.

## Architecture

- `compare_mcp/config.py` — loads ~/.compare/config.json, expands $ENV_VAR references
- `compare_mcp/models.py` — provider adapters (anthropic, openai_compat, cli subprocess)
- `compare_mcp/diff.py` — rapidfuzz-based insight deduplication
- `compare_mcp/debate.py` — cross-model critique + synthesis
- `compare_mcp/store.py` — aiosqlite todo CRUD
- `compare_mcp/server.py` — FastMCP server, 7 tools
- `.claude/skills/compare/SKILL.md` — /compare slash command

## Running

```bash
python -m compare_mcp          # start MCP server
pytest                          # run tests
ruff check .                    # lint
```

## Key decisions

- `mcp` package (official MCP Python SDK), not the `fastmcp` PyPI package
- dedup_threshold is configurable (default 0.75) — tune per use case
- debate capped at 4 providers to limit API call explosion
- compare_todos accepts either diff's `recommended` or debate's `refined_findings`
- compare_todo_update exists so subagents can mark todos done after fixing
