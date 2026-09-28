# Templates and starting points

Copy these to start new work. They exist so that adding to the team does not require
reconstructing conventions from memory.

| Template | Use it to |
|----------|-----------|
| `agent.md` | define a new role under `.cursor/agents/` |
| `rule.mdc` | add a rule under `.cursor/rules/` |
| `skill.md` | add a reusable procedure under `.cursor/skills/<name>/SKILL.md` |
| `task/` | rare hand-start: follow its README under `tasks/active/<TASK-ID>/` (there is no `tasks/_template/`) |
| `knowledge/` | product-owned starters → `docs/knowledge/` on seed create |
| `architecture/` | optional product-owned starters → `docs/architecture/` on seed create (never upgraded) |
| `project-baseline.yaml` | → `.agent/project-baseline.yaml` on seed create |

## After adding any of these

These registrations must stay in sync. The setup lint checks them, so run it and fix what it reports:

```bash
python .agent/tools/validate.py --check-setup
```

1. **New role** → add it to the `team:` block of `.agent/config.yaml`. The lint reports
   `agent_registered` if you forget, and `agent_missing` if you declare a role with no file.
   Also add it to `ARTIFACT_WRITERS` in `.agent/tools/validate.py` so the readonly/artifact-write
   conflict can be checked; the lint warns `agent_unmapped` if you forget.
2. **New rule** → no registration needed; `glob`/`description` handles activation. Confirm the
   frontmatter uses only `description`, `alwaysApply`, and `globs`.
3. **New skill** → no registration needed. One directory per skill, containing `SKILL.md`.
4. **New artifact type** → three changes, all required:
   - add a schema to `.agent/schemas/`
   - add the filename, schema, and sole writer to `ARTIFACT_CONTRACTS` in `.agent/tools/validate.py`
   - document it in the artifact table in `AGENTS.md`

   Skipping any one of these produces an artifact with no contract — the exact blind spot that
   made a gate stage unverifiable in one of the reference projects this framework was built from.
5. **New stage** → add a checker to `.agent/tools/validate.py`, register it in `STAGE_CHECKERS` and
   `ALL_STAGES`, include it in `applicable_stages` if it does not apply to every task, add it to the
   relevant stages in `.agent/workflows/*.yaml`, and add a selftest canary proving it fires.

## New intake: the duplicate check is mandatory

Every task's `intake.json` must carry `overlap_check`, including when the comparison found nothing.
When writing an intake by hand, run the scorer and record what it says:

```bash
python .agent/tools/validate.py --task <TASK-ID> --stage duplicate_check
```

A `likely` match must be adjudicated by **the human**, not the orchestrator — see
`docs/agents/protocols.md`. The check exists because two active tasks describing one request both look
authoritative, and nothing else in the pipeline can see it.

## Never set `readonly: true` on a role that writes an artifact

Cursor's `readonly` flag is a **capability switch**, not a documentation field: `true` removes write
tools entirely, including the ability to write the role's own report. Since every role in this team
writes at least one artifact, **no role here is readonly**.

Authority — "does not write application code" — is enforced by the role's `NON-GOALS` and by the
validator's scope invariants, never by the flag. The lint refuses a readonly role that is a required
artifact writer (`readonly_cannot_write_artifact`), because that combination is dispatched successfully
and then fails on its first write.

## Regenerating the governance documents

`docs/agents/permissions.md` and `docs/agents/responsibilities.md` are generated from the role
contracts. Regenerate after editing any agent file:

```bash
python .agent/regenerate-governance-docs.py
```

Hand-editing them guarantees drift, and a permission matrix that disagrees with the contracts is
worse than no matrix, because it is trusted.

## Naming

| Prefix | Meaning |
|--------|---------|
| no prefix | core team role or first-party asset |
| (specialists live in `.cursor/agents/specialists/`) | conditional specialist |

## Extension checklist

- [ ] Role file includes the four **required** sections (`ROLE`, `PRIMARY OBJECTIVE`, `CORE RESPONSIBILITIES`, `NON-GOALS`); also add `DECISION FRAMEWORK` by convention
- [ ] `description` states when to use the agent
- [ ] Frontmatter uses only Cursor-recognised fields: `name`, `description`, `model`, `readonly`, `is_background`
- [ ] `NON-GOALS` names enough exclusions that validate does not warn (warns when fewer than **3**; aim for clear role separation)
- [ ] Registered in `.agent/config.yaml` if it is a role
- [ ] Artifact has a schema, a contract entry, and a row in `AGENTS.md` if it produces one
- [ ] `python .agent/tools/validate.py --selftest` still passes
