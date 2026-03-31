---
name: tasksmith-loop
description: Orchestrate repeated Tasksmith node execution until a node passes evaluation or stops for a non-revision reason. Use when Codex needs `tasksmith-worker` to run one node, `tasksmith-evaluator` to judge the result, and then a follow-up worker attempt to consume structured evaluator feedback. Always require `tasksmith-worker` and `tasksmith-evaluator` to run through `tasksmith-exec` in fresh isolated sessions rather than sharing the planner session.
---

# Tasksmith Loop

Run the worker-evaluator repair cycle for exactly one node.
Keep orchestration separate from execution: this skill decides whether to continue, but each worker and evaluator attempt must remain isolated.

## Core Rule

Never execute the node directly inside the loop session.
Always call `tasksmith-worker`, and rely on that worker to invoke `tasksmith-exec` for the node run and `tasksmith-evaluator` for the judgment.
If a retry is needed, pass only the structured evaluator artifact from the previous attempt back into the next worker attempt.

## Workflow

Follow this sequence:

1. Read one authoritative node from a DAG JSON file or standalone node JSON.
2. Start worker attempt `1`.
3. Let `tasksmith-worker` execute the node through `tasksmith-exec`.
4. Let `tasksmith-worker` trigger `tasksmith-evaluator`, which must also run through `tasksmith-exec`.
5. Inspect the worker result.
6. If the result is `success`, stop.
7. If the result is `needs_revision`, pass the evaluator JSON from that attempt into the next worker attempt through `--revision-file`.
8. Stop when a non-revision terminal status occurs or the loop reaches `--max-attempts`.
9. Save a loop-level summary record.

## Isolation Requirement

The loop session is only the orchestrator.
It must not become the execution session for either:

- the node worker
- the node evaluator

Preserve these boundaries:

- `tasksmith-loop`: decide whether to run another attempt
- `tasksmith-worker`: execute one attempt and trigger evaluation
- `tasksmith-evaluator`: judge one attempt
- `tasksmith-exec`: guarantee a fresh isolated session for worker and evaluator runs

If a runtime path bypasses `tasksmith-exec`, treat that as a design violation.

## Execute The Loop

Use the bundled script:

```bash
python3 scripts/run_loop.py \
  --dag-file /absolute/path/tasksmith/dag.json \
  --node-id N12 \
  --cwd /absolute/worktree \
  --max-attempts 3 \
  --json
```

Useful variants:

```bash
python3 scripts/run_loop.py \
  --node-file /absolute/path/N12.json \
  --cwd /absolute/worktree \
  --provider codex \
  --evaluation-provider codex \
  --json

python3 scripts/run_loop.py \
  --dag-file /absolute/path/tasksmith/dag.json \
  --node-id N12 \
  --cwd /absolute/worktree \
  --dry-run \
  --json
```

## Retry Policy

Retry only when the worker result is `needs_revision`.
Do not retry automatically on:

- `blocked`
- `failed`
- missing evaluator artifacts
- malformed evaluator output

Treat those as loop-stopping conditions unless an outer planner deliberately changes the node or inputs.

## Revision Handoff

For revision attempts, pass only the previous evaluator JSON.
Do not pass the whole prior worker transcript.
Do not merge multiple evaluator attempts into one synthetic prompt unless a higher-level planner explicitly needs that aggregation.

Use the evaluator artifact as repair guidance for the next isolated worker attempt.

## Loop Record

Save loop artifacts under a stable workspace path such as:

```text
tasksmith/loop-runs/N12/run-001/
```

Persist at least:

- `summary.json`

The summary should capture:

- node id
- final status
- stop reason
- max attempts
- attempt list with worker result refs and evaluator refs

## Validation

Before first use and after substantial edits:

1. Run the loop in `--dry-run` mode and confirm it prepares an isolated worker command.
2. Run one case that passes on the first attempt.
3. Run one case that returns `needs_revision` once and then passes after a revision attempt.
4. Run one case that stops on `blocked` or `failed`.

## Tasksmith Context

Use this skill after the graph already contains an execution-ready node and you want the worker/evaluator cycle to continue until either the node passes or the loop has enough evidence to stop.
The conceptual namespace is `tasksmith:loop`, and the filesystem skill id is `tasksmith-loop`.
