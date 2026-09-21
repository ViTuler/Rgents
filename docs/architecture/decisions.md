# Architecture decision records

Decisions that are **settled**. A settled decision is not reopened by a passing agent — disagreeing
with one is a reason to raise a proposal, not to work around it.

Every non-obvious, hard-to-reverse decision made by the tech lead is recorded here. `.cursor/rules/architecture.mdc`
requires it, and `design.json` carries the `adrs` array that produces these entries.

**Why record rejected alternatives:** a decision without its alternatives gets relitigated every few
months by someone who reasonably assumes it was never considered. The rejected options are often more
valuable than the decision itself.

## Status values

| Status | Meaning |
|---|---|
| `proposed` | under discussion; not yet binding |
| `accepted` | binding; agents must follow it |
| `superseded` | replaced by a later ADR — link it |
| `deprecated` | still in the code but should not be extended |

## Template

```markdown
## ADR-000 — <short title>

- **Status:** proposed | accepted | superseded by ADR-0XX | deprecated
- **Date:** YYYY-MM-DD
- **Task:** TASK-XXX
- **Deciders:** <roles>

### Context

What forced a decision. The constraints, the forces, and what made this non-obvious.

### Decision

What we will do. Stated as a rule someone can follow, not as a discussion.

### Consequences

What becomes easier. What becomes harder. What we are now committed to maintaining.

### Alternatives rejected

| Alternative | Why rejected |
|---|---|
| | |
```

---

## ADR-001 — Adopt a multi-agent team with independent quality gates

- **Status:** accepted
- **Date:** 2026-01-01
- **Task:** framework bootstrap
- **Deciders:** human owner

### Context

Software work done by a single AI agent has no independent verification. The agent that writes the
implementation also decides whether it is correct, secure, and maintainable — which means its blind
spots become the project's defects. Prompting an agent to "review your own work" does not fix this,
because the review inherits the same misunderstandings as the implementation.

### Decision

Structure development as a team of roles with non-overlapping authority, where:

- implementation and verification are always different roles
- communication happens through validated artifacts on disk, not relayed conversation
- quality gates are conditional on the task's risk profile rather than always-on ceremony
- the framework's own rules are enforced by an executable validator wherever a check is possible

### Consequences

**Easier:** defects are caught by a role whose incentives oppose the implementer's; every handoff is
auditable after the fact; context stays bounded because agents pass paths rather than transcripts.

**Harder:** more handoffs means more latency per task; roles must be kept genuinely non-overlapping or
the team degrades into duplicated work; a trivial task must be classified trivial or the process
becomes disproportionate.

**Committed to:** maintaining the role contracts, the schemas, and the validator as the team evolves.

### Alternatives rejected

| Alternative | Why rejected |
|---|---|
| A single agent with a self-review step | The review inherits the implementation's blind spots; independence is structural, not instructional |
| Persona prompts with no artifact contracts | Nothing is auditable, nothing is resumable, and handoffs decay into conversation relay |
| Always-on gates for every task | Disproportionate cost on trivial work; teams abandon gates that feel ceremonial |
| A workflow engine with an external dependency | Portability and zero-install matter more than orchestration features the agent can already follow |

---

## ADR-002 — Artifacts are the communication protocol

- **Status:** accepted
- **Date:** 2026-01-01
- **Task:** framework bootstrap
- **Deciders:** human owner

### Context

Multi-agent systems degrade as context grows: each handoff relays a longer transcript, the receiving
agent cannot distinguish current truth from stale discussion, and the task becomes unresumable because
its state exists only in a conversation.

### Decision

Every handoff is a JSON artifact at a known path, written by exactly one role, validated against a
schema. Agents receive **paths**, never contents, and read the artifact themselves.

### Consequences

**Easier:** bounded context; each step independently checkable; a task resumable by any agent or human
from disk alone; drift between what was claimed and what was done becomes mechanically detectable.

**Harder:** artifact shapes must be maintained and versioned; an agent that writes a sloppy artifact
breaks a downstream gate; free-form nuance must be forced into fields.

### Alternatives rejected

| Alternative | Why rejected |
|---|---|
| Pass artifact contents inline in the prompt | Reintroduces unbounded context and stale-copy risk |
| A shared conversational memory | Not auditable, not resumable, and grows without limit |
| A database or service for state | Adds an install and a failure mode for something a directory does adequately |
