# `.agent/tools/` — framework tooling

Tools here act **on** a project. They are not part of a product application's business logic.

| File | Runs where | Copied into a project? |
|---|---|---|
| `validate.py` | inside a project (`python .agent/tools/validate.py ...`) | **yes** — gate machinery; also `--ci-changed`, `--fixtures` |
| `archive_task.py` | inside a project at `/ship` | **yes** — move `tasks/active/<ID>/` → `completed/` or `archive/`; `--rewrite-paths` backfills stale `artifact_path` |
| `init_project.py` (+ `.cmd` / `.ps1` / `.sh`) | inside a project or pointed at `--target` | **yes** — local `git init`, no remote |
| `parallel_worktree.py` | inside a project when a plan uses `parallel_group` | **yes** — path leases, merge lock, git worktrees (C2) |
| `seed_framework.py` | from the **framework** checkout, pointed at a product | **no** — create / upgrade provisioning |
| `bootstrap-project.ps1` | thin wrapper → `seed_framework.py create` | **no** — removed from the target |
| `bootstrap-product-skeleton.ps1` | from the framework, via `--with-product-skeleton` | **no** — same reason |
| `../regenerate-governance-docs.py` | framework checkout / CI | **no** — stripped on create (`never_copy_names`); regenerates `docs/agents/permissions.md` + `responsibilities.md` |

## Why some tools are removed from the target

A copied tool is a second copy that drifts. Worse, `bootstrap-product-skeleton.ps1` encodes one
product's stack, and leaving it in a seeded project would suggest the framework has an opinion about
that project's stack. It does not.

The line is: **anything a project needs at run time is copied; anything used to create or upgrade a
project is not.** Contract: `.agent/framework-manifest.yaml`.

## Windows console encoding

On Windows, prefer an **activated** named env (`conda activate <your-env>`) or invoking that
env's `python` on PATH over `conda run -n <your-env> python …` when you need to **read** tool
output. `conda run` often wraps stdout in the system code page (e.g. GBK); non-ASCII print then
fails with `UnicodeEncodeError`.
`validate.py` and `archive_task.py` call `stdout/stderr.reconfigure(encoding="utf-8")` at startup
when the stream allows it — that helps activated/direct runs, not the `conda run` wrapper itself.

Do **not** commit personal absolute interpreter paths (drive letters, home directories, private
env names) into framework docs or baselines — this repository is public. Use placeholders such as
`<your-env>` in examples.

## Create (first seed)

```
python .agent/tools/seed_framework.py create --target <new-project-path>
# or
./.agent/tools/bootstrap-project.ps1 -Target <new-project-path> [-WithProductSkeleton]
```

- Refuses a non-empty directory.
- Copies framework surfaces listed in the manifest; strips `__pycache__` / selftest scratch / provisioning tools.
- Re-scaffolds `docs/knowledge/*`, `docs/architecture/*`, `.gitignore`, and
  `.agent/project-baseline.yaml` from **templates** (never the framework repo's own
  architecture ADRs, knowledge facts, or maintainer-only ignore rules).
- Writes `.agent/seeded-from.yaml` (release + framework commit).
- Runs `init_project.py` (local git, no remote). Does **not** create the first commit.

## Upgrade (existing product)

```
python .agent/tools/seed_framework.py upgrade --target <product-path> --dry-run
python .agent/tools/seed_framework.py upgrade --target <product-path> --yes
```

- Replaces only `replaceable` paths from the manifest.
- Never touches `product_owned` (baseline, knowledge, **architecture**, tasks, `available.yaml`, …).
- Backs up prior copies under `.rgents/upgrade-backups/<date>/`.
- Rewrites `.agent/seeded-from.yaml`.

## Initializing git alone

```
python .agent/tools/init_project.py
python .agent/tools/init_project.py --target <path> --ensure-baseline --refresh-models
```

### `--refresh-models` (C1 catalog)

Writes `.agent/models/available.yaml`. **Never stores API keys.** Priority:

1. **Cursor Agent CLI** — `agent models` / `--list-models` (full account / IDE-dispatchable set)
2. **cursor_sdk** (if installed) unioned with `seed.yaml`
3. **Cloud Agents API** (`/v1/models` + `/v0/models` via `CURSOR_API_KEY`) unioned with seed — often a
   narrowed recommended subset
4. **`seed.yaml` alone**

Parser check (no network): `python .agent/tools/init_project.py --selftest-models-parser`.

Install/login CLI when you need the live full catalog: https://cursor.com/docs/cli/overview

## What create deliberately does not copy

| Path | Why |
|---|---|
| `README.md` | the product repository writes its own |
| `.gitignore` (framework checkout) | products get `.agent/templates/gitignore` (no `docs/architecture/` / `refers/`) |
| `docs/architecture/` (framework-filled) | products get blank templates from `.agent/templates/architecture/` |
| `tasks/**` | the previous project's task history |
| provisioning tools | `seed_framework.py`, bootstrap scripts — see table above |
| `framework-known-issues.md` | framework-checkout defect list; stripped via `never_copy_names` |
| `regenerate-governance-docs.py` | regenerates `docs/agents/*` from a framework checkout / CI; stripped via `never_copy_names` |
| `__pycache__` / `.selftest*` / `.rgents` | scratch; never ship |

## The trap this design exists to close

Copying `docs/knowledge/` or `docs/architecture/` wholesale would ship **the framework's own
accumulated facts and ADRs** into the new project. Scaffolding from `.agent/templates/knowledge/` and
`.agent/templates/architecture/` (plus the project-baseline template) is the fix. Copying the
framework checkout's `.gitignore` would silently ignore product `docs/architecture/` — products
get `.agent/templates/gitignore` instead. The same class of trap applies to
`.agent/framework-known-issues.md`: it is stripped on create so products do not inherit the
framework defect list. Upgrade must not reintroduce those traps: knowledge, architecture,
`.gitignore`, and baseline stay product-owned forever.
