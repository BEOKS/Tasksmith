---
name: tasksmith-benchmark
description: Design, run, and compare Tasksmith benchmark experiments across multiple harness variants such as single-session baselines, sequential split baselines, DAG planning with shared sessions, and DAG planning with isolated execution. Use when Codex needs to validate whether the Tasksmith architecture improves success rate, token efficiency, wall-clock time, retry behavior, failure recovery, or session-isolation quality, especially for SWE-bench-style tasks, internal regression suites, ablation studies, or benchmark report generation.
---

# Tasksmith Benchmark

Design benchmark experiments that test whether the Tasksmith harness is actually better than simpler alternatives.
Use this skill to define comparison variants, run repeatable trials, aggregate artifacts from earlier Tasksmith skills, and produce a report that separates decomposition effects from isolation effects.

## Core Rule

Treat benchmarking as a separate analysis layer above the runtime skills.
Do not collapse benchmark interpretation into the planner, scheduler, or worker sessions.
Do not infer benchmark outcomes from anecdotes.
Use persisted run artifacts and explicit experiment metadata.

Keep these boundaries sharp:

- `tasksmith-benchmark`: choose comparison groups, define metrics, aggregate evidence, and write benchmark reports
- `tasksmith-clarifier`: refine the benchmark request if goals or constraints are ambiguous
- `tasksmith-dag-builder`, `tasksmith-scheduler`, `tasksmith-loop`, `tasksmith-worker`, `tasksmith-evaluator`, `tasksmith-propagator`: produce the runtime artifacts being measured
- `tasksmith-exec`: provide isolated execution where the experimental design requires it

## Use This Skill When

Use this skill when any of the following is true:

- the team needs evidence that DAG decomposition helps compared with a single long-context run
- the team needs to isolate the effect of fresh-session execution from the effect of task decomposition
- the team wants an ablation study for one Tasksmith component such as propagation, scheduler parallelism, or incremental DAG building
- the team wants benchmark manifests and summary reports saved in the workspace
- the team wants to compare repeated runs across variants, models, providers, or task sets
- the team wants a benchmark report for SWE-bench, internal regression tasks, research tasks, or mixed non-code agent tasks

Do not use this skill for:

- first-pass task clarification
- first-pass DAG construction
- single-node execution
- failure propagation on one live DAG
- ad hoc opinions about whether the system "felt better"

## Comparison Variants

Prefer explicit variant names and keep the definitions stable across runs.

At minimum, support these benchmark variants when they match the user's request:

1. `single-session`
   One long-context agent handles the whole task directly.
2. `split-sequential`
   Work is manually split into multiple steps, but executed sequentially without a DAG scheduler.
3. `dag-shared-session`
   Work is represented as a DAG, but node execution reuses planner or shared execution context.
4. `dag-isolated-session`
   Work is represented as a DAG and each node executes in a fresh isolated session through `tasksmith-exec` or an equivalent primitive.

Use the fourth variant as the default Tasksmith target architecture.
If the user asks for ablations, add explicit variants such as:

- `dag-isolated-no-propagation`
- `dag-isolated-no-parallel`
- `dag-isolated-no-incremental-build`
- `dag-isolated-no-recording`

## Metrics

Track metrics that can distinguish architecture effects instead of only reporting one final pass/fail number.
Use the metric definitions in [references/benchmark-manifest.md](references/benchmark-manifest.md).

Prefer these metric groups:

1. Outcome quality
   - success rate
   - evaluator pass rate
   - benchmark-specific correctness score
2. Efficiency
   - wall-clock seconds
   - total input tokens
   - total output tokens
   - cost estimate when available
3. Retry and recovery
   - attempts per task
   - revision loops per node
   - propagation count
   - recovered-after-failure rate
4. Parallelism and isolation
   - average ready-node wave width
   - parallel time saved estimate
   - isolation mode
   - isolation breach count

When token or cost data is unavailable, record the gap explicitly instead of fabricating estimates.

## Workflow

Follow this sequence:

