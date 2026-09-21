---
description: Confirm delivery readiness and close the task — including human sign-off for high-risk work.
---

# /ship

Confirm the change is deliverable, then close the task.

**Arguments:** a task ID.

## Preconditions

- `python .agent/tools/validate.py --task <TASK-ID> --stage review` passes.
- Every activated gate has a passing verdict.

## Do this

1. **Adopt the `orchestrator` role yourself** by reading `.cursor/agents/orchestrator.md`, then run the
   `delivery` stage if `devops`
   is activated, then the `completion` stage.

2. If activated, **devops** writes `delivery-report.json`: reproducible build, complete and validated
   configuration, secret handling, migration safety, **rollback procedure**, health/readiness checks,
   and observability of the new failure modes.

3. Run the completion check, which requires that **every gate the task needed has an
   artifact with a passing verdict.** A gate with no artifact has not passed — it has not run.

4. On success:

   - updates `task.yaml` to `completed`
   - appends any durable lesson to `docs/knowledge/lessons.yaml` (max 50 entries; drop the oldest)
   - archives `tasks/active/<TASK-ID>/` to `tasks/completed/`

## Human sign-off

Obtain explicit human approval before closing when:

- `complexity == complex`, or `risk == high`
- the change is irreversible (schema migration on existing data, deletion, credential rotation)
- a security `critical` finding was resolved by a scope reduction rather than a fix

Present the human with: what changed, which gates ran and their verdicts, the rollback procedure, and
anything deferred. Do not describe a task as done while a gate is unpassed.

## Verify

```bash
python .agent/tools/validate.py --task <TASK-ID> --stage completion
python .agent/tools/validate.py --task <TASK-ID> --all
```

## Agents do not ship

No agent merges, deploys, force pushes, or pushes to a protected branch. `/ship` confirms readiness and
closes the task; a **human** performs the merge and the deploy.

## Do not

- Do not close a task on the basis that the change "looks fine" while a gate is missing.
- Do not report a task as complete when a blocking finding remains open.
