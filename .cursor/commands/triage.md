---
description: Classify an incoming request or a failure — decide the workflow, and route a defect to the role that owns it.
---

# /triage

Classify a request, or route a failure to its owner.

**Arguments:** either a request, or a failing task ID with the failure description.

## Mode 1 — classify a new request

1. **Adopt the `orchestrator` role yourself** by reading `.cursor/agents/orchestrator.md`. Do not
   dispatch `orchestrator` with the Task tool — it is not resolvable through `subagent_type`.
2. Acting as the orchestrator, classify against `.agent/config.yaml`:

   | Dimension | Values |
   |---|---|
   | type | `feature` \| `bugfix` \| `refactor` \| `incident` |
   | complexity | `trivial` \| `standard` \| `complex` |
   | risk | `low` \| `medium` \| `high` |
   | layers | frontend \| backend \| database \| infrastructure \| data \| docs |

3. It selects the workflow and activates specialists, **recording a reason for every skip**.

### Classifying honestly

If you cannot justify a `trivial` classification against the definitions in `.agent/config.yaml`, it is
not trivial. Trivial means 1–2 files, one layer, no new abstraction, no interface change. A
misclassified-trivial task skips design, review, and specialist gates — which is how a "small change"
ships a regression.

### Misclassification to watch for

| Looks like | Actually is |
|---|---|
| a bugfix | a requirement change — the observed behavior matches the spec |
| a refactor | a feature — behavior is meant to change |
| trivial | standard — it crosses a layer boundary or changes an interface |
| a feature | an incident — production is currently degraded |

## Mode 2 — route a failure

Determine the **owner of the defect**, not the owner of the symptom. Misattribution sends the fix to an
agent that cannot make it, which costs a full extra cycle.

| Classification | When | Route to |
|---|---|---|
| `implementation_defect` | behavior does not match the design or criteria | `developer` |
| `requirement_defect` | the criterion is wrong, ambiguous, or contradictory | `product` |
| `design_defect` | the interface or plan cannot satisfy the requirement | `tech-lead` |
| `test_defect` | the assertion is wrong, or the harness is broken | `qa` |
| `unclear_scope` | it is not determinable what is in bounds | `orchestrator` (re-classify) |

Record `routing_decisions` and the retry count in `task.yaml`, then re-enter at the **qa** stage.

## Budgets

| Budget | Value | On exceed |
|---|---|---|
| retries per stage | 2 | escalate to human |
| total cycles | 3 (5 for `incident`) | escalate to human |
| escalations | not counted against retries | — |

Escalation is cheap and expected. Guessing is the expensive path.

## Escalate to the human when

- requirements are ambiguous or a product decision is unresolved
- the change is irreversible
- a security `critical` finding cannot be fixed within scope
- the same stage has failed three times
- governance surfaces need to change
- risk is `high` and the task is ready to complete

## Verify

```bash
python .agent/tools/validate.py --artifact tasks/active/<TASK-ID>/intake.json
python .agent/tools/validate.py --task <TASK-ID> --all
```
