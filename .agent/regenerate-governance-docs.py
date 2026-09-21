"""Regenerate docs/agents/permissions.md and docs/agents/responsibilities.md from the contracts.

Run from the repository root:
    python .agent/regenerate-governance-docs.py

Why a generator: these documents describe the role contracts. Hand-maintaining them guarantees
drift, and a permission matrix that disagrees with the contracts is worse than no matrix, because
it is trusted. This reads the actual frontmatter and the actual NON-GOALS text.
"""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
AGENTS = ROOT / ".cursor" / "agents"
(ROOT / "docs" / "agents").mkdir(parents=True, exist_ok=True)

ORDER = ["orchestrator", "product", "tech-lead", "developer", "qa", "reviewer",
         "ux", "security", "devops", "database", "data", "performance"]

# Role -> (team, capability summary). Kept beside the generated tables because it is prose
# interpretation, not a field in the contracts.
CAPABILITY = {
    "orchestrator": ("core", "all", "state files only", "✗", "✗ (closes only)"),
    "product": ("core", "all", "its artifact only", "✗", "requirements"),
    "tech-lead": ("core", "all", "its artifacts + spikes", "✗", "design"),
    "developer": ("core", "all", "✓", "✓", "✗"),
    "qa": ("core", "all", "✗", "✓", "functional verification"),
    "reviewer": ("core", "all", "its artifact only", "✗", "code (final engineering gate)"),
    "ux": ("specialist", "all", "its artifact + UI specs/tokens", "✗", "UX"),
    "security": ("specialist", "all", "its artifact + hardening patches", "✓", "security (blocking)"),
    "devops": ("specialist", "all", "its artifact + CI/IaC/config", "✗", "production readiness"),
    "database": ("specialist", "all", "its artifact + migrations", "✗", "schema changes"),
    "data": ("specialist", "all", "its artifact + pipelines", "✗", "data contracts"),
    "performance": ("specialist", "all", "its artifact + benchmarks", "✗", "performance"),
}

records = {}
for path in sorted(AGENTS.rglob("*.md")):
    text = path.read_text(encoding="utf-8")
    m = re.match(r"\A---\s*\n(.*?)\n---\s*\n(.*)\Z", text, re.DOTALL)
    if not m:
        continue
    fm, body = m.group(1), m.group(2)
    name = re.search(r"^name:\s*(\S+)\s*$", fm, re.M).group(1)
    ro = re.search(r"^readonly:\s*(\S+)\s*$", fm, re.M)
    non_goals = []
    if "## NON-GOALS" in body:
        for line in body.split("## NON-GOALS", 1)[1].splitlines():
            s = line.strip()
            if s.startswith("- "):
                non_goals.append(s[2:].strip())
    records[name] = {
        "path": path.relative_to(ROOT).as_posix(),
        "readonly": ro.group(1) if ro else "(unset)",
        "non_goals": non_goals,
    }

missing = [r for r in ORDER if r not in records]
if missing:
    raise SystemExit(f"ERROR: no agent definition for {missing}")

# ---------------------------------------------------------------- responsibilities.md
lines = [
    "# Responsibilities — primary owner and independent reviewer per concern", "",
    "Generated from `.cursor/agents/**` by `.agent/regenerate-governance-docs.py`.",
    "Regenerate rather than hand-editing: a responsibility matrix that drifts from the role",
    "contracts is worse than no matrix, because it is trusted.", "",
    "**Primary owner** is the only role that may write the artifact for that concern.",
    "**Independent reviewer** is the role that may block it. A role is never its own reviewer.", "",
    "| Concern | Team | Primary owner | Independent reviewer |", "|---|---|---|---|",
]
for concern, team, owner, rev in [
    ("Triage & routing", "core", "orchestrator", "human"),
    ("Requirements", "core", "product", "tech-lead"),
    ("Acceptance criteria", "core", "product", "qa"),
    ("Architecture", "core", "tech-lead", "reviewer"),
    ("Technical design", "core", "tech-lead", "reviewer"),
    ("Interface contracts", "core", "tech-lead", "reviewer"),
    ("Task decomposition", "core", "tech-lead", "orchestrator"),
    ("Implementation", "core", "developer", "reviewer"),
    ("Unit tests", "core", "developer", "qa"),
    ("Integration tests", "core", "qa", "reviewer"),
    ("Functional verification", "core", "qa", "reviewer"),
    ("Final engineering quality", "core", "reviewer", "human"),
    ("UX flow & states", "specialist", "ux", "product"),
    ("UI / interaction design", "specialist", "ux", "reviewer"),
    ("Accessibility", "specialist", "ux", "reviewer"),
    ("Security architecture", "specialist", "security", "tech-lead"),
    ("Security testing", "specialist", "security", "reviewer"),
    ("Database schema", "specialist", "database", "tech-lead"),
    ("Migrations", "specialist", "database", "devops"),
    ("Query performance", "specialist", "database", "performance"),
    ("Event & metric contracts", "specialist", "data", "product"),
    ("CI/CD & build", "specialist", "devops", "reviewer"),
    ("Production readiness", "specialist", "devops", "reviewer"),
    ("Rollback", "specialist", "devops", "database"),
    ("Measured performance", "specialist", "performance", "tech-lead"),
    ("Task lifecycle & closure", "core", "orchestrator", "human"),
]:
    lines.append(f"| {concern} | {team} | `{owner}` | `{rev}` |")

