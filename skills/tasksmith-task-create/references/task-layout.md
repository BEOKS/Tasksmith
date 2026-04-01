# Task Layout

Create task directories under:

```text
./tasksmith/tasks/{ID}-{title}
```

Normalize `{title}` by trimming whitespace, replacing inner spaces with `-`, and removing filesystem-unsafe characters.

## Required Files

Every task directory must contain:

- `현재상태.md`: current workflow state
- `의존하는-작업-ID.md`: task IDs this task depends on
- `의존되는-작업-ID.md`: task IDs that depend on this task
- `목표.md`: task objective and expected outcome
- `통과기준-정량.md`: measurable acceptance criteria
- `통과기준-정성.py`: executable qualitative acceptance checks

## Status Vocabulary

Prefer these status values:

- `대기`
- `진행중`
- `완료`
- `보류`
- `차단됨`

Use a different value only when the request explicitly requires it.

## Dependency Rules

- Keep task IDs globally unique within one `tasks/` root.
- Write one task ID per bullet.
- Keep duplicates out.
- If task `A` depends on task `B`, add `A` to `B/의존되는-작업-ID.md` when that directory already exists.
- If task `A` is depended on by task `C`, add `A` to `C/의존하는-작업-ID.md` when that directory already exists.
- When rewriting task `A`, remove stale reciprocal links from neighbors that are no longer connected to `A`.

## Example Tree

```text
tasksmith/tasks/
└── TASK-001-로그인-오류-문구-정리/
    ├── 목표.md
    ├── 의존되는-작업-ID.md
    ├── 의존하는-작업-ID.md
    ├── 현재상태.md
    ├── 통과기준-정량.md
    └── 통과기준-정성.py
```
