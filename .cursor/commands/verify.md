---
description: Run the quality gates — functional verification first, then any activated specialist assessment.
---

# /verify

Run the verification gates for a task.

**Arguments:** a task ID.

## Preconditions

`python .agent/tools/validate.py --task <TASK-ID> --stage implementation` passes, and
`worker-result.json` exists with `status: completed`.

## Do this

1. **Adopt the `orchestrator` role yourself** by reading `.cursor/agents/orchestrator.md`, then run the
   `qa` stage and any activated specialist gates. Do not dispatch `orchestrator` with the Task tool.

2. Dispatch **qa**, which writes `qa-report.json`:

   - a verdict for **every** acceptance criterion, each with evidence
   - independently derived edge cases — not the developer's test list
   - regression results, separating pre-existing failures from new ones
   - findings with reproduction, expected vs actual, and **the role that owns the defect**
   - `not_verified` — everything it could not check, and why

3. Any specialist activated at `stage_position: parallel_with_qa` runs alongside: `security`,
   `performance`, `data`.

## The gate conditions

| Gate | Passes when |
|---|---|
| qa | `verdict == PASS`, every criterion has a verdict, no unresolved critical/major finding |
| security | `verdict == PASS`, no unresolved critical/high finding |
| performance | `verdict == PASS` or a justified `SKIP` |
| data | `verdict == PASS` or a justified `SKIP` |

The validator enforces these. A `PASS` carrying a failed criterion, a blocker, or an open critical
finding is **rejected** — this is checked mechanically, not trusted.

## On failure

Route to the owner of the defect and re-enter at QA. A fix invalidates prior
verification, so **the whole gate chain re-runs** — a partial re-run is not available.

`NOT VERIFIED` is a first-class verdict. An unverifiable criterion reported as PASS is worse than one
reported as NOT VERIFIED, because it converts a known gap into false confidence.

## Verify

```bash
python .agent/tools/validate.py --task <TASK-ID> --stage qa
```

## Do not

- Do not write `qa-report.json` yourself. Sole writer: `qa`.
- Do not let the developer's own tests stand in for verification.
- Do not accept a security `critical` or `high` finding as a follow-up task. It blocks.
- Do not proceed to `/review-code` while a blocking gap remains.
