# `.agent/tools/` — framework tooling

Tools here act **on** a project. They are not part of a product application's business logic.

| File | Runs where | Copied into a project? |
|---|---|---|
| `validate.py` | inside a project (`python .agent/tools/validate.py ...`) | **yes** — gate machinery; also `--ci-changed` for light CI |
| `archive_task.py` | inside a project at `/ship` | **yes** — move `tasks/active/<ID>/` → `completed/` or `archive/`; `--rewrite-paths` backfills stale `artifact_path` |
| `init_project.py` (+ `.cmd` / `.ps1` / `.sh`) | inside a project or pointed at `--target` | **yes** — local `git init`, no remote |
| `parallel_worktree.py` | inside a project when a plan uses `parallel_group` | **yes** — path leases, merge lock, git worktrees (C2) |
| `seed_framework.py` | from the **framework** checkout, pointed at a product | **no** — create / upgrade provisioning |
| `bootstrap-project.ps1` | thin wrapper → `seed_framework.py create` | **no** — removed from the target |
| `bootstrap-product-skeleton.ps1` | from the framework, via `--with-product-skeleton` | **no** — same reason |

## Why some tools are removed from the target

A copied tool is a second copy that drifts. Worse, `bootstrap-product-skeleton.ps1` encodes one
product's stack, and leaving it in a seeded project would suggest the framework has an opinion about
that project's stack. It does not.

The line is: **anything a project needs at run time is copied; anything used to create or upgrade a
project is not.** Contract: `.agent/framework-manifest.yaml`.

## Windows console encoding

On Windows, prefer an activated env (`conda activate vi`) or a direct interpreter path over
`conda run -n vi python …` when you need to **read** tool output. `conda run` often wraps stdout in
the system code page (e.g. GBK); non-ASCII print then fails with `UnicodeEncodeError`.
`validate.py` and `archive_task.py` call `stdout/stderr.reconfigure(encoding="utf-8")` at startup
when the stream allows it — that helps activated/direct runs, not the `conda run` wrapper itself.

## Create (first seed)

```
python .agent/tools/seed_framework.py create --target <new-project-path>
# or
./.agent/tools/bootstrap-project.ps1 -Target <new-project-path> [-WithProductSkeleton]
```

- Refuses a non-empty directory.
- Copies framework surfaces listed in the manifest; strips `__pycache__` / selftest scratch / provisioning tools.
- Re-scaffolds `docs/knowledge/*` and `.agent/project-baseline.yaml` from **templates** (never the framework's own facts).
- Writes `.agent/seeded-from.yaml` (release + framework commit).
- Runs `init_project.py` (local git, no remote). Does **not** create the first commit.

## Upgrade (existing product)

```
python .agent/tools/seed_framework.py upgrade --target <product-path> --dry-run
python .agent/tools/seed_framework.py upgrade --target <product-path> --yes
```

- Replaces only `replaceable` paths from the manifest.
- Never touches `product_owned` (baseline, knowledge, tasks, `available.yaml`, …).
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
| `refers/` | reference reading for the framework's authors; inert at runtime |
| `README.md` | the product repository writes its own |
| `tasks/**` | the previous project's task history |
| provisioning tools | see table above |
| `__pycache__` / `.selftest*` | scratch; never ship |

## The trap this design exists to close

Copying `docs/knowledge/` wholesale ships **the framework's own accumulated facts** into the new
project. Scaffolding from `.agent/templates/knowledge/` (and the project-baseline template) is the fix.
Upgrade must not reintroduce that trap: knowledge and baseline stay product-owned forever.
