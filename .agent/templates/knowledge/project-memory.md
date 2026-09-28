# Project memory — stable facts the team should not have to rediscover

This file is long-term memory. It records facts that stay true across tasks: the stack, the binding
architectural decisions, and the constraints that are not visible in the code.

`docs/knowledge/lessons.yaml` records what went *wrong*. This file records what is *true*.

> **Status: template.** Populate it for the project the team is working on. Until it is filled in,
> every agent rediscovers the same facts on every task — which is the problem this file exists to solve.

## Stack

| Layer | Technology | Notes |
|---|---|---|
| Language(s) | | |
| Framework(s) | | |
| Persistence | | |
| Frontend | | |
| Runtime / hosting | | |
| Build & CI | | |
| Test tooling | | |

## Commands

The exact commands agents should run. Do not guess these — record them.

| Task | Command |
|---|---|
| Install | |
| Build | |
| Lint | |
| Typecheck | |
| Unit tests | |
| Integration tests | |
| Run locally | |
| Migrate | |

## Architecture

Summary of the system's shape. If the project keeps an architecture overview (often
`docs/architecture/overview.md`), put detail there; keep here only what an agent needs to avoid a
wrong assumption. Rgents does not require that path.

- **Layering:**
- **Where business logic lives:**
- **How data flows:**
- **Authentication / authorization model:**
- **Configuration mechanism:**
- **Error handling convention:**

## Binding decisions

Decisions that are settled and must not be relitigated. Full records live where the project keeps
ADRs (often `docs/architecture/decisions.md` when that file exists).

| Decision | Rationale (one line) | Do not |
|---|---|---|
| | | |

## Constraints agents get wrong

Not visible in the code, learned the hard way. This section is usually the most valuable.

-

## Conventions

- **Naming:**
- **File layout:**
- **Test layout:**
- **Commit style:**
- **Branch style:**
- **Comments:** document why, not what

## External dependencies that constrain us

| Dependency | Constraint it imposes |
|---|---|
| | |

## Environments

| Environment | Purpose | Who may deploy | Notes |
|---|---|---|---|
| local | | | |
| staging | | | |
| production | | | |

Agents never deploy, migrate, or perform destructive operations against `staging` or `production`.
