---
name: tasksmith-processor
description: Supervise one Tasksmith task by repeatedly launching fresh non-interactive `tasksmith:worker` and `tasksmith:evaluator` runs until the evaluator returns `통과` or a terminal blocker is confirmed. Use when Codex needs to orchestrate retryable execution for one existing task in `./tasksmith/tasks/{ID}-{title}`, respond to prompts such as `tasksmith:processor`, or implement a processor loop that delegates each attempt through isolated runners such as `codex exec` or `claude -p`.
---

# Tasksmith Processor

Supervise one Tasksmith task through a worker and evaluator retry loop.
Treat `tasksmith-worker` as the implementation step and `tasksmith-evaluator` as the gate that decides whether another worker pass is required.

## Execution Boundary

Run every worker and evaluator attempt through a fresh non-interactive agent session.
Use isolated runners such as:

- `codex exec`
- `claude -p`

Do not execute the worker body or evaluator body inline inside the supervising session.
The processor may remain in the current session, but each delegated run must be fresh and non-interactive.
Do not replace those runs with `spawn_agent` or any other interactive delegation tool.

## Core Algorithm

Implement this control flow:

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

## Workflow

Follow this sequence:

1. Resolve the target task.
   Accept either a task ID such as `TASK-001` or an absolute task directory path.
2. Inspect the latest task state.
   Read `현재상태.md` and `평가결과.md` when it exists so the next worker attempt starts from the newest evidence.
3. Launch the worker in a fresh non-interactive session.
   Pass only the task identifier, the repository path when needed, and the latest evaluator feedback.
4. Launch the evaluator in a second fresh non-interactive session.
   Treat the evaluator verdict as authoritative for loop control.
5. Branch on the verdict.
   Stop on `통과`, retry on `수정필요`, and stop on `차단됨`.
6. Return a compact processor summary.
   Include the final verdict, the number of worker attempts, and the current task path.

## Retry Rules

Apply these rules on every retry:

- re-read `평가결과.md` before the next worker run
- tell the worker to address only the concrete gaps named by the evaluator
- keep retries scoped to the same task; do not silently split or create sibling tasks
- preserve truthful task files between attempts
- stop retrying when the evaluator returns `차단됨`

If the same `수정필요` reason repeats without any material repository or task-file change, stop and report the loop as stalled instead of hiding an infinite retry.

## Non-Interactive Invocation

Use any runner that guarantees a fresh session for each delegated step.

Examples:

```bash
codex exec --ephemeral "Use \$tasksmith-worker to execute TASK-001"
```

```bash
codex exec --ephemeral "Use \$tasksmith-evaluator to evaluate TASK-001"
```

```bash
claude -p "Use \$tasksmith-worker to execute TASK-001"
```

```bash
claude -p "Use \$tasksmith-evaluator to evaluate TASK-001"
```

If a local wrapper already standardizes non-interactive execution, use that wrapper.
What matters is the contract:

- one fresh session per worker attempt
- one fresh session per evaluator attempt
- no hidden dependence on interactive planner state
- evaluator feedback carried forward explicitly

In Codex runtimes, `spawn_agent`, `send_input`, `wait_agent`, `resume_agent`, and `close_agent` do not satisfy this contract.
If a required non-interactive run cannot be launched, stop and report the blocker instead of delegating interactively.

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
