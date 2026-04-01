# Processor Loop Contract

Supervise one existing task until it passes or reaches a terminal stop condition.

## Inputs

Expect one task identifier or one task directory under:

```text
./tasksmith/tasks/{ID}-{title}
```

Expect the worker and evaluator skills to own the task mutations.
The processor owns orchestration only.

## Loop Semantics

Run attempts in this order:

1. worker
2. evaluator
3. branch on evaluator verdict

Treat the evaluator verdicts like this:

- `통과`: finish successfully
- `수정필요`: retry the worker with the evaluator's unmet items
- `차단됨`: finish with blocked status

## Retry Input

Before each retry, pass the worker only the minimum context needed:

- task ID or task path
- repository root when not running from it
- latest `평가결과.md`
- any blocking note from `현재상태.md`

Do not re-send the entire planner conversation when the task files already contain the authoritative contract.

## Stall Detection

Treat the loop as stalled when all of the following are true:

1. the evaluator returns `수정필요` again
2. the main unmet item is materially the same as the previous attempt
3. the worker did not change repository evidence or task evidence enough to move the task forward

When stalled, stop and report the repeated unmet item rather than hiding an infinite loop.

## Summary Contract

Return a compact summary with:

- task ID
- final verdict
- number of worker attempts
- path to the latest `평가결과.md`
- next action for either the next worker, the divider, or a human
