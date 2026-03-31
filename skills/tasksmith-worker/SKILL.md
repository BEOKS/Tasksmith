---
name: tasksmith-worker
description: Execute one Tasksmith DAG node from an authoritative DAG JSON file or a standalone node brief, prepare a minimal execution brief, run that node only through `tasksmith-exec` in a fresh isolated session, and then have `tasksmith-evaluator` judge whether the produced work actually satisfies the node. Use when Codex needs single-node execution with strict session isolation, retryable node-level runs, structured result records, and a separate pass/fail evaluation instead of relying on file existence alone.
---

# Tasksmith Worker

Execute exactly one DAG node and leave a structured execution record that a later orchestrator can inspect.
Keep the worker narrow: it is the single-node executor, not the full DAG scheduler.

## Core Rule

Always execute the node through `tasksmith-exec` or an equivalent fresh-session runner.
Do not execute the node inside the planner session.
Do not reuse another node's session.
Do not pass the full planner transcript unless the node explicitly requires it and the requirement is captured inside the node itself.

## Responsibilities

Do all of the following:

1. Read one node from the authoritative DAG JSON file or a standalone node JSON brief.
2. Validate that the node contains the minimum execution fields.
3. Inspect the node inputs and identify which local artifacts are actually required now.
4. Build a compact worker brief with only the node goal, required artifacts, constraints, success criteria, and output contract.
5. Call `tasksmith-exec` to run the node in a fresh isolated session.
6. If execution succeeds far enough to produce candidate outputs, call `tasksmith-evaluator` in another fresh isolated session.
7. When a previous evaluator run returned `needs_revision`, pass only that structured evaluator payload into the next worker attempt as revision guidance.
8. Save the prompt, raw execution envelope, stdout, stderr, evaluation artifacts, and normalized result record.

Do not do any of the following:

- topological scheduling
- multi-node orchestration
- planner-driven graph expansion
- global retry policy across the DAG
- failure propagation across downstream nodes
- judging semantic completion inside the worker session itself

## Required Node Fields

Expect these fields at minimum:

- `id`
- `goal`
- `inputs`
- `depends_on`
- `constraints`
- `success_criteria`
- `output_contract`

Allow additional optional fields such as:

- `allowed_tools`
- `execution_policy`
- `status`
- node-local metadata

Treat the DAG JSON as authoritative when both a DAG file and a separate node brief exist.

## Input Artifact Rules

Inspect the `inputs` list before execution.

Use these rules:

- Treat plain file paths as local artifact requirements.
- Resolve relative paths against the worker `--cwd`.
- Treat strings such as `N8:output` as dependency references, not local file paths.
- If a required local input file is missing, mark the node as `blocked` and do not execute the provider.
- If the node has only dependency references and no concrete local artifacts, execute with the references listed exactly as the node provides them.

Do not silently substitute missing inputs.

## Worker Brief Format

Build a brief that contains only the minimum execution context.

Use a shape equivalent to:

```text
Node ID: N12
Goal: Compare the provided competitor notes and write a concise comparison.
Inputs:
- /abs/path/research/notes.md
- N8:output
Constraints:
- Use only the provided artifacts.
- Do not browse the web.
Allowed Tools:
- local filesystem
Success Criteria:
- Produce a concise comparison with pricing, positioning, and gaps.
Output Contract:
- Save analysis/competitor-comparison.md
```

Keep the brief operational and short.
Do not include planner commentary, DAG construction notes, or unrelated node history.

## Execute Through Tasksmith Exec

Use the bundled worker script to prepare and run the node:

```bash
python3 scripts/run_worker.py \
  --dag-file /absolute/path/tasksmith/dag.json \
  --node-id N12 \
  --cwd /absolute/worktree \
  --provider auto \
  --json
```

Useful variants:

```bash
python3 scripts/run_worker.py \
  --node-file /absolute/path/N12.json \
  --cwd /absolute/worktree \
  --provider codex \
  --model gpt-5.4 \
  --json

python3 scripts/run_worker.py \
  --dag-file /absolute/path/tasksmith/dag.json \
  --node-id N12 \
  --cwd /absolute/worktree \
  --revision-file /absolute/path/tasksmith/evaluator-runs/N12/attempt-001/evaluation.json \
  --json

python3 scripts/run_worker.py \
  --dag-file /absolute/path/tasksmith/dag.json \
  --node-id N12 \
  --cwd /absolute/worktree \
  --dry-run \
  --json
```

The worker script must call:

```bash
python3 ../tasksmith-exec/scripts/run_isolated_agent.py ...
```

or the equivalent resolved absolute path inside the repository.

Do not bypass `tasksmith-exec` by calling `codex exec` or `claude` directly from the skill workflow.

## Revision Attempts

When a previous evaluator verdict is `needs_revision`, pass that evaluator JSON back through `--revision-file` on the next worker attempt.

Treat the evaluator payload as repair guidance, not as permission to expand the node scope.
Only pass the structured evaluator artifact, not the whole prior session transcript.
The follow-up worker attempt must still run through `tasksmith-exec` in a fresh isolated session.

## Result Record

Normalize each run into a structured record.
Use the schema in [references/result-schema.md](references/result-schema.md).

At minimum, record:

- `node_id`
- `status`
- `provider`
- `attempt`
- `output_paths`
- `result_summary`
- `warnings`
- `failure_reason`
- `raw_execution_ref`
- `evaluation_verdict`
- `evaluation_summary`
- `evaluation_ref`
- `revision_source_ref`

Save attempt artifacts under a stable workspace path such as:

```text
tasksmith/worker-runs/N12/attempt-001/
```

Persist at least:

- `brief.txt`
- `stdout.txt`
- `stderr.txt`
- `execution.json`
- `result.json`

Persist evaluation artifacts in the paired evaluator run directory when evaluation is attempted.

## Status Semantics

Use these meanings consistently:

- `success`: provider run completed and the output contract appears satisfied
- `needs_revision`: provider run completed, but the evaluator found the node incomplete or insufficient
- `failed`: provider ran but exited non-zero or returned an unusable result
- `blocked`: the node could not be attempted because required local prerequisites were missing or unreadable

Do not label a node `success` when the expected output artifacts are absent or the evaluator did not return `pass`.

## Validation And Retry

Before first use and after substantial edits:

1. Run the worker in `--dry-run` mode to verify the isolated command shape.
2. Run at least one happy-path node execution and confirm the paired evaluator returns `pass`.
3. Run one negative-path evaluation where the worker produces an artifact but the evaluator returns `needs_revision`.
4. Run one blocked-path case with a missing input file.
5. Run `quick_validate.py` on the skill folder.

Retries belong at the node level only.
Preserve earlier attempt folders and increment the attempt number instead of overwriting prior records.

## Tasksmith Context

Use this skill after `tasksmith-dag` or another planner has already created an execution-ready node.
Treat `tasksmith-worker` as the bridge between node specification and isolated execution.
Keep the responsibility boundary sharp:

- `tasksmith-dag`: define nodes
- `tasksmith-worker`: execute one node and trigger evaluation
- `tasksmith-evaluator`: judge whether the completed node actually passed
- `tasksmith-exec`: provide fresh-session isolation
