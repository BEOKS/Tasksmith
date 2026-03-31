---
name: tasksmith-dag
description: Expand a Tasksmith planning artifact such as `plan.md` into the next batch of DAG nodes while preserving the current graph state in one authoritative DAG JSON file. Use when Codex needs to read an existing Tasksmith plan, inspect which parts of the request are already covered by nodes, add only the next context-sized nodes, mutate the DAG through a script rather than manual edits, and mark the newly converted request text with strikethrough plus node footnotes.
---

# Tasksmith DAG

Read the current planning artifact, preserve the existing DAG, and add only the next smallest useful batch of nodes.
Treat the DAG JSON file as the single source of truth and mutate it only through the bundled script.
Convert request text into execution-ready node specs without exceeding what one isolated worker session should handle.

## Workflow

Follow this sequence:

1. Read `plan.md` and the current DAG JSON file.
2. Identify which request spans are already mapped to nodes.
3. Find the next uncovered spans that should become nodes now.
4. Add a small batch of new nodes that each fit one worker context.
5. Mutate the DAG JSON only through `scripts/manage_dag.py`.
6. Connect dependencies to existing or newly added nodes through the same script.
7. Mark the covered request spans in `plan.md` with `~~strikethrough~~ [N#]`.
8. Save both artifacts back to disk.

Do not execute the nodes here.
Do not redesign the whole graph if only incremental expansion is needed.
Do not hand-edit node definitions inside the JSON file except when repairing a broken file and no script path is possible.

## Source Of Truth

Store the DAG in exactly one JSON file, for example `tasksmith/dag.json` or another explicit path chosen by the project.
Treat that JSON file as authoritative for:

- node ids
- node fields
- dependency edges
- status and retry metadata
- coverage links back to request spans when the project stores them

Treat `plan.md` as a human-readable planning view, not the authoritative graph store.
When `plan.md` and the JSON disagree, reconcile `plan.md` to the JSON unless the JSON is clearly corrupted.

## Use The Script For All Graph Mutations

Use the bundled script for node creation and graph mutation:

```bash
python3 scripts/manage_dag.py --dag-file /absolute/path/to/dag.json <command> ...
```

Use script commands instead of manual JSON editing for:

- node creation
- node updates
- node deletion
- dependency addition
- dependency removal

Prefer commands such as:

```bash
python3 scripts/manage_dag.py --dag-file /abs/dag.json init
python3 scripts/manage_dag.py --dag-file /abs/dag.json add-node --node-file /tmp/N12.json
python3 scripts/manage_dag.py --dag-file /abs/dag.json update-node --node-id N12 --patch-file /tmp/N12-patch.json
python3 scripts/manage_dag.py --dag-file /abs/dag.json add-dependency --node-id N12 --depends-on N8
python3 scripts/manage_dag.py --dag-file /abs/dag.json remove-dependency --node-id N12 --depends-on N8
python3 scripts/manage_dag.py --dag-file /abs/dag.json delete-node --node-id N12
```

If the script is missing, add it before continuing.
If the DAG file is missing, initialize it through the script before adding nodes.

## Size The Nodes For One Worker Session

Treat each node as the payload for one isolated execution agent.
Keep the node small enough that a downstream worker can succeed with minimal context.

Prefer a node that has:

- one clear goal
- a narrow input set
- a short success checklist
- one primary output artifact

Split a candidate node before adding it if it would require:

- too many independent decisions
- too many source files or documents at once
- both exploration and heavy synthesis in one step
- multiple deliverables that could fail independently
- broad background context from the planner conversation

Prefer over-splitting to under-splitting when unsure, but avoid trivial nodes that add overhead without reducing cognitive load.

## Expand Incrementally

Add only the next batch of nodes, not the entire future graph, unless the artifact clearly asks for full expansion.

Use a default batch size of `3` new nodes.
Reduce the batch size when the uncovered work is ambiguous or tightly coupled.
Increase the batch size only when the remaining uncovered work is clearly separable and each node remains small.

