# Changelog

## Unreleased

- **Publish hygiene:** `docs/architecture/` is gitignored (local maintainer notes only); removed from the public tree. Product scaffolds still come from `.agent/templates/architecture/`.
- **Seed hygiene (A1):** `never_copy_names` strips `framework-known-issues.md` and `regenerate-governance-docs.py` from product creates; docs updated so products no longer inherit the framework defect list or the governance regenerator.
- **Docs / config alignment (DeepSeek audit):** `docs/agents/**` listed in `AGENTS.md` governance; database/ux `stage_position` aligned with workflows; `/orchestrator` wording corrected; `design_defect` terminology; human-intervention list (8); reviewer C5 dimension; agent skeleton / templates / ADR-003 language consistency; CHANGELOG header restored.

## 1.0.2 — 2026-09-28

DeepSeek-aligned packaging fixes (cheap crack-sealing; N4 / other suggestions still deferred).

- **Stage-only PASS:** `--stage X` success lines now read `RESULT: PASS (stage-only: X — other stages not checked; use --all before /ship)` so a green qa stage cannot be mistaken for a full-task pass.
- **Workflow gates:** `check_setup` verifies `gates_in_order` aliases map to `GATE_ORDER`, and every dispatched specialist/reviewer agent has its gate listed. `feature.yaml` now includes `ux`. `incident.yaml` review `reads` no longer cites missing `design.json`.
- **Fixtures:** `tasks/fixtures/TASK-900/` + `python .agent/tools/validate.py --fixtures` (`must_fire` / `must_not_fire`). TASK-900 asserts `step_target_missing`.
- **CI:** `framework-ci.yml` adds `--fixtures` and a governance-docs job (`regenerate-governance-docs.py` + `git diff --exit-code`).
- **Docs / version:** `VERSION` / manifest / AGENTS / README / zh guides → **1.0.2**.
- **Docs:** task-lane layout (`active` / `completed` / `archive` / `fixtures`); removed stale `tasks/_template/` claim; `--fixtures` wording.
- **Packaging:** `docs/architecture/` is **product_owned** for seeded products (templates under `.agent/templates/architecture/`). The framework checkout keeps maintainer architecture notes **local-only** (gitignored), not as a published replaceable surface.

## 1.0.1 — 2026-09-24 (docs/models/KI follow-ups through 2026-09-26)

Sandbox E2E follow-ups and subsequent catalog/validator fixes (no framework-repo task lane; verified via `--selftest` + sandbox).

- **C1 models:** `init_project --refresh-models` prefers Cursor Agent CLI (`agent models` / `--list-models`) for the full account catalog; falls back to `cursor_sdk`, then Cloud Agents API (`/v1`+`/v0`) unioned with `seed.yaml`, then seed alone. Parser selftest: `--selftest-models-parser`. Zero-dep YAML also accepts trailing commas in multiline flow `{…}` list items (seed/available style).
- **KI-005:** `stage_plan` compares plan step DDL (`description_sql` / `description` / …) to `design.data_model` nullability. `TEXT PRIMARY KEY` without `NOT NULL` errors when the design forbids nulls (SQLite still allows NULL). Selftest canary `KI-005:`.
- **S1:** Confirmed trivial may omit `plan.json`; implementation still gated on `worker-result`. Declared `docs/knowledge/**` that actually changed is not `scope_missing` (exempt applies to undeclared dirt only). Sandbox **TASK-011** E2E closed without `plan.json`.
- **S2:** Implementation `scope_extra` ignores dirty paths outside `plan.affected_files` (parallel-task hygiene); worker overclaim still errors.
- **S3:** Stale `validate_log_ids` errors list candidate fresh log uuids.
- **S4:** UX activate/skip triggers clarified (`ux_specification_for_upcoming_surface`, `ux_spec_is_the_sole_deliverable`, …).
- **S5:** `overlap_needs_human` only for **active** likely matches.
- **S6:** Guide notes for multi-active working trees.
- **S7:** `archive_task.py` + `archive_active_residual`; `/ship` must not claim done while `active/` remains; rewrite `task.yaml` `artifact_path` prefixes on archive; `--rewrite-paths` backfills already-archived tasks.
- **Packaging:** `.gitignore` is `product_owned` (create still seeds; upgrade does not overwrite).
- **Ship:** Run `validate.py --task <ID> --all` before completion (fresh stage logs).
- **Windows:** UTF-8 stdio reconfigure in `validate.py` / `archive_task.py`; docs warn against `conda run` for reading tool output (GBK pipe).
- **Docs:** KI-005 / KI-006 / KI-007 marked Resolved in `docs/knowledge/known-issues.md`.
- **E2E:** Sandbox S1 closed — confirmed trivial with **no** `plan.json`.

## 1.0.0 — 2026-09-23

First design-correction closure (C0–C7, N2/N3). Details: this changelog.
