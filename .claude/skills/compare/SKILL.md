---
name: compare
description: Multi-model code review. Fan out a bug or task to multiple LLMs, diff
  their findings, optionally debate, then dispatch subagents to fix in parallel.
  Use when the user types /compare or asks to compare models on a code issue.
---

# /compare skill

## Trigger

User types: `/compare <issue description> [--debate] [--providers claude,openai]`
Or naturally: "compare models on this bug", "get a second opinion from multiple models"

## Workflow

### Step 1 — discover
Call `compare_models` to show the user which providers are enabled.
If fewer than 2 are enabled, stop and tell the user:
> Enable at least 2 providers in `~/.compare/config.json`. Run `compare_models` to check.

### Step 2 — read code
Use the Read tool to load the relevant file(s). If the user didn't specify a file,
use Glob + Grep to find the most relevant file for the issue description.

Respect `max_file_lines` from config (default 1000). If the file is larger, ask the
user to specify a line range or pass the most relevant section.

### Step 3 — dispatch
Call `compare_run` with the file contents and issue description.
If `--providers` was specified, pass the provider list.
While waiting, tell the user: "Querying [provider1], [provider2]... (parallel)"

### Step 4 — diff
Call `compare_diff` with the responses.
Display a findings table:

```
Finding                   | Providers        | Severity
--------------------------|------------------|----------
Memory leak in tile loop  | claude, openai   | high
Dead code: prevVisible    | openai           | medium
```

Show: "Models agreed on X% of findings."

### Step 5 — debate (if `--debate` flag or user asks)
Call `compare_debate` with the responses.
Display: "Debate complete. [N] findings disputed, [N] additions. [N] API calls made."
Use `refined_findings` instead of `recommended` for the todos step.

### Step 6 — todos
Call `compare_todos` with either the diff's `recommended` list or debate's `refined_findings`,
plus the file path.
Display the ranked todo list with IDs.

### Step 7 — implement
Ask: "Dispatch subagents to implement all [N] todos in parallel? (y/n/select)"
- **y**: spawn one Agent (subagent) per todo, all in parallel
- **select**: show numbered list, user picks which ones
- **n**: stop here

Each subagent receives:
- The specific finding title + description
- The file path and its contents
- Instruction: implement this fix, then run existing tests if any exist
- Instruction: commit with message `fix(compare): {todo title}`

After each subagent completes, call `compare_todo_update` to mark the todo as `done`.

## Sub-commands

### `/compare status`
Call `compare_status` and display todos grouped by status.

### `/compare models`
Call `compare_models` and display a table of configured providers.

### `/compare update <id> <status>`
Call `compare_todo_update` to change a todo's status.
