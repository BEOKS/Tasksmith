---
name: tasksmith-clarifier
description: Clarify underspecified user requests into a highly detailed execution-ready brief with explicit objective, scope boundaries, deliverables, constraints, assumptions, dependencies, decision points, acceptance criteria, and open questions. Use when Codex needs to refine ambiguous requests before planning or DAG decomposition, especially for multi-step work, research, coding, document production, or any task where the success criteria, output shape, workflow, or boundaries are not yet explicit.
---

# Tasksmith Clarifier

Convert an underspecified request into a detailed clarification brief that a planner can consume without carrying the full conversation forward.
Reduce avoidable ambiguity before DAG decomposition by making objective, scope, deliverables, constraints, dependencies, assumptions, success criteria, and missing decisions explicit.

Do not solve the task here. Make the task precisely definable and safely plannable.

## Data Storage Rule

Persist any Tasksmith handoff data, intermediate artifacts, or reusable run state that this skill creates for downstream skills under the workspace `.tasksmith/` directory.
Use temporary paths outside `.tasksmith/` only for short-lived scratch files that are consumed immediately and do not represent durable Tasksmith state.

## Do This

Follow this sequence:

1. Restate the request in operational terms.
2. Extract what is already known.
3. Detect what is still ambiguous.
4. Expand the request into concrete execution dimensions, expected outputs, and acceptance conditions.
5. Ask only the smallest set of questions needed to unblock planning.
6. If a safe assumption is cheaper than a question, record the assumption and proceed.
7. Produce a structured clarification brief with enough detail for downstream decomposition.

## Clarify In This Order

Prefer this field order so the output is stable and easy for later skills to consume:

1. Objective
2. User intent and problem statement
3. Scope
4. Out of scope
5. Deliverables
6. Acceptance criteria
7. Constraints
8. Inputs and dependencies already available
9. Risks or ambiguity hotspots
10. Assumptions
11. Open questions
12. Suggested next step

## Ask Only High-Leverage Questions

Ask for information in this priority order:

1. Missing success criteria
2. Missing output format or artifact shape
3. Missing workflow, audience, usage context, or operational scenario
4. Hard constraints such as time, tools, policy, budget, environment, or dependencies
5. Priority tradeoffs such as speed vs. completeness
6. Nice-to-have preferences

Do not ask questions that can be answered by:

- inspecting the workspace
- inferring from explicit user wording
- making a low-risk default assumption

When questions are necessary:

- ask at most 1 to 3 tightly scoped questions
- phrase them so each answer changes planning or execution
- avoid broad discovery interviews
- prefer concrete options when the tradeoff is non-obvious
- if the environment supports it and structured user input would help, you may use Plan mode to ask the minimal set of high-leverage questions
- stop asking once planning can begin safely

## Prefer Assumptions Over Interviews

Make a default assumption instead of asking when all of the following are true:

- the assumption is low risk
- the assumption is easy to revise later
- the assumption does not silently change the user's core intent
- writing the assumption down preserves transparency

Escalate with a question instead of assuming when the missing information would change:

- whether the task should be done at all
- what artifact should be produced
- what constraints must be obeyed
- how success will be judged

## Output Contract

Return a brief with these headings:

```md
Objective
- ...

User Intent / Problem Statement
- ...

Scope
- ...

Out of Scope
- ...

Deliverables
- ...

Acceptance Criteria
- ...

Constraints
- ...

Available Inputs
- ...

Risks / Ambiguity Hotspots
- ...

Assumptions
- ...

Open Questions
- ...

Suggested Next Step
- ...
```

Save the clarified requirements as a Markdown file (`.md`) in the workspace rather than leaving them only in the chat response.

If no questions remain, explicitly write `Open Questions` as `- None`.

Keep bullets concrete and specific. Prefer enough detail that a downstream planner could produce tasks without re-reading the transcript.
Include explicit details when they can be inferred or confirmed, such as:

- who the output is for
- what exact artifact should exist at the end
- what decisions are already fixed versus still pending
- what constraints are binding versus flexible
- what would cause the work to be considered done
- what information is missing but non-blocking

## Defaults

If the user does not specify an item, prefer these defaults unless context clearly suggests otherwise:

- aim for a minimally sufficient first version
- preserve existing repository patterns
- optimize for correctness before polish
- prefer editable text or code artifacts over presentation-heavy output
- call out assumptions instead of hiding them
- prefer explicit acceptance criteria over vague notions of completion

## Handoff Standard

Treat the brief as a handoff artifact for later Tasksmith skills.
Write it so a planner can decompose work into nodes without re-reading the entire transcript.
Persist the handoff artifact as an `.md` file so downstream skills can consume a stable saved brief.

Include enough detail to answer these downstream questions:

- what is the user trying to achieve
- why do they want it and for whom
- what outputs are expected
- what "done" looks like in observable terms
- what constraints or dependencies matter
- what risks or uncertainties could change the plan
- what is still unresolved
- what should happen next

## Tasksmith Context

Treat this skill as the front door for the wider Tasksmith skill family.
Use it before planning skills when the request is still fuzzy.
Hand off a detailed clarified brief to later skills rather than the full conversation transcript.

The conceptual namespace is `tasksmith:clarifier`, but the filesystem skill id is `tasksmith-clarifier` to satisfy skill naming constraints.
