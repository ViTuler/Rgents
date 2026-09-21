---
name: <role-name>
description: <What this role does, in one sentence.> Use <when this agent should be invoked — this sentence is the only automatic routing trigger surface Cursor sees, so be specific about the conditions.>
model: inherit
readonly: <true | false>
---

# <ROLE NAME>

<!--
Template for a new role. Fill every section. Do not delete sections.

Rules for a good role definition:
  * Frontmatter accepts exactly four fields: name, description, model, readonly.
    Cursor recognises no others; extra fields are ignored and will drift.
  * The description must state WHEN to use the agent. That sentence is the routing trigger.
  * The four required sections are: ROLE, PRIMARY OBJECTIVE, CORE RESPONSIBILITIES, NON-GOALS.
  * NON-GOALS is the primary authority boundary. It replaces a machine-readable tool allowlist.
    Write at least four, and make them a mutually exclusive matrix against the other roles:
    what this role must never do because another role owns it.
  * Keep it under ~120 lines. A role definition is a contract, not an essay.
  * Do not restate policy from .agent/config.yaml or AGENTS.md. Reference it.
-->

## ROLE

<Who this agent is, and what it owns. State the question this role exists to answer.>

Consumes: <upstream artifacts>. Produces: <artifact this role writes>.

## PRIMARY OBJECTIVE

<The single outcome this role optimizes for. One short paragraph. If you cannot state it in two
sentences, the role's boundary is not clear enough yet.>

## CORE RESPONSIBILITIES

<!-- Concrete, checkable duties. Prefer lists over prose. -->

- ...
- ...

## DECISION FRAMEWORK

<!--
Optional but recommended. The tie-breaking rules this role applies when trade-offs conflict.
Stating these explicitly is what makes a role's output predictable across runs.
-->

1. ...
2. ...

## NON-GOALS

<!--
The authority boundary. This is the most important section: it is what keeps roles from
overlapping, and overlap is what makes multi-agent teams unreliable.

At least four. Each should name the role that DOES own the thing.
-->

- Does not ...
- Does not ...
- Does not ...
- Does not modify `.cursor/**`, `.agent/**`, `AGENTS.md`, or `docs/agents/**` (human-owned governance)
