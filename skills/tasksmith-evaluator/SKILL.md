---
name: tasksmith-evaluator
description: Independently supervise and evaluate one Tasksmith task after `tasksmith:worker` works on a scaffold created by `tasksmith:task:create`. Use when Codex needs to inspect `./tasksmith/tasks/{ID}-{title}`, verify status, dependencies, quantitative and qualitative acceptance evidence, and generate concrete pass/fail feedback such as `tasksmith:evaluator`.
---

# Tasksmith Evaluator

Judge whether one created Tasksmith task is actually complete.
Treat the task directory and repository evidence as the source of truth, not the worker's claim.

## Single-Agent Boundary

Complete this evaluation inside the current agent run.
Do not use `spawn_agent` or any other interactive sub-agent or delegation tool to inspect evidence or write the verdict.
If the evaluation cannot be completed safely in one run, return `차단됨` or `수정필요` with the missing prerequisite instead of delegating hidden work.

## Responsibility Boundary

Do all of the following:

1. Read one task directory created by `tasksmith-task-create`.
2. Re-check dependency readiness before trusting any completion claim.
3. Inspect the task files and the repository artifacts that the worker says satisfy the goal.
4. Re-run the qualitative checklist when it exists.
5. Produce a clear verdict and actionable feedback.
6. Persist the feedback in `평가결과.md` inside the task directory.

Do not do any of the following:

- execute a different task than the one under review
- silently finish missing implementation work on behalf of the worker
- mark a task passed because files exist without checking the goal
- trust checked boxes or `완료` status without evidence

## Workflow

Follow this sequence:

1. Resolve the evaluation brief.
   Run `python3 skills/tasksmith-evaluator/scripts/prepare_evaluation.py --task TASK-001 --format json`.
2. Gate on dependencies.
   If an upstream task is missing or not `완료`, return `차단됨`. Do not pass the task even if local files changed.
3. Inspect the task contract.
   Read `목표.md`, `통과기준-정량.md`, and `통과기준-정성.py`. Treat `목표.md` as scope and `통과기준-*` as closure.
4. Inspect worker evidence directly.
   Open the files, diffs, and test outputs that are necessary to prove the task goal was met.
5. Re-run qualitative review.
   Execute `python3 통과기준-정성.py --json` from the task directory and use its exit code plus the reported checks as evidence.
6. Write the evaluation result.
   Create or replace `평가결과.md` using the format in [references/evaluation-contract.md](references/evaluation-contract.md).
7. Keep task state truthful.
   Leave the task `완료` only when the evidence supports a pass. Otherwise change it to `보류` or `차단됨` and explain why in `현재상태.md`.

## Quick Start

Inspect one task:

```bash
python3 skills/tasksmith-evaluator/scripts/prepare_evaluation.py \
  --task TASK-001 \
  --format json
```

Render a compact brief:

```bash
python3 skills/tasksmith-evaluator/scripts/prepare_evaluation.py \
  --task /absolute/path/to/tasksmith/tasks/TASK-001-로그인-오류-문구-정리 \
  --format brief
```

If the repository root is not the current working directory, pass:

```bash
--root /absolute/path/to/repo/tasksmith/tasks
```

## Verdict Rules

Use these verdict meanings:

- `통과`: the repository work matches `목표.md`, every quantitative item is checked with evidence, dependencies are resolved, and `통과기준-정성.py` exits `0`
- `수정필요`: the worker made progress, but the task is incomplete, unverifiable, or inconsistent with the goal
- `차단됨`: an external prerequisite such as an upstream dependency or missing task context prevents valid completion

Keep the verdict conservative.
Artifact existence alone is not enough for `통과`.

## Feedback Rules

Write `평가결과.md` with these sections:

1. `# 평가 결과`
2. `- 작업 ID: ...`
3. `- 판정: 통과 | 수정필요 | 차단됨`
4. `## 요약`
5. `## 확인한 근거`
6. `## 미충족 항목`
7. `## 다음 작업 제안`

Keep each section concise and specific.
Reference concrete files, commands, or unchecked criteria wherever possible.

## State Rules

Apply these rules every time:

- prefer `완료`, `보류`, or `차단됨` as the post-evaluation task state
- leave `완료` unchanged only when the verdict is `통과`
- change the task to `차단됨` when unresolved dependencies or missing prerequisites caused the failure
- change the task to `보류` when the worker can continue later but the current attempt does not satisfy the task contract
- append short evidence notes under `## 메모` in `현재상태.md` rather than rewriting the task contract

## Resources

Use these bundled resources:

- `scripts/prepare_evaluation.py`: resolve a task, summarize dependency and acceptance status, and re-run the qualitative checklist
- [references/evaluation-contract.md](references/evaluation-contract.md): verdict meanings, feedback file format, and state update rules

## Failure Rules

Do not use `spawn_agent` or any other interactive sub-agent feature while evaluating this task.

## Tasksmith Context

The conceptual namespace is `tasksmith:evaluator`, and the filesystem skill id is `tasksmith-evaluator`.
Use this skill after `tasksmith-worker` finishes or claims to finish one created task.
Keep the responsibility boundary sharp:

- `tasksmith-unit`: size work
- `tasksmith-divider`: split work into atomic leaves
- `tasksmith-task-create`: create one task scaffold
- `tasksmith-worker`: execute one created task
- `tasksmith-evaluator`: judge the worker result and write feedback
