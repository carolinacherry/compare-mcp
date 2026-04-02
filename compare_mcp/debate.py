from __future__ import annotations

import asyncio
import json
import logging
import sys
from typing import Any

logger = logging.getLogger("compare_mcp.debate")

CRITIQUE_PROMPT = """You are a senior engineer reviewing another model's code review findings.

Here are findings from another model:
{findings_json}

Which do you agree with, disagree with, or want to add nuance to?

Return ONLY valid JSON with exactly these keys:
- agreed: list of finding titles you agree with
- disputed: list of {{"title": str, "reason": str}} for findings you disagree with
- additions: list of {{"title": str, "description": str, "severity": "high"|"medium"|"low"}} for new findings

Return ONLY valid JSON. No markdown fences, no preamble."""

SYNTHESIS_PROMPT = """You are a senior engineer producing the final, merged code review.

Original findings from all models:
{all_findings_json}

Cross-critique results:
{critiques_json}

Produce a final merged findings list that:
1. Keeps findings that multiple models agreed on
2. Removes findings that were convincingly disputed
3. Incorporates valuable additions from the critique round
4. Removes duplicates

Return ONLY valid JSON: a list of {{"title": str, "description": str, "severity": "high"|"medium"|"low", "source_providers": [str]}}
No markdown fences, no preamble."""

# Cap providers in debate to limit API calls (N providers = N*(N-1) + 1 calls)
MAX_DEBATE_PROVIDERS = 4

EMPTY_CRITIQUE: dict[str, list] = {"agreed": [], "disputed": [], "additions": []}


def _validate_critique(result: dict[str, Any]) -> dict[str, Any]:
    return {key: (result[key] if isinstance(result.get(key), list) else []) for key in ("agreed", "disputed", "additions")}


async def run_debate(
    responses: dict[str, dict[str, Any]],
    providers: dict[str, dict[str, Any]],
    max_tokens: int = 2048,
    timeout: int = 60,
    rounds: int = 1,
) -> dict[str, Any]:
    """Cross-critique: each model reviews others' findings, then one synthesizes."""
    from .models import ADAPTERS

    provider_names = list(responses.keys())[:MAX_DEBATE_PROVIDERS]
    if len(provider_names) < 2:
        return {"error": "debate requires at least 2 provider responses"}

    async def critique_task(
        critic_name: str, target_name: str
    ) -> tuple[str, str, dict[str, Any]]:
        critic_config = providers.get(critic_name)
        if not critic_config:
            return critic_name, target_name, EMPTY_CRITIQUE.copy()

        target_findings = responses[target_name].get("findings", [])
        ptype = critic_config.get("type", "openai_compat")
        adapter = ADAPTERS.get(ptype)
        if not adapter:
            return critic_name, target_name, EMPTY_CRITIQUE.copy()

        prompt_text = CRITIQUE_PROMPT.format(findings_json=json.dumps(target_findings, indent=2))

        try:
            result = await adapter(critic_config, prompt_text, "", max_tokens, timeout)
            if "_error" in result:
                return critic_name, target_name, EMPTY_CRITIQUE.copy()
            if "agreed" in result or "disputed" in result or "additions" in result:
                return critic_name, target_name, _validate_critique(result)
            logger.warning(f"Critique {critic_name}->{target_name}: unexpected response shape")
            return critic_name, target_name, EMPTY_CRITIQUE.copy()
        except Exception as e:
            logger.warning(f"Critique {critic_name}->{target_name} failed: {e}")
            return critic_name, target_name, EMPTY_CRITIQUE.copy()

    # Fan out all cross-critiques in parallel
    tasks = [
        critique_task(critic, target)
        for critic in provider_names
        for target in provider_names
        if critic != target
    ]
    critique_results = await asyncio.gather(*tasks)

    # Aggregate critiques per critic
    critiques: dict[str, dict[str, Any]] = {}
    for critic, target, result in critique_results:
        if critic not in critiques:
            critiques[critic] = {"agreed": [], "disputed": [], "additions": []}
        critiques[critic]["agreed"].extend(result.get("agreed", []))
        critiques[critic]["disputed"].extend(result.get("disputed", []))
        critiques[critic]["additions"].extend(result.get("additions", []))

    # Consensus = provider whose findings were most agreed with by others
    agreed_with_counts: dict[str, int] = {name: 0 for name in provider_names}
    for _critic, target, result in critique_results:
        agreed_with_counts[target] += len(result.get("agreed", []))

    consensus_provider = (
        max(agreed_with_counts, key=agreed_with_counts.get)
        if any(v > 0 for v in agreed_with_counts.values())
        else provider_names[0]
    )

    # Synthesis: consensus provider merges everything
    synth_config = providers.get(consensus_provider, next(iter(providers.values())))
    adapter = ADAPTERS.get(synth_config.get("type", "openai_compat"))

    refined_findings: list[dict[str, Any]] = []
    if adapter:
        synth_prompt = SYNTHESIS_PROMPT.format(
            all_findings_json=json.dumps(
                {name: resp.get("findings", []) for name, resp in responses.items()},
                indent=2,
            ),
            critiques_json=json.dumps(critiques, indent=2),
        )
        try:
            synth_result = await adapter(synth_config, synth_prompt, "", max_tokens, timeout)
            if isinstance(synth_result, list):
                refined_findings = synth_result
            elif isinstance(synth_result, dict) and "_error" not in synth_result:
                for key in ("findings", "refined_findings", "recommended"):
                    if key in synth_result and isinstance(synth_result[key], list):
                        refined_findings = synth_result[key]
                        break
                if not refined_findings:
                    logger.warning(f"Synthesis returned unexpected shape: {list(synth_result.keys())}")
        except Exception as e:
            logger.warning(f"Synthesis failed: {e}")
            print(f"[compare-mcp] debate synthesis failed: {e}", file=sys.stderr)

    return {
        "critiques": critiques,
        "refined_findings": refined_findings,
        "consensus_provider": consensus_provider,
        "debate_api_calls": len(tasks) + 1,
    }
