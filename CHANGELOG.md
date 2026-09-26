# Changelog

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
- **Docs:** KI-005 / KI-006 / KI-007 moved to Resolved in `framework-known-issues.md`.
- **E2E:** Sandbox S1 closed — confirmed trivial with **no** `plan.json` (see `sandbox-e2e-fix-tasks.md`).

## 1.0.0 — 2026-09-23

First design-correction closure (C0–C7, N2/N3). See `docs/architecture/correction-backlog.md`.
