---
name: tasksmith-task-create
description: Create a Tasksmith task scaffold under `./tasksmith/tasks/{ID}-{title}` with status, dependency, goal, and acceptance files. Use when an agent needs to initialize a new Tasksmith task, create `목표.md`, write measurable acceptance criteria in Markdown, create executable qualitative acceptance checks in Python, or respond to requests phrased like `tasksmith:task:create`.
---

# Tasksmith Task Create

Create a new Tasksmith task directory and the required tracking files.

## Single-Agent Boundary

Create the scaffold inside the current agent run.
Do not use `spawn_agent` or any other interactive sub-agent or delegation tool to draft the task files.
If required task details are missing, return the missing fields explicitly instead of delegating hidden work.

## Workflow

Follow this sequence:

1. Normalize the request.
   Extract the task ID, title, status, dependencies, dependents, goal text, and any quantitative or qualitative acceptance hints.
2. Create the scaffold.
   Run `python3 skills/tasksmith-task-create/scripts/create_task.py ...` from the repository root when possible. If the current working directory is not the repository root, always pass an explicit absolute `--root` that points at the active Tasksmith `tasks/` directory.
3. Review the generated files.
   Open the new task directory and replace placeholders with task-specific content when the request includes more detail than the initial scaffold.
4. Keep links consistent.
   Let the script update reciprocal dependency files when referenced task directories already exist.
5. Return the created path and any follow-up edits that still need human decisions.

## Quick Start

If the current directory is the repository root, run:

```bash
python3 skills/tasksmith-task-create/scripts/create_task.py \
  --id TASK-001 \
  --title "로그인 오류 문구 정리" \
  --status 대기 \
  --depends-on TASK-000 \
  --depended-by TASK-010 \
  --goal "로그인 실패 시 사용자에게 원인과 다음 행동을 명확히 안내한다." \
  --quant-criterion "관련 테스트 명령이 모두 성공한다." \
  --quant-criterion "에러 문구가 정의된 화면과 API 응답에 모두 반영된다." \
  --qual-criterion "문구가 사용자 관점에서 이해 가능하다." \
  --qual-criterion "다른 인증 흐름과 어조가 일관된다."
```

If you are outside the repository root, add:

```bash
--root /absolute/path/to/repo/tasksmith/tasks
```

If the active Tasksmith root is `./.tasksmith`, use:

```bash
--root /absolute/path/to/repo/.tasksmith/tasks
```

## Required Output

The scaffold must contain these files:

- `현재상태.md`
- `의존하는-작업-ID.md`
- `의존되는-작업-ID.md`
- `목표.md`
- `통과기준-정량.md`
- `통과기준-정성.py`

## Editing Rules

Apply these rules every time:

- Keep the directory name in `{ID}-{title}` format.
- Preserve the provided task ID exactly and keep it globally unique within the chosen `tasks/` root.
- Use explicit status values such as `대기`, `진행중`, `완료`, `보류`, or `차단됨`.
- Keep dependency files as one ID per bullet.
- Keep `통과기준-정량.md` objectively measurable.
- Keep `통과기준-정성.py` executable and able to return a failing exit code until all manual checks are marked `PASS`.
- When rewriting an existing task with `--force`, keep reciprocal dependency files synchronized by removing stale reverse links as well as adding new ones.

## Resources

Use these bundled resources:

- `scripts/create_task.py`: create the scaffold and optionally synchronize reciprocal dependency links
- [references/task-layout.md](references/task-layout.md): file contract, status vocabulary, and generated output shape

## Failure Rules

Do not use `spawn_agent` or any other interactive sub-agent feature while creating the task scaffold.
