# Tasksmith Unit Scoring Rubric

Score every request across six buckets.
Use whole numbers only.
After scoring, sum the bucket values and clamp the result to a minimum of `1`.

## Agent-Neutral Baseline

Apply this rubric against a generic single-agent LLM baseline, not a brand-specific environment.
Ignore small product differences such as editor UX, shell wrappers, or prompt formatting helpers.
Only count additional work when the task itself requires more reasoning, context, implementation, validation, coordination, or risk handling.

## Buckets

| Bucket | Range | What it measures | Scoring cues |
| --- | --- | --- | --- |
| Clarification | `0-5` | Missing decisions or ambiguity that materially change execution | `0`: fully specified. `1`: one minor assumption. `2-3`: missing success criteria, inputs, or workflow details. `4-5`: exploratory or shape-changing ambiguity. |
| Context | `0-8` | How much context gathering or codebase discovery is required before acting | `0`: prompt or obvious local context is enough. `1-2`: one file, doc, or small subsystem. `3-5`: multiple files, one subsystem, or unfamiliar docs. `6-8`: cross-repo, cross-domain, or deep archaeology. |
| Implementation | `1-12` | Minimum number of independently meaningful production slices needed to deliver the result | `1`: one atomic slice. `2-4`: a few tightly related slices. `5-8`: one feature or analysis package with several parts. `9-12`: many independently completable slices or artifacts. |
| Validation | `0-8` | Verification breadth required to claim completion safely | `0`: trivial sanity check. `1-2`: one direct check or a few simple tests. `3-5`: mixed manual and automated checks, or several test surfaces. `6-8`: integration, end-to-end, migration, performance, or failure-path testing. |
| Coordination | `0-6` | Dependency and integration overhead across systems, artifacts, people, or staged handoffs | `0`: self-contained. `1-2`: one dependency or environment. `3-4`: several dependent surfaces. `5-6`: multiple chains, staged rollout, or complex contract alignment. |
| Risk | `0-6` | Expected rework from unknowns, statefulness, or failure-sensitive behavior | `0`: routine work. `1-2`: minor unknowns. `3-4`: meaningful chance of false starts or rework. `5-6`: discovery-heavy or state-sensitive work where the first attempt is unlikely to be enough. |

## Interpretation Notes

- Treat `Implementation` as the core delivery burden even for non-coding work.
- For research, design, or documentation tasks, map each independently necessary analysis or output slice into `Implementation`.
- Use `Clarification` for ambiguity before action, not for unknown technical difficulty.
- Use `Risk` for rework likelihood after the task shape is already understood.
- Do not double-count the same concern in both `Context` and `Risk`.

## Quick Heuristics

Use these shortcuts when the request is easy to classify:

- One clear edit, one clear test, one subsystem: usually `1-2` units total.
- One feature with code changes plus tests across one subsystem: often `4-8` units.
- Cross-cutting feature or migration touching multiple contracts: often `9-15` units.
- Multi-surface initiative with persistence, retries, integration, and end-to-end validation: often `16-30` units.

## Decomposition Hint

If the total is larger than `4`, assume the work probably contains more than one atomic node.
If the total is larger than `8`, assume explicit planning should happen before execution.
If the total is larger than `15`, assume execution should happen in multiple waves.
