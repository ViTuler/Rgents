# Responsibilities — primary owner and independent reviewer per concern

Generated from `.cursor/agents/**` by `.agent/regenerate-governance-docs.py`.
Regenerate rather than hand-editing: a responsibility matrix that drifts from the role
contracts is worse than no matrix, because it is trusted.

**Primary owner** is the only role that may write the artifact for that concern.
**Independent reviewer** is the role that may block it. A role is never its own reviewer.

| Concern | Team | Primary owner | Independent reviewer |
|---|---|---|---|
| Triage & routing | core | `orchestrator` | `human` |
| Requirements | core | `product` | `tech-lead` |
| Acceptance criteria | core | `product` | `qa` |
| Architecture | core | `tech-lead` | `reviewer` |
| Technical design | core | `tech-lead` | `reviewer` |
| Interface contracts | core | `tech-lead` | `reviewer` |
| Task decomposition | core | `tech-lead` | `orchestrator` |
| Implementation | core | `developer` | `reviewer` |
| Unit tests | core | `developer` | `qa` |
| Integration tests | core | `qa` | `reviewer` |
| Functional verification | core | `qa` | `reviewer` |
| Final engineering quality | core | `reviewer` | `human` |
| UX flow & states | specialist | `ux` | `product` |
| UI / interaction design | specialist | `ux` | `reviewer` |
| Accessibility | specialist | `ux` | `reviewer` |
| Security architecture | specialist | `security` | `tech-lead` |
| Security testing | specialist | `security` | `reviewer` |
| Database schema | specialist | `database` | `tech-lead` |
| Migrations | specialist | `database` | `devops` |
| Query performance | specialist | `database` | `performance` |
| Event & metric contracts | specialist | `data` | `product` |
| CI/CD & build | specialist | `devops` | `reviewer` |
| Production readiness | specialist | `devops` | `reviewer` |
| Rollback | specialist | `devops` | `database` |
| Measured performance | specialist | `performance` | `tech-lead` |
| Task lifecycle & closure | core | `orchestrator` | `human` |

## Separation of duties

No role appears as both primary owner and independent reviewer for the same concern.
Three separations matter most, and each is enforced structurally rather than by instruction:

1. **Implementation vs. verification.** `developer` writes code; `qa` writes the verdict on it.
   The validator rejects a QA report claiming PASS while a criterion or a critical finding fails.
2. **Implementation vs. engineering approval.** `developer` never writes `review-report.json`.
   The validator rejects a review PASS that still carries blockers or concerns.
3. **Assessment vs. waiver.** A blocking finding raised by `security`, `database`, `performance`,
   or `devops` cannot be downgraded or waived by `developer`, `tech-lead`, or `orchestrator`.
   Only the raising specialist may resolve its own finding, and only with evidence.

## How enforcement actually works

Three mechanisms, in order of strength:

| Mechanism | Enforces | Strength |
|---|---|---|
| `readonly` frontmatter | removes write tools from the subagent entirely | **hard** — the subagent cannot write anything |
| `.agent/tools/validate.py` scope invariants | the plan's file list vs. the real `git diff`, in both directions | **hard** — errors block the gate |
| One-writer-per-artifact matrix | who may write which artifact | **convention** — not machine-enforced |
| `NON-GOALS` per role | domain authority ("does not write application code") | **convention** — not machine-enforced |

### The `readonly` flag is a capability switch, not a documentation field

Cursor documents it as: *"if `true`, the subagent runs with restricted write permissions
(no file edits, no state-changing shell commands)."* It is therefore **all-or-nothing**: a
readonly subagent cannot write its own report artifact either.

This has a direct consequence, and getting it wrong is not hypothetical: **a role that must write
an artifact cannot be readonly.** An earlier revision of this framework declared `product`,
`tech-lead`, and `reviewer` as `readonly: true` while they were the sole writers of
`requirements.json`, `design.json`/`plan.json`, and `review-report.json`. Each was dispatched and
then failed on its first write; the failure surfaced only at runtime.

That class of mistake is now a configuration-time error rather than a runtime surprise.
`.agent/tools/validate.py --check-setup` reports `readonly_cannot_write_artifact`, and the selftest
carries a canary that fails if the conflict is reintroduced.

So: `readonly` expresses **can this role write at all**, never **is this role allowed to write code**.
The second question is answered by `NON-GOALS` and by the artifact matrix — conventions that the
framework states plainly as conventions rather than dressing them up as enforcement.
