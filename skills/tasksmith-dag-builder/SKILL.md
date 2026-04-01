---
name: tasksmith-dag-builder
description: Convert a Tasksmith `plan.md` produced by `tasksmith:clarifier` into a complete DAG graph by repeatedly adding the next single node, updating request coverage marks, and stopping only when no uncovered work remains. Use when Codex must orchestrate full DAG construction over multiple isolated runs, call `tasksmith:dag` for node specification and graph mutation, and enforce that every node-building step runs through `tasksmith:exec` or an equivalent fresh session instead of sharing the planner session.
---

# Tasksmith DAG Builder

Turn a clarified Tasksmith plan into a fully covered DAG without letting the planner session absorb every node-building decision.
Use this skill as the orchestration layer above `tasksmith:dag` and `tasksmith:exec`.

## Data Storage Rule

Persist any Tasksmith handoff data, intermediate artifacts, or reusable run state that this skill creates for downstream skills under the workspace `.tasksmith/` directory.
Use temporary paths outside `.tasksmith/` only for short-lived scratch files that are consumed immediately and do not represent durable Tasksmith state.

## Purpose

Do all of the following:

1. Read the latest `plan.md`.
2. Inspect the current authoritative DAG JSON.
3. Add exactly one next node per loop.
4. Update `plan.md` so the covered request span is shown as `~~text~~ [N#]`.
5. Repeat until no uncovered request span should become another node.

Do not execute business-work nodes here unless the workflow explicitly includes execution after graph completion.
Do not let the planner and node-builder share one long-running session.

## Core Rule

Treat node construction itself as isolated execution.
When deciding the next node, run that step through `tasksmith:exec` or an equivalent subagent execution path that creates a fresh session.

The isolated node-building run must not share:

- the planner conversation state
- previous node-builder session state
- unrelated node contexts

Pass only the minimum planning payload needed for that one node-building step.

## Required Inputs

Expect these artifacts before starting:

- `plan.md` from `tasksmith:clarifier` or a later planner pass
- the authoritative DAG JSON file used by `tasksmith:dag`
- any existing planner notes needed to understand remaining uncovered work

If the DAG JSON does not exist yet, initialize it through `tasksmith:dag`'s mutation script before the first loop.

## Loop

Follow this loop strictly:

1. Read `plan.md` and the DAG JSON.
2. Find the next uncovered request span.
3. Decide whether that span should become a node now.
4. Build a minimal prompt for one isolated node-builder run.
5. Invoke `tasksmith:exec` to run that node-builder step in a fresh session.
6. In that isolated run, use `tasksmith:dag` to:
   - inspect the current graph
   - choose the next node id
   - add one new node
   - connect real dependencies
   - update `plan.md` coverage marks
7. Return the structured result to the planner.
8. Re-read the updated artifacts.
9. Stop only when no uncovered span should be converted into another node.

Default to one node per loop, not batches.
Use a larger batch only if the user explicitly changes the policy.

## Isolated Node-Builder Brief

Prepare each isolated run with only:

- DAG file path
- `plan.md` path
- current uncovered span or the smallest relevant excerpt
- existing node ids and dependency facts needed for placement
- node sizing constraints
- mutation requirement to use `tasksmith:dag`
- output format for the planner

Do not pass the whole planner transcript unless a specific node genuinely requires it.

Use a brief shape like:

```text
Role: isolated DAG node-builder
Goal: add the next single DAG node that covers the next uncovered part of plan.md
Artifacts:
- /abs/path/plan.md
- /abs/path/.tasksmith/dag.json
Constraints:
- use tasksmith:dag for DAG mutations
- add exactly one new node
- update coverage marks in plan.md
- do not execute the node's business task
- assume no planner context beyond this brief
Success Criteria:
- one new node exists in DAG JSON
- dependency edges are valid
- the corresponding request span is marked with ~~...~~ [N#]
- unresolved request spans remain untouched
Output:
- node_id
- covered_span_summary
- dependency_summary
- stop_recommendation
```

## Delegation Boundary

Split responsibilities clearly:

- `tasksmith:dag-builder` decides the loop, prepares isolated briefs, checks stop conditions, and records progress.
- `tasksmith:dag` performs DAG-aware planning and graph mutation for the one node being added.
- `tasksmith:exec` guarantees fresh-session execution for that one node-building run.

If the environment offers another equivalent isolated execution primitive, it may substitute for `tasksmith:exec` only if it guarantees a fresh session.

## Coverage Rule

Update coverage only after the node is successfully written to the DAG JSON.
Use visible strikethrough plus node references in `plan.md`.

Allowed forms:

```md
~~research competitors~~ [N4]
~~summarize findings~~ [N5][N6]
```

Never strike text speculatively.
Never mark a span as covered before the node exists in the authoritative DAG.

## Stop Condition

Stop the loop when any of these is true:

- all actionable request spans are already mapped to nodes
- the only remaining gaps are explicitly deferred or blocked ambiguities
- the remaining text is commentary that should not become a node

When stopping, leave a short note in `plan.md` or planner notes that explains why DAG construction is complete.

## Failure Handling

If an isolated node-builder run fails:

1. Record the failed attempt, node intent, and error.
2. Decide whether the failure is transient, artifact-related, or ambiguity-related.
3. Retry only when a retry changes something material.
4. If the remaining request cannot be decomposed safely, leave it uncovered and note the blocker.

Do not silently patch the DAG by hand around a failed isolated run unless the DAG file itself is corrupted and manual repair is the only recovery path.

## Output Contract

After the full loop finishes, leave:

- an updated `plan.md`
- an updated authoritative DAG JSON
- enough planner notes or execution logs to show:
  - which spans were converted
  - which isolated run produced each node
  - why the loop stopped

Keep the graph authoritative in JSON and the coverage view human-readable in Markdown.

## Tasksmith Context

Use this skill after `tasksmith:clarifier` has produced `plan.md`.
Use it before any broad DAG execution phase when the graph is not yet complete.
Treat `tasksmith:dag-builder` as the full-DAG constructor that repeatedly calls `tasksmith:dag` through `tasksmith:exec` until the request has been fully transformed into a DAG graph.

The conceptual namespace is `tasksmith:dag-builder`, and the filesystem skill id is `tasksmith-dag-builder`.
