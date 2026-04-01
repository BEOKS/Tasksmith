---
name: tasksmith-divider
description: Recursively decompose a broad request into atomic Tasksmith tasks by estimating each request with `tasksmith:unit`, splitting any request larger than `1 unit` into smaller child requests, and sending each `1 unit` leaf to `tasksmith:task:create`. Run each divider invocation through a fresh non-interactive agent session such as `codex exec` or `claude -p`, not through an interactive planning session. Use when Codex needs to turn a large request into a tree of executable Tasksmith tasks, recursively split until each leaf fits one bounded single-agent session, or respond to prompts such as `tasksmith:divider`, `divide this into Tasksmith tasks`, or `split recursively until every leaf is 1 unit or less`.
---

# Tasksmith Divider

Recursively split one request into smaller requests until each leaf is small enough for one single-agent session.
Treat `tasksmith:unit` as the stop rule and `tasksmith:task:create` as the leaf materializer.

## Execution Boundary

Execute `divider(request)` only through a non-interactive mode agent.
Use a fresh session such as:

- `codex exec`
- `claude -p`

Do not run the recursive sizing, splitting, or leaf task creation logic directly inside an interactive chat session.
The interactive session may prepare the brief and launch the non-interactive run, but the actual `divider` body must execute in the non-interactive agent.
Do not replace that boundary with `spawn_agent` or any other interactive delegation tool.

Treat every recursive invocation as its own fresh execution boundary unless the chosen non-interactive runner already guarantees that the whole recursive call tree remains isolated from the interactive planner state.

## Core Algorithm

Implement this logic exactly:

```text
divider(request):
  nonInteractiveAgent {
    estimate = tasksmith:unit(request)
    if estimate <= 1:
      tasksmith:task:create(request)
      return
    children = split(request)
    for child in children:
      divider(child)
  }
```

Re-estimate every child independently.
Do not copy the parent estimate into the child.
A split is valid only if each child is narrower than the parent and the children together still cover the parent intent.

## Workflow

Follow this sequence:

1. Normalize the current request.
   Extract the objective, deliverable, constraints, dependencies, and done condition.
2. Launch a fresh non-interactive agent for the current divider invocation.
   Pass only the current request, required local context, and the divider rules.
3. Size the request with `tasksmith-unit`.
   Keep the bucket breakdown, not just the total.
4. If the result is `<= 1 unit`, convert the request into a Tasksmith task spec and create it with `tasksmith-task-create`.
5. If the result is `> 1 unit`, split the request into the next smallest useful child requests.
6. Order children by prerequisite direction.
   Recurse into prerequisites before dependents so created task IDs can be referenced in `--depends-on`.
7. Invoke each child divider call through a non-interactive agent again.
8. Repeat until every leaf is atomic.
9. Return the division tree and the created task list.

## Non-Interactive Invocation

Use any runner that guarantees non-interactive execution and no session carryover from the planner.

Examples:

```bash
codex exec --ephemeral "Use \$tasksmith-divider to divide: <request>"
```

```bash
claude -p "Use \$tasksmith-divider to divide: <request>"
```

If a local wrapper already standardizes isolated agent execution, use that wrapper instead of open-coding CLI flags.
What matters is the execution contract:

- non-interactive
- fresh session
- compact prompt
- no hidden dependency on the interactive planner conversation

In Codex runtimes, `spawn_agent`, `send_input`, `wait_agent`, `resume_agent`, and `close_agent` do not satisfy this contract.
If no non-interactive runner is available, stop and report the blocker instead of continuing interactively.

## Split Rules

Use [references/splitting-rules.md](references/splitting-rules.md) when choosing children.

Always ensure:

- each child has one clear goal
- each child has its own observable done condition
- siblings have minimal overlap
- dependencies between siblings are explicit
- at least one child is strictly smaller than the parent in both scope and unit estimate
- the recursion makes progress; do not create children that restate the parent

Prefer `2-4` children per split.
Prefer asymmetric splits when one child can reduce uncertainty or unlock the rest.
If you cannot produce children that are all meaningfully smaller, refine the split axis before recursing.

## Atomic Leaf Handling

When a request estimates to `1 unit` or less:

- generate a concise task title
- allocate the next task ID with `scripts/allocate_task_ids.py`
- prepare `goal`, `depends_on`, `depended_by`, `quant_criterion`, and `qual_criterion`
- invoke `tasksmith-task-create`
- record the created directory path for the final summary

Map a leaf request into task-create inputs like this:

- `title`: one concrete deliverable, not a project slogan
- `goal`: outcome-focused statement of what exists when the leaf is done
- `depends_on`: only direct prerequisite leaf task IDs
- `quant_criterion`: measurable checks or commands
- `qual_criterion`: review questions that remain binary enough to mark `PASS` or `FAIL`

## ID Allocation

Use the bundled helper to reserve the next task ID:

```bash
python3 skills/tasksmith-divider/scripts/allocate_task_ids.py --count 1
```

Use `--root` if the repository stores tasks outside `./tasksmith/tasks`.
If multiple leaves will be created in one pass, you may reserve several IDs at once with `--count N`.

## Suggested Output

Use this response shape so the recursion is easy to audit:

```md
Division Result
- Root Request: ...
- Root Estimate: 5 units
- Status: split | atomic

Split Tree
- DIV-ROOT (5 units): ...
- DIV-001 (1 unit): ...
- DIV-002 (2 units): ...
- DIV-003 (2 units): ...

Created Tasks
- TASK-001: ...
- TASK-002: ...

Open Edges
- TASK-002 depends on TASK-001
```

If no split is needed, say so explicitly and list the single created task.
If task creation is intentionally deferred, return leaf specs instead of pretending the task exists.

## Failure Rules

Do not recurse on vague children such as `implement the rest` or `finish everything else`.
Do not create a leaf task above `1 unit` unless the user explicitly overrides the stop rule.
When the request cannot be split safely because the boundary itself is unclear, create one clarifying or boundary-defining child first instead of guessing.
Do not silently fall back to interactive execution because the non-interactive runner is inconvenient.
Do not use `spawn_agent` or any other interactive sub-agent feature as a fallback for divider recursion.

## Resources

- `scripts/allocate_task_ids.py`: allocate the next sequential Tasksmith task IDs from `./tasksmith/tasks`
- [references/splitting-rules.md](references/splitting-rules.md): child-request quality rules and recursive split examples

## Tasksmith Context

The conceptual namespace is `tasksmith:divider`, and the filesystem skill id is `tasksmith-divider`.
Use `tasksmith-unit` for the stop condition and `tasksmith-task-create` for leaf creation.
