# Framework known issues — accepted problems in Rgents itself

Problems here are **known and deliberately not being fixed**. They are recorded so that agents and
humans stop rediscovering them, stop reporting them as new findings, and stop "fixing" them as scope
creep in an unrelated task.

**This file lives under `.agent/` on purpose.** It is framework knowledge, and `.agent/**` is a
governance surface that is **not** copied into a product repository. `docs/knowledge/` **is** copied
(bootstrap: `Copy-Tree 'docs/knowledge'`), so a framework defect recorded there would ship into every
new project and appear, on first read, to be a defect of that project. Accepted problems in a project
the team is working on belong in **that project's** `docs/knowledge/known-issues.md`.

Each entry records *why* it is accepted. An accepted issue without a stated reason is
indistinguishable from an oversight.

## How to use this file

- **Reference, do not fix.** Encountering one of these while working on something else is a note in
  your report, not a work item.
- **Do not suppress reporting entirely.** If a known issue makes a task's acceptance criteria
  unverifiable, that is a new finding and must be raised.
- **Removing an entry is an explicit decision**, not a cleanup. Say what changed.

## Open

| ID | Issue | Impact | Why accepted | Revisit when |
|---|---|---|---|---|
| KI-005 | `plan.json` can contradict `design.json` on the same schema detail, and nothing checks it. In TASK-001 the plan's `description_sql` said `id TEXT PRIMARY KEY` while the design and the database consultation required `... NOT NULL`. | A different implementer would follow the plan and create a table that permits NULL ids — rows that `SELECT`/`DELETE ... WHERE id = ?` can never match, so they are invisible to the designed paths. Measured, not hypothesised: consultation DB-N2 stored two NULL ids on the proposed DDL and matched neither. | The contradiction was caught only because the developer raised it as a declared deviation. Building a plan↔design schema comparator is real work and no task has needed it yet. The absence of published data on cross-artifact inconsistency rates is itself a reason for caution rather than urgency. | A validator check compares a plan's DDL against the design's data model, or a task touches this migration again. |
| KI-006 | Documentation fixes are out of scope for the task that motivates them. `docs/knowledge/**` is not in `SCOPE_EXEMPT_PREFIXES`, so correcting a stale fact in `project-memory.md` after implementation fails the implementation gate with `scope_extra`. | A stale fact that a completed task has just invalidated stays stale until a separate task fixes it. In TASK-001 the review gate found `project-memory.md` still declaring the error-handling convention unset, one line after ADR-003 defined it — and correcting it would have failed the scope check on the very task that produced the fact (recorded as review nit REV-N1). | `docs/architecture/**` is genuinely part of a plan and is correctly checked. Whether project memory belongs with it, or with the exempt `docs/knowledge/**` prefix that already exempts lessons, is a policy decision nobody has made. Applying the fix inside the task would have been an out-of-plan edit. | The next task that changes a project-level fact, or when `SCOPE_EXEMPT_PREFIXES` is reviewed. |
| KI-007 | A checker can exist, be correct, be canaried, and never be called. `check_requirements()` and its canary were both present and green while the function was unreachable from every stage, so unresolved product questions blocked nothing. | A guessed product decision propagates into design, plan, code, and every gate that verifies it. Observed live: a `requirements.json` carrying four unanswered product decisions validated as `PASS`, and only the orchestrator's own judgement stopped the pipeline. | Fixed: the function is wired into `stage_plan`, and its canary now drives `stage_plan` so that removing the call site fails the selftest. Kept as a record of how this class of defect hides — the canary that mirrored the checker instead of driving it was the reason it stayed hidden. | Removing this entry is an explicit decision, not cleanup. |

## Resolved

| ID | Issue | Resolved by | Date |
|---|---|---|---|
| KI-R1 | Marking a role `readonly: true` while it is the sole writer of an artifact | Cursor's flag removes write tools entirely, so the role failed on its first write. All roles now carry `readonly: false`, and `validate.py --check-setup` reports `readonly_cannot_write_artifact` as a configuration error. | 2026-09-20 |

## Prohibited workarounds

Patterns that have been tried and rejected. Record them here so they are not re-proposed.

| Workaround | Why it was rejected |
|---|---|
| Widening a portability exemption by adding one field name at a time | It was done twice during TASK-001 and the pattern was still incomplete: a machine path lands wherever an artifact quotes a command it ran, and the field name drifts with the artifact (`evidence`, `rollback_evidence`, `plan_evidence`, `description`). The class is now stated once in `_PORTABILITY_EXEMPT_KEYS` / `_PORTABILITY_EXEMPT_KEY_SUFFIXES` in `validate.py`, with a canary that fails if an unlisted key is exempted. |
| Writing a framework defect into `docs/knowledge/known-issues.md` | That directory is copied into every product repository by the bootstrap, so a framework defect would ship into new projects and read as a project defect. This file exists because that mistake was made once. |