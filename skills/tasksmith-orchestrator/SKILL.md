---
name: tasksmith-orchestrator
description: Orchestrate the full Tasksmith lifecycle from request intake to final result by deciding when to clarify requirements, build or extend the DAG, execute ready nodes, trigger failure propagation, replan when needed, and assemble the final user-facing outcome. Use when Codex needs a single control-plane skill for complex multi-step work that should run through the Tasksmith architecture instead of ad hoc one-off delegation, especially when session isolation, resumable execution, structured run records, or graph-level recovery matter.
---

# Tasksmith Orchestrator

Drive the whole Tasksmith workflow without collapsing planning, execution, evaluation, and recovery into one long session.
Use this skill as the top-level control plane above the rest of the Tasksmith skill family.

## Core Rule

Treat orchestration as stateful control, not as direct work execution.
Do not execute business-work nodes in the orchestrator session.
Do not let planner reasoning leak into node execution sessions.
Delegate each specialized step to the corresponding Tasksmith skill and keep the handoff artifacts explicit.

Keep these boundaries sharp:

- `tasksmith-orchestrator`: choose the next stage, maintain run state, decide when to escalate or stop, and assemble the final result
- `tasksmith-clarifier`: refine the request into an execution-ready brief
- `tasksmith-dag-builder`: turn `plan.md` into a fully covered DAG through isolated node-building runs
- `tasksmith-dag`: mutate the authoritative DAG through its script
- `tasksmith-scheduler`: dispatch ready DAG nodes and update graph-visible statuses
- `tasksmith-loop`: retry a single node when revision is warranted
- `tasksmith-worker`: execute one node
- `tasksmith-evaluator`: judge one node result
- `tasksmith-exec`: provide the fresh isolated session
- `tasksmith-propagator`: recover after upstream failure or deadlock
- `tasksmith-benchmark`: evaluate architecture quality after runtime work is complete

If a path bypasses these boundaries and performs node work inside the orchestrator session, treat that as a design violation.

## Use This Skill When

Use this skill when any of the following is true:

- a user request should be handled as a full Tasksmith run rather than a single isolated node
- the request is complex enough to justify clarification, DAG construction, scheduling, and possible recovery
- the team needs one stable entrypoint that decides which Tasksmith sub-skill to call next
- the work must remain resumable with persisted run artifacts and stage transitions
- the system needs a run ledger that ties together plan artifacts, DAG revisions, node attempts, propagation passes, and final deliverables
- the task may require replanning after failure rather than stopping at the first broken node

Do not use this skill for:

- one-off request clarification only
- manual DAG editing without full-run control
- single-node execution
- standalone benchmark reporting with no live runtime orchestration

## Responsibilities

Do all of the following:

1. Choose or create a run id and working artifact directory.
2. Decide whether the request needs clarification before planning.
3. Ensure a persisted clarification brief such as `plan.md` exists.
4. Ensure the authoritative DAG JSON exists and is expanded enough for execution.
5. Start or resume DAG execution through the scheduler.
6. Detect terminal success, blocked execution, or deadlock conditions.
7. Trigger propagation or replanning when normal scheduling cannot finish the objective safely.
8. Record every stage transition, artifact reference, and major decision in the run ledger.
9. Decide when the system should escalate to the user.
10. Assemble the final user-facing result from successful node outputs and run artifacts.

## Workflow

Follow this sequence:

1. Read the user request and inspect the workspace for any existing Tasksmith artifacts.
2. Create or resume a run directory.
3. If the request is underspecified, invoke `tasksmith-clarifier` and persist `plan.md`.
4. If no execution-ready DAG exists or the current DAG does not fully cover the clarified request, invoke `tasksmith-dag-builder`.
5. Invoke `tasksmith-scheduler` to execute ready nodes.
6. Inspect the scheduler result.
7. If the graph completed successfully enough to satisfy the objective, assemble the final outcome and stop.
8. If the scheduler stopped because of upstream failures, blocked nodes, or deadlock, decide whether to:
   - invoke `tasksmith-propagator`
   - invoke `tasksmith-dag-builder` again for replanning
   - escalate to the user
