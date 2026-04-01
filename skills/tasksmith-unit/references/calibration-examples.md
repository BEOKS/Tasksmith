# Tasksmith Unit Calibration Examples

Use these examples to keep estimates consistent across requests.
Do not match examples mechanically; use them to calibrate scale.

## Example 1: `1 unit`

Request:
`Update one prompt string in tasksmith-worker and adjust the related snapshot test.`

Breakdown:

- Clarification: `0`
- Context: `0`
- Implementation: `1`
- Validation: `0`
- Coordination: `0`
- Risk: `0`

Total: `1 unit`

Why:
One agent can inspect the local files, make one coherent change, and verify the result without a separate planning step.

## Example 2: `4 units`

Request:
`Add a new CLI flag to the isolated runner, update argument parsing, and cover the new path with tests.`

Breakdown:

- Clarification: `0`
- Context: `1`
- Implementation: `2`
- Validation: `1`
- Coordination: `0`
- Risk: `0`

Total: `4 units`

Why:
The work is still compact, but it spans code reading, code change, and explicit test coverage.

## Example 3: `8 units`

Request:
`Inspect the repository, write a plan for a resumable run ledger, identify affected modules, and produce an implementation-ready design doc.`

Breakdown:

- Clarification: `1`
- Context: `3`
- Implementation: `2`
- Validation: `1`
- Coordination: `0`
- Risk: `1`

Total: `8 units`

Why:
This is still mostly one output, but it requires non-trivial discovery and multiple reasoning passes before the design is credible.

## Example 4: `15 units`

Request:
`Add a new DAG node status, thread it through scheduler and worker result handling, update persisted artifacts, and add integration tests.`

Breakdown:

- Clarification: `1`
- Context: `3`
- Implementation: `5`
- Validation: `3`
- Coordination: `1`
- Risk: `2`

Total: `15 units`

Why:
Several subsystems and contracts change together, and the verification burden is high enough that a single atomic node is no longer realistic.

## Example 5: `30 units`

Request:
`Add durable run-resume support to Tasksmith: persist a run ledger, resume incomplete DAGs, wire scheduler stage transitions, reconnect failure propagation paths, and cover success, resume, and failure with end-to-end tests.`

Breakdown:

- Clarification: `2`
- Context: `5`
- Implementation: `10`
- Validation: `6`
- Coordination: `3`
- Risk: `4`

Total: `30 units`

Why:
The request spans state persistence, orchestration semantics, multiple Tasksmith subsystems, and broad verification of failure-sensitive behavior.

Recommendation:
Plan first, decompose into waves, and treat the estimate as evidence that the request is far beyond a single bounded agent task.