1. Read the benchmark request and identify the target questions.
2. Define the task set and comparison variants.
3. Write or update an experiment manifest.
4. Run or collect trials for each variant.
5. Normalize the resulting artifact paths and metadata.
6. Aggregate trial outcomes with `scripts/summarize_benchmark.py`.
7. Interpret the results in terms of the benchmark question.
8. Save a benchmark report with findings, caveats, and recommended next experiments.

## Benchmark Questions

State the benchmark question before running anything.
Prefer a concrete question such as:

- Does `dag-isolated-session` improve completion rate over `single-session` on this task set
- Does isolation reduce retries or downstream contamination compared with `dag-shared-session`
- Does propagation improve final objective completion after upstream failures
- Does bounded parallel scheduling reduce wall-clock time without lowering success rate

Avoid vague questions such as "Is Tasksmith good".

## Experiment Manifest

Store experiment definitions in a JSON manifest.
Use a stable path such as:

```text
tasksmith/benchmarks/<experiment-name>/manifest.json
```

The manifest should define:

- experiment id and description
- benchmark question
- task set
- variants
- trials
- metric field names
- result artifact locations

Use the exact field contract documented in [references/benchmark-manifest.md](references/benchmark-manifest.md).

## Trial Inputs

Each trial record should point to real artifacts, not only to narrative summaries.
Prefer trial data that includes:

- variant id
- task id
- run id
- status
- scheduler, loop, worker, evaluator, or propagation summary paths when they exist
- duration, token, cost, and attempt counts when available
- notes about provider, model, and isolation mode

If a benchmark includes non-Tasksmith baselines, normalize them into the same metric fields so the report can compare them directly.

## Aggregation

Use the bundled script to aggregate manifest-linked trial data:

```bash
python3 scripts/summarize_benchmark.py \
  --manifest /absolute/path/tasksmith/benchmarks/exp-001/manifest.json \
  --output-dir /absolute/path/tasksmith/benchmarks/exp-001/results \
  --json
```

Useful variants:

```bash
python3 scripts/summarize_benchmark.py \
  --manifest /absolute/path/tasksmith/benchmarks/exp-001/manifest.json \
  --output-dir /absolute/path/tasksmith/benchmarks/exp-001/results \
  --markdown

python3 scripts/summarize_benchmark.py \
  --manifest /absolute/path/tasksmith/benchmarks/exp-001/manifest.json \
  --dry-run \
  --json
```

The script aggregates variant-level and task-level summaries.
Use it to avoid hand-counting success rates or mixing inconsistent trial metadata.

## Interpretation Rules

Separate these effects in the written analysis:

1. decomposition effect
   Compare `single-session` or `split-sequential` against DAG-based variants
2. isolation effect
   Compare `dag-shared-session` against `dag-isolated-session`
3. orchestration effect
   Compare ablations such as no-parallel, no-propagation, or no-incremental-build against the full design

When a variant wins on one metric and loses on another, make the tradeoff explicit.
Do not describe the result as a clear win unless the benchmark question supports that interpretation.

## Output Contract

Persist benchmark artifacts under a stable workspace path such as:

```text
tasksmith/benchmarks/<experiment-name>/
```

Persist at minimum:

- `manifest.json`
- `results/summary.json`
- `results/summary.md`

The report should capture:

- benchmark question
- task set and trial counts
- variant definitions
- per-variant aggregate metrics
- pairwise comparisons
- decomposition, isolation, and ablation findings
- data quality gaps
- recommended next experiments

## Validation

Before relying on the skill after substantial edits:

1. Run `scripts/summarize_benchmark.py --help`.
2. Run the script on a small synthetic manifest with at least two variants and two trials.
3. Confirm the script produces both JSON and Markdown summaries.
4. Confirm missing metrics are preserved as null or absent values rather than silently rewritten to zero.
5. Run `quick_validate.py` on the skill folder.

## Tasksmith Context

Use this skill after Tasksmith execution skills have produced benchmarkable artifacts or when planning a benchmark campaign for those skills.
This is the evidence layer for the Tasksmith architecture, not the runtime layer itself.

The conceptual namespace is `tasksmith:benchmark`, and the filesystem skill id is `tasksmith-benchmark`.
