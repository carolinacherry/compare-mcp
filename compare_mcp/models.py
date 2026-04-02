from __future__ import annotations

import asyncio
import json
import logging
import sys
from typing import Any

logger = logging.getLogger("compare_mcp.models")

REVIEW_PROMPT = """You are a senior engineer doing a focused code review.
Issue reported: {issue}

Code:
```
{code}
```

Return a JSON object with exactly these keys:
- findings: list of {{"title": str, "description": str, "severity": "high"|"medium"|"low"}}
- dead_code: list of str (variable/function names that are assigned but never used)
- suggestions: list of str (concrete improvement ideas beyond the reported issue)

Return ONLY valid JSON. No markdown fences, no preamble, no explanation."""


def _build_prompt(code: str, issue: str) -> str:
    # Empty issue = raw prompt (used by debate for critique/synthesis)
    if not issue:
        return code
    return REVIEW_PROMPT.format(issue=issue, code=code)


def _parse_json_response(text: str) -> dict[str, Any]:
    """Extract JSON from a response that might have markdown fences or preamble."""
    text = text.strip()
    if text.startswith("```"):
        lines = text.split("\n")
        lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        text = "\n".join(lines).strip()

    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # Find a balanced JSON object in the text
    start = text.find("{")
    if start != -1:
        depth = 0
        for i in range(start, len(text)):
            if text[i] == "{":
                depth += 1
            elif text[i] == "}":
                depth -= 1
                if depth == 0:
                    try:
                        return json.loads(text[start : i + 1])
                    except json.JSONDecodeError:
                        break

    return {"findings": [], "dead_code": [], "suggestions": [], "_parse_error": text[:500]}


async def query_anthropic(
    provider_config: dict[str, Any],
    code: str,
    issue: str,
    max_tokens: int,
    timeout: int,
) -> dict[str, Any]:
    try:
        import anthropic
    except ImportError:
        return {"_error": "anthropic package not installed"}

    api_key = provider_config.get("api_key")
    if not api_key:
        return {"_error": "missing api_key in provider config"}

    client = anthropic.AsyncAnthropic(api_key=api_key)
    prompt = _build_prompt(code, issue)

    try:
        response = await asyncio.wait_for(
            client.messages.create(
                model=provider_config["model"],
                max_tokens=max_tokens,
                messages=[{"role": "user", "content": prompt}],
            ),
            timeout=timeout,
        )
        return _parse_json_response(response.content[0].text)
    except asyncio.TimeoutError:
        return {"_error": f"timeout after {timeout}s"}
    except Exception as e:
        return {"_error": str(e)}


async def query_openai_compat(
    provider_config: dict[str, Any],
    code: str,
    issue: str,
    max_tokens: int,
    timeout: int,
) -> dict[str, Any]:
    try:
        import openai
    except ImportError:
        return {"_error": "openai package not installed"}

    api_key = provider_config.get("api_key")
    if not api_key:
        return {"_error": "missing api_key in provider config"}

    client = openai.AsyncOpenAI(
        api_key=api_key,
        base_url=provider_config.get("base_url", "https://api.openai.com/v1"),
    )
    prompt = _build_prompt(code, issue)

    try:
        response = await asyncio.wait_for(
            client.chat.completions.create(
                model=provider_config["model"],
                max_tokens=max_tokens,
                messages=[{"role": "user", "content": prompt}],
            ),
            timeout=timeout,
        )
        return _parse_json_response(response.choices[0].message.content or "")
    except asyncio.TimeoutError:
        return {"_error": f"timeout after {timeout}s"}
    except Exception as e:
        return {"_error": str(e)}


async def query_cli(
    provider_config: dict[str, Any],
    code: str,
    issue: str,
    _max_tokens: int,
    timeout: int,
) -> dict[str, Any]:
    cmd = provider_config.get("cli_command")
    if not cmd:
        return {"_error": "missing cli_command in provider config"}

    args = provider_config.get("cli_args", [])
    prompt = _build_prompt(code, issue)

    try:
        proc = await asyncio.create_subprocess_exec(
            cmd, *args,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await asyncio.wait_for(
            proc.communicate(input=prompt.encode()),
            timeout=timeout,
        )
    except FileNotFoundError:
        return {"_error": f"command not found: {cmd}"}
    except asyncio.TimeoutError:
        proc.kill()
        await proc.wait()
        return {"_error": f"CLI timeout after {timeout}s"}
    except Exception as e:
        return {"_error": str(e)}

    if proc.returncode != 0:
        return {"_error": f"CLI exit {proc.returncode}: {stderr.decode()[:200]}"}

    return _parse_json_response(stdout.decode().strip())


ADAPTERS = {
    "anthropic": query_anthropic,
    "openai_compat": query_openai_compat,
    "cli": query_cli,
}


async def query_provider(
    name: str,
    provider_config: dict[str, Any],
    code: str,
    issue: str,
    max_tokens: int = 2048,
    timeout: int = 60,
) -> tuple[str, dict[str, Any]]:
    ptype = provider_config.get("type", "openai_compat")
    adapter = ADAPTERS.get(ptype)
    if not adapter:
        return name, {"_error": f"unknown provider type: {ptype}"}

    logger.info(f"Querying {name} ({ptype}/{provider_config.get('model', '?')})")
    result = await adapter(provider_config, code, issue, max_tokens, timeout)

    if "_error" in result:
        logger.warning(f"{name} error: {result['_error']}")
        print(f"[compare-mcp] {name}: {result['_error']}", file=sys.stderr)

    return name, result


async def query_all(
    providers: dict[str, dict[str, Any]],
    code: str,
    issue: str,
    max_tokens: int = 2048,
    timeout: int = 60,
) -> dict[str, dict[str, Any]]:
    tasks = [
        query_provider(name, config, code, issue, max_tokens, timeout)
        for name, config in providers.items()
    ]
    results = await asyncio.gather(*tasks)

    successful = {}
    errors = {}
    for name, result in results:
        if "_error" not in result:
            successful[name] = result
        else:
            errors[name] = result["_error"]

    if not successful and errors:
        return {"_all_failed": True, "_errors": errors}

    return successful
