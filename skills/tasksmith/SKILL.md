---
name: tasksmith
description: Orchestrate the full Tasksmith workflow for one user request by resolving the repository Tasksmith root, launching or reusing `tasksmith-dispatcher.py`, delegating recursive task creation to `tasksmith-divider`, and monitoring execution until the task tree either completes or reaches a terminal blocker. Use when Codex needs to run work through Tasksmith end to end, bootstrap a new Tasksmith workspace, dispatch existing waiting tasks, or respond to prompts such as `tasksmith`, `tasksmith:run`, `run this through Tasksmith`, or `orchestrate this request with Tasksmith`.
---

# Tasksmith

Orchestrate one request through the entire Tasksmith system.
Keep the current session as the supervisor, use `tasksmith-divider` to materialize tasks, and use `tasksmith-dispatcher.py` to drive `tasksmith-processor` runs over the created task tree.
Use CLI-launched non-interactive agents for every delegated Tasksmith step.
Do not substitute interactive delegation tools such as `spawn_agent`, `send_input`, `wait_agent`, `resume_agent`, or `close_agent`.

## Root Resolution

Resolve the Tasksmith root before launching anything.
Use this order:

1. Use `./.tasksmith` when it already exists.
2. Else use `./tasksmith` when it already exists.
3. Else create `./.tasksmith/tasks`, `./.tasksmith/logs`, and `./.tasksmith/runtime/dispatcher`, then use `./.tasksmith`.

Treat the chosen root as authoritative for the whole run.
Because several lower-level Tasksmith scripts default to `./tasksmith/tasks`, pass an explicit absolute task path or `--root` whenever the chosen root is not `./tasksmith`.

## Workflow

Follow this sequence:

1. Normalize the request.
   Extract the requested outcome, constraints, dependencies, and the done condition that should govern the whole Tasksmith run.
2. Resolve the Tasksmith root.
   Create the missing directories if needed so the dispatcher has `tasks/`, `logs/`, and `runtime/dispatcher/`.
3. Start or reuse exactly one dispatcher for that root.
   Do not launch a second dispatcher against the same root if one is already active.
4. Delegate decomposition to `tasksmith-divider`.
   Run the divider through a fresh non-interactive agent session so it creates atomic leaf tasks under the resolved Tasksmith root. If that runner is unavailable, stop and report the blocker instead of using an interactive sub-agent.
5. Let the dispatcher process runnable tasks.
   The dispatcher launches `tasksmith-processor`, which in turn launches fresh `tasksmith-worker` and `tasksmith-evaluator` runs.
6. Monitor the task tree and dispatcher logs.
   Re-read task states, `평가결과.md`, and dispatcher logs until the run clearly finishes or stalls.
7. Return the outcome truthfully.
   Report success only when all observed tasks are `완료`. Report a blocker when the tree is stalled in `보류`, `차단됨`, or dependency-blocked `대기`.

## Dispatcher Control

Prefer a background dispatcher so the current session can continue supervising.
Use a command shape like this from the repository root:

```bash
TASKSMITH_ROOT="${TASKSMITH_ROOT:-$(pwd)/.tasksmith}"
mkdir -p "$TASKSMITH_ROOT/tasks" "$TASKSMITH_ROOT/logs" "$TASKSMITH_ROOT/runtime/dispatcher"
nohup python3 tasksmith-dispatcher.py "$TASKSMITH_ROOT" \
  > "$TASKSMITH_ROOT/logs/tasksmith-dispatcher.console.log" 2>&1 &
```

Do not use files under `<tasksmith-root>/runtime/dispatcher/` as dispatcher liveness. Those JSON files describe per-task processor runs, not the dispatcher process itself.
Reuse an existing dispatcher only when you can confirm the dispatcher process is still alive for that exact root, for example with a command match such as `pgrep -af "python3 tasksmith-dispatcher.py <absolute-tasksmith-root>"`.
If dispatcher liveness is unclear, verify the process directly before deciding to reuse it or start a replacement.
When a foreground run is more appropriate, `python3 tasksmith-dispatcher.py <absolute-tasksmith-root>` is acceptable, but keep in mind that the dispatcher exits only when all observed tasks are `완료` or when it receives a signal.

