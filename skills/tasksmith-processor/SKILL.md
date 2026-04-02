---
name: tasksmith-processor
description: Supervise one Tasksmith task by running a deterministic processor loop around fresh non-interactive `tasksmith:worker` and `tasksmith:evaluator` sessions until the evaluator returns `통과` or a terminal blocker is confirmed. Use when Codex needs to orchestrate retryable execution for one existing task in `./tasksmith/tasks/{ID}-{title}`, respond to prompts such as `tasksmith:processor`, or drive the loop through `skills/tasksmith-processor/scripts/run_processor.py`.
---

# Tasksmith Processor

Supervise one Tasksmith task through a worker/evaluator retry loop.
Treat `tasksmith-worker` as the implementation step and `tasksmith-evaluator` as the gate.
Use the bundled scripts first so loop control stays deterministic and repeatable.

## Script-First Workflow

1. Resolve the task context.
   Run `python3 skills/tasksmith-processor/scripts/prepare_processor.py --task TASK-001 --format brief`.
2. Run the processor loop.
   Run `python3 skills/tasksmith-processor/scripts/run_processor.py --task TASK-001`.
3. Inspect the result.
   Trust `평가결과.md` as the authoritative verdict source, not worker stdout.

If the Tasksmith root is not `./tasksmith/tasks`, pass `--root <absolute-task-root>`.
If the repository root is not the current working directory, pass `--workspace-root <absolute-repo-root>`.

## Execution Boundary

Run every worker and evaluator attempt through a fresh non-interactive agent session.
Use isolated runners such as `codex exec` or `claude -p`.
Do not execute the worker or evaluator body inline inside the supervising session.
Do not replace those runs with `spawn_agent` or any other interactive delegation tool.

## Core Algorithm

The loop contract is:

```text
processor(task):
  do:
    nonInteractiveAgent {
      tasksmith:worker(task)
    }
    verdict = nonInteractiveAgent {
      tasksmith:evaluator(task)
    }
  while verdict == non-pass
```

Interpret `non-pass` conservatively:

- `통과`: stop successfully
- `수정필요`: run another worker attempt using the latest `평가결과.md`
- `차단됨`: stop and report the blocker instead of spinning forever

`run_processor.py` makes these decisions from task files:

- resolve the task directory deterministically
- launch one fresh worker session
- launch one fresh evaluator session
- parse `평가결과.md` for the authoritative verdict
- detect stalls when the same unmet item repeats without material task or repository change
- stop on `통과`, `차단됨`, worker/evaluator runner failure, or max-attempt limit

## Runner Configuration

Use the default preset when possible:

```bash
python3 skills/tasksmith-processor/scripts/run_processor.py --task TASK-001
```

Override the runner when needed:

```bash
python3 skills/tasksmith-processor/scripts/run_processor.py \
  --task TASK-001 \
  --runner claude \
  --runner-bin claude
```

Use explicit command templates when the repository already has a wrapper:

```bash
python3 skills/tasksmith-processor/scripts/run_processor.py \
  --task TASK-001 \
  --worker-command 'my-runner worker --task {task_id} --root {tasks_root}' \
  --evaluator-command 'my-runner evaluator --task {task_id} --root {tasks_root}'
```

Supported template placeholders:

- `{task_id}`
- `{task_dir}`
- `{tasks_root}`
- `{tasksmith_root}`
- `{workspace_root}`
- `{evaluation_report}`
- `{prompt}`

Use `{prompt}` only when the wrapper expects a raw non-interactive prompt string.

## Retry Rules

Apply these rules on every retry:

- re-read `평가결과.md` before the next worker run
- tell the worker to address only the concrete gaps named by the evaluator
- keep retries scoped to the same task; do not silently split or create sibling tasks
- preserve truthful task files between attempts
- stop retrying when the evaluator returns `차단됨`

Treat a repeated `수정필요` reason plus unchanged task/workspace fingerprints as a stalled loop.
Stop and report the repeated gap instead of hiding an infinite retry.

## Suggested Output

Use this response shape:

```md
Processor Result
- Task: TASK-001
- Final Verdict: 통과 | 수정필요 | 차단됨
- Worker Attempts: 2
- Last Evaluation: ./tasksmith/tasks/TASK-001-.../평가결과.md

Next Action
- ...
```

If the loop stalls, say so explicitly and name the repeated evaluator reason.

## Failure Rules

Do not bypass the evaluator because the worker claims success.
Do not merge multiple tasks into one processor loop.
Do not keep retrying a task that is blocked by unresolved dependencies.
Do not overwrite evaluator findings with optimistic summaries.
When the task should be re-scoped or decomposed, stop and hand control back to `tasksmith-divider` or a human operator instead of continuing the same loop.
Do not use `spawn_agent` or any other interactive sub-agent feature as a substitute for worker or evaluator runs.

## Resources

Use these bundled resources:

- `scripts/prepare_processor.py`: resolve the task and summarize the latest processor-loop context
- `scripts/run_processor.py`: run the deterministic worker/evaluator loop
- `scripts/task_io.py`: shared task resolution, report parsing, and stall-detection helpers
- [references/processor-loop.md](references/processor-loop.md): loop control rules, verdict handling, and prompt handoff guidance

## Tasksmith Context

The conceptual namespace is `tasksmith:processor`, and the filesystem skill id is `tasksmith-processor`.
Use this skill after a task already exists and needs supervised execution through repeated worker and evaluator passes.
Keep the responsibility boundary sharp:

- `tasksmith-unit`: size work
- `tasksmith-divider`: split work into atomic leaves
- `tasksmith-task-create`: create one task scaffold
- `tasksmith-worker`: execute one created task
- `tasksmith-evaluator`: judge one worker result
- `tasksmith-processor`: supervise worker and evaluator retries for one task
