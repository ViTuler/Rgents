---
description: Produce the technical design and the implementation plan for a specified task.
---

# /design

Turn requirements into a technical design and an executable plan.

**Arguments:** a task ID (e.g. `TASK-014`).

## Do this

1. **Adopt the `orchestrator` role yourself** by reading `.cursor/agents/orchestrator.md`, then run
   the `design` and `planning` stages for the given task. Do not dispatch `orchestrator` with the
   Task tool — it is not resolvable through `subagent_type`.

2. Dispatch **tech-lead**, which reads `requirements.json` and the codebase and writes:

   - `design.json` — architecture, components, **exact interface contracts**, data model, dependency
     decisions, ADRs with rejected alternatives, risks, irreversible steps, and `not_designed`
   - `plan.json` — ordered steps with `depends_on`, `parallel_group`, acceptance mapping, risk levels,
     and rollback for high-risk steps

3. As the orchestrator, reconcile `specialists_required` from the plan against the activation policy in
   `.agent/config.yaml`, and records the execution DAG and the gates the task must clear.

## Requirements the design must meet

- **Every acceptance criterion maps to a step.** The validator treats an unmapped criterion as an error.
- **Every file in `affected_files` has a step, and every step's file is in `affected_files`.** Enforced
  in both directions.
- **Every high-risk or irreversible step carries a rollback procedure.**
- Interfaces are frozen here. Parallel implementation is only safe once they are.

## Design-time consultation

For anything crossing a trust boundary, touching schema, or carrying a performance budget, the
specialist should be consulted **now**, not after implementation. A specialist consulted during design
costs one message; consulted afterwards it costs a rework cycle.

## Stop conditions

Escalate to the human rather than guessing when:

- a requirement is unbuildable as written (route to `product`, not a reinterpretation)
- the design requires changing existing architecture in a way that affects other tasks
- an irreversible step has no acceptable rollback

## Verify

```bash
python .agent/tools/validate.py --artifact tasks/active/<TASK-ID>/design.json
python .agent/tools/validate.py --task <TASK-ID> --stage plan
```

## Do not

- Do not write `design.json` or `plan.json` yourself. Sole writer: `tech-lead`.
- Do not start implementation from this command. `/build` does that.
