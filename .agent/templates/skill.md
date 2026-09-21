---
name: <skill-name>
description: "<What this procedure accomplishes, and when to pull it in. Written in the third person; this text is how an agent decides to load the skill. Longer and more explicit than an agent description.>"
---

<!--
Template for a skill.

A skill is a reusable PROCEDURE: "here is how we do this kind of work".
An agent is a role: "here is what I am responsible for".
A rule is a constraint: "here is what always applies".

If you are about to paste a numbered procedure into an agent file, it belongs here instead.
Skills load on demand, so they cost nothing until they are needed — which is why detailed
checklists belong in a skill rather than in an always-on rule.

Layout: .cursor/skills/<skill-name>/SKILL.md  (one directory per skill)

Frontmatter accepts exactly two fields: name, description.
-->

# <Skill title>

## When to use

- <Trigger conditions. Be concrete enough that an agent can decide without guessing.>

## Procedure

1. ...
2. ...
3. ...

## Output

<What this procedure produces, and where it goes. Reference the artifact path and its schema.>

## Anti-patterns

- <The specific mistakes this procedure exists to prevent.>
