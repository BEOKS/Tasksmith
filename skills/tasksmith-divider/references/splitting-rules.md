# Tasksmith Divider Split Rules

Use this file when the current request is larger than `1 unit` and you need to choose the next recursive child requests.

## What A Good Child Looks Like

A good child request has all of these properties:

- one primary objective
- one observable done condition
- a stable boundary that does not rely on hidden parent context
- narrower scope than the parent
- a likely unit estimate below the parent estimate
- explicit sibling dependencies when they exist

If a child still sounds like a project rather than a task, split again before recursing.

## Preferred Split Axes

Prefer these axes in roughly this order:

1. prerequisite vs dependent work
2. boundary definition vs implementation
3. research vs production change
4. backend vs frontend vs validation
5. core path vs follow-up polish

Prefer asymmetric splits when one child can reduce uncertainty for the rest.
Do not force balanced `50:50` splits.

## Anti-Patterns

Avoid child requests like:

- `finish the rest`
- `misc cleanup`
- `implement everything else`
- `handle remaining issues`
- `full integration` when the concrete surfaces are still mixed together

These do not create recursion progress because they keep the hard part hidden inside one vague bucket.

## Dependency Rules

Make dependencies explicit when one child must exist before another can be created or verified.

Examples:

- `Define API contract` -> `Implement API handler`
- `Create repository contract` -> `Implement service logic`
- `Collect current schema facts` -> `Write migration plan`

When siblings are independent, keep them independent.
Do not invent dependencies only because the parent request mentioned them in one sentence.

## Stop Rule

Stop recursing only when the current request safely fits `1 unit` by the `tasksmith-unit` rubric.
If the estimate is still above `1`, do not create a task yet.

If the request is almost atomic but still contains two different validation surfaces or two independent deliverables, keep splitting.

## Example

Parent request:

```text
Add user export support with API, CSV generation, and admin UI download action.
```

One valid recursive path:

```text
R0 (5 units)
- R1: Define export API contract and response shape. (1 unit)
- R2: Implement CSV generation service and persistence access. (2 units)
- R3: Add admin UI download flow and wiring. (2 units)

R2 (2 units)
- R2.1: Implement export query and domain mapping. (1 unit)
- R2.2: Implement CSV formatter and download response integration. (1 unit)

R3 (2 units)
- R3.1: Add admin UI button and request trigger. (1 unit)
- R3.2: Add success and failure feedback states. (1 unit)
```

Leaf creation order:

1. `R1`
2. `R2.1`
3. `R2.2`
4. `R3.1`
5. `R3.2`

That order keeps prerequisite task IDs available for later `depends_on` links.
