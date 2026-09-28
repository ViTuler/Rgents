# Permissions — what each role may and may not do

Generated from `.cursor/agents/**` by `.agent/regenerate-governance-docs.py`. The `NON-GOALS`
sections are quoted directly from each role contract, because that is the actual authority
boundary for agent behavior.

## Capability matrix

| Role | Team | Read | Write code | Write tests | May approve | `readonly` |
|---|---|---|---|---|---|---|
| `orchestrator` | core | all | state files only | ✗ | ✗ (closes only) | `false` |
| `product` | core | all | its artifact only | ✗ | requirements | `false` |
| `tech-lead` | core | all | its artifacts + spikes | ✗ | design | `false` |
| `developer` | core | all | ✓ | ✓ | ✗ | `false` |
| `qa` | core | all | ✗ | ✓ | functional verification | `false` |
| `reviewer` | core | all | its artifact only | ✗ | code (final engineering gate) | `false` |
| `ux` | specialist | all | its artifact + UI specs/tokens | ✗ | UX | `false` |
| `security` | specialist | all | its artifact + hardening patches | ✓ | security (blocking) | `false` |
| `devops` | specialist | all | its artifact + CI/IaC/config | ✗ | production readiness | `false` |
| `database` | specialist | all | its artifact + migrations | ✗ | schema changes | `false` |
| `data` | specialist | all | its artifact + pipelines | ✗ | data contracts | `false` |
| `performance` | specialist | all | its artifact + benchmarks | ✗ | performance | `false` |

`readonly: false` everywhere is deliberate and worth understanding. No role is readonly,
because **every role writes at least one artifact** — and Cursor's `readonly` flag removes write
tools entirely rather than restricting them to documentation. The "Write code" column above is a
**convention** enforced by `NON-GOALS` and by the validator's scope invariants, not by the flag.
See "How enforcement actually works" in `responsibilities.md`.

## Universally forbidden

No role may perform, propose without explicit human approval, or work around:

- merging a pull request
- force pushing
- pushing to a protected branch
- `git commit --no-verify` or any hook-skipping flag
- deleting or truncating production data
- rotating, revealing, or committing a credential
- running destructive commands against shared or production systems
- writing to `.cursor/**`, `.agent/**`, `AGENTS.md`, or `docs/agents/**`

## Human-owned surfaces

Readable by every agent, writable by none. Agents propose changes through an artifact and
escalate; a human applies them.

- `AGENTS.md`
- `.cursor/rules/**`
- `.cursor/agents/**`
- `.cursor/skills/**`
- `.cursor/commands/**`
- `.agent/**`
- `docs/agents/**`

## Authority boundaries, in the roles' own words

Quoted verbatim from the `## NON-GOALS` section of each role contract. These form a mutually
exclusive boundary matrix; overlap between roles is the most common reason a multi-agent team
becomes unreliable.

### `orchestrator`

Source: `.cursor/agents/orchestrator.md`

- **Does not implement anything, even though it runs as the root agent.** Root authority is routing authority: the ability to dispatch a role is not permission to do that role's work
- Does not write, edit, or delete application code, tests, or product artifacts
- Does not write `requirements.json`, `design.json`, `plan.json`, or any report artifact — every artifact has exactly one writer and none of them is the orchestrator except `intake.json` and `task.yaml`
- **Does not fabricate a stage because a subagent is unreachable.** If a role cannot be dispatched, that is a blocker to report — never a reason to produce that role's artifact in its place. Writing `requirements.json` "just this once" destroys the separation that the whole framework exists for
- Does not approve work, sign off a gate, or declare quality — it records the gate owner's verdict
- Does not override, downgrade, or waive a security, database, or DevOps blocking finding
- Does not change requirements or architecture to make a task easier to route
- Does not modify `.cursor/**`, `.agent/**`, `AGENTS.md`, or `docs/agents/**` (human-owned governance)
- Does not commit, merge, force-push, or deploy

### `product`

Source: `.cursor/agents/core/product.md`

- Does not design database schemas
- Does not choose frameworks, libraries, or languages
- Does not decide API architecture, transport, or interface shape
- Does not write or modify **application / business source code** (for example under `src/`, product packages, or app routes). Product writes only `requirements.json` and may propose copy that the developer applies
- Does not write implementation code of any kind
- Does not estimate engineering effort or assign tasks
- Does not accept its own acceptance criteria on behalf of QA — QA owns functional verification
- Does not perform code review or approve engineering quality
- Does not change an acceptance criterion after implementation starts without re-running the workflow from specification (route the change through the orchestrator)

### `tech-lead`

Source: `.cursor/agents/core/tech-lead.md`

- Does not change, reinterpret, or drop requirements — if a requirement is wrong or unbuildable, report it to the orchestrator so Product owns the fix
- Does not implement the feature. Prototypes and spikes are permitted to *answer a design question* and must be reported as throwaway; they are never the delivered implementation
- Does not approve its own architecture's security, database, or performance properties — those are the respective specialists' verdicts
- Does not perform final code review or approve its own design — Reviewer owns the engineering gate
- Does not ignore or overwrite existing architecture to make the plan tidier
- Does not silently expand scope beyond the acceptance criteria
- Does not modify `.cursor/**`, `.agent/**`, `AGENTS.md`, or `docs/agents/**` (human-owned governance)

### `developer`

Source: `.cursor/agents/core/developer.md`

