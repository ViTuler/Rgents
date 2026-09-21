---
name: code-review
description: "Perform the final engineering review of a completed change — trace every requirement to the code that satisfies it, assess maintainability, architectural fit, complexity, test quality, and scope against the approved plan, and issue a verdict with located, actionable findings. Use when a change has passed functional verification and requires the engineering quality gate."
---

# Code review

## When to use

- You are the Reviewer and a change has passed QA and any activated specialist gates.
- You need to decide whether a change belongs in the codebase, as opposed to whether it works.

## Procedure

### 1. Read the whole change, not the diff in isolation

Read `requirements.json`, `design.json`, `plan.json`, and every specialist report before reading code.
A diff reviewed without its intent produces style commentary instead of engineering judgement.

Confirm the inputs you actually received. A review that ignores an activated specialist report is incomplete.

### 2. Trace requirements to code

For each acceptance criterion, identify the code and test that satisfy it. Two failures to catch here:

- **an unsatisfied or partially satisfied criterion** → blocker
- **a change not traceable to any criterion** → scope creep, blocker regardless of quality

### 3. Correctness against the design

Does the implementation match the approved interfaces and data model? Where it deviates, is the
deviation recorded in `worker-result.json → deviations` with a reason?

- Declared and justified deviation → acceptable
- Silent deviation → blocker, because the design no longer describes the system

### 4. Assess maintainability

- Would an engineer unfamiliar with this work understand it?
- Are the names accurate — do they describe what the thing *is*, not what it was during development?
- Is the control flow followable without executing it mentally?
- Are failure paths legible, or do they silently swallow?
- Was documentation updated where behavior or contracts changed?

### 5. Assess architectural fit

- Did it introduce accidental coupling — reaching across layers, bypassing an abstraction that exists
  for this purpose, or duplicating a responsibility that already has an owner?
- Does it violate a principle in `.cursor/rules/architecture.mdc` or an accepted ADR?
- Does it create a second way to do something that already has a way?

**Drift is a blocker even when the code works.** Working code in the wrong place is a future cost paid
by everyone.

### 6. Assess complexity — look for what to remove

- Could this have been simpler?
- Was an abstraction introduced for a single call site?
- Is there speculative generality: configuration, indirection, or extension points nothing uses?
- Is there dead code, commented-out code, or leftover scaffolding?

**Subtraction is a legitimate and often the most valuable review outcome.** "Delete this" is a
finding, not a non-finding.

### 7. Assess test quality

- Are the important paths covered, or is coverage nominal?
- Do the assertions test behavior, or do they restate the implementation?
- Would these tests pass against a broken implementation? Name any that would.
- Are the failure paths and boundaries from `requirements.json` tested?

### 8. Assess scope

Compare the changed files against `plan.json → affected_files`. Did a two-file change touch forty
files? That is a blocker, not diligence.

### 9. Classify and locate every finding

| Severity | Content | Effect |
|---|---|---|
| **Blocker** | correctness, safety, scope violation, architecture drift | change cannot pass |
| **Concern** | quality, maintainability, incomplete coverage | change cannot pass |
| **Nit** | style, naming, optional improvement | does not block |

Every finding carries `file`, `line`, `description`, and a concrete `fix`. **A blocker without a
location is not actionable** and will waste a rework cycle.

### 10. Issue the verdict

- `PASS` **only** when the sole remaining findings are nits. If `verdict == "PASS"`, `blockers` must be
  empty and `concerns` must be empty — the validator enforces both.
- Any blocker or concern → `FAIL`, routed to the owner of the defect.
- **No conditional approvals.** "Approved once you fix X" is not a verdict; it is an unauditable middle
  state that lets an unverified change proceed. Issue `FAIL` with fix instructions.

## Output

`tasks/<TASK-ID>/review-report.json`, matching `.agent/schemas/review-report.schema.json`.

```bash
python .agent/tools/validate.py --artifact tasks/active/<TASK-ID>/review-report.json
python .agent/tools/validate.py --task <TASK-ID> --stage review
```

## Anti-patterns

- **Reviewing only the diff** and missing that a requirement is unimplemented.
- **Approving because the tests pass.** Tests passing is QA's verdict, already recorded. The reviewer's
  question is whether the change belongs here.
- **Conditional approval.** Issue `FAIL`.
- **Inflating nits into blockers** to appear rigorous, or **burying a blocker among nits** to be agreeable.
  Both destroy the signal value of severity.
- **Fixing the code yourself.** The reviewer requests; the developer changes. A reviewer that edits the
  change has destroyed the independence of the gate.
- **Reviewing your own prototype.** If you authored it, hand the review to another agent.
- **Asserting problems without locating them.** Cite file and line.
