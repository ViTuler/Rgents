# Architecture overview

> **Status: template.** Replace with the real system architecture for the project this team works on.
> Agents read this before designing anything; an outdated architecture doc is worse than none because
> it is trusted. Keep it current or delete sections that are no longer true.

## Purpose

What the system does, in two sentences, for someone who has never seen it.

## System context

Who and what talks to this system.

```
        ┌──────────┐        ┌──────────┐
        │  Actor A │        │  Actor B │
        └────┬─────┘        └────┬─────┘
             │                   │
             └─────────┬─────────┘
                       ▼
              ┌────────────────┐
              │     System     │
              └───────┬────────┘
                      │
        ┌─────────────┼─────────────┐
        ▼             ▼             ▼
   ┌─────────┐  ┌──────────┐  ┌──────────┐
   │ Store   │  │ External │  │ Queue /  │
   │         │  │ Service  │  │ Jobs     │
   └─────────┘  └──────────┘  └──────────┘
```

## Components

| Component | Responsibility | Depends on | Owns data |
|---|---|---|---|
| | | | |

## Layering rules

Binding. Violations are review blockers, not style preferences.

- Layer direction:
- What may call what:
- Where business logic lives:
- Where persistence access lives:
- What may not import what:

## Data

| Entity | Owner | Lives in | Retention |
|---|---|---|---|
| | | | |

Key invariants enforced by the schema rather than by application code:

-

## Trust boundaries

Where untrusted input enters, and what is verified at each boundary. Security uses this to scope its
threat model.

| Boundary | What crosses it | Verified by |
|---|---|---|
| | | |

## Cross-cutting concerns

| Concern | Mechanism | Convention |
|---|---|---|
| Authentication | | |
| Authorization | | |
| Logging | | |
| Error handling | | |
| Configuration | | |
| Observability | | |
| Feature flags | | |

## Deployment

| Aspect | Approach |
|---|---|
| Build artifact | |
| Environments | |
| Migration strategy | |
| Rollback strategy | |
| Health checks | |

## Known architectural debt

Structural problems that are known, accepted, and *not* to be fixed opportunistically. Fixing these
requires a dedicated refactor task with its own gates.

| Debt | Impact | Why it persists |
|---|---|---|
| | | |
