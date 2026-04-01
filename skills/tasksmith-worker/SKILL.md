---
name: tasksmith-worker
description: Execute one Tasksmith task created by `tasksmith:task:create` by reading `./tasksmith/tasks/{ID}-{title}`, checking upstream dependencies, carrying out the goal in `목표.md`, and verifying `통과기준-정량.md` and `통과기준-정성.py` without changing task state. Use when Codex needs to work one created Tasksmith task end to end, respond to prompts such as `tasksmith:worker`, or turn a scaffolded task directory into completed repository work with truthful execution evidence.
---

# Tasksmith Worker

Execute exactly one created Tasksmith task and keep the task directory truthful.
Treat the task files as the execution contract, not as loose guidance.
Treat `현재상태.md` as read-only input for this skill.

## Single-Agent Boundary

Complete this task inside the current agent run.
Do not use `spawn_agent` or any other interactive sub-agent or delegation tool to inspect, implement, or verify the task.
If the task is too large or ambiguous for one run, report the blocker or handoff point truthfully instead of delegating hidden work.

## Responsibility Boundary

Do all of the following:

1. Read one task directory created by `tasksmith-task-create`.
2. Check `의존하는-작업-ID.md` before starting implementation.
3. Perform only the repository work required by `목표.md`.
4. Verify the measurable checks in `통과기준-정량.md`.
5. Update `통과기준-정성.py` to reflect the real review result.
6. Leave task state unchanged and report execution results truthfully.

Do not do any of the following:

- execute multiple tasks at once
- silently expand scope beyond the task goal
- ignore incomplete or missing upstream dependencies
- mark a task `완료` without evidence
- edit `현재상태.md` or otherwise change task state

## Workflow

Follow this sequence:

1. Resolve the task and inspect its contract.
   Run `python3 skills/tasksmith-worker/scripts/prepare_task.py --task TASK-001 --json`.
2. Gate on dependencies.
   If any upstream task is missing or not `완료`, stop and report the blocker. Do not edit `현재상태.md`.
3. Execute the task goal.
   Use `목표.md` as the boundary. Read only the local files needed to finish this task.
4. Verify quantitative acceptance.
   Turn each unchecked item in `통과기준-정량.md` into an observable command, diff, or file existence check. Mark completed items as checked.
5. Verify qualitative acceptance.
   Replace `TODO` statuses in `통과기준-정성.py` with truthful `PASS` or `FAIL` values, then run the script.
6. Finish truthfully.
   Report whether the task is effectively complete based on the quantitative checklist and `통과기준-정성.py`, but do not change task state.

## Quick Start

Inspect one task:

```bash
python3 skills/tasksmith-worker/scripts/prepare_task.py \
  --task TASK-001 \
  --json
```

Render a compact brief:

```bash
python3 skills/tasksmith-worker/scripts/prepare_task.py \
  --task /absolute/path/to/tasksmith/tasks/TASK-001-로그인-오류-문구-정리 \
  --format brief
```

If the repository root is not the current working directory, pass:

```bash
--root /absolute/path/to/repo/tasksmith/tasks
```

## State Rules

Apply these rules every time:

- Keep the first `- 상태:` line in `현재상태.md` authoritative and read-only.
- Do not edit `현재상태.md`.
- If execution is blocked or incomplete, report that in your response instead of changing task state.
- Preserve dependency files as one task ID per bullet.
- Leave quantitative criteria measurable and qualitative criteria executable.

Use these status meanings when interpreting dependency readiness or reporting outcome:

- `대기`: work has not started yet
- `진행중`: the worker is actively executing the task
- `완료`: repository work and acceptance checks are both done
- `보류`: work stopped intentionally without an external blocker
- `차단됨`: execution cannot continue because of a missing dependency, missing context, or failing prerequisite

## Verification Rules

Use these rules when closing the task:

- Run explicit commands when the quantitative checklist names them.
- If a quantitative item is phrased as an outcome, verify it through repository state or test output before checking it off.
- Do not leave `TODO` in `통과기준-정성.py` after claiming the task is finished.
- Run `python3 통과기준-정성.py` from the task directory after editing the review statuses.
- Keep failure evidence concise and specific enough for the next worker to continue, but do not write it into `현재상태.md`.

## Failure Rules

Do not treat the task as complete when any upstream dependency remains unresolved.
Do not claim closure if the qualitative script still exits non-zero.
Do not rewrite the task goal to match work that already happened; change the work or leave the task incomplete.
When the task contract is ambiguous, stop and report the ambiguity instead of guessing across scope boundaries.
Do not use `spawn_agent` or any other interactive sub-agent feature while executing this task.

## Resources

Use these bundled resources:

- `scripts/prepare_task.py`: resolve a task ID or path, summarize the task contract, and report dependency readiness
- [references/task-execution-contract.md](references/task-execution-contract.md): canonical interpretation of task files, dependency gating, and completion semantics

## Tasksmith Context

The conceptual namespace is `tasksmith:worker`, and the filesystem skill id is `tasksmith-worker`.
Use this skill after `tasksmith-task-create` has created a task directory.
Keep the responsibility boundary sharp:

- `tasksmith-unit`: size work
- `tasksmith-divider`: split work into atomic leaves
- `tasksmith-task-create`: create one task scaffold
- `tasksmith-worker`: execute one created task
- `tasksmith-evaluator`: judge whether the worker result actually passes
