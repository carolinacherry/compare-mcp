from __future__ import annotations

import copy
import json
import os
import re
from pathlib import Path
from typing import Any

DEFAULT_CONFIG_PATH = Path.home() / ".compare" / "config.json"

DEFAULT_CONFIG: dict[str, Any] = {
    "providers": {
        "claude": {
            "enabled": True,
            "type": "anthropic",
            "api_key": "$ANTHROPIC_API_KEY",
            "model": "claude-opus-4-5",
        },
        "openai": {
            "enabled": True,
            "type": "openai_compat",
            "api_key": "$OPENAI_API_KEY",
            "model": "gpt-4o",
            "base_url": "https://api.openai.com/v1",
        },
        "kimi": {
            "enabled": False,
            "type": "openai_compat",
            "api_key": "$MOONSHOT_API_KEY",
            "model": "moonshot-v1-auto",
            "base_url": "https://api.moonshot.ai/v1",
        },
        "minimax": {
            "enabled": False,
            "type": "openai_compat",
            "api_key": "$MINIMAX_API_KEY",
            "model": "MiniMax-Text-01",
            "base_url": "https://api.minimax.io/v1",
        },
        "ollama": {
            "enabled": False,
            "type": "cli",
            "cli_command": "ollama",
            "cli_args": ["run", "codellama"],
            "cli_parser": "text",
        },
    },
    "compare": {
        "max_tokens": 2048,
        "timeout_seconds": 120,
        "db_path": "~/.compare/todos.sqlite",
        "dedup_threshold": 0.65,
        "max_file_lines": 1000,
    },
}

_ENV_VAR_RE = re.compile(r"^\$([A-Z_][A-Z0-9_]*)$")


def _expand_env_vars(value: Any) -> Any:
    if isinstance(value, str):
        m = _ENV_VAR_RE.match(value)
        if m:
            return os.environ.get(m.group(1), "")
        return value
    if isinstance(value, dict):
        return {k: _expand_env_vars(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_expand_env_vars(v) for v in value]
    return value


def load_config(path: Path | None = None) -> dict[str, Any]:
    config_path = path or DEFAULT_CONFIG_PATH

    if config_path.exists():
        with open(config_path) as f:
            raw = json.load(f)
    else:
        raw = {}

    defaults = copy.deepcopy(DEFAULT_CONFIG)
    config = defaults
    if "providers" in raw:
        config["providers"] = raw["providers"]
    if "compare" in raw:
        config["compare"] = {**defaults["compare"], **raw["compare"]}

    config["providers"] = _expand_env_vars(config["providers"])
    config["compare"]["db_path"] = str(Path(config["compare"]["db_path"]).expanduser())

    return config


def get_enabled_providers(config: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        name: prov
        for name, prov in config["providers"].items()
        if prov.get("enabled", False)
    }


def get_provider_summary(config: dict[str, Any]) -> dict[str, Any]:
    providers = {}
    for name, prov in config["providers"].items():
        providers[name] = {
            "enabled": prov.get("enabled", False),
            "type": prov.get("type", "unknown"),
            "model": prov.get("model", prov.get("cli_command", "unknown")),
        }
    enabled_count = sum(1 for p in providers.values() if p["enabled"])
    return {"providers": providers, "enabled_count": enabled_count}
