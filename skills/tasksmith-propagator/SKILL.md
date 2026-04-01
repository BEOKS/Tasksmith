---
name: tasksmith-propagator
description: Analyze a failed or blocked Tasksmith DAG node, trace its downstream impact, and decide whether the graph can continue through replacement inputs, rewired dependencies, explicit skips, or user escalation. Use when `tasksmith-scheduler` or another orchestrator reaches a terminal upstream failure, when unresolved nodes remain after normal execution, when Tasksmith must preserve the overall objective instead of stopping at the first failed node, or when Codex needs a structured failure-propagation pass that keeps planner reasoning separate from isolated node execution sessions.
---

# Tasksmith Propagator

Recover graph progress after a node fails without pretending the original plan is still intact.
Use this skill to determine whether downstream nodes truly require the missing output, whether an alternative path can satisfy them, and whether the DAG should be patched, partially skipped, or escalated to the user.

## Data Storage Rule

Persist any Tasksmith handoff data, intermediate artifacts, or reusable run state that this skill creates for downstream skills under the workspace `.tasksmith/` directory.
Use temporary paths outside `.tasksmith/` only for short-lived scratch files that are consumed immediately and do not represent durable Tasksmith state.

## Core Rule

Treat failure propagation as graph-level reasoning, not node execution.
Do not re-run business-work nodes inside this skill.
Do not let the propagator absorb worker or evaluator session state.
When a repair requires new node execution, hand the repaired graph back to `tasksmith-scheduler`, `tasksmith-loop`, or `tasksmith-worker`.

Keep these boundaries sharp:

- `tasksmith-propagator`: inspect failure impact, determine recovery options, patch graph state, and escalate when no safe recovery exists
- `tasksmith-scheduler`: dispatch ready nodes and stop when failure propagation is needed
- `tasksmith-loop`: retry one node only when the node itself is revisable
- `tasksmith-worker`: execute one node attempt
- `tasksmith-evaluator`: judge one node attempt
- `tasksmith-dag`: own DAG mutations through the shared mutation script
- `tasksmith-exec`: guarantee fresh isolated execution for actual node work

## Use This Skill When

Use this skill when any of the following is true:

- a node ended in `failed` or `blocked` and unresolved downstream nodes remain
- the scheduler stopped because no ready nodes remain while parts of the graph are still incomplete
- a failed node output might be replaceable by another artifact or by relaxing a downstream requirement
- a downstream node may be skippable without losing the user's final objective
- the system needs a structured explanation of what changed in the DAG after a failure

Do not use this skill for:

- first-pass DAG construction
- ordinary worker revision cycles that stay inside one node
- normal topological scheduling when no failure recovery is needed
- semantic evaluation of node outputs

## Inputs

Expect these artifacts before starting:

- the authoritative DAG JSON
- the scheduler summary or stop reason that triggered propagation
- the failed or blocked node id
- the latest loop, worker, and evaluator artifacts for that node when they exist
- any existing outputs from upstream successful nodes that may substitute for the missing result
- the clarified `plan.md` or equivalent planning artifact when graph intent must be re-read

Treat the DAG JSON as the source of truth for node definitions and statuses.
Treat worker and evaluator artifacts as evidence for what failed and why.

## Propagation Workflow

Follow this sequence:

1. Read the authoritative DAG JSON and identify the trigger node.
2. Classify the trigger failure as one of:
   - transient execution failure
   - missing prerequisite or environment issue
   - semantic failure where the node cannot currently satisfy its contract
   - planning failure where the node itself is no longer the right decomposition
3. Find all downstream nodes that directly or transitively depend on the trigger node.
4. For each downstream node, inspect what input from the failed node it actually needs.
5. Decide whether the dependency is:
   - still mandatory
   - satisfiable by an alternative existing artifact
   - satisfiable by rewiring to another node
   - removable because the downstream node can be narrowed
   - impossible to satisfy without changing the user's requirements
6. Record one propagation decision per affected node.
7. Apply only the graph mutations needed to represent the chosen recovery path.
8. Mark nodes that should no longer run as `skipped` only when the skip is explicit and justified.
9. Leave a propagation report that explains the trigger, affected nodes, chosen actions, and remaining blockers.
10. Hand the graph back to the scheduler if runnable work still exists.

