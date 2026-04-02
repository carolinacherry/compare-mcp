from compare_mcp.diff import compute_diff


def test_identical_findings_are_shared():
    responses = {
        "claude": {
            "findings": [
                {"title": "Memory leak in loop", "description": "The loop allocates without freeing", "severity": "high"}
            ],
        },
        "openai": {
            "findings": [
                {"title": "Memory leak in the loop", "description": "Loop body leaks memory", "severity": "high"}
            ],
        },
    }
    result = compute_diff(responses, threshold=0.75)
    assert len(result["shared"]) == 1
    assert set(result["shared"][0]["providers"]) == {"claude", "openai"}
    assert result["summary"]["agreement_rate"] == 1.0


def test_different_findings_are_unique():
    responses = {
        "claude": {
            "findings": [
                {"title": "SQL injection in query builder", "description": "User input not sanitized", "severity": "high"}
            ],
        },
        "openai": {
            "findings": [
                {"title": "Missing null check on response", "description": "API response can be null", "severity": "medium"}
            ],
        },
    }
    result = compute_diff(responses, threshold=0.75)
    assert len(result["shared"]) == 0
    assert len(result["unique"].get("claude", [])) == 1
    assert len(result["unique"].get("openai", [])) == 1
    assert result["summary"]["agreement_rate"] == 0.0


def test_recommended_ordering():
    responses = {
        "a": {
            "findings": [
                {"title": "Same bug", "description": "d", "severity": "medium"},
                {"title": "Only A finds this", "description": "d", "severity": "low"},
            ],
        },
        "b": {
            "findings": [
                {"title": "Same bug here too", "description": "d", "severity": "medium"},
                {"title": "Only B finds this", "description": "d", "severity": "high"},
            ],
        },
    }
    result = compute_diff(responses, threshold=0.75)
    rec = result["recommended"]
    assert len(rec) >= 2
    shared_titles = [r["title"] for r in result["shared"]]
    assert rec[0]["title"] in shared_titles or len(rec[0]["source_providers"]) >= 2


def test_empty_findings():
    responses = {
        "a": {"findings": []},
        "b": {"findings": []},
    }
    result = compute_diff(responses)
    assert result["shared"] == []
    assert result["recommended"] == []
    assert result["summary"]["agreement_rate"] == 0.0


def test_threshold_tuning():
    responses = {
        "a": {
            "findings": [
                {"title": "Possible memory leak", "description": "d", "severity": "high"}
            ],
        },
        "b": {
            "findings": [
                {"title": "Memory leak detected", "description": "d", "severity": "high"}
            ],
        },
    }
    low_threshold = compute_diff(responses, threshold=0.5)
    high_threshold = compute_diff(responses, threshold=0.95)
    assert len(low_threshold["shared"]) >= len(high_threshold["shared"])


def test_same_provider_findings_not_grouped():
    """Bug #21: similar titles from same provider should NOT merge."""
    responses = {
        "a": {
            "findings": [
                {"title": "Memory leak in loop", "description": "loop issue", "severity": "high"},
                {"title": "Memory leak in parser", "description": "parser issue", "severity": "high"},
            ],
        },
        "b": {
            "findings": [
                {"title": "Null pointer dereference", "description": "unrelated", "severity": "medium"},
            ],
        },
    }
    result = compute_diff(responses, threshold=0.5)
    # Both of provider a's findings should survive as separate entries
    a_unique = result["unique"].get("a", [])
    assert len(a_unique) == 2


def test_empty_title_findings_skipped():
    """Bug #22: empty titles should not match each other."""
    responses = {
        "a": {
            "findings": [
                {"title": "", "description": "something from a", "severity": "high"},
                {"title": "Real finding", "description": "d", "severity": "medium"},
            ],
        },
        "b": {
            "findings": [
                {"title": "", "description": "something from b", "severity": "high"},
            ],
        },
    }
    result = compute_diff(responses)
    # Empty titles should be dropped entirely
    total = result["summary"]["unique_finding_groups"]
    assert total == 1  # only "Real finding"


def test_severity_normalization():
    """Bug #23: unknown/mixed-case severity should normalize to valid values."""
    responses = {
        "a": {
            "findings": [
                {"title": "Bug A", "description": "d", "severity": "HIGH"},
                {"title": "Bug B", "description": "d", "severity": "critical"},
                {"title": "Bug C", "description": "d", "severity": ""},
            ],
        },
        "b": {"findings": []},
    }
    result = compute_diff(responses)
    a_findings = result["unique"].get("a", [])
    severities = [f["severity"] for f in a_findings]
    assert "high" in severities  # HIGH -> high
    assert "medium" in severities  # critical -> medium (unknown)
    assert all(s in ("high", "medium", "low") for s in severities)