Base each loop on:

- the original user request captured in the artifact
- the already-created nodes
- the dependency graph so far
- any notes from earlier planning loops

## Preserve Graph Continuity

Never renumber existing nodes.
Use the next available node id from the JSON graph.
Preserve existing dependency edges unless the artifact itself shows they are wrong.
Reference existing nodes instead of duplicating them.

For every new node, make these fields explicit in the DAG JSON:

- node id
- goal
- inputs
- depends_on
- constraints
- success criteria
- output contract

Keep wording short and operational so `tasksmith:exec` or an equivalent isolated worker can consume it directly.

Use a JSON shape equivalent to:

```json
{
  "version": 1,
  "nodes": {
    "N12": {
      "id": "N12",
      "goal": "Compare top 5 competitors on pricing and packaging.",
      "inputs": ["research/market-notes.md", "N8:output"],
      "depends_on": ["N8"],
      "constraints": ["Use only local artifacts unless browsing is explicitly allowed."],
      "success_criteria": ["Produce a comparison table with pricing, positioning, and notable gaps."],
      "output_contract": ["Save analysis/competitor-comparison.md"],
      "status": "pending"
    }
  }
}
```

## Mark Converted Request Text

Use visible coverage tracking inside the request-to-graph mapping area.
When a span of user intent is converted into a node, rewrite that span as:

```md
~~original request span~~ [N12]
```

If one request span maps to multiple nodes, attach multiple footnotes in order:

```md
~~research competitors~~ [N12][N13]
```

Only strike text that is genuinely represented by nodes already present in the graph after your edit.
Leave unresolved spans untouched so the next loop can find them.

## Output Contract

Update `plan.md` in place and keep the artifact easy for later loops to diff.
Keep the DAG JSON as the system of record.
Prefer `plan.md` to contain these logical parts when present:

1. Source request or request mapping area
2. Coverage annotations pointing to node ids
3. Dependency summary or graph snapshot derived from the JSON
4. Planner notes or next expansion notes

Reflect each new node in `plan.md` in a stable Markdown shape such as:

```md
### N12
- Goal: Compare top 5 competitors on pricing and feature packaging.
- Inputs:
  - `research/market-notes.md`
  - outputs from `N8`
- Depends on:
  - `N8`
- Constraints:
  - Use only local artifacts unless the plan explicitly allows browsing.
- Success Criteria:
  - Comparison table with pricing, positioning, and notable gaps.
- Output Contract:
  - Save `analysis/competitor-comparison.md`
```

If the file already uses a different stable node template, preserve that template and append the same fields in its existing style.
Do not treat the Markdown block as the authoritative record if the JSON already contains the node.

## Decision Rules

Prefer dependency edges only when they are real prerequisites.
Keep siblings independent when they can run in parallel.
Do not create a parent node that merely repeats its children.
Do not create an execution node that depends on planner-only hidden context.
Do not leave a new node underspecified enough that a worker would need the whole transcript.

When a span is still too ambiguous to decompose safely:

- add a clarification or planning node only if that ambiguity is itself actionable
- otherwise leave the span uncovered and note why in planner notes

## Handoff Standard

Write nodes so a later isolated worker receives only:

- node id
- goal
- required prior artifacts
- allowed tools or limits
- success criteria
- output format

Assume the worker will run in a fresh session and will not share the planner's context.
Optimize the node definitions for isolation, replayability, and selective retry.

## Tasksmith Context

Use this skill after `tasksmith:clarifier` has produced a planning artifact and before `tasksmith:exec` runs worker nodes.
Treat `tasksmith:dag` as the incremental planner that converts remaining request text into context-sized DAG nodes.
Use `scripts/manage_dag.py` as the required mutation layer for the authoritative DAG JSON file.
The conceptual namespace is `tasksmith:dag`, and the filesystem skill id is `tasksmith-dag`.
