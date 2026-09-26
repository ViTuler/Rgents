---
description: Confirm delivery readiness and close the task — including human sign-off for high-risk work.
---

# /ship

Confirm the change is deliverable, then close the task.

**Arguments:** a task ID.

## Preconditions

- Every activated gate has a passing verdict (qa, review, and any specialists).
- For `complex` / `high`, human sign-off is recorded before close.

## Do this

1. **Adopt the `orchestrator` role yourself** by reading `.cursor/agents/orchestrator.md`. If
   `devops` is activated, run the `delivery` stage first (`delivery-report.json`).

2. **Refresh validate logs (required before completion).** Long-running tasks often lack a fresh
   `duplicate_check` (or other) log even when gates PASSed earlier — C4 then fails completion.
   Always run:

   ```bash
   python .agent/tools/validate.py --task <TASK-ID> --all
   ```

   Fix any errors. If QA cites stale `validate_log_ids`, refresh ids using the candidate uuids in the
   error (S3), then re-run `--stage qa` and `--all` again.

3. **Completion check:**

   ```bash
   python .agent/tools/validate.py --task <TASK-ID> --stage completion
   ```

   Every required gate must have a passing artifact. A gate with no artifact has not run.

4. On success:

   - updates `task.yaml` to `completed`
   - appends any durable lesson to `docs/knowledge/lessons.yaml` (max 50 entries; drop the oldest)
   - **archives with the tool** (do not hand-copy then hope delete works):

     ```bash
     python .agent/tools/archive_task.py <TASK-ID>
     # cancelled / superseded → --lane archive
     ```

     The tool also rewrites `tasks/active/…` prefixes inside `task.yaml` `artifact_path` fields to
     `tasks/completed/…` (or `archive/`).

   - **Do not report `/ship` complete** while `tasks/active/<TASK-ID>/` still exists. If deletion is
     blocked by the environment, stop and ask the human to approve the remove; then re-run
     `archive_task.py`. Leaving both `active/` and `completed/` is a protocol failure
     (`archive_active_residual` on `--stage completion`).

5. Re-check after archive (resolves under `completed/`):

   ```bash
   python .agent/tools/validate.py --task <TASK-ID> --stage completion
   ```

## Human sign-off

Obtain explicit human approval before closing when:

- `complexity == complex`, or `risk == high`
- the change is irreversible (schema migration on existing data, deletion, credential rotation)
- a security `critical` finding was resolved by a scope reduction rather than a fix

Present the human with: what changed, which gates ran and their verdicts, the rollback procedure, and
anything deferred. Do not describe a task as done while a gate is unpassed.

## Agents do not ship

No agent merges, deploys, force pushes, or pushes to a protected branch. `/ship` confirms readiness and
closes the task; a **human** performs the merge and the deploy.

## Do not

- Do not run `--stage completion` before `--all` on a task that has been sitting open (stale log trap).
- Do not close a task on the basis that the change "looks fine" while a gate is missing.
- Do not report a task as complete when a blocking finding remains open, or while `tasks/active/<ID>/` remains.
