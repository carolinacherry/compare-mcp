from __future__ import annotations

from typing import Any

from rapidfuzz import fuzz

VALID_SEVERITIES = {"high", "medium", "low"}


def _normalize(text: str) -> str:
    return text.strip().lower()


def _normalize_severity(severity: str) -> str:
    s = severity.strip().lower() if severity else "medium"
    return s if s in VALID_SEVERITIES else "medium"


def _are_similar(a: str, b: str, threshold: float) -> bool:
    a_norm, b_norm = _normalize(a), _normalize(b)
    if not a_norm or not b_norm:
        return False
    return fuzz.token_sort_ratio(a_norm, b_norm) / 100.0 >= threshold


def compute_diff(responses: dict[str, dict[str, Any]], threshold: float = 0.75) -> dict[str, Any]:
    """Extract unique vs shared insights across provider responses.

    Args:
        responses: output from compare_run — {provider_name: {findings, dead_code, suggestions}}
        threshold: similarity threshold (0-1). Higher = stricter matching.
    """
    all_findings: list[dict[str, Any]] = []
    for provider, resp in responses.items():
        for f in resp.get("findings", []):
            title = f.get("title", "")
            if not title or not title.strip():
                continue
            all_findings.append({
                "title": title,
                "description": f.get("description", ""),
                "severity": _normalize_severity(f.get("severity", "medium")),
                "provider": provider,
            })

    # Group similar findings from DIFFERENT providers only
    groups: list[list[dict[str, Any]]] = []
    used = [False] * len(all_findings)

    for i, fi in enumerate(all_findings):
        if used[i]:
            continue
        group = [fi]
        used[i] = True
        for j in range(i + 1, len(all_findings)):
            if used[j]:
                continue
            # Only group findings from different providers
            if all_findings[j]["provider"] == fi["provider"]:
                continue
            if _are_similar(fi["title"], all_findings[j]["title"], threshold):
                group.append(all_findings[j])
                used[j] = True
        groups.append(group)

    # Classify as shared (2+ providers) or unique (1 provider)
    shared = []
    unique: dict[str, list[dict[str, Any]]] = {p: [] for p in responses}

    for group in groups:
        providers_in_group = list({f["provider"] for f in group})
        best = max(group, key=lambda f: len(f.get("description", "")))
        entry = {
            "title": best["title"],
            "description": best["description"],
            "severity": best["severity"],
        }

        if len(providers_in_group) >= 2:
            shared.append({**entry, "providers": providers_in_group})
        else:
            unique[providers_in_group[0]].append(entry)

    severity_order = {"high": 0, "medium": 1, "low": 2}

    recommended = []
    for item in sorted(shared, key=lambda x: severity_order.get(x["severity"], 1)):
        recommended.append({
            "title": item["title"],
            "description": item["description"],
            "severity": item["severity"],
            "source_providers": item["providers"],
        })
    for provider in sorted(unique.keys()):
        for item in sorted(unique[provider], key=lambda x: severity_order.get(x["severity"], 1)):
            recommended.append({
                "title": item["title"],
                "description": item["description"],
                "severity": item["severity"],
                "source_providers": [provider],
            })

    unique = {k: v for k, v in unique.items() if v}

    total_unique_titles = len(groups)
    shared_count = len(shared)
    agreement_rate = shared_count / total_unique_titles if total_unique_titles > 0 else 0.0

    return {
        "shared": shared,
        "unique": unique,
        "recommended": recommended,
        "summary": {
            "total_findings": sum(len(r.get("findings", [])) for r in responses.values()),
            "unique_finding_groups": total_unique_titles,
            "agreement_rate": round(agreement_rate, 3),
            "provider_count": len(responses),
        },
    }