lines += [
    "", "## Separation of duties", "",
    "No role appears as both primary owner and independent reviewer for the same concern.",
    "Three separations matter most, and each is enforced structurally rather than by instruction:", "",
    "1. **Implementation vs. verification.** `developer` writes code; `qa` writes the verdict on it.",
    "   The validator rejects a QA report claiming PASS while a criterion or a critical finding fails.",
    "2. **Implementation vs. engineering approval.** `developer` never writes `review-report.json`.",
    "   The validator rejects a review PASS that still carries blockers or concerns.",
    "3. **Assessment vs. waiver.** A blocking finding raised by `security`, `database`, `performance`,",
    "   or `devops` cannot be downgraded or waived by `developer`, `tech-lead`, or `orchestrator`.",
    "   Only the raising specialist may resolve its own finding, and only with evidence.", "",
    "## How enforcement actually works", "",
    "Three mechanisms, in order of strength:", "",
    "| Mechanism | Enforces | Strength |",
    "|---|---|---|",
    "| `readonly` frontmatter | removes write tools from the subagent entirely | **hard** — the subagent cannot write anything |",
    "| `.agent/tools/validate.py` scope invariants | the plan's file list vs. the real `git diff`, in both directions | **hard** — errors block the gate |",
    "| One-writer-per-artifact matrix | who may write which artifact | **convention** — not machine-enforced |",
    "| `NON-GOALS` per role | domain authority (\"does not write application code\") | **convention** — not machine-enforced |",
    "",
    "### The `readonly` flag is a capability switch, not a documentation field",
    "",
    "Cursor documents it as: *\"if `true`, the subagent runs with restricted write permissions",
    "(no file edits, no state-changing shell commands).\"* It is therefore **all-or-nothing**: a",
    "readonly subagent cannot write its own report artifact either.",
    "",
    "This has a direct consequence, and getting it wrong is not hypothetical: **a role that must write",
    "an artifact cannot be readonly.** An earlier revision of this framework declared `product`,",
    "`tech-lead`, and `reviewer` as `readonly: true` while they were the sole writers of",
    "`requirements.json`, `design.json`/`plan.json`, and `review-report.json`. Each was dispatched and",
    "then failed on its first write; the failure surfaced only at runtime.",
    "",
    "That class of mistake is now a configuration-time error rather than a runtime surprise.",
    "`.agent/tools/validate.py --check-setup` reports `readonly_cannot_write_artifact`, and the selftest",
    "carries a canary that fails if the conflict is reintroduced.",
    "",
    "So: `readonly` expresses **can this role write at all**, never **is this role allowed to write code**.",
    "The second question is answered by `NON-GOALS` and by the artifact matrix — conventions that the",
    "framework states plainly as conventions rather than dressing them up as enforcement.",
    "",
]
(ROOT / "docs" / "agents" / "responsibilities.md").write_text("\n".join(lines), encoding="utf-8")
print("wrote docs/agents/responsibilities.md")

# ---------------------------------------------------------------- permissions.md
perm = [
    "# Permissions — what each role may and may not do", "",
    "Generated from `.cursor/agents/**` by `.agent/regenerate-governance-docs.py`. The `NON-GOALS`",
    "sections are quoted directly from each role contract, because that is the actual authority",
    "boundary for agent behavior.", "",
    "## Capability matrix", "",
    "| Role | Team | Read | Write code | Write tests | May approve | `readonly` |",
    "|---|---|---|---|---|---|---|",
]
for role in ORDER:
    team, read, code, tests, approve = CAPABILITY[role]
    perm.append(f"| `{role}` | {team} | {read} | {code} | {tests} | {approve} | `{records[role]['readonly']}` |")

perm += [
    "", "`readonly: false` everywhere is deliberate and worth understanding. No role is readonly,",
    "because **every role writes at least one artifact** — and Cursor's `readonly` flag removes write",
    "tools entirely rather than restricting them to documentation. The \"Write code\" column above is a",
    "**convention** enforced by `NON-GOALS` and by the validator's scope invariants, not by the flag.",
    "See \"How enforcement actually works\" in `responsibilities.md`.", "",
    "## Universally forbidden", "",
    "No role may perform, propose without explicit human approval, or work around:", "",
]
for forbidden in [
    "merging a pull request", "force pushing", "pushing to a protected branch",
    "`git commit --no-verify` or any hook-skipping flag",
    "deleting or truncating production data",
    "rotating, revealing, or committing a credential",
    "running destructive commands against shared or production systems",
    "writing to `.cursor/**`, `.agent/**`, `AGENTS.md`, or `docs/agents/**`",
]:
    perm.append(f"- {forbidden}")

perm += ["", "## Human-owned surfaces", "",
         "Readable by every agent, writable by none. Agents propose changes through an artifact and",
         "escalate; a human applies them.", ""]
for surface in ["`AGENTS.md`", "`.cursor/rules/**`", "`.cursor/agents/**`", "`.cursor/skills/**`",
                "`.cursor/commands/**`", "`.agent/**`", "`docs/agents/**`"]:
    perm.append(f"- {surface}")

perm += ["", "## Authority boundaries, in the roles' own words", "",
         "Quoted verbatim from the `## NON-GOALS` section of each role contract. These form a mutually",
         "exclusive boundary matrix; overlap between roles is the most common reason a multi-agent team",
         "becomes unreliable.", ""]
for role in ORDER:
    perm += [f"### `{role}`", "", f"Source: `{records[role]['path']}`", ""]
    perm += [f"- {item}" for item in records[role]["non_goals"]]
    perm.append("")

(ROOT / "docs" / "agents" / "permissions.md").write_text("\n".join(perm), encoding="utf-8")
print("wrote docs/agents/permissions.md")
