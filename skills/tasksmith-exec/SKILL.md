---
name: tasksmith-exec
description: Run one task in a fresh isolated agent session through a locally installed agent CLI such as Codex or Claude Code. Use when Tasksmith needs true node-level session isolation for DAG execution, retryable subtask runs, minimal-context execution, or provider-swappable single-agent execution without sharing planner conversation state.
---

# Tasksmith Exec

Run exactly one subtask in a new agent session and return only the result artifact needed by the caller.
Keep planner context out of the worker session. Pass only the node brief, required inputs, constraints, success criteria, and output contract.

## Workflow

Follow this sequence:

1. Build a compact node brief.
2. Choose a provider.
3. Invoke the isolated runner script.
4. Capture stdout, stderr, exit code, and provider metadata.
5. Return a structured result to the planner.

## Build The Node Brief

Include only:

- node id
- goal
- required input artifacts
- allowed tools or workspace limits
- success criteria
- exact output format

Do not pass the full planner transcript unless the node genuinely depends on it.
Prefer a prompt file for long briefs so quoting stays stable.

## Choose The Provider

Use `auto` unless the task requires a specific model family or a specific CLI feature.
The runner currently supports:

- `codex`
  Uses `codex exec --ephemeral` for a fresh non-persistent session.
  Prefer when you want `--output-schema`, Codex-specific sandbox flags, or Codex-native JSONL event output.
- `claude`
  Uses `claude -p --no-session-persistence` for a fresh non-persistent session.
  Prefer when you want `--json-schema` or Claude-specific permission modes.

Read [references/cli-notes.md](references/cli-notes.md) if you need the exact CLI behaviors discovered from `codex -h`, `codex exec -h`, and `claude -h`.

## Run The Worker

Use the bundled script:

```bash
python3 scripts/run_isolated_agent.py \
  --provider auto \
  --cwd /absolute/worktree \
  --prompt-file /tmp/node-brief.txt
```

Useful flags:

- `--schema-file <path>` to enforce structured final output on either provider
- `--model <name>` to pin a model
- `--json` to emit a machine-readable execution envelope from the wrapper
- `--capture-output <path>` to save stdout
- `--capture-error <path>` to save stderr
- `--dry-run` to inspect the exact command without executing it

## Output Contract

Return a compact object or section set with:

- node id
- provider used
- command metadata if needed for debugging
- exit status
- primary result
- notable warnings
- retry recommendation if the run failed

If the worker cannot complete the task, preserve the raw failure signal and summarize the blocking reason instead of silently rewriting the result.

## Defaults

- default provider: `auto`
- fresh session: always on
- prompt source: stdin or `--prompt-file`
- result handling: capture raw stdout before summarizing
- planner responsibility: prepare the brief, choose retries, and integrate outputs

## Example

```bash
cat > /tmp/node-brief.txt <<'EOF'
Node ID: N7
Goal: Summarize benchmark findings into 5 bullets.
Inputs:
- /tmp/benchmark-results.json
Constraints:
- Use only the provided file.
- Do not browse the web.
Success Criteria:
- 5 bullets
- Mention the strongest and weakest result
Output Format:
- JSON object with keys summary and confidence
EOF

python3 scripts/run_isolated_agent.py \
  --provider auto \
  --cwd /Users/leejs/Project/tasksmith \
  --schema-file /tmp/summary-schema.json \
  --prompt-file /tmp/node-brief.txt \
  --json
```

## Tasksmith Context

Treat `tasksmith:exec` as the execution primitive for DAG nodes.
The conceptual namespace is `tasksmith:exec`, but the filesystem skill id is `tasksmith-exec` to satisfy skill naming constraints.