## Allowed Recovery Actions

Prefer the least invasive action that preserves the user's real objective.

Allowed actions:

- keep a downstream dependency unchanged because the failure is local and the graph should wait for a planner decision
- rewire a downstream node to depend on another existing node that provides the needed artifact
- update a downstream node's `inputs`, `constraints`, `success_criteria`, or `output_contract` when the node can be narrowed safely
- mark a downstream node `skipped` when its value was optional or no longer relevant after recovery
- add a new clarification or replanning node only when the ambiguity itself is now actionable
- escalate to the user when no safe substitute or graph rewrite preserves the intended outcome

Disallowed actions:

- silently deleting failed nodes to make the graph appear healthy
- changing the user objective without recording the tradeoff
- re-running business-work nodes directly inside the propagation session
- using hidden planner context that is not reflected in the DAG or propagation notes

## Decision Rules

Use these rules in order:

1. Preserve the final objective before preserving the original decomposition.
2. Prefer using already-existing successful artifacts before inventing new work.
3. Prefer rewiring or narrowing one downstream node over rewriting large parts of the graph.
4. Skip only when the skipped node is genuinely unnecessary for the remaining objective.
5. Escalate when a proposed recovery would materially change deliverables, scope, correctness, or user risk.

If a downstream node depends on the failed node only nominally, remove or replace that dependency.
If a downstream node still needs the missing content but another node already produced an equivalent artifact, rewire it.
If no equivalent artifact exists but a smaller replacement node would recover the path, add that node through `tasksmith-dag` semantics and keep it explicit in the DAG.
If none of these are safe, stop and escalate.

## Mutation Rule

Mutate the authoritative DAG through `tasksmith-dag/scripts/manage_dag.py`.
Use patch-based updates instead of hand-editing the JSON file.

Typical propagation mutations include:

- updating a node's `depends_on`
- updating a node's `inputs`
- updating a node's `constraints`
- updating a node's `success_criteria`
- updating a node's `output_contract`
- marking a node `skipped`
- appending recovery metadata such as `propagation_ref`, `propagation_reason`, or `recovery_source`

If the graph needs a new node, create it as a normal explicit DAG node rather than describing it only in notes.

## Output Contract

Leave a propagation report in Markdown or JSON under a stable workspace path such as:

```text
.tasksmith/propagation-runs/run-001/
```

Persist at least:

- `summary.json` or `summary.md`

The report should capture:

- trigger node id
- trigger status and failure summary
- affected downstream node ids
- per-node dependency analysis
- chosen recovery action per node
- exact DAG mutations that were applied
- nodes marked `skipped`
- nodes still blocked
- whether the scheduler may resume
- any user escalation questions that remain

## Escalation Standard

Escalate to the user when:

- the only recovery path changes the final deliverable
- the only recovery path reduces correctness or evidence quality in a material way
- multiple plausible recovery paths exist with non-obvious tradeoffs
- the graph lacks enough information to choose a safe substitute
- the failure reflects a genuine impossibility rather than a local execution issue

When escalating, present:

- what failed
- which downstream goals are now affected
- what recovery options exist
- what tradeoff each option introduces
- which option you recommend

## Validation

Before first use and after substantial edits:

1. Run one DAG where an upstream node fails but a sibling output can satisfy the downstream node after rewiring.
2. Run one DAG where a downstream node should be explicitly marked `skipped`.
3. Run one DAG where propagation ends in user escalation because no safe alternative exists.
4. Confirm all graph mutations are reflected in the authoritative DAG JSON rather than only in notes.
5. Run `quick_validate.py` on the skill folder.

## Tasksmith Context

Use this skill after `tasksmith-scheduler` reaches a blocked or failure-driven terminal state and before benchmark analysis layers.
This is the recovery layer that distinguishes “one node failed” from “the whole task is impossible.”

The conceptual namespace is `tasksmith:propagator`, and the filesystem skill id is `tasksmith-propagator`.
