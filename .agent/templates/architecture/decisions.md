# Architecture decision records (product template)

> **Product-owned.** Rgents seeds this file once on `create`; upgrades never overwrite it.
> Record *your product's* settled decisions here. Disagreeing with an accepted ADR is a reason to
> raise a proposal, not to work around it.

**Why record rejected alternatives:** a decision without its alternatives gets relitigated every few
months by someone who reasonably assumes it was never considered.

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

## Records

<!-- Append accepted ADRs below. -->
