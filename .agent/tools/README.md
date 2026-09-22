# `.agent/tools/` — framework tooling

Tools here act **on** a project. They are not part of a product application's business logic.

| File | Runs where | Copied into a project? |
|---|---|---|
| `validate.py` | inside a project (`python .agent/tools/validate.py ...`) | **yes** — gate machinery |
| `init_project.py` (+ `.cmd` / `.ps1` / `.sh`) | inside a project or pointed at `--target` | **yes** — local `git init`, no remote |
| `parallel_worktree.py` | inside a project when a plan uses `parallel_group` | **yes** — path leases, merge lock, git worktrees (C2) |
| `bootstrap-project.ps1` | from the framework, pointed at a new project | **no** — removed from the target |
| `bootstrap-product-skeleton.ps1` | from the framework, via `-WithProductSkeleton` | **no** — same reason |

## Why some tools are removed from the target

A copied tool is a second copy that drifts. Worse, `bootstrap-product-skeleton.ps1` encodes one
product's stack, and leaving it in a seeded project would suggest the framework has an opinion about
that project's stack. It does not.

The line is: **anything a project needs at run time is copied; anything used to create a project is
not.** If a tool turns out to be needed at run time, that is a change to this table and to the
bootstrap's exclusion list, not something to leave lying in the target.

## Bootstrapping a project

```
./.agent/tools/bootstrap-project.ps1 -Target <new-project-path> [-WithProductSkeleton]
```

It refuses to seed into a non-empty directory, derives the framework root from its own location,
copies the framework surfaces, scaffolds knowledge files and **`.agent/project-baseline.yaml` from
the empty template** (never the framework's own `framework_meta` baseline), creates empty task lanes,
and runs `init_project.py` so the target has a local git repo **without** a remote.

**It does not create the first commit or add a remote.** The human owns those.

## Initializing git alone

```
python .agent/tools/init_project.py
python .agent/tools/init_project.py --target <path> --ensure-baseline
```

## What the bootstrap deliberately does not copy

| Path | Why |
|---|---|
| `refers/` | reference reading for the framework's authors; inert at runtime |
| `README.md` | the product repository writes its own |
| `tasks/**` | the previous project's task history belongs to that project |
| `bootstrap-*.ps1` | see above |

## The trap this design exists to close

Copying `docs/knowledge/` wholesale ships **the framework's own accumulated facts** into the new
project. That mistake was made twice while this framework was being tested: framework known issues
landed in a product repository, and then one product's known issues landed back in the framework's
template slot. Both are the same defect in opposite directions.

Scaffolding from `.agent/templates/knowledge/` (and the project-baseline template) is the fix.