9. Repeat the schedule or repair cycle until the objective is completed or safely escalated.
10. Persist a final summary for the run.

Default to explicit stage transitions instead of implicit handoffs.
At each transition, save the input artifact paths, output artifact paths, and the reason for moving to the next stage.

## Stage Transition Rules

Use these decision rules:

1. Clarify before planning when success criteria, deliverables, or constraints are materially ambiguous.
2. Build or extend the DAG before scheduling when the clarified request still has uncovered actionable spans.
3. Schedule only when the DAG is valid enough that at least one node can eventually become ready.
4. Propagate only after the scheduler reaches a non-success terminal state with unresolved work remaining.
5. Replan only when propagation or execution evidence shows that the current decomposition is no longer adequate.
6. Escalate only when no safe automatic path preserves the intended objective or when key tradeoffs require user choice.

Prefer the least invasive next step that keeps the overall objective alive.
Do not restart the whole run when a smaller repair step will do.

## Run Ledger

Persist run artifacts under a stable path such as:

```text
tasksmith/runs/run-001/
```

Maintain at least these artifacts:

- `request.md`
- `plan.md` or a reference to the latest clarified brief
- `dag.json` or a reference to the authoritative DAG path
- `run-ledger.json`
- `final-summary.md`

The run ledger should capture:

- `run_id`
- original request summary
- current stage
- stage history with timestamps
- active artifact paths
- scheduler run references
- propagation run references
- whether the run is resumable
- final status
- escalation notes when present

When available, also record:

- isolated session ids or execution envelope references returned by worker and evaluator runs
- node attempt counts
- retry decisions
- DAG revisions and why they happened

## Minimal Handoffs

Pass only the minimum artifact set needed for the next skill.
Prefer persisted files over replaying large chat histories.

Examples:

- `tasksmith-clarifier` receives the raw request and local context needed to clarify it
- `tasksmith-dag-builder` receives `plan.md`, the DAG path, and any remaining uncovered spans
- `tasksmith-scheduler` receives the authoritative DAG path, workspace root, and runtime options
- `tasksmith-propagator` receives the DAG path, scheduler stop reason, trigger node, and evidence artifacts

Do not use the orchestrator session as hidden shared memory for downstream stages.

## Resume Behavior

Before starting a new run, inspect whether the workspace already contains a compatible incomplete run.
Resume instead of duplicating when all of the following are true:

- the run goal still matches the current request closely enough
- artifact paths are still valid
- the DAG and ledger are readable
- resuming is cheaper and safer than rebuilding

When resuming:

- preserve the existing `run_id`
- append to the stage history instead of rewriting it
- record why the run resumed and from which stage

When starting fresh:

- record why the prior run was not reused

## Escalation Standard

Escalate to the user when:

- clarification is still required after safe assumptions are exhausted
- propagation found multiple recovery paths with non-obvious tradeoffs
- the only remaining path would materially change the final deliverable or evidence quality
- infrastructure issues prevent safe continuation
- the run produced partial success but not enough evidence to claim completion

When escalating, present:

- the current stage
- what succeeded
- what failed or remains unresolved
- what automatic recovery was attempted
- what decision or information is needed next

## Finalization

Do not end the run merely because all node processes stopped.
End the run only when one of these is true:

- the clarified objective has been satisfied by the available successful outputs
- the user has been given a clear escalation with the minimum decision needed
- the run has been explicitly abandoned with the blocker recorded

The final summary should include:

- requested objective
- completed deliverables
- remaining gaps or caveats
- key artifact locations
- whether the run can resume later

## Defaults

- default first step: inspect for an existing run, then clarify if needed
- default graph policy: prefer incremental DAG construction rather than one giant plan dump
- default execution policy: keep node execution isolated through `tasksmith-exec`
- default repair policy: prefer propagation before full replanning
- default persistence policy: save every stage transition in the run ledger

## Tasksmith Context

Use this skill as the main entrypoint for end-to-end Tasksmith operation.
It is the control plane that ties together clarification, DAG construction, isolated execution, recovery, and final result assembly while preserving strict session isolation at node-execution boundaries.

The conceptual namespace is `tasksmith:orchestrator`, and the filesystem skill id is `tasksmith-orchestrator`.
