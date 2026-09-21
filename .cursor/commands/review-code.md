---
description: Run the final engineering quality gate on a verified change.
---

# /review-code

Run the engineering quality gate.

> **Why this is `/review-code` and not `/review`:** Cursor ships built-in `/review`,
> `/review-bugbot`, and `/review-security` skills. A custom `/review` collides with the built-in
> in the command palette and is easy to trigger by mistake. The name is the only thing that
> changed — the stage and the agent are still `review` / `reviewer`.

**Arguments:** a task ID.

## Preconditions

- The `qa` gate passed.
- Every activated specialist gate passed (or justified a `SKIP`).
- `python .agent/tools/validate.py --task <TASK-ID> --stage qa` passes.

## Do this

1. **Adopt the `orchestrator` role yourself** by reading `.cursor/agents/orchestrator.md`, then run the
   `review` stage. Do not dispatch `orchestrator` with the Task tool — it is not resolvable through
   `subagent_type`.

2. Dispatch **reviewer**, which reads the **whole change** — requirements, design,
   plan, code, tests, and every specialist report — and writes `review-report.json` assessing:

   - **requirements traceability** — every criterion satisfied; every change traceable to a criterion
   - **correctness** against the approved design, including whether deviations were declared
   - **maintainability** — would an unfamiliar engineer understand it
   - **architectural fit** — accidental coupling, layer violations, duplicated responsibilities
   - **complexity** — could it be simpler; speculative generality; dead code
   - **consistency** with existing conventions
   - **test quality** — meaningful assertions, not restatements of the implementation
   - **scope** — the changed files against the plan

   Findings are classified `blocker` / `concern` / `nit`, each with `file`, `line`, `description`, `fix`.

## The verdict rules

- `PASS` **only** when the sole remaining findings are nits. `blockers` and `concerns` must both be
  empty — enforced by the validator.
- Any blocker or concern ⇒ `FAIL`, routed to the owner of the defect.
- **No conditional approvals.** "Approved once you fix X" is not a verdict; it is an unauditable middle
  state. Issue `FAIL` with fix instructions.

## On failure

Route to the owner: an implementation defect to `developer`, an unworkable interface to `tech-lead`, a
wrong criterion to `product`. The task re-enters at QA — the full chain re-runs.

## Verify

```bash
python .agent/tools/validate.py --task <TASK-ID> --stage review
```

## Do not

- Do not write `review-report.json` yourself. Sole writer: `reviewer`.
- Do not let the reviewer edit the code. The reviewer requests; the developer changes.
- Do not approve on the basis that tests pass — that is QA's verdict, already recorded.
