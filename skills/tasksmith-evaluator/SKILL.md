---
name: tasksmith-evaluator
description: Evaluate a completed Tasksmith DAG node against the node goal, constraints, success criteria, and output contract after `tasksmith-worker` finishes execution. Use when Codex needs a separate pass/fail judgment with concrete deficiency feedback, especially when output files exist but completion quality still needs verification, when revision guidance must be recorded, or when execution and evaluation must remain isolated in different sessions.
---

# Tasksmith Evaluator

Judge whether one finished node actually satisfies the task, not just whether the worker produced files.
Keep the evaluator separate from the worker session so execution context does not leak into the judgment.

## Data Storage Rule

Persist any Tasksmith handoff data, intermediate artifacts, or reusable run state that this skill creates for downstream skills under the workspace `.tasksmith/` directory.
Use temporary paths outside `.tasksmith/` only for short-lived scratch files that are consumed immediately and do not represent durable Tasksmith state.

## Workflow

Follow this sequence:

1. Read the authoritative node specification.
2. Read the latest worker result and execution envelope.
3. Inspect the worker output artifacts that the node claims to have produced.
4. Compare the artifacts against the node goal, constraints, success criteria, and output contract.
5. Return a structured verdict with either `pass` or `needs_revision`.
6. Record deficiencies and concrete improvement actions when the verdict is not `pass`.

Do not execute the business task again unless the evaluation is explicitly about retrying or repairing it.
Do not inherit the planner session or the worker session.

## Core Rule

Run the evaluator through `tasksmith-exec` or an equivalent fresh-session runner.
The evaluator must not share session state with:

- the planner
- the node worker
- any other node evaluator

Pass only the minimum evaluation payload: node requirements, worker attempt artifacts, and the output locations that must be checked.

## Inputs

Expect these artifacts:

- one node definition from the DAG JSON or a standalone node file
- one worker result JSON
- one worker execution envelope JSON
- any output files listed by the worker result

Treat the node definition as the source of truth for what counts as completion.
Treat the worker result as evidence, not as the final authority.

## Evaluation Brief

Build a compact brief with:

- node id
- goal
- constraints
- success criteria
- output contract
- worker status and summary
- absolute paths to output artifacts that exist
- absolute paths to `stdout.txt`, `stderr.txt`, and `execution.json` for supporting evidence
- explicit instruction to inspect artifacts directly before judging

Use a brief shape like:

```text
Node ID: N12
Goal: Compare the provided competitor notes and write a concise comparison.
Constraints:
- Use only the provided artifacts.
Success Criteria:
- Cover pricing, positioning, and product gaps.
Output Contract:
- Save analysis/competitor-comparison.md
Worker Evidence:
- Worker status: success
- Worker summary: Created analysis/competitor-comparison.md
- Output artifacts:
  - /abs/path/analysis/competitor-comparison.md
- Supporting files:
  - /abs/path/.tasksmith/worker-runs/N12/attempt-001/stdout.txt
  - /abs/path/.tasksmith/worker-runs/N12/attempt-001/execution.json
Evaluation Task:
- Inspect the artifacts directly.
- Return pass only if the produced work satisfies the node.
- Otherwise return needs_revision with deficiencies and concrete repair guidance.
```

Keep the brief operational and short.
Do not include planner commentary or unrelated node history.

## Structured Output

Use the schema in [references/evaluation-schema.md](references/evaluation-schema.md).

At minimum, return:

- `node_id`
- `verdict`
- `summary`
- `satisfied_criteria`
- `deficiencies`
- `improvement_actions`
- `evidence`
- `confidence`

Use these verdict meanings:

- `pass`: The node output satisfies the required task well enough to unblock downstream work.
- `needs_revision`: The worker produced something usable for review, but the node is incomplete, incorrect, or underspecified relative to the node contract.

## Storage

Save evaluation artifacts under a stable path such as:

```text
.tasksmith/evaluator-runs/N12/attempt-001/
```

Persist at least:

- `brief.txt`
- `stdout.txt`
- `stderr.txt`
- `execution.json`
- `evaluation.json`

Keep attempt numbers aligned with the worker attempt when practical.
Do not overwrite older attempts.

## Defaults

- default provider: `auto`
- session isolation: always on
- evidence source: worker artifacts first, not chat memory
- pass threshold: require clear satisfaction of the node, not just artifact existence

## Validation

Before first use and after substantial edits:

1. Run the evaluator in `--dry-run` mode to verify the isolated command shape.
2. Run one happy-path evaluation where the artifact clearly satisfies the node.
3. Run one negative-path evaluation where the artifact exists but does not satisfy the node.
4. Run `quick_validate.py` on the skill folder.

## Tasksmith Context

Use this skill immediately after `tasksmith-worker` produces a candidate result.
Keep the responsibility boundary sharp:

- `tasksmith-dag`: define nodes
- `tasksmith-worker`: execute one node
- `tasksmith-evaluator`: judge whether the completed node actually passed
- `tasksmith-exec`: provide fresh-session isolation

The conceptual namespace is `tasksmith:evaluator`, and the filesystem skill id is `tasksmith-evaluator`.
