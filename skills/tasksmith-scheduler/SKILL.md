---
name: tasksmith-scheduler
description: Orchestrate full-DAG execution for Tasksmith by reading the authoritative DAG JSON, identifying ready nodes from dependency state, dispatching each ready node through `tasksmith-loop`, and updating node statuses as waves complete. Use when Codex needs graph-level scheduling after planning is finished, especially for topological execution, bounded parallel node dispatch, isolated node runs, or resumable DAG progress across multiple nodes.
---

# Tasksmith Scheduler

Run the whole DAG without collapsing the graph into one long planner session.
Use this skill after `tasksmith-dag-builder` or another planner has produced an execution-ready DAG and you need graph-level orchestration.

## Data Storage Rule

Persist any Tasksmith handoff data, intermediate artifacts, or reusable run state that this skill creates for downstream skills under the workspace `.tasksmith/` directory.
Use temporary paths outside `.tasksmith/` only for short-lived scratch files that are consumed immediately and do not represent durable Tasksmith state.

## Core Rule

The scheduler is the DAG-level orchestrator, not the executor.
It must never execute business-work nodes directly.
Each runnable node must go through `tasksmith-loop`, which in turn keeps `tasksmith-worker` and `tasksmith-evaluator` isolated through `tasksmith-exec`.

Keep these boundaries sharp:

- `tasksmith-scheduler`: choose ready nodes, dispatch waves, update DAG status, stop or resume the graph
- `tasksmith-loop`: retry one node until pass or a terminal non-revision result
- `tasksmith-worker`: execute one node attempt
- `tasksmith-evaluator`: judge one node attempt
- `tasksmith-exec`: provide the fresh isolated session

If a path bypasses `tasksmith-loop` and runs node work in the scheduler session, treat that as a design violation.

## Responsibilities

Do all of the following:

1. Read the authoritative DAG JSON.
2. Determine each node's current effective status.
3. Identify ready nodes whose dependencies have all succeeded.
4. Group ready nodes into a bounded execution wave.
5. Mark dispatched nodes as `running`.
6. Launch one isolated `tasksmith-loop` process per dispatched node.
7. Wait for the wave to finish and collect structured loop summaries.
8. Update each node status in the DAG JSON based on the loop result.
9. Repeat until the DAG reaches a terminal scheduler state.
10. Persist a scheduler summary with wave-by-wave history.

Do not do any of the following:

- create or resize DAG nodes
- repair failed nodes inside the scheduler session
- invent missing dependencies
- silently ignore terminal failures
- merge planner context into worker prompts

## Ready Rule

Treat a node as ready only when all of the following are true:

- its status is absent or one of the scheduler's runnable statuses such as `pending`
- every node in `depends_on` exists
- every dependency status is `success`

Treat a node as not ready when:

- any dependency is still `pending`, `running`, or `needs_revision`
- any dependency is `failed`, `blocked`, or another terminal non-success state
- the graph contains missing dependency references

Do not dispatch speculative work.
Only run nodes that are truly unlocked by the current graph state.

## Scheduler Status Semantics

Use these meanings consistently at the DAG level:

- `pending`: node has not been dispatched yet
- `running`: node is currently being processed by `tasksmith-loop`
- `success`: node passed evaluation and unblocks dependents
- `needs_revision`: reserved for node-level loop internals; the scheduler should normally see the loop continue until another final status
- `failed`: node ran and ended in a terminal failure
- `blocked`: node could not be attempted because prerequisites or required local inputs were missing
- `skipped`: optional explicit terminal status when a later recovery or propagation step decides not to run the node

If the DAG already contains other status strings, preserve them in reports instead of rewriting them blindly.

## Execution Workflow

Follow this sequence:

1. Read the DAG JSON.
2. Validate that dependency references point to real nodes.
3. Compute the ready set.
4. If no ready nodes remain:
   - stop with `success` if all nodes are terminal and successful enough for completion
   - stop with `blocked` if unresolved nodes are waiting on terminal upstream failures
   - stop with `deadlock` if unresolved nodes remain but no legal dispatch is possible
5. Select up to `max_parallel` ready nodes for the next wave.
6. Update those nodes to `running`.
7. Launch one `tasksmith-loop` run per node.
8. Collect each loop summary and map it back to the node.
9. Update node statuses in the authoritative DAG JSON.
10. Save the scheduler wave summary.
11. Re-read the DAG and continue.

## Use The Script

Use the bundled script:

```bash
python3 scripts/run_scheduler.py \
  --dag-file /absolute/path/.tasksmith/dag.json \
  --cwd /absolute/worktree \
  --max-parallel 3 \
  --json
```

Useful variants:

```bash
python3 scripts/run_scheduler.py \
  --dag-file /absolute/path/.tasksmith/dag.json \
  --cwd /absolute/worktree \
  --provider codex \
  --evaluation-provider codex \
  --max-parallel 4 \
  --json

python3 scripts/run_scheduler.py \
  --dag-file /absolute/path/.tasksmith/dag.json \
  --cwd /absolute/worktree \
  --resume \
  --json

python3 scripts/run_scheduler.py \
  --dag-file /absolute/path/.tasksmith/dag.json \
  --cwd /absolute/worktree \
  --dry-run \
  --json
```

## Mutation Rule

Treat the DAG JSON as authoritative and mutate it through `tasksmith-dag/scripts/manage_dag.py`.
Use patch-based node updates rather than hand-editing the JSON file inside the scheduler.

At minimum, write back:

- node `status`
- scheduler-visible status metadata such as `last_run_ref` or `last_scheduler_run`

If the DAG file is corrupted and the mutation script cannot operate, stop and surface the error instead of writing ad hoc repairs.

## Parallel Dispatch

Dispatch only bounded waves.
Default to a conservative `max_parallel` such as `2` or `3` unless the user asks for more.

Keep parallelism at the node level only.
Do not share one loop session across multiple nodes.
Each loop run must have its own process invocation and its own output directory.

When multiple ready nodes exist:

- prefer nodes that are already fully specified
- preserve deterministic ordering by node id when priorities are equal
- avoid starvation by eventually dispatching all ready nodes

## Stop Conditions

Stop the scheduler when any of these is true:

- every node reached `success`
- no ready nodes remain and unresolved nodes are blocked by terminal upstream failures
- no ready nodes remain and the graph appears cyclic, inconsistent, or otherwise deadlocked
- a fatal scheduler infrastructure error prevents safe continuation

Do not pretend the DAG succeeded when unresolved nodes remain.

## Output Contract

Persist scheduler artifacts under a stable workspace path such as:

```text
.tasksmith/scheduler-runs/run-001/
```

Persist at least:

- `summary.json`

The summary should capture:

- DAG path
- scheduler run number
- scheduler final status
- stop reason
- `max_parallel`
- wave list
- per-wave node dispatch order
- per-node loop summary references

## Validation

Before first use and after substantial edits:

1. Run the scheduler in `--dry-run` mode and confirm it selects only ready nodes.
2. Run one small DAG where two independent nodes can execute in parallel.
3. Run one DAG where a dependency failure leaves downstream work unresolved.
4. Confirm node statuses are written back to the DAG JSON through the mutation script.
5. Run `quick_validate.py` on the skill folder.

## Tasksmith Context

Use this skill after the DAG is built and before failure-propagation or benchmark analysis layers.
This is the missing runtime layer that turns a graph of isolated node definitions into an executing multi-node system.

The conceptual namespace is `tasksmith:scheduler`, and the filesystem skill id is `tasksmith-scheduler`.
