# Rgents

**Version:** `1.0.0` (see `VERSION` and `.agent/framework-manifest.yaml → release`)

A **multi-agent software development organization** for Cursor (and any agent runtime that reads
`.cursor/agents/*.md` — Claude Code, Codex, and DeepSeek Harness subagents all work with the same files).

It is not a pile of personas. It is a small software organization with:

- **1 orchestrator** that classifies work, activates only the specialists a task's risk profile needs,
  builds the task DAG, and enforces the quality gates. It runs as the **root agent** — Cursor's Task
  tool cannot resolve a project agent through `subagent_type`, so the orchestrator is a role the main
  thread adopts rather than a subagent it dispatches.
- **5 core roles** — Product, Tech Lead, Developer, QA, Reviewer — present on every non-trivial task.
- **6 specialists** — UX, Security, DevOps, Database, Data, Performance — activated conditionally.
- **Artifact contracts** — every handoff is a validated JSON file under `tasks/<TASK-ID>/`, not relayed conversation.
- **Executable quality gates** — a zero-dependency validator turns the classic multi-agent failure modes
  (plan/implementation drift, skipping past a failure, "PASS" verdicts that carry blockers, agents
  touching files outside their scope, two active tasks describing one request) into hard errors.

## Why this exists

Multi-agent coding teams fail in predictable ways:

| Failure mode | How this framework prevents it |
|---|---|
| Agents narrate progress instead of proving it | Every claim maps to an artifact field; `evidence` is a required key |
| The plan drifts from the implementation | `plan_scope_match` invariant compares the plan's file list against the actual diff |
| A gate gets skipped when it is inconvenient | `.agent/workflows/*.yaml` declares required gates; `validate.py --stage` checks them |
| "PASS" verdicts that quietly contain blockers | `verdict_consistent` invariant |
| Everyone edits everything | `NON-GOALS` per role + `scope` invariants + a declared permission matrix |
| An agent approves its own work | Structural: the writer of `worker-result.json` can never write a report artifact |
| Context explodes across handoffs | Agents pass **paths**, never artifact contents |
| The same mistake happens every task | `docs/knowledge/lessons.yaml` with a hard entry cap |
| Every task runs every specialist | Risk-based gate activation declared in `.agent/config.yaml` |

## Quick start

```bash
# 1. Prove the gates actually fire — canaries in validate.py --selftest, zero dependencies, Python 3.8+
python .agent/tools/validate.py --selftest

# 2. Confirm the team's own configuration is consistent
python .agent/tools/validate.py --check-setup
```

Then, in Cursor, drive a task with the slash commands:

```
/spec    "users should be able to invite teammates to their organization"
/design  TASK-NNN
/build   TASK-NNN
/verify  TASK-NNN
/review-code TASK-NNN
/ship    TASK-NNN
```

Each command delegates to the orchestrator, which consults `.agent/config.yaml` for routing and
`.agent/workflows/<type>.yaml` for the stage sequence. `tasks/active/` stays empty until you open a
live task; release or archive it when the work is done.

## Worked examples

One completed example ships with the framework so artifact shapes are concrete rather than described.
`tasks/archive/TASK-004/` is an archived high-risk intake/requirements record (same invite feature,
stopped early) if you want the fuller artifact shapes without an active blocked task.

| Example | What it shows |
|---|---|
| `tasks/completed/TASK-002/` | A `trivial` copy change that ran only the QA gate and completed: no design, no plan, no specialists, no review — because 1–2 files with no interface change needs none of them. |

```bash
# The completed example passes, running only the stages its classification requires
python .agent/tools/validate.py --task TASK-002 --all
```

## Using this as a template

Copy `.cursor/`, `.agent/`, `docs/agents/`, `docs/knowledge/`, and `AGENTS.md` into a product
repository. The framework is self-contained: no install, no dependencies, no build step.

Then establish `.agent/project-baseline.yaml` via a **project-level** spec/design (human + product +
tech-lead): stack, environment manager, and authoritative commands. Set `status: established`.
`docs/knowledge/project-memory.md` may summarise the same facts for humans; it is **not** the
machine-checked source of truth.

### Project-agnostic and path-portable

The framework carries **no machine-specific absolute path** and **assumes no particular project
layout**. Three consequences, each enforced rather than promised:

| Property | How it holds | Check |
|---|---|---|
| The project root is discovered at runtime, from the validator's own file location | `Path(__file__).resolve().parents[N]` | `root_not_derived` |
| Relative paths resolve against the project root, **not the working directory** | so the tool behaves identically from a subdirectory, an editor task, or a CI step | `cwd_dependency` |
| No **framework** file hard-codes a drive letter, a UNC share, or a home directory | the framework gets copied onto arbitrary machines; **task run records under `tasks/` are exempt** (they may name the interpreter that actually ran) | `machine_specific_path` |

`python .agent/tools/validate.py --check-setup` verifies all three. They are also covered by selftest
canaries, including a negative test that plants an absolute path under `.agent/` and asserts it is
caught, and a positive test that a path under `tasks/` is not.

**Where a project-specific path is genuinely needed, take it as an argument, read it from
configuration, or record it in a task artifact — never bake it into framework source.** `.agent/config.yaml`
is the single source of truth for anything project-shaped in routing policy. Stack and authoritative
commands live in `.agent/project-baseline.yaml` (structured baseline; see C6).

