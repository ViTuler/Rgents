---
description: Start a task — classify the request, activate the specialists its risk profile requires, and produce testable requirements.
---

# /spec

Turn a request into a classified task with testable requirements.

**Arguments:** the request in natural language.

## Do this

1. **Adopt the `orchestrator` role yourself.** Read `.cursor/agents/orchestrator.md` and follow it.
   Do **not** try to dispatch `orchestrator` with the Task tool — a project agent is not
   resolvable through `subagent_type`, and that dispatch will fail. You are the orchestrator.

   Pass it: the raw request, and the instruction to run the `intake` and `specification` stages of the
   workflow named in `.agent/config.yaml`.

2. Acting as the orchestrator, you will:

   - create `tasks/active/<TASK-ID>/`
   - write `intake.json` — type, complexity, risk, layers, **activated specialists, and skipped
     specialists with a reason for each skip**
   - for non-trivial tasks, also write **`model_assignments`** (C1): `assigned_model` slugs for
     `qa` / `reviewer` / (when activated) `security`, pairwise distinct, from
     `.agent/models/available.yaml` ∩ the session allow-list. Pass each slug as the Task `model`
     when dispatching. Do not assign the root orchestrator.
   - select the workflow (`feature` | `bugfix` | `refactor` | `incident`)

3. If complexity is not `trivial`, dispatch **product**, which writes
   `requirements.json`: goal, actors, user stories, acceptance criteria with stable `AC-*` IDs,
   business rules, edge cases, out-of-scope items, assumptions.

   If complexity **is** `trivial`, **stop for human confirmation** before implementation/QA. Record
   in `intake.json`:

   ```json
   "classification_confirmation": {
     "decided_by": "human",
     "confirmed_at": "YYYY-MM-DD",
     "note": "optional"
   }
   ```

   `standard` / `complex` do not need this field.

## What to report back

- the task ID
- the classification, with the reasoning
- which specialists are activated and which are skipped, **with why**
- the acceptance criteria
- **any `open_questions`** — these block progress and need a human answer

## Stop conditions

Return control to the human when `requirements.json → open_questions` is
non-empty. Do not proceed to design on a guessed product decision; everything downstream would inherit
the guess.

## Verify

```bash
python .agent/tools/validate.py --artifact tasks/active/<TASK-ID>/intake.json
python .agent/tools/validate.py --artifact tasks/active/<TASK-ID>/requirements.json
```

## Do not

- Do not write `requirements.json` yourself. Sole writer: `product`.
- Do not skip `intake.json` because the request "seems obvious". An unrecorded classification is an
  unauditable one, and a silently skipped specialist is the most common way this pipeline produces a
  confidently wrong result.