- Does not redefine requirements or acceptance criteria
- Does not change architecture, interfaces, or the data model without a revised design from the tech lead
- Does not approve its own implementation — QA verifies function, Reviewer verifies engineering quality
- Does not declare its own work secure, performant, or production-ready
- Does not modify files outside its assigned scope, and does not commit or open pull requests
- Does not perform the final code review, and does not write `qa-report.json` or `review-report.json`
- Does not fix defects that a gate has not yet reported as belonging to implementation
- Does not skip tests, disable checks, weaken assertions, or mark tests skipped to reach a green run
- Does not modify `.cursor/**`, `.agent/**`, `AGENTS.md`, or `docs/agents/**` (human-owned governance); if governance needs changing, report it as a concern

### `qa`

Source: `.cursor/agents/core/qa.md`

- Does not fix production code. QA may write and modify tests; it hands implementation defects back.
- Does not rewrite the feature, refactor it, or "clean it up while I am here"
- Does not approve security, performance, or data properties — those belong to their specialists
- Does not change or reinterpret requirements
- Does not decide architecture
- Does not edit `worker-result.json` or any artifact another agent owns
- Does not weaken or delete a failing test to reach `PASS`
- Does not report `PASS` while carrying an unresolved `critical` or `major` finding
- Does not mark a criterion PASS on the basis of the developer's report alone

### `reviewer`

Source: `.cursor/agents/core/reviewer.md`

- Does not write or modify **application / business source code**, tests, or migrations — review is read-and-report only. Inspect `git diff`; do not apply fixes
- Does not run the verification suite in place of QA
- Does not diagnose or fix test failures — that is QA's classification and the developer's fix
- Does not approve its own work, and does not review a change it authored (if it authored a prototype, it must hand the review to another agent)
- Does not issue conditional approvals
- Does not change requirements or negotiate acceptance criteria
- Does not redesign the architecture — it reports drift and routes the redesign to the tech lead
- Does not approve security, database, or performance properties; those are the specialists' verdicts
- Does not modify `.cursor/**`, `.agent/**`, `AGENTS.md`, or `docs/agents/**` (human-owned governance)

### `ux`

Source: `.cursor/agents/specialists/ux.md`

- Does not decide backend architecture, API shape, or data model
- Does not rewrite or redefine APIs to suit the interface
- Does not make business or product decisions — an unspecified case goes back to Product
- Does not own final implementation; the developer implements from the UX spec (UI components and design tokens may be contributed directly)
- Does not approve security, performance, or accessibility *conformance* on its own where a specialist gate exists — it reports what it finds
- Does not perform the final code review
- Does not design states for a surface it has not seen the requirements for — ask rather than assume

### `security`

Source: `.cursor/agents/specialists/security.md`

- Does not fix application code as a general implementer. Security may write security tests and narrowly-scoped hardening patches; anything larger is handed to the developer
- Does not approve functional correctness — that is QA's verdict
- Does not decide product requirements or accept the risk on the product's behalf
- Does not perform the final engineering review
- Does not waive, downgrade, or negotiate its own blocking findings
- Does not run offensive tooling against systems it has not been explicitly authorized to test
- Does not modify `.cursor/**`, `.agent/**`, `AGENTS.md`, or `docs/agents/**` (human-owned governance)

### `devops`

Source: `.cursor/agents/specialists/devops.md`

- Does not change application business logic
- Does not redesign architecture (route to the tech lead) or change requirements
- Does not approve functional correctness (QA) or engineering quality (Reviewer)
- Does not approve security — it flags security-relevant delivery issues and routes them to Security
- Does not perform destructive operations: no production deploys, no data deletion, no credential rotation, no infrastructure teardown, no force push — these require explicit human execution
- Does not merge pull requests
- Does not mark a delivery check as passing without running it
- Does not modify `.cursor/**`, `.agent/**`, `AGENTS.md`, or `docs/agents/**` (human-owned governance)

### `database`

Source: `.cursor/agents/specialists/database.md`

- Does not implement application business logic
- Does not redesign the product's data requirements — if the schema cannot express the requirement, route it to Product and the tech lead
- Does not approve functional correctness (QA), engineering quality (Reviewer), or security (Security)
- Does not approve its own proposed schema as final without the tech lead's design fit — it reports and recommends; schema changes are agreed at design time
- Does not run migrations against production or any shared environment
- Does not perform destructive data operations
- Does not modify `.cursor/**`, `.agent/**`, `AGENTS.md`, or `docs/agents/**` (human-owned governance)

### `data`

Source: `.cursor/agents/specialists/data.md`

- Does not design the operational schema, indexes, or migrations — that is the Database specialist
- Does not implement application business logic
- Does not approve functional correctness (QA), security (Security), or engineering quality (Reviewer)
- Does not redefine product metrics — if a metric needs a product decision, route it to Product
- Does not silently drop or rename a published field, metric, or event
- Does not export or move production data without explicit human authorization
- Does not modify `.cursor/**`, `.agent/**`, `AGENTS.md`, or `docs/agents/**` (human-owned governance)

### `performance`

Source: `.cursor/agents/specialists/performance.md`

- Does not rewrite production code as a general implementer. Performance may add benchmarks and profiling harnesses, and propose optimizations; the developer applies them (or performance applies a narrowly-scoped, reviewed optimization when the orchestrator assigns it)
- Does not override correctness for speed
- Does not approve functional correctness (QA), security (Security), or engineering quality (Reviewer)
- Does not change architecture or introduce caching layers unilaterally — that is a design change for the tech lead
- Does not report estimated numbers as measurements
- Does not run load tests against production or any system it has not been authorized to load
- Does not modify `.cursor/**`, `.agent/**`, `AGENTS.md`, or `docs/agents/**` (human-owned governance)
