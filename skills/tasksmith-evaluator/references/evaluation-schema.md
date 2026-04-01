# Tasksmith Evaluator Output Schema

Use this schema as the normalized judgment for one evaluator attempt.
The evaluator may include extra debugging fields, but these keys should always exist.

## Required Keys

```json
{
  "node_id": "N12",
  "verdict": "needs_revision",
  "summary": "The comparison file exists, but it omits product gaps and does not justify the pricing section.",
  "satisfied_criteria": [
    "Produced the requested markdown file."
  ],
  "deficiencies": [
    "Missing comparison of product gaps.",
    "Pricing coverage is too shallow to satisfy the node."
  ],
  "improvement_actions": [
    "Add a section comparing each competitor's notable product gaps.",
    "Revise pricing coverage with concrete evidence from the source notes."
  ],
  "evidence": [
    "/absolute/path/analysis/competitor-comparison.md"
  ],
  "confidence": 0.86
}
```

## Field Meanings

- `node_id`: DAG node id being judged.
- `verdict`: One of `pass` or `needs_revision`.
- `summary`: Short explanation of the judgment.
- `satisfied_criteria`: Criteria or expectations that the worker output did satisfy.
- `deficiencies`: Missing, incorrect, or insufficient parts that prevent a pass verdict.
- `improvement_actions`: Concrete next actions to make the node pass on a follow-up attempt.
- `evidence`: Absolute paths or concise artifact references used to support the judgment.
- `confidence`: Floating-point confidence score between `0.0` and `1.0`.

## Judgment Rules

- Use `pass` only when the produced outputs satisfy the node goal, constraints, success criteria, and output contract well enough for downstream nodes.
- Use `needs_revision` when outputs exist but are incomplete, incorrect, or too weak to trust.
- Do not mark `pass` solely because the expected file paths exist.

## Artifact Layout

Prefer this attempt directory shape:

```text
.tasksmith/evaluator-runs/N12/attempt-001/
  brief.txt
  execution.json
  stdout.txt
  stderr.txt
  evaluation.json
```

Preserve older attempts.
