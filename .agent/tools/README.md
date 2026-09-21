# `.agent/tools/` — framework tooling

Tools here act **on** a project. They are not part of a project.

| File | Runs where | Copied into a project? |
|---|---|---|
| `validate.py` | inside a project (`python .agent/tools/validate.py ...`) | **yes** — it is the gate machinery, and every project needs it |
| `bootstrap-project.ps1` | from the framework, pointed at a new project | **no** — the bootstrap removes it from the target |
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

It refuses to seed into a non-empty directory, derives the framework root from its own location (so it
carries no machine-specific path and runs from any working directory), copies the framework surfaces,
scaffolds the knowledge files from `.agent/templates/knowledge/`, and creates empty task lanes.

**It does not run `git init`.** The human commits, so the first commit is an explicit act. It must
happen before task work starts, or the implementation gate has no real diff to compare a plan against
and silently degrades to a warning.

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

The fix is structural, not a reminder: the scaffolded files come from `.agent/templates/knowledge/`,
which is a template directory and therefore never accumulates project facts, and the bootstrap fails
loudly if a template is missing rather than falling back to whatever the framework is carrying.