## Divider Invocation

Treat `tasksmith-divider` as the only component allowed to recursively split the request into Tasksmith tasks.
Do not inline the divider algorithm inside the interactive supervisor session.

Use a fresh non-interactive invocation such as:

```bash
codex exec --skip-git-repo-check --full-auto --ephemeral -C "$(pwd)" \
  "Use \$tasksmith-divider to divide this request into Tasksmith tasks. \
Tasksmith root: $TASKSMITH_ROOT. \
Pass explicit task paths or --root whenever needed. \
User request: <request>"
```

If another isolated runner is already standardized for the repository, use it instead of open-coding CLI flags.
What matters is the contract:

- fresh non-interactive execution
- divider-owned recursive splitting
- leaf tasks created inside the resolved Tasksmith root
- no hidden dependence on the interactive orchestration conversation

In Codex runtimes, `spawn_agent`, `send_input`, `wait_agent`, `resume_agent`, and `close_agent` are not acceptable substitutes for this execution boundary.
If the required non-interactive runner cannot be launched, fail closed and report the blocker.

## Monitoring Rules

Monitor these surfaces during the run:

- `<tasksmith-root>/logs/tasksmith-dispatcher.log`
- `<tasksmith-root>/logs/dispatcher-runs/*.stdout.log`
- `<tasksmith-root>/logs/dispatcher-runs/*.stderr.log`
- `<tasksmith-root>/tasks/*/현재상태.md`
- `<tasksmith-root>/tasks/*/평가결과.md`

Treat the overall run as successful only when both conditions hold:

- every observed task is `완료`
- the dispatcher has exited or is otherwise clearly idle after reaching all-`완료`

Treat the overall run as terminally blocked when both conditions hold:

- no runnable tasks remain
- at least one task is `보류`, `차단됨`, or still `대기` only because an upstream dependency is not `완료`

When the run is terminally blocked, stop waiting for dispatcher exit and report the blocking task IDs, current statuses, and the concrete reason from `현재상태.md` or `평가결과.md`.

## Failure Rules

Do not run multiple dispatchers against the same Tasksmith root.
Do not run the divider body directly in the interactive supervisor session.
Do not use interactive sub-agents or delegation tools as a substitute for `codex exec`, `claude -p`, or another non-interactive runner.
Do not claim end-to-end success because some tasks finished while others are still blocked.
Do not rely on `./tasksmith/tasks` defaults when the active root is `./.tasksmith`.
Do not silently rewrite blocked tasks into success; surface the blocker and stop.

## Resources

Use these repository resources:

- `tasksmith-dispatcher.py`: filesystem watcher and dispatcher for runnable tasks
- `skills/tasksmith-divider/SKILL.md`: recursive task decomposition contract
- `skills/tasksmith-processor/SKILL.md`: per-task worker/evaluator retry loop
- `skills/tasksmith-worker/SKILL.md`: single-task execution contract
- `skills/tasksmith-evaluator/SKILL.md`: independent evaluation and feedback contract
- `skills/tasksmith-task-create/SKILL.md`: task scaffold creation contract

## Tasksmith Context

The conceptual namespace is `tasksmith`, and the filesystem skill id is `tasksmith`.
Use this skill as the top-level Tasksmith orchestrator.
Keep the responsibility boundary sharp:

- `tasksmith`: supervise the full request, dispatcher lifecycle, and overall outcome
- `tasksmith-unit`: size work for the divider stop rule
- `tasksmith-divider`: recursively split the request into leaf tasks
- `tasksmith-task-create`: materialize one leaf task
- `tasksmith-worker`: execute one created task
- `tasksmith-evaluator`: judge one worker result
- `tasksmith-processor`: loop worker and evaluator for one task