**One caveat about the scope check.** The implementation-stage invariant compares `plan.json` against
the real `git diff` of whatever repository the team is working in. Inside this framework repository
there is no product code, so that check reports the framework's own files as out of scope — which is
correct behavior, and the reason the check exists at all. It becomes meaningful once the team is
working in a product repository where `plan.json` describes that repository's files.

## Layout

```
Rgents/
├── AGENTS.md                    # the constitution
├── .cursor/
│   ├── agents/
│   │   ├── orchestrator.md      # coordinator (specialist team)
│   │   ├── core/                # product, tech-lead, developer, qa, reviewer
│   │   └── specialists/         # ux, security, devops, database, data, performance
│   ├── rules/                   # global, architecture, coding, testing, security, documentation, delivery
│   ├── skills/                  # reusable procedures (spec, design, testing, review, security, …)
│   └── commands/                # /spec /design /build /verify /review-code /ship /triage
├── .agent/
│   ├── config.yaml              # roster + routing policy (single source of truth)
│   ├── workflows/               # feature, bugfix, refactor, incident
│   ├── schemas/                 # artifact JSON Schemas
│   └── tools/validate.py        # zero-dependency validator + gate checker
├── docs/
│   ├── agents/                  # responsibilities, permissions, protocols
│   ├── architecture/            # overview, decisions (ADRs), conventions
│   ├── knowledge/               # project memory, lessons, known issues
│   └── zh/                      # 中文使用手册
└── tasks/
    ├── active/                  # live work
    ├── completed/
    ├── archive/
    └── _template/               # copy this to start a task by hand
```

## Design influences

This framework was built after auditing two reference projects:

- **[JahnelGroup/multi-agents](https://github.com/JahnelGroup/multi-agents)** — a Cursor pipeline
  template. Adopted: the four-section agent skeleton (`ROLE` / `PRIMARY OBJECTIVE` /
  `CORE RESPONSIBILITIES` / `NON-GOALS`), minimal frontmatter, the single-writer artifact contract,
  the plan↔diff scope invariants, the `error`/`warning` severity split, `lessons.yaml` with a capacity
  cap, and the "escalation is cheap and expected" cost stance. Corrected: its `lib/` cross-directory
  import (which breaks when the bundle is copied into a project as documented), a gate stage that had
  no artifact contract, and its reliance on a `readonly` flag that a static checker cannot enforce.
- **[pridiuksson/cursor-agents](https://github.com/pridiuksson/cursor-agents)** — a design-document
  repository, not a framework. Adopted: independent review via a *different model* rather than a
  different prompt, conditional security gating, rework loops that return to the start of the gate
  chain, the five-field failure schema (Error / Symptom / Root Cause / Solution / Verification), star
  topology with conclusion-level returns, and the traceability triplet (design reference + requirement
  ID + quality gate) on every task.

Full audits: `refers/_refs/_audit-jahnel.md`, `refers/_refs/_audit-pridiuksson.md`.

### Two corrections found by running it, not by reading it

Both are the kind of mistake a framework cannot catch by inspection — they only surface in execution.

**`readonly` is a capability switch, not an authority statement.** Cursor documents it as removing
write tools entirely: *no file edits, no state-changing shell commands*. An early revision marked
`product`, `tech-lead`, and `reviewer` as `readonly: true` while they were the sole writers of their
artifacts. Each was dispatched successfully and then failed on its first write; the failure appeared
only at runtime. All roles now correctly carry `readonly: false`, and the conflict is a
configuration-time error (`readonly_cannot_write_artifact`) with a selftest canary guarding against
reintroduction. Domain authority — "does not write application code" — is a **convention** enforced by
`NON-GOALS` and by the validator's scope invariants, and is documented as a convention rather than
dressed up as enforcement.

**A missing gate artifact must never be read as a pass.** A gate that never ran and a gate that passed
look identical if you only look for the absence of complaints. The validator reports `gate_not_run`
instead, and the completion check refuses to close a task while any required gate has no artifact.

It is worth noting *how* the first defect surfaced: the coordinator was dispatched, discovered the
conflict, and **refused to work around it** — it did not write `requirements.json` on the product's
behalf and did not edit the human-owned agent definition, even though it held write permission to do
both. It reported the blocker and stopped. That is the `NON-GOALS` boundary doing the work that the
`readonly` flag was never able to do.

## Extending the team

- **Add a role**: copy `.agent/templates/agent.md`, add it to `.agent/config.yaml`, add it to
  `ARTIFACT_WRITERS` in `.agent/tools/validate.py`, add its artifact to `.agent/schemas/` if it produces
  one, then run `python .agent/tools/validate.py --check-setup`. Never set `readonly: true` on a role
  that writes an artifact — Cursor's flag removes write tools entirely, so the role would fail on its
  first write.
- **Add a gate**: add a stage to `.agent/workflows/*.yaml` and a checker to `.agent/tools/validate.py`.
- **Change routing**: edit `.agent/config.yaml` only — it is the single source of truth. Agent files
  reference it rather than restating it.
- **After editing any agent file**: run `python .agent/regenerate-governance-docs.py` so the permission
  and responsibility matrices stay derived from the contracts instead of drifting.

## Governance

`.cursor/**`, `.agent/**`, and `AGENTS.md` are **human-owned**. Agents may propose changes through an
artifact; they may not apply them. See `docs/agents/protocols.md`.

## 中文文档

- `docs/zh/README.zh-CN.md` — 团队总览与快速上手
- `docs/zh/roles.zh-CN.md` — 12 个角色的职责、边界与协作方式
- `docs/zh/workflow.zh-CN.md` — 工作流、门禁与任务状态机
