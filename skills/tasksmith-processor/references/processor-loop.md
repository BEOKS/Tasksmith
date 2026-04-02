# Processor Loop Contract

`tasksmith-processor` owns orchestration only.
Prefer `scripts/run_processor.py` over open-coded loop logic.

## Inputs

- one task ID or one task directory
- one fresh non-interactive worker run per attempt
- one fresh non-interactive evaluator run per attempt
- latest `평가결과.md` carried into the next worker attempt

## Verdict Rules

- `통과`: stop successfully
- `수정필요`: run another worker attempt against the evaluator's concrete unmet items
- `차단됨`: stop and surface the blocker

Treat `평가결과.md` as the authoritative verdict source, not worker stdout.

## Stall Rule

Treat the loop as stalled when both are true:

1. the evaluator repeats the same unmet item
2. the task or workspace shows no material change across attempts

When stalled, stop and report the repeated unmet item instead of retrying indefinitely.

## Summary

Return:

- task ID
- final verdict
- worker attempt count
- latest `평가결과.md` path
- next action
