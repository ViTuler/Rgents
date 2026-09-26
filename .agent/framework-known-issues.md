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
| — | *(none open)* | | | |

## Resolved

| ID | Issue | Resolved by | Date |
|---|---|---|---|
| KI-005 | `plan.json` can contradict `design.json` on the same schema detail, and nothing checks it. In TASK-001 the plan's `description_sql` said `id TEXT PRIMARY KEY` while the design and the database consultation required `... NOT NULL`. | `check_plan_ddl_against_design` in `validate.py`, wired through `stage_plan`. Rejects plan DDL that allows NULL when `design.data_model` requires NOT NULL; `TEXT PRIMARY KEY` without `NOT NULL` is an error (SQLite still stores NULL). Selftest canary `KI-005:`. | 2026-09-26 |
| KI-R1 | Marking a role `readonly: true` while it is the sole writer of an artifact | Cursor's flag removes write tools entirely, so the role failed on its first write. All roles now carry `readonly: false`, and `validate.py --check-setup` reports `readonly_cannot_write_artifact` as a configuration error. | 2026-09-20 |
| KI-006 | `docs/knowledge/**` edits failed implementation scope as `scope_extra` (not exempt); stale `project-memory.md` could not be fixed in the same task | `SCOPE_EXEMPT_PREFIXES` now includes `docs/knowledge/`. S2 (2026-09-24) also ignores dirty paths outside `plan.affected_files` for `scope_extra`. Updating project memory in-plan is no longer blocked by the old exemption gap. Residual policy choice (whether memory *should* be in every plan) remains a product concern, not a validator false positive. | 2026-09-24 |
| KI-007 | `check_requirements()` existed and was canaried but unreachable from every stage | Wired into `stage_plan`; canary drives `stage_plan` so removing the call site fails selftest. Kept as a resolved record of "checker without call site". | 2026-09-20 (fix) / 2026-09-24 (moved to Resolved) |

## Prohibited workarounds

Patterns that have been tried and rejected. Record them here so they are not re-proposed.

| Workaround | Why it was rejected |
|---|---|
| Widening a portability exemption by adding one field name at a time | It was done twice during TASK-001 and the pattern was still incomplete: a machine path lands wherever an artifact quotes a command it ran, and the field name drifts with the artifact (`evidence`, `rollback_evidence`, `plan_evidence`, `description`). The class is now stated once in `_PORTABILITY_EXEMPT_KEYS` / `_PORTABILITY_EXEMPT_KEY_SUFFIXES` in `validate.py`, with a canary that fails if an unlisted key is exempted. |
| Writing a framework defect into `docs/knowledge/known-issues.md` | That directory is copied into every product repository by the bootstrap, so a framework defect would ship into new projects and read as a project defect. This file exists because that mistake was made once. |
