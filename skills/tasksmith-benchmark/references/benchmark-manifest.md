# Tasksmith Benchmark Manifest

Use this reference when creating `manifest.json` files for `tasksmith-benchmark`.
The manifest should be compact, explicit, and stable across reruns.

## Recommended Layout

Store benchmark experiments under:

```text
.tasksmith/benchmarks/<experiment-name>/
  manifest.json
  results/
    summary.json
    summary.md
```

## Manifest Shape

Use a JSON object shaped like:

```json
{
  "experiment_id": "exp-001",
  "title": "Isolation vs shared-session benchmark",
  "benchmark_question": "Does isolated execution improve success rate and retry behavior over shared-session execution?",
  "task_set": {
    "name": "tasksmith-smoke",
    "description": "Small representative internal task set"
  },
  "metrics": [
    "success",
    "wall_clock_seconds",
    "input_tokens",
    "output_tokens",
    "attempt_count",
    "propagation_count"
  ],
  "variants": [
    {
      "id": "dag-shared-session",
      "label": "DAG shared session",
      "family": "dag",
      "session_mode": "shared"
    },
    {
      "id": "dag-isolated-session",
      "label": "DAG isolated session",
      "family": "dag",
      "session_mode": "isolated"
    }
  ],
  "trials": [
    {
      "variant_id": "dag-isolated-session",
      "task_id": "task-001",
      "run_id": "run-001",
      "status": "success",
      "metrics": {
        "success": 1,
        "wall_clock_seconds": 24.3,
        "input_tokens": 5421,
        "output_tokens": 811,
        "attempt_count": 2,
        "propagation_count": 0
      },
      "artifacts": {
        "scheduler_summary": "/absolute/path/.tasksmith/scheduler-runs/run-004/summary.json",
        "report": "/absolute/path/.tasksmith/benchmarks/exp-001/results/task-001-run-001.md"
      },
      "notes": {
        "provider": "codex",
        "model": "gpt-5.4"
      }
    }
  ]
}
```

## Required Top-Level Fields

- `experiment_id`
- `title`
- `benchmark_question`
- `variants`
- `trials`

## Variant Fields

Each variant should include:

- `id`
- `label`

Recommended additional fields:

- `family`
- `session_mode`
- `planner_mode`
- `scheduler_mode`
- `propagation_mode`
- `notes`

Keep `id` stable across reruns so summaries remain comparable.

## Trial Fields

Each trial should include:

- `variant_id`
- `task_id`
- `run_id`
- `status`

Recommended additional fields:

- `metrics`
- `artifacts`
- `notes`

## Metric Conventions

Prefer numeric metrics so they can be averaged or summed.

Recommended conventions:

- `success`: `1` for success, `0` for non-success
- `wall_clock_seconds`: floating-point seconds
- `input_tokens`: integer
- `output_tokens`: integer
- `attempt_count`: integer
- `propagation_count`: integer
- `recovered_after_failure`: `1` or `0`
- `parallel_wave_width`: floating-point average
- `cost_usd`: floating-point dollars

When a metric is unavailable, omit it or set it to `null`.
Do not coerce unknown values to `0`.

## Interpretation Tips

Use paired comparisons when task sets are aligned across variants.
Be explicit about whether a reported difference reflects:

- decomposition
- session isolation
- propagation
- parallel execution
- model or provider differences

Do not compare variants with different task sets as if the numbers were directly equivalent.
