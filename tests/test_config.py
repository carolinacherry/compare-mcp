"""Tests for config loading and env var expansion."""

import json
import os

from compare_mcp.config import load_config, get_enabled_providers, get_provider_summary, _expand_env_vars


def test_expand_env_vars_with_set_var():
    os.environ["TEST_COMPARE_KEY"] = "sk-test-123"
    assert _expand_env_vars("$TEST_COMPARE_KEY") == "sk-test-123"
    del os.environ["TEST_COMPARE_KEY"]


def test_expand_env_vars_with_unset_var():
    result = _expand_env_vars("$NONEXISTENT_COMPARE_VAR_XYZ")
    assert result == ""


def test_expand_env_vars_non_var_string():
    assert _expand_env_vars("just a string") == "just a string"


def test_expand_env_vars_nested_dict():
    os.environ["TEST_CMP_NESTED"] = "secret"
    result = _expand_env_vars({"key": "$TEST_CMP_NESTED", "other": "plain"})
    assert result == {"key": "secret", "other": "plain"}
    del os.environ["TEST_CMP_NESTED"]


def test_load_config_defaults(tmp_path):
    config = load_config(tmp_path / "nonexistent.json")
    assert "providers" in config
    assert "compare" in config
    assert "claude" in config["providers"]
    assert "openai" in config["providers"]


def test_load_config_from_file(tmp_path):
    cfg = {
        "providers": {
            "test_provider": {
                "enabled": True,
                "type": "openai_compat",
                "api_key": "raw-key",
                "model": "test-model",
                "base_url": "http://localhost:1234/v1",
            }
        },
        "compare": {"timeout_seconds": 120},
    }
    config_file = tmp_path / "config.json"
    config_file.write_text(json.dumps(cfg))

    config = load_config(config_file)
    assert "test_provider" in config["providers"]
    assert config["providers"]["test_provider"]["api_key"] == "raw-key"
    assert config["compare"]["timeout_seconds"] == 120
    # Defaults should fill in missing compare keys
    assert "max_tokens" in config["compare"]


def test_get_enabled_providers():
    config = {
        "providers": {
            "a": {"enabled": True, "type": "anthropic"},
            "b": {"enabled": False, "type": "openai_compat"},
            "c": {"enabled": True, "type": "cli"},
        }
    }
    enabled = get_enabled_providers(config)
    assert set(enabled.keys()) == {"a", "c"}


def test_get_provider_summary_no_api_keys():
    config = {
        "providers": {
            "claude": {
                "enabled": True,
                "type": "anthropic",
                "api_key": "sk-secret-key",
                "model": "claude-opus-4-5",
            }
        }
    }
    summary = get_provider_summary(config)
    assert "api_key" not in str(summary["providers"]["claude"])
    assert summary["providers"]["claude"]["model"] == "claude-opus-4-5"
    assert summary["enabled_count"] == 1
