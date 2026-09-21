---
description: Implement a planned task — dispatch the developer, then the activated specialists.
---

# /build

Implement the approved plan.

**Arguments:** a task ID.

## Preconditions

- `requirements.json`, `design.json`, and `plan.json` all exist.
- `python .agent/tools/validate.py --task <TASK-ID> --stage plan` passes.

If the plan stage does not pass, stop and fix the plan. Implementing against a plan whose file list and
steps disagree guarantees a scope failure at the implementation gate.

## Do this

1. **Adopt the `orchestrator` role yourself** by reading `.cursor/agents/orchestrator.md`, then run
   the implementation stage. Do not dispatch `orchestrator` with the Task tool — it is not
   resolvable through `subagent_type`.

2. Dispatch **developer**, which:

   - reads the existing implementation before changing it
   - implements only the assigned steps, following the designed interfaces
   - writes tests that verify behavior, not the absence of exceptions
   - runs lint, typecheck, and the relevant tests, fixing mechanical errors (up to 2 self-fixes)
   - writes `worker-result.json` with files changed, real commands and real results,
     acceptance addressed, **deviations**, and **unresolved concerns**

3. Specialists activated with `stage_position: parallel_with_implementation` (`ux`, `database`) run
   alongside where the plan declares it safe.

## The rule that matters most

**Report the truth even when it is unflattering.** A hidden problem is not a solved problem — it is
transferred to QA and Review, where it costs more to find and more to fix. Never report a command as
passing that was not run.

## Deviations

Any departure from the plan goes in `worker-result.json → deviations` with a reason. A silent deviation
is a review blocker, because the design no longer describes the system. If the design is genuinely
unworkable, report it as a `design_defect` so it routes to the tech lead — do not
redesign it in place.

## Verify

```bash
python .agent/tools/validate.py --task <TASK-ID> --stage implementation
```

The implementation gate compares the plan's `affected_files` against the real `git diff` in both
directions: files changed but not planned are errors, planned files with no change are warnings.

## Do not

- Do not write `worker-result.json` yourself. Sole writer: `developer`.
- Do not let the developer approve its own work — `/verify` and `/review-code` are separate agents.
- Do not expand scope. Newly discovered work becomes a new task.
