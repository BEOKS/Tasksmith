# Tasksmith Worker Result Schema

Use this schema as the normalized record for one worker attempt.
The worker may include additional debugging fields, but these keys should always exist.

## Required Keys

```json
{
  "node_id": "N12",
  "status": "needs_revision",
  "provider": "codex",
  "attempt": 1,
  "output_paths": [
    "/absolute/path/analysis/competitor-comparison.md"
  ],
  "result_summary": "Produced the requested markdown output and completed evaluator pass/fail review.",
  "warnings": [],
  "failure_reason": "Evaluator found the file incomplete for the node requirements.",
  "raw_execution_ref": "/absolute/path/.tasksmith/worker-runs/N12/attempt-001/execution.json",
  "evaluation_verdict": "needs_revision",
  "evaluation_summary": "The file exists but omits product gaps and does not satisfy the comparison criteria.",
  "evaluation_ref": "/absolute/path/.tasksmith/evaluator-runs/N12/attempt-001/evaluation.json",
  "revision_source_ref": "/absolute/path/.tasksmith/evaluator-runs/N12/attempt-001/evaluation.json"
}
```

## Field Meanings

- `node_id`: DAG node id that was executed.
- `status`: One of `success`, `needs_revision`, `failed`, or `blocked`.
- `provider`: Provider chosen by `tasksmith-exec`, or `unknown` when execution never started.
- `attempt`: 1-based attempt number for this node.
- `output_paths`: Absolute paths inferred from the output contract and confirmed to exist.
- `result_summary`: Short human-readable summary of the outcome.
- `warnings`: Non-fatal issues such as unresolved non-file dependency references.
- `failure_reason`: Null on success. On failure or blocked states, a concise explanation.
- `raw_execution_ref`: Absolute path to the saved execution envelope JSON.
- `evaluation_verdict`: Null when no evaluation ran. Otherwise one of `pass` or `needs_revision`.
- `evaluation_summary`: Null when no evaluation ran. Otherwise a short evaluator judgment.
- `evaluation_ref`: Null when no evaluation ran. Otherwise the absolute path to `tasksmith-evaluator`'s saved judgment.
- `revision_source_ref`: Null on first attempts. On revision attempts, the absolute path to the previous evaluator JSON used as repair guidance.

## Status Rules

- Use `blocked` when the worker could not run because prerequisites were missing or unreadable.
- Use `failed` when the provider ran but returned a non-zero exit code or the output contract was not met.
- Use `needs_revision` when the provider run completed and output artifacts exist, but the evaluator judged the node insufficient.
- Use `success` only when the provider run completed, expected output artifacts exist when the contract specifies file creation, and the evaluator returned `pass`.

## Artifact Layout

Prefer this attempt directory shape:

```text
.tasksmith/worker-runs/N12/attempt-001/
  brief.txt
  execution.json
  stdout.txt
  stderr.txt
  result.json
```

Preserve older attempts.
Do not overwrite a previous attempt directory.

The corresponding evaluation attempt should usually live at:

```text
.tasksmith/evaluator-runs/N12/attempt-001/
```
