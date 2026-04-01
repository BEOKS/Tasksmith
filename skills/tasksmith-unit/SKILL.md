---
name: tasksmith-unit
description: Define and estimate Tasksmith work in `unit`s, where `1 unit` is the smallest task a single LLM agent can complete end-to-end in one bounded session. Use when an agent needs to size a request, judge whether work fits inside one agent, compare task sizes, decide whether decomposition is needed, or produce estimates such as `1 unit`, `8 units`, or `30 units` for coding, research, planning, documentation, or mixed workflows. Keep the scoring agent-neutral so it can be applied from Codex, Claude Code, or similar single-agent runtimes.
---

# Tasksmith Unit

Estimate how much work a request represents by translating it into Tasksmith units.
Treat a unit as work size, not elapsed time.

## Runtime Neutrality

Use the same scoring model regardless of whether the active runtime is Codex, Claude Code, or another single-agent LLM tool.
Do not change the estimate only because one product has better tools, a longer context window, or different UI affordances.

Estimate against the portable baseline:

- one capable LLM agent
- one bounded working session
- ordinary local tools and file access
- no hidden help from parallel subagents unless the task explicitly includes decomposition
- no `spawn_agent` or other interactive sub-agent delegation shortcuts

If a request only fits because of runtime-specific advantages, score the underlying work, not the product-specific shortcut.
If a task only fits because the runtime can secretly fan out to sub-agents, estimate it as larger than one agent run.

## Core Definition

Treat `1 unit` as the smallest task that still has a meaningful done condition and that one LLM agent can complete safely in one bounded session.

Expect a `1 unit` task to have all of these properties:

- one primary objective
- one dominant work surface or subsystem
- enough context to act without a separate planning project
- one clear completion test or review target
- low enough ambiguity that assumptions do not change the task shape

If any of those properties break, the work is probably larger than `1 unit`.

## Workflow

Follow this sequence:

1. Normalize the request.
   Extract the objective, deliverables, constraints, dependencies, and verification target.
2. Check whether the task is already atomic.
   If one agent could execute it directly with one coherent done condition, start from `1 unit`.
3. Score the request with the six buckets in [references/rubric.md](references/rubric.md).
4. Sum the bucket values.
   Use mental math or run `python3 scripts/calc_units.py ...`.
5. Interpret the result.
   Use the total to decide whether to execute directly or decompose first.
6. Return the estimate with evidence.
   Include the total, bucket breakdown, assumptions, and the main drivers.

## Counting Rules

Use these rules to keep estimates stable:

- Count independent reasoning surfaces, not raw file count.
- Count a new subsystem only when it changes how the agent must inspect, act, or verify.
- Bundle tightly related edits into one implementation slice when they share one done condition.
- Split work when outputs can fail independently or when different validation paths are required.
- Add risk units only for genuine unknowns or likely rework; do not pad routine work.
- Estimate minimum safe work, not calendar time, team size, or story points.
- Prefer the lowest defensible number over optimistic guesses or padded budgets.

## Result Bands

Use these bands after summing the buckets:

- `1`: atomic single-agent task
- `2-4`: small task; optional split
- `5-8`: multi-step task; prefer a few nodes
- `9-15`: medium project; decompose before execution
- `16-30`: large initiative; plan and execute in waves
- `31+`: program-scale request; require explicit scope control

## Output Contract

Return results in this shape:

```md
Unit Estimate
- Total: 30 units
- Band: large initiative

Breakdown
- Clarification: 2
- Context: 5
- Implementation: 10
- Validation: 6
- Coordination: 3
- Risk: 4

Assumptions
- ...

Main Drivers
- ...

Recommendation
- ...
```

If the request is already atomic, still show the reasoning and explicitly say why it remains `1 unit`.

## Resources

Use these bundled resources:

- [references/rubric.md](references/rubric.md): bucket definitions, ranges, and scoring cues
- [references/calibration-examples.md](references/calibration-examples.md): example estimates, including a `30 unit` case
- `scripts/calc_units.py`: deterministic calculator for bucket totals and band labels

## Calculator

Run the bundled calculator after choosing bucket values:

```bash
python3 scripts/calc_units.py \
  --clarification 2 \
  --context 5 \
  --implementation 10 \
  --validation 6 \
  --coordination 3 \
  --risk 4
```

Use `--json` when another tool or script should consume the result.
