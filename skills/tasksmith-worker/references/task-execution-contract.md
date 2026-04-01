# Task Execution Contract

Treat one task directory as the authoritative contract for one bounded worker run.
For `tasksmith-worker`, `현재상태.md` is read-only.

## Task Directory

Expect this layout:

```text
./tasksmith/tasks/{ID}-{title}
├── 현재상태.md
├── 의존하는-작업-ID.md
├── 의존되는-작업-ID.md
├── 목표.md
├── 통과기준-정량.md
└── 통과기준-정성.py
```

## Source Of Truth

Read the files with these meanings:

- `현재상태.md`: current lifecycle state, read as input only by `tasksmith-worker`
- `의존하는-작업-ID.md`: upstream tasks that must be `완료` before execution
- `의존되는-작업-ID.md`: downstream tasks that may rely on this task
- `목표.md`: the execution boundary and expected outcome
- `통과기준-정량.md`: measurable completion checklist
- `통과기준-정성.py`: executable qualitative review checklist

Treat `목표.md` as the scope boundary.
Treat `통과기준-*` as the closure boundary.

## Dependency Gate

Before editing repository files:

1. Resolve every task ID in `의존하는-작업-ID.md`.
2. Read each upstream `현재상태.md`.
3. Continue only when every upstream task exists and is `완료`.

If any upstream task is missing or not `완료`, do not begin implementation.
Report which task ID blocked execution, but do not change task state.

## Status File

Keep `현재상태.md` simple.
The first status line is authoritative:

```md
# 현재 상태

- 상태: 진행중

## 메모

- 어떤 이유로 이 상태인지
- 다음 작업자가 이어받기 위해 알아야 할 내용
```

`tasksmith-worker` must not edit this file.

## Quantitative Criteria

Keep `통과기준-정량.md` as a checkbox list.
Check an item only after there is observable evidence such as:

- a passing test command
- a created or modified file in the expected location
- a measurable diff in the repository

Unchecked items mean the task is not done.

## Qualitative Criteria

`통과기준-정성.py` is executable and must reflect the real review state.

Replace placeholder `TODO` values with truthful `PASS` or `FAIL` values before running it.
The task can be reported as effectively complete only when the script exits `0`.

## Completion Rule

Report the task as complete only when all of the following are true:

- upstream dependencies are `완료`
- repository work matches `목표.md`
- quantitative checklist items are checked
- `통과기준-정성.py` exits `0`

Otherwise report the task as blocked or incomplete without editing `현재상태.md`.
