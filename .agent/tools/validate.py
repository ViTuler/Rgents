#!/usr/bin/env python3
"""Rgents — zero-dependency artifact validator, gate invariant checker, and setup linter.

Why this exists
---------------
A multi-agent team fails in predictable ways that no amount of prompt discipline fixes reliably:

  1. The plan drifts from the implementation.
  2. A gate gets skipped, or a "pass" is inferred from a missing report.
  3. A "PASS" verdict quietly carries blockers.
  4. An agent writes outside its declared scope.
  5. The team's own configuration drifts out of sync with its agent files.

This script turns each of those into a hard, executable error. It deliberately uses only the
standard library so it can be copied into any project and run anywhere.

Usage
-----
    python .agent/tools/validate.py --selftest
    python .agent/tools/validate.py --check-setup
    python .agent/tools/validate.py --ci-changed --base origin/main
    python .agent/tools/validate.py --artifact tasks/TASK-001/plan.json
    python .agent/tools/validate.py --task TASK-001 --stage plan
    python .agent/tools/validate.py --task TASK-001 --stage implementation
    python .agent/tools/validate.py --task TASK-001 --stage qa
    python .agent/tools/validate.py --task TASK-001 --stage review
    python .agent/tools/validate.py --task TASK-001 --all

Exit codes
----------
    0  all checks passed (warnings allowed)
    1  one or more errors — a gate did not pass
    2  environment error — bad path, unreadable file, malformed JSON
"""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
import os
import re
import stat
import subprocess
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

# --------------------------------------------------------------------------------------
# Constants
# --------------------------------------------------------------------------------------

REPO_ROOT = Path(__file__).resolve().parents[2]

# artifact filename -> (schema filename, sole writer role)
ARTIFACT_CONTRACTS = {
    "intake.json": ("intake.schema.json", "orchestrator"),
    "requirements.json": ("requirements.schema.json", "product"),
    "design.json": ("design.schema.json", "tech-lead"),
    "plan.json": ("plan.schema.json", "tech-lead"),
    "worker-result.json": ("worker-result.schema.json", "developer"),
    "qa-report.json": ("qa-report.schema.json", "qa"),
    "review-report.json": ("review-report.schema.json", "reviewer"),
    "security-report.json": ("security-report.schema.json", "security"),
    "ux-report.json": ("specialist-report.schema.json", "ux"),
    "db-report.json": ("specialist-report.schema.json", "database"),
    "perf-report.json": ("specialist-report.schema.json", "performance"),
    "data-report.json": ("specialist-report.schema.json", "data"),
    "delivery-report.json": ("specialist-report.schema.json", "devops"),
}

# specialist-report.json documents whose `role` field must match the writer
SPECIALIST_ROLE_BY_ARTIFACT = {
    "ux-report.json": "ux",
    "db-report.json": "database",
    "perf-report.json": "performance",
    "data-report.json": "data",
    "delivery-report.json": "devops",
}

# Roles that may write a design-time consultation (consultation-<role>.json).
# `devops` is deliberately absent: delivery readiness is assessed against a built artifact, and a
# consultation written before any code exists would have nothing to confirm.
CONSULTATION_ROLES = frozenset({"ux", "security", "database", "performance", "data"})

# Consultations are per-specialist, so their filenames are dynamic: consultation-<role>.json. They
# get their own schema rather than a placeholder entry in ARTIFACT_CONTRACTS, because the point of
# the artifact is that it is NOT a gate report: a gate report that exists before the code does is a
# wrong claim, and a placeholder entry would let a consultation be read as a passed gate.
CONSULTATION_PREFIX = "consultation-"

# Files the implementation diff is allowed to touch without being flagged as out of scope.
SCOPE_EXEMPT_PREFIXES = ("tasks/", ".agent/", "docs/knowledge/")

# Gate order from .agent/config.yaml. Kept here so the checker can detect a skipped gate
# without parsing YAML.
GATE_ORDER = ["qa", "security", "performance", "ux", "database", "data", "review", "devops"]

GATE_ARTIFACT = {
    "qa": "qa-report.json",
    "security": "security-report.json",
    "performance": "perf-report.json",
    "ux": "ux-report.json",
    "database": "db-report.json",
    "data": "data-report.json",
    "review": "review-report.json",
    "devops": "delivery-report.json",
}

AGENT_FRONTMATTER_FIELDS = {"name", "description", "model", "readonly", "is_background"}
REQUIRED_AGENT_SECTIONS = ["## ROLE", "## PRIMARY OBJECTIVE", "## CORE RESPONSIBILITIES", "## NON-GOALS"]

# Which artifacts each role is required to write.
#
# This exists because `readonly` is a TOOL CAPABILITY, not a statement of domain authority:
# Cursor documents it as "restricted write permissions (no file edits, no state-changing shell
# commands)". A role that must write an artifact therefore CANNOT be readonly, or it will be
# dispatched and then fail on its first write.
#
# Getting this wrong is not hypothetical: `product`, `tech-lead` and `reviewer` were originally
# declared `readonly: true` while being the sole writers of their artifacts, and the failure only
# surfaced at runtime when the product subagent was dispatched twice and both writes were refused.
# The check below turns that runtime failure into a configuration-time error.
#
# Authority ("must not write application code") is enforced by the role's NON-GOALS and by the
# artifact matrix, NOT by `readonly`. See docs/agents/permissions.md.
ARTIFACT_WRITERS: dict[str, tuple[str, ...]] = {
    "orchestrator": (),                      # writes state files only; see AGENTS.md
    "product": ("requirements.json",),
    "tech-lead": ("design.json", "plan.json"),
    "developer": ("worker-result.json",),
    "qa": ("qa-report.json",),
    "reviewer": ("review-report.json",),
    "ux": ("ux-report.json",),
    "security": ("security-report.json",),
    "devops": ("delivery-report.json",),
    "database": ("db-report.json",),
    "data": ("data-report.json",),
    "performance": ("perf-report.json",),
}

RATING_ORDER = {"critical": 0, "high": 1, "medium": 2, "low": 3, "major": 1, "minor": 2}


# --------------------------------------------------------------------------------------
# Reporting
# --------------------------------------------------------------------------------------


class Problem:
    """A single validation result. `error` blocks a gate; `warning` does not."""

    __slots__ = ("check", "message", "severity", "path")

    def __init__(self, check: str, message: str, severity: str = "error", path: str | None = None):
        self.check = check
        self.message = message
        self.severity = severity
        self.path = path

    def render(self) -> str:
        where = f" [{self.path}]" if self.path else ""
        return f"  {'ERROR' if self.severity == 'error' else 'WARN '} {self.check}: {self.message}{where}"


class Report:
    def __init__(self, title: str):
        self.title = title
        self.problems: list[Problem] = []
        self.notes: list[str] = []

    def error(self, check: str, message: str, path: str | None = None) -> None:
        self.problems.append(Problem(check, message, "error", path))

    def warn(self, check: str, message: str, path: str | None = None) -> None:
        self.problems.append(Problem(check, message, "warning", path))

    def note(self, message: str) -> None:
        self.notes.append(message)

    @property
    def errors(self) -> list[Problem]:
        return [p for p in self.problems if p.severity == "error"]

    @property
    def warnings(self) -> list[Problem]:
        return [p for p in self.problems if p.severity == "warning"]

    def emit(self) -> int:
        print(f"== {self.title}")
        for line in self.notes:
            print(f"   {line}")
        for problem in self.problems:
            print(problem.render())
        if self.errors:
            print(f"RESULT: {len(self.errors)} error(s), {len(self.warnings)} warning(s) - FAIL")
            return 1
        if self.warnings:
            print(f"RESULT: PASS with {len(self.warnings)} warning(s)")
            return 0
        print("RESULT: PASS")
        return 0


# --------------------------------------------------------------------------------------
# Minimal YAML frontmatter reader (stdlib only)
# --------------------------------------------------------------------------------------

_FRONTMATTER = re.compile(r"\A---\s*\n(.*?)\n---\s*\n?(.*)\Z", re.DOTALL)


def read_frontmatter(text: str) -> tuple[dict, str]:
    """Parse YAML frontmatter and return (fields, body).

    Handles only the scalar subset this repository uses: `key: value` plus `key: [a, b]`.
    Anything it cannot parse is returned as a raw string, and structural checks that depend
    on parsing are skipped rather than guessed.
    """
    match = _FRONTMATTER.match(text)
    if not match:
        return {}, text

    raw, body = match.group(1), match.group(2)
    fields: dict[str, object] = {}
    current_list_key: str | None = None

    for line in raw.splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        if line.startswith(("  - ", "  -", "\t- ")) and current_list_key:
            value = line.strip().lstrip("-").strip().strip("'\"")
            existing = fields.get(current_list_key)
            if isinstance(existing, list):
                existing.append(value)
            continue
        if line.startswith((" ", "\t")):  # nested mapping we do not model
            continue
        key, sep, value = line.partition(":")
        if not sep:
            continue
        key, value = key.strip(), value.strip()
        if value == "":
            fields[key] = []
            current_list_key = key
            continue
        current_list_key = None
        if value.startswith("[") and value.endswith("]"):
            inner = value[1:-1].strip()
            fields[key] = [v.strip().strip("'\"") for v in inner.split(",") if v.strip()] if inner else []
        elif value.lower() in ("true", "false"):
            fields[key] = value.lower() == "true"
        else:
            fields[key] = value.strip("'\"")
    return fields, body


def load_json(path: Path) -> object:
    # utf-8-sig tolerates editors/PowerShell that write a BOM.
    with path.open("r", encoding="utf-8-sig") as handle:
        return json.load(handle)


# --------------------------------------------------------------------------------------
# Lightweight JSON Schema validator (draft-07 subset)
# --------------------------------------------------------------------------------------

_TYPE_MAP = {
    "object": dict,
    "array": list,
    "string": str,
    "integer": int,
    "number": (int, float),
    "boolean": bool,
    "null": type(None),
}


def _type_name(value: object) -> str:
    return {
        dict: "object", list: "array", str: "string", bool: "boolean",
        int: "integer", float: "number", type(None): "null",
    }.get(type(value), type(value).__name__)


class SchemaValidator:
    """Validates the schema subset this repository uses.

    Supported keywords: type, required, properties, items, enum, const, minItems,
    minLength, minimum, maximum, pattern, additionalProperties, $ref (#/definitions/*).

    Deliberately strict where this repository's contracts depend on it (enum, required,
    pattern, minLength) and permissive elsewhere, because a validator that rejects valid
    work is worse than one with a smaller surface.
    """

    def __init__(self, root_schema: dict):
        self.root = root_schema

    def validate(self, schema: dict, value: object, pointer: str, problems: Report, artifact: str) -> None:
        if "$ref" in schema:
            ref = schema["$ref"]
            if ref.startswith("#/definitions/"):
                target = self.root.get("definitions", {}).get(ref.split("/")[-1])
                if target is None:
                    problems.warn("schema_ref", f"unresolvable $ref {ref}", artifact)
                    return
                schema = target
            else:
                problems.warn("schema_ref", f"unsupported $ref {ref}", artifact)
                return

        if "type" in schema:
            expected = _TYPE_MAP.get(schema["type"])
            if expected is not None:
                actual_value = value
                if isinstance(value, bool) and schema["type"] in ("integer", "number"):
                    problems.error("type", f"{pointer} must be {schema['type']}, got boolean", artifact)
                    return
                if not isinstance(actual_value, expected):
                    problems.error(
                        "type",
                        f"{pointer} must be {schema['type']}, got {_type_name(value)}",
                        artifact,
                    )
                    return

        if "enum" in schema and value not in schema["enum"]:
            problems.error("enum", f"{pointer} must be one of {schema['enum']}, got {value!r}", artifact)

        if "const" in schema and value != schema["const"]:
            problems.error("const", f"{pointer} must equal {schema['const']!r}, got {value!r}", artifact)

        if isinstance(value, str):
            if "minLength" in schema and len(value) < schema["minLength"]:
                problems.error(
                    "minLength",
                    f"{pointer} must be at least {schema['minLength']} characters, got {len(value)}",
                    artifact,
                )
            if "pattern" in schema and not re.search(schema["pattern"], value):
                problems.error("pattern", f"{pointer} must match {schema['pattern']}, got {value!r}", artifact)

        if isinstance(value, bool):
            pass
        elif isinstance(value, (int, float)):
            if "minimum" in schema and value < schema["minimum"]:
                problems.error("minimum", f"{pointer} must be >= {schema['minimum']}, got {value}", artifact)
            if "maximum" in schema and value > schema["maximum"]:
                problems.error("maximum", f"{pointer} must be <= {schema['maximum']}, got {value}", artifact)

        if isinstance(value, list):
            if "minItems" in schema and len(value) < schema["minItems"]:
                problems.error(
                    "minItems",
                    f"{pointer} must have at least {schema['minItems']} item(s), got {len(value)}",
                    artifact,
                )
            item_schema = schema.get("items")
            if isinstance(item_schema, dict):
                for index, item in enumerate(value):
                    self.validate(item_schema, item, f"{pointer}[{index}]", problems, artifact)

        if isinstance(value, dict):
            for key in schema.get("required", []):
                if key not in value:
                    problems.error("required", f"{pointer} is missing required key '{key}'", artifact)
            for key, sub_schema in schema.get("properties", {}).items():
                if key in value:
                    self.validate(sub_schema, value[key], f"{pointer}.{key}", problems, artifact)
            additional = schema.get("additionalProperties")
            if additional is False:
                known = set(schema.get("properties", {}))
                for key in value:
                    if key not in known:
                        problems.error(
                            "additionalProperties",
                            f"{pointer} has unexpected key '{key}'",
                            artifact,
                        )


# --------------------------------------------------------------------------------------
# Artifact validation
# --------------------------------------------------------------------------------------


def contract_for(filename: str) -> tuple[str, str] | None:
    """Resolve an artifact filename to (schema filename, sole writer role).

    Registered consultations resolve by pattern rather than by an entry in ARTIFACT_CONTRACTS,
    because there is one artifact per consulting specialist. An unknown name under the
    `consultation-` prefix resolves to nothing, so it is reported rather than silently accepted.
    """
    if filename.startswith(CONSULTATION_PREFIX) and filename.endswith(".json"):
        role = filename[len(CONSULTATION_PREFIX) : -len(".json")]
        if role in CONSULTATION_ROLES:
            return ("consultation.schema.json", role)
        return None
    return ARTIFACT_CONTRACTS.get(filename)


def check_artifact(path: Path, problems: Report) -> None:
    """Read an artifact from disk and validate it."""
    name = path.name
    contract = contract_for(name)
    if contract is None:
        problems.error(
            "known_artifact",
            f"'{name}' is not a registered artifact. Registered: {sorted(ARTIFACT_CONTRACTS)}",
            str(path),
        )
        return

    schema_name, _writer = contract
    schema_path = REPO_ROOT / ".agent" / "schemas" / schema_name
    if not schema_path.exists():
        problems.error("schema_missing", f"schema not found: {schema_path}", str(path))
        return

    try:
        data = load_json(path)
    except json.JSONDecodeError as exc:
        problems.error("json_parse", f"invalid JSON: {exc}", str(path))
        return
    except OSError as exc:
        problems.error("io", f"cannot read file: {exc}", str(path))
        return

    validate_artifact_data(name, data, schema_name, problems, str(path))


def validate_artifact_data(
    name: str, data: object, schema_name: str, problems: Report, label: str | None = None
) -> None:
    """Schema-validate one artifact document and enforce cross-field rules its schema cannot express.

    Separated from :func:`check_artifact` so the selftest can exercise the rules without
    writing scratch files to disk.
    """
    where = label or name

    if not isinstance(data, dict):
        problems.error("type", "artifact root must be a JSON object", where)
        return

    schema = load_json(REPO_ROOT / ".agent" / "schemas" / schema_name)
    SchemaValidator(schema).validate(schema, data, name, problems, where)

    # --- cross-field rules the schema cannot express -----------------------------------

    expected_role = SPECIALIST_ROLE_BY_ARTIFACT.get(name)
    if expected_role and data.get("role") != expected_role:
        problems.error(
            "role_writer_match",
            f"role must be '{expected_role}' for {name}, got {data.get('role')!r}",
            where,
        )

    if data.get("verdict") in ("SKIP", "NOT APPLICABLE") and not data.get("skip_reason"):
        problems.error("skip_justified", "a SKIP verdict must carry skip_reason", where)

    if data.get("verdict") == "PASS":
        # Never allow a pass that quietly carries blocking material.
        if isinstance(data.get("blockers"), list) and data["blockers"]:
            problems.error(
                "verdict_consistent",
                f"verdict is PASS but {len(data['blockers'])} blocker(s) are present",
                where,
            )
        if isinstance(data.get("blocking_findings"), list) and data["blocking_findings"]:
            problems.error(
                "verdict_consistent",
                f"verdict is PASS but blocking_findings is non-empty: {data['blocking_findings']}",
                where,
            )
        findings = data.get("findings")
        if isinstance(findings, list):
            unresolved = [
                f.get("severity")
                for f in findings
                if isinstance(f, dict)
                and f.get("severity") in ("critical", "high")
                and f.get("status", "open") == "open"
                and f.get("blocking", True)
            ]
            if unresolved:
                problems.error(
                    "verdict_consistent",
                    f"verdict is PASS but unresolved {sorted(set(unresolved))} finding(s) are present",
                    where,
                )

    if name == "worker-result.json":
        if data.get("status") == "blocked" and not data.get("blockers"):
            problems.error("blocked_has_reason", "status is blocked but blockers is empty", where)
        for entry in data.get("tests_run") or []:
            if isinstance(entry, dict) and entry.get("result") == "not_run" and not entry.get("not_run_reason"):
                problems.error(
                    "not_run_reason",
                    f"test '{entry.get('command')}' is not_run without a not_run_reason",
                    where,
                )
        # The environment gate. An unconfirmed environment turns setup problems into false defect
        # reports, and a false defect costs a full rework cycle — far more than the confirmation.
        environment = data.get("environment")
        if not isinstance(environment, dict):
            problems.error(
                "environment_unconfirmed",
                "worker-result.json has no `environment` block. The development environment must be "
                "confirmed with the human BEFORE any build, lint, typecheck or test command runs, and "
                "the confirmation recorded. A failure caused by the wrong runtime or an unactivated "
                "environment is indistinguishable from a code defect, so an unconfirmed run produces "
                "false findings. See .cursor/rules/environment.mdc.",
                where,
            )
        elif environment.get("confirmed_by_user") is not True:
            problems.error(
                "environment_unconfirmed",
                "environment.confirmed_by_user is not true. Verification was run in an environment the "
                "human has not confirmed, so any failure it produced cannot be attributed to the code "
                "with confidence. Ask the human which runtime, package manager, services and commands "
                "to use, then record the answer here.",
                where,
            )
        elif not environment.get("runtime") and not environment.get("commands_confirmed"):
            problems.warn(
                "environment_thin",
                "environment is confirmed but records neither the runtime nor the confirmed commands, "
                "so the report cannot be reproduced",
                where,
            )

    if name == "qa-report.json":
        criteria = data.get("criteria") or []
        if data.get("verdict") == "PASS":
            failing = [c.get("criterion_id") for c in criteria if isinstance(c, dict) and c.get("verdict") == "FAIL"]
            if failing:
                problems.error(
                    "verdict_consistent",
                    f"verdict is PASS but criteria failed: {failing}",
                    where,
                )
            unresolved = [
                f for f in (data.get("findings") or [])
                if isinstance(f, dict) and f.get("severity") in ("critical", "major")
            ]
            if unresolved:
                problems.error(
                    "verdict_consistent",
                    f"verdict is PASS but {len(unresolved)} critical/major finding(s) are unresolved",
                    where,
                )
        for entry in data.get("tests", {}).get("commands_run", []) or []:
            if isinstance(entry, dict) and entry.get("result") == "not_run" and not entry.get("not_run_reason"):
                problems.error(
                    "not_run_reason",
                    f"test '{entry.get('command')}' is not_run without a not_run_reason",
                    where,
                )

    if name == "security-report.json" and data.get("verdict") == "PASS":
        areas = data.get("assessed_areas") or {}
        unassessed = [k for k, v in areas.items() if v == "not_assessed"]
        if unassessed:
            problems.warn(
                "security_coverage",
                f"verdict is PASS but these areas are marked not_assessed: {unassessed}",
                where,
            )


# --------------------------------------------------------------------------------------
# Scope invariant — the highest-value check in this file
# --------------------------------------------------------------------------------------


def git_changed_files(cwd: Path) -> tuple[list[str], str | None]:
    """Return changed files from git, or ([], reason) when git cannot be consulted."""
    commands = [
        ["git", "diff", "--name-only", "HEAD"],
        ["git", "ls-files", "--others", "--exclude-standard"],
    ]
    changed: list[str] = []
    for command in commands:
        try:
            completed = subprocess.run(
                command, cwd=str(cwd), capture_output=True, text=True, timeout=30, check=False
            )
        except (OSError, subprocess.SubprocessError) as exc:
            return [], f"git unavailable: {exc}"
        if completed.returncode != 0:
            return [], f"`{' '.join(command)}` failed: {completed.stderr.strip()[:200]}"
        changed.extend(line.strip() for line in completed.stdout.splitlines() if line.strip())
    return sorted(set(changed)), None


# How a step's action relates to the state of its target file.
#
# The distinction matters because a plan is written against an assumed codebase. When the
# assumption is wrong — the plan was drafted for a repository that is not the one in front of
# the developer — every `modify` step points at a file that does not exist. Left unchecked, the
# developer either fails confusingly at step 6 or, far worse, manufactures the missing surface
# and silently expands scope to cover it.
STEP_EXPECTS_FILE_PRESENT = {"modify", "delete"}
STEP_EXPECTS_FILE_ABSENT = {"create"}


def check_plan_against_repository(plan: dict, problems: Report) -> None:
    """Verify the plan's file assumptions hold in the repository it is about to be implemented in.

    This is the guard that catches a plan written for a different codebase. It is the difference
    between a developer discovering the mismatch by reasoning and the validator stating it as a
    fact before any work starts.
    """
    steps = [s for s in (plan.get("steps") or []) if isinstance(s, dict)]
    created_earlier: set[str] = set()

    for step in sorted(steps, key=lambda s: s.get("order") or 0):
        action = step.get("action")
        file_ref = step.get("file")
        order = step.get("order")
        if not isinstance(file_ref, str) or not file_ref:
            continue
        exists = (REPO_ROOT / file_ref).exists()

        if action in STEP_EXPECTS_FILE_PRESENT and not exists and file_ref not in created_earlier:
            problems.error(
                "step_target_missing",
                f"step {order} says '{action}' on '{file_ref}', but that file does not exist in this "
                f"repository. A plan is written against an assumed codebase, so this usually means the "
                f"plan (or the design behind it) describes a different project. Re-run design against "
                f"this repository, or run the task in the repository the design assumes. Do not "
                f"manufacture the missing file: the design almost certainly depends on surrounding "
                f"components that are also absent, which turns one step into an unplanned rewrite.",
                "plan.json",
            )
        elif action in STEP_EXPECTS_FILE_ABSENT and exists and file_ref not in created_earlier:
            problems.warn(
                "step_target_exists",
                f"step {order} says 'create' on '{file_ref}', but that file already exists. Creating it "
                f"may overwrite existing work; if the intent is to extend it, the action should be "
                f"'modify'.",
                "plan.json",
            )

        if action == "create":
            created_earlier.add(file_ref)


def check_plan(plan: dict, problems: Report) -> None:
    """Two-way consistency between the plan's file list and its steps.

    This is what makes plan/implementation drift a hard error rather than something a
    reviewer is expected to notice by eye.
    """
    affected = plan.get("affected_files") or []
    affected_set = {f for f in affected if isinstance(f, str)}
    if not affected_set:
        problems.error("affected_files", "affected_files is empty", "plan.json")

    steps = plan.get("steps") or []
    if not steps:
        problems.error("steps", "steps is empty", "plan.json")
        return

    step_files: dict[str, list[int]] = {}
    for step in steps:
        if not isinstance(step, dict):
            problems.error("step_shape", "every step must be an object", "plan.json")
            continue
        order = step.get("order")
        if not isinstance(order, int) or order < 1:
            problems.error("step_order", f"step order must be a positive integer, got {order!r}", "plan.json")
        if step.get("risk_level") == "high" and not step.get("rollback"):
            problems.error(
                "high_risk_rollback",
                f"step {order} is risk_level high without a rollback procedure",
                "plan.json",
            )
        if step.get("reversible") is False and not step.get("rollback"):
            problems.error(
                "irreversible_rollback",
                f"step {order} is irreversible without a rollback procedure",
                "plan.json",
            )
        file_ref = step.get("file")
        if isinstance(file_ref, str) and file_ref:
            step_files.setdefault(file_ref, []).append(order if isinstance(order, int) else -1)

    # affected_files -> steps (every planned file must have a step)
    for file_ref in sorted(affected_set):
        if file_ref not in step_files:
            problems.error(
                "file_has_step",
                f"affected_files lists '{file_ref}' but no step references it",
                "plan.json",
            )

    # steps -> affected_files (every step's file must be planned)
    for file_ref, orders in sorted(step_files.items()):
        if file_ref not in affected_set:
            problems.error(
                "step_in_affected",
                f"step(s) {orders} reference '{file_ref}' which is not in affected_files",
                "plan.json",
            )

    # acceptance mapping completeness
    mapping = plan.get("acceptance_mapping") or {}
    if not mapping:
        problems.error("ac_mapping", "acceptance_mapping is empty", "plan.json")
    for criterion_id, target in sorted(mapping.items()):
        if not isinstance(target, str) or not target.strip():
            problems.error(
                "ac_mapped",
                f"acceptance criterion {criterion_id} has an empty mapping",
                "plan.json",
            )

    # parallel groups must reference real steps, claim disjoint paths (C2), and avoid depends_on cycles
    declared = {s.get("order") for s in steps if isinstance(s, dict)}
    for group in plan.get("parallel_groups") or []:
        if not isinstance(group, dict):
            continue
        for step_order in group.get("steps") or []:
            if step_order not in declared:
                problems.error(
                    "parallel_group_steps",
                    f"parallel group '{group.get('group')}' references unknown step {step_order}",
                    "plan.json",
                )

    check_parallel_claimed_paths(plan, problems)

    # dependency sanity
    for step in steps:
        if not isinstance(step, dict):
            continue
        for dependency in step.get("depends_on") or []:
            if dependency not in declared:
                problems.error(
                    "depends_on",
                    f"step {step.get('order')} depends on unknown step {dependency}",
                    "plan.json",
                )
            elif isinstance(step.get("order"), int) and dependency >= step["order"]:
                problems.error(
                    "depends_on_order",
                    f"step {step['order']} depends on step {dependency}, which is not earlier",
                    "plan.json",
                )


def check_parallel_claimed_paths(plan: dict, problems: Report) -> None:
    """C2: multi-step parallel_groups need pairwise-disjoint streams[].claimed_paths."""
    tools_dir = Path(__file__).resolve().parent
    if str(tools_dir) not in sys.path:
        sys.path.insert(0, str(tools_dir))
    try:
        from parallel_worktree import check_plan_disjoint  # noqa: WPS433
    except ImportError as exc:
        problems.error(
            "parallel_worktree_import",
            f"cannot import parallel_worktree.py for C2 checks: {exc}",
            "plan.json",
        )
        return
    for message in check_plan_disjoint(plan):
        check_id = "parallel_depends_on" if "depends_on" in message else "parallel_claimed_paths"
        problems.error(check_id, message, "plan.json")


def check_implementation(task_dir: Path, plan: dict, problems: Report) -> None:
    """Compare the plan's scope against the actual working-tree diff."""
    affected = {f for f in (plan.get("affected_files") or []) if isinstance(f, str)}

    changed, reason = git_changed_files(REPO_ROOT)
    if reason:
        problems.warn(
            "scope_check_skipped",
            f"cannot verify implementation scope ({reason}). Treat scope as unverified.",
            "plan.json",
        )
        return

    def is_exempt(path: str) -> bool:
        return path.startswith(SCOPE_EXEMPT_PREFIXES)

    relevant = {p for p in changed if not is_exempt(p)}
    extra = sorted(relevant - affected)
    missing = sorted(affected - relevant)

    for path in extra:
        problems.error(
            "scope_extra",
            f"file changed but not in plan affected_files: {path}",
            "plan.json",
        )
    for path in missing:
        problems.warn(
            "scope_missing",
            f"planned file has no changes: {path}",
            "plan.json",
        )

    worker_path = task_dir / "worker-result.json"
    if worker_path.exists():
        try:
            worker = load_json(worker_path)
        except (json.JSONDecodeError, OSError):
            return
        declared = set(worker.get("files_changed") or []) | set(worker.get("files_created") or [])
        if isinstance(worker, dict):
            undeclared = sorted(relevant - declared - {".agent", ""})
            for path in undeclared:
                if path not in affected:
                    continue
                problems.warn(
                    "worker_underreported",
                    f"'{path}' changed and is in the plan, but worker-result.json does not list it",
                    "worker-result.json",
                )


def check_requirements(requirements: dict, problems: Report) -> None:
    if requirements.get("open_questions"):
        problems.error(
            "open_questions",
            f"{len(requirements['open_questions'])} unresolved product question(s) must be answered before proceeding",
            "requirements.json",
        )
    for criterion in requirements.get("acceptance_criteria") or []:
        if isinstance(criterion, dict) and not criterion.get("text", "").strip():
            problems.error("ac_text", f"acceptance criterion {criterion.get('id')} has no text", "requirements.json")


def check_plan_covers_requirements(plan: dict, requirements: dict, problems: Report) -> None:
    """Every acceptance criterion must be mapped by the plan."""
    criteria = {
        c.get("id")
        for c in (requirements.get("acceptance_criteria") or [])
        if isinstance(c, dict) and c.get("id")
    }
    mapping = plan.get("acceptance_mapping") or {}
    for criterion_id in sorted(criteria - set(mapping)):
        problems.error(
            "acceptance_unmapped",
            f"acceptance criterion {criterion_id} has no entry in plan.acceptance_mapping",
            "plan.json",
        )
    for criterion_id in sorted(set(mapping) - criteria):
        problems.warn(
            "acceptance_unknown",
            f"plan maps acceptance criterion {criterion_id}, which is not in requirements.json",
            "plan.json",
        )


def check_design_time_consultation(task_dir: Path, plan: dict, problems: Report) -> None:
    """Every design-time consultation the plan claims must exist, be readable, and be an agreement.

    Why this check exists. `plan.json -> specialists_required[].design_time_consultation` is an
    unfalsifiable field on its own: nothing distinguished a specialist that really reviewed the
    design from a tech lead that marked the box after reviewing its own work. In one task the
    specialist subagents were dispatched and delivered real reviews, the plan recorded
    `design_time_consultation: true`, and no artifact existed anywhere — so the claim rested on a
    chat message, and a chat message is not a handoff. The consultation artifact and this check are
    what make the claim checkable in both directions.
    """
    required: list[str] = []
    for entry in plan.get("specialists_required") or []:
        if not isinstance(entry, dict) or entry.get("design_time_consultation") is not True:
            continue
        specialist = entry.get("specialist")
        if not isinstance(specialist, str):
            continue
        if specialist not in CONSULTATION_ROLES:
            problems.error(
                "consultation_role_unknown",
                f"specialist '{specialist}' cannot record a design-time consultation. "
                f"Consultation roles are {sorted(CONSULTATION_ROLES)}.",
                "plan.json",
            )
            continue
        required.append(specialist)

    for specialist in sorted(set(required)):
        artifact_path = task_dir / f"{CONSULTATION_PREFIX}{specialist}.json"
        if not artifact_path.exists():
            problems.error(
                "consultation_recorded",
                f"plan.json records a design-time consultation by '{specialist}', but "
                f"{artifact_path.name} does not exist. The consultation must be written by the "
                f"specialist itself; a mark in the plan is only a claim until the artifact is "
                f"there. Write it, or set design_time_consultation to false.",
                str(task_dir.name),
            )
            continue
        try:
            data = load_json(artifact_path)
        except (json.JSONDecodeError, OSError) as exc:
            problems.error("consultation_readable", f"cannot read {artifact_path.name}: {exc}", artifact_path.name)
            continue
        if data.get("verdict") == "FAIL":
            problems.error(
                "consultation_failed",
                f"{artifact_path.name} records verdict FAIL: the design may not proceed to "
                f"implementation. Correct the design, then have the specialist re-consult.",
                artifact_path.name,
            )
        reviewed = data.get("artifacts_reviewed") or []
        if not {"design.json", "plan.json"} & {str(item) for item in reviewed}:
            problems.error(
                "consultation_scope",
                f"{artifact_path.name} reviewed neither design.json nor plan.json "
                f"(artifacts_reviewed={reviewed!r}). A consultation that read nothing cannot be "
                f"told apart from no consultation.",
                artifact_path.name,
            )

    # A consultation that exists while the plan does not claim it is drift in the other direction:
    # the record is real, so the plan understates what happened.
    for role in sorted(CONSULTATION_ROLES):
        artifact_path = task_dir / f"{CONSULTATION_PREFIX}{role}.json"
        if artifact_path.exists() and role not in required:
            problems.warn(
                "consultation_unclaimed",
                f"{artifact_path.name} exists but plan.json does not record a design-time "
                f"consultation by '{role}'. Record it, or remove the artifact so the design record "
                f"and the consultation record agree.",
                "plan.json",
            )


def check_qa_covers_requirements(qa: dict, requirements: dict, problems: Report) -> None:
    """Every acceptance criterion must have received a verdict from QA."""
    criteria = {
        c.get("id")
        for c in (requirements.get("acceptance_criteria") or [])
        if isinstance(c, dict) and c.get("id")
    }
    reported = {
        c.get("criterion_id")
        for c in (qa.get("criteria") or [])
        if isinstance(c, dict) and c.get("criterion_id")
    }
    for criterion_id in sorted(criteria - reported):
        problems.error(
            "qa_criteria_incomplete",
            f"acceptance criterion {criterion_id} has no QA verdict",
            "qa-report.json",
        )


def check_gate_presence(task_dir: Path, gates: list[str], problems: Report) -> None:
    """A gate with no artifact has not passed — it has not run. Never infer a pass from absence."""
    for gate in gates:
        artifact = GATE_ARTIFACT.get(gate)
        if not artifact:
            continue
        path = task_dir / artifact
        if not path.exists():
            problems.error(
                "gate_not_run",
                f"gate '{gate}' has no artifact ({artifact}); it has not passed",
                str(task_dir.name),
            )
            continue
        try:
            data = load_json(path)
        except (json.JSONDecodeError, OSError) as exc:
            problems.error("gate_unreadable", f"gate '{gate}' artifact is unreadable: {exc}", artifact)
            continue
        verdict = data.get("verdict") if isinstance(data, dict) else None
        if verdict not in ("PASS", "SKIP", "NOT APPLICABLE"):
            problems.error(
                "gate_not_passed",
                f"gate '{gate}' verdict is {verdict!r}, expected PASS or a justified SKIP",
                artifact,
            )


# --------------------------------------------------------------------------------------
# Duplicate-request detection
# --------------------------------------------------------------------------------------
# Two active tasks describing one request both look authoritative and produce divergent
# requirement sets. The per-task invariants cannot see this, because they compare a task
# against its own plan and never against another task. This section scores a new request
# against every active task so that intake can force an explicit human adjudication.
#
# The scoring is a deterministic token-overlap heuristic, not semantic understanding. It is
# deliberately transparent so a human can inspect the shared terms and disagree with it.

DEDUPE_DEFAULTS = {
    "likely": 0.48,
    "possible": 0.24,
    "min_shared_tokens": 3,
    "stopwords": [],
    "aliases": {},
}

# Canonicalisation is what makes the heuristic usable in this bilingual repository: a purely
# lexical score cannot see that "邀请同事" and "invite a colleague" are the same request.
DEDUPE_ALIAS_FALLBACK = {
    "invite": ["邀请", "invitation", "invitations", "inviting"],
    "colleague": ["同事", "teammate", "teammates"],
    "organization": ["组织", "organisation", "org", "company", "tenant", "workspace"],
    "join": ["加入", "joining", "accept", "accepted", "membership"],
    "email": ["邮箱", "邮件", "mail", "address"],
    "expire": ["过期", "expiry", "expiration", "expires", "ttl", "lifetime"],
    "token": ["令牌", "link", "links"],
    "role": ["角色", "permission", "permissions", "privilege", "privileges"],
    "login": ["登录", "signin", "sign_in", "authentication", "auth"],
    "password": ["密码", "credential", "credentials"],
    "delete": ["删除", "remove", "removal", "destroy", "purge"],
    "create": ["创建", "新建", "add", "adding", "insert", "register"],
    "update": ["更新", "修改", "edit", "modify", "change"],
    "search": ["搜索", "查询", "filter", "query", "find"],
    "report": ["报表", "报告", "dashboard", "analytics", "metric", "metrics"],
    "payment": ["支付", "billing", "invoice", "subscription", "checkout"],
    "notification": ["通知", "alert", "alerts", "notify", "reminder"],
    "export": ["导出", "download", "dump"],
    "import": ["导入", "upload", "ingest"],
    "performance": ["性能", "latency", "throughput", "speed"],
    "test": ["测试", "tests", "testing", "spec", "specs"],
    "docs": ["文档", "documentation", "readme", "guide"],
}

_CJK_OR_WORD = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff\u3040-\u30ff\uac00-\ud7af]+|[a-zA-Z0-9]+")
_TOP_LEVEL_KEY = re.compile(r"^([a-z_]+):\s*$")


def _decode_scalar(raw: str) -> object:
    """Decode a YAML scalar, preferring JSON semantics, falling back to a plain string."""
    raw = raw.strip()
    if not raw:
        return ""
    try:
        return json.loads(raw)
    except (json.JSONDecodeError, ValueError):
        return raw.strip("'\"")


def _yaml_blocks(text: str) -> list[tuple[int, str]]:
    """Strip comments and blanks, and return (indent, content) pairs.

    A `#` begins a comment only when preceded by whitespace or at the start of a line, so a
    glob such as `"**/*.md"` and a `#` inside a quoted value survive intact.
    """
    blocks: list[tuple[int, str]] = []
    for line in text.splitlines():
        stripped = line.rstrip()
        if not stripped.strip():
            continue
        indent = len(stripped) - len(stripped.lstrip(" "))
        content = stripped.strip()
        if content.startswith("#"):
            continue
        content = re.split(r"\s+#", content, maxsplit=1)[0].rstrip()
        if not content:
            continue
        blocks.append((indent, content))
    return blocks


def _parse_yaml_block(blocks: list[tuple[int, str]], index: int, indent: int):
    """Parse either a mapping or a sequence at the given indent. Returns (value, next_index).

    A real indentation-based parser rather than a regex over line shapes. The earlier
    line-matching attempt silently returned the wrong top-level section, which is exactly the
    kind of failure a configuration reader must not have.
    """
    if index < len(blocks) and blocks[index][1].startswith("- "):
        items: list = []
        while index < len(blocks):
            line_indent, content = blocks[index]
            if line_indent != indent or not content.startswith("- "):
                break
            items.append(_decode_scalar(content[2:]))
            index += 1
        return items, index

    mapping: dict = {}
    while index < len(blocks):
        line_indent, content = blocks[index]
        if line_indent != indent or content.startswith("- "):
            break
        key, separator, raw = content.partition(":")
        if not separator:
            index += 1
            continue
        key = key.strip()
        raw = raw.strip()
        index += 1

        # A collection that spans several lines: `key: [a,` ... `]` or `key: {a: 1,` ... `}`.
        # Joined back into one line before decoding, so an inline list may be wrapped for
        # readability without becoming unparseable. Only a line that opens with an identifier
        # followed by a colon is treated as a new key, so a continuation line such as
        # `"a", "an",` is not mistaken for one.
        if raw[:1] in ("[", "{"):
            needed = {"[": "]", "{": "}"}[raw[:1]]
            pieces = [raw]
            while needed not in "".join(pieces) and index < len(blocks):
                candidate = blocks[index][1]
                if re.match(r"^[A-Za-z_][A-Za-z0-9_-]*:", candidate):
                    break
                pieces.append(candidate)
                index += 1
            mapping[key] = _decode_scalar(" ".join(pieces))
            continue

        if raw and raw not in ("|", ">"):
            mapping[key] = _decode_scalar(raw)
            continue
        # A nested block, or an empty scalar. A sequence takes priority over a mapping when the
        # next line opens with a dash, which is what distinguishes
        #     stopwords:
        #       - "the"
        # from a nested mapping such as
        #     thresholds:
        #       likely: 0.6
        if index < len(blocks) and blocks[index][0] >= line_indent and (
            blocks[index][0] > line_indent or blocks[index][1].startswith("- ")
        ):
            mapping[key], index = _parse_yaml_block(blocks, index, blocks[index][0])
        else:
            mapping[key] = ""
    return mapping, index


def parse_yaml(text: str) -> dict:
    """Parse the YAML subset this repository uses, via a real indentation-based reader."""
    value, _ = _parse_yaml_block(_yaml_blocks(text), 0, 0)
    return value if isinstance(value, dict) else {}


def load_duplicate_detection_config() -> dict:
    """Read duplicate-detection thresholds and vocabulary from .agent/config.yaml."""
    config_path = REPO_ROOT / ".agent" / "config.yaml"
    settings = dict(DEDUPE_DEFAULTS)
    try:
        config = parse_yaml(config_path.read_text(encoding="utf-8"))
    except OSError:
        config = {}

    section = config.get("duplicate_detection")
    section = section if isinstance(section, dict) else {}

    thresholds = section.get("thresholds")
    if isinstance(thresholds, dict):
        for name in ("likely", "possible"):
            value = thresholds.get(name)
            if isinstance(value, (int, float)):
                settings[name] = float(value)
    minimum = section.get("min_shared_tokens")
    if isinstance(minimum, int):
        settings["min_shared_tokens"] = minimum

    stopwords = section.get("stopwords")
    settings["stopwords"] = {str(word).lower() for word in stopwords} if isinstance(stopwords, list) else set()

    aliases = section.get("aliases")
    source = aliases if isinstance(aliases, dict) and aliases else DEDUPE_ALIAS_FALLBACK
    canonical: dict[str, str] = {}
    for head, variants in source.items():
        canonical[str(head).lower()] = str(head).lower()
        if isinstance(variants, list):
            for variant in variants:
                canonical[str(variant).lower()] = str(head).lower()
    settings["aliases"] = canonical
    return settings


def tokenize(text: str, settings: dict) -> set[str]:
    """Normalise text into a comparable token set: tokenise, lowercase, drop stopwords, canonicalise."""
    if not text:
        return set()
    stopwords = settings.get("stopwords") or set()
    aliases = settings.get("aliases") or {}
    tokens = set()
    for raw in _CJK_OR_WORD.findall(text):
        token = raw.lower()
        if token in stopwords or len(token) < 2:
            continue
        tokens.add(aliases.get(token, token))
    return tokens


def text_similarity(left: str, right: str, settings: dict) -> tuple[float, list[str]]:
    """Jaccard overlap of canonical tokens. Returns (score, shared terms)."""
    left_tokens = tokenize(left, settings)
    right_tokens = tokenize(right, settings)
    if not left_tokens or not right_tokens:
        return 0.0, []
    shared = left_tokens & right_tokens
    union = left_tokens | right_tokens
    return (len(shared) / len(union) if union else 0.0), sorted(shared)


def task_corpus(data: dict) -> str:
    """Broad corpus: title, request, goal and every acceptance criterion.

    Catches the same feature described in different words, and across languages, because the
    acceptance criteria carry the shared domain vocabulary even when the requests do not.
    """
    parts = [str(data.get("title") or ""), str(data.get("request") or "")]
    requirements = data.get("requirements")
    if isinstance(requirements, dict):
        parts.append(str(requirements.get("goal") or ""))
        for criterion in requirements.get("acceptance_criteria") or []:
            if isinstance(criterion, dict):
                parts.append(str(criterion.get("text") or ""))
    return " ".join(parts)


def request_corpus(data: dict) -> str:
    """Narrow corpus: only the title and the request as the human phrased them.

    This is the precise signal. Two tasks whose requests are near-verbatim the same are the same
    request, and the narrow comparison says so emphatically. It is blind to a restatement in
    another language, which is what the broad corpus is for.
    """
    return " ".join([str(data.get("title") or ""), str(data.get("request") or "")])


# The narrow comparison is meaningful even with very few shared tokens, because a high score
# there already means the wording is near-identical.
NARROW_MIN_SHARED = 2


def load_task_documents(task_dir: Path) -> dict:
    """Load the documents used to describe a task: its intake, and its requirements if present."""
    intake = load_json(task_dir / "intake.json") if (task_dir / "intake.json").exists() else {}
    requirements_path = task_dir / "requirements.json"
    if requirements_path.exists():
        try:
            intake = dict(intake)
            intake["requirements"] = load_json(requirements_path)
        except (json.JSONDecodeError, OSError):
            pass
    return intake


def active_task_dirs(exclude: str | None = None) -> list[tuple[Path, str]]:
    """Every task directory that can be compared against: active, completed, and archive.

    The three locations carry different meanings, and the distinction is what keeps the check
    useful instead of noisy:

      * `active`    — a live collision. Two active tasks describing one request both look
                      authoritative, so this is the failure the check exists for.
      * `completed` — usually information. Re-asking for shipped work is not a collision.
      * `archive`   — settled. Superseded or abandoned work must still be scannable, or a match
                      that was recorded against it would look like a fabricated entry.

    Archive is scanned on purpose even though it is not a conflict: without it, archiving a task
    would make the previously-recorded overlap unverifiable and the validator would report it as
    unreproduced.
    """
    found: list[tuple[Path, str]] = []
    for base in ("active", "completed", "archive"):
        directory = REPO_ROOT / "tasks" / base
        if not directory.is_dir():
            continue
        for path in sorted(directory.iterdir()):
            if path.is_dir() and path.name != exclude and (path / "intake.json").exists():
                found.append((path, base))
    return found


def score_against_active_tasks(task_dir: Path, settings: dict) -> list[dict]:
    """Score this task's request against every other task. Returns matches at or above `possible`.

    Two comparisons are made and the higher score wins, because each catches what the other
    misses:
      * narrow — title and request only. Precise. Two near-verbatim requests score ~1.0.
      * broad  — title, request, goal and all acceptance criteria. Catches the same feature
                 described differently, including in another language, where the narrow
                 comparison sees nothing.
    """
    own = load_task_documents(task_dir)
    if not own:
        return []
    own_broad = task_corpus(own)
    own_narrow = request_corpus(own)
    minimum = settings["min_shared_tokens"]
    results: list[dict] = []
    for other_dir, location in active_task_dirs(exclude=task_dir.name):
        other = load_task_documents(other_dir)

        narrow_score, narrow_shared = text_similarity(own_narrow, request_corpus(other), settings)
        broad_score, broad_shared = text_similarity(own_broad, task_corpus(other), settings)

        if narrow_score >= broad_score:
            score, shared, method = narrow_score, narrow_shared, "request_narrow"
            floor = NARROW_MIN_SHARED
        else:
            score, shared, method = broad_score, broad_shared, "document_broad"
            floor = minimum

        if score < settings["possible"] or len(shared) < floor:
            continue
        results.append({
            "task_id": other_dir.name,
            "score": round(score, 4),
            "level": "likely" if score >= settings["likely"] else "possible",
            "shared_terms": shared,
            "location": location,
            "method": method,
            "broad_score": round(broad_score, 4),
            "narrow_score": round(narrow_score, 4),
        })
    return sorted(results, key=lambda m: (-m["score"], m["location"] != "active"))


def stage_duplicate_check(task_dir: Path, problems: Report) -> None:
    """Enforce that a request overlapping an existing task was adjudicated explicitly.

    This is the check that would have caught TASK-003 and TASK-004 describing one request.
    """
    intake_path = task_dir / "intake.json"
    if not intake_path.exists():
        problems.error("intake_exists", "intake.json is missing; overlap cannot be assessed", str(task_dir.name))
        return

    try:
        intake = load_json(intake_path)
    except (json.JSONDecodeError, OSError) as exc:
        problems.error("intake_readable", f"intake.json is unreadable: {exc}", str(task_dir.name))
        return
    if not isinstance(intake, dict):
        problems.error("intake_shape", "intake.json must be an object", str(task_dir.name))
        return

    check_trivial_classification_gate(intake, problems)
    check_model_assignments(intake, problems)

    overlap = intake.get("overlap_check")
    if not isinstance(overlap, dict):
        problems.error(
            "overlap_check_missing",
            "intake.json has no overlap_check. Every intake must record the comparison against "
            "active tasks, including when the comparison found nothing. Without it, two active "
            "tasks describing one request can both look authoritative.",
            "intake.json",
        )
        return

    settings = load_duplicate_detection_config()
    recomputed = score_against_active_tasks(task_dir, settings)
    recomputed_map = {m["task_id"]: m for m in recomputed}

    recorded = overlap.get("matches") or []
    recorded_ids = {m.get("task_id") for m in recorded if isinstance(m, dict)}

    # 1. A real overlap with another ACTIVE task that the intake did not record.
    #    This is the failure the check exists for: two active tasks describing one request both
    #    look authoritative. An overlap with a completed task is reported without blocking,
    #    because re-asking for something already shipped is usually information, not a collision.
    for match in recomputed:
        if match["task_id"] in recorded_ids:
            continue
        if match["level"] == "likely" and match["location"] == "active":
            problems.error(
                "overlap_unrecorded",
                f"this request overlaps the active task {match['task_id']} at {match['score']:.2f} "
                f"(shared: {', '.join(match['shared_terms'][:8])}) but intake.json does not record it",
                "intake.json",
            )
        elif match["location"] == "active":
            problems.warn(
                "overlap_unrecorded_possible",
                f"possible overlap with the active task {match['task_id']} at "
                f"{match['score']:.2f}; record it and adjudicate it",
                "intake.json",
            )
        else:
            problems.note(
                f"similarity to {match['location']} task {match['task_id']}: {match['score']:.2f} "
                f"({match['level']}) — informational; {'re-asking for shipped work is not a collision' if match['location'] == 'completed' else 'already superseded, so no adjudication is needed'}"
            )

    # 2. A material understatement of the highest score.
    recorded_highest = overlap.get("highest_score")
    actual_highest = recomputed[0]["score"] if recomputed else 0.0
    if isinstance(recorded_highest, (int, float)) and actual_highest - recorded_highest > 0.05:
        problems.error(
            "overlap_score_understated",
            f"highest_score records {recorded_highest:.2f} but independent scoring finds "
            f"{actual_highest:.2f}",
            "intake.json",
        )

    # 3. Recorded matches must agree with reality on level.
    for entry in recorded:
        if not isinstance(entry, dict):
            continue
        other = entry.get("task_id")
        recomputed_match = recomputed_map.get(other)
        if recomputed_match is None:
            # An archived task is a settled one. The recorded match stays legitimate even though
            # it is no longer a live conflict, so it is noted rather than warned about.
            archived = (REPO_ROOT / "tasks" / "archive" / str(other)).is_dir()
            if archived:
                problems.note(
                    f"recorded match {other} is archived; the overlap is settled and needs no adjudication"
                )
            else:
                problems.warn(
                    "overlap_match_unknown",
                    f"recorded match {other} is not reproduced by independent scoring; "
                    "verify it, or record why under override",
                    "intake.json",
                )
            continue
        if entry.get("level") != recomputed_match["level"]:
            problems.warn(
                "overlap_level_mismatch",
                f"{other} is recorded as {entry.get('level')!r} but scores "
                f"{recomputed_match['score']:.2f} ({recomputed_match['level']})",
                "intake.json",
            )

    has_likely = any(isinstance(m, dict) and m.get("level") == "likely" for m in recorded)
    decision = overlap.get("decision") or {}
    outcome = decision.get("outcome")
    decided_by = decision.get("decided_by")
    override = overlap.get("override")

    # 4. A likely overlap requires a human decision, not the orchestrator's.
    if has_likely and outcome != "no_overlap" and decided_by != "human":
        if not isinstance(override, dict):
            problems.error(
                "overlap_needs_human",
                f"a likely overlap was found but decision.decided_by is {decided_by!r}. "
                "The orchestrator may run the comparison but may not adjudicate a likely match: "
                "choosing 'new' silently forks the work and choosing 'reuse' discards the requester's "
                "intent. Escalate to the human, or record an override with a reason.",
                "intake.json",
            )

    # 5. `new` alongside a real overlap needs a stated reason.
    if outcome == "new" and recorded and not (decision.get("rationale") or "").strip():
        if not isinstance(override, dict):
            problems.error(
                "new_needs_rationale",
                "outcome is 'new' while an overlap exists, but no rationale is recorded. "
                "State why the existing work does not already satisfy this request.",
                "intake.json",
            )

    # 6. `reuse` means no new task should exist.
    if outcome == "reuse":
        if not decision.get("reused_task_id"):
            problems.error("reuse_names_task", "outcome is reuse but reused_task_id is absent", "intake.json")
        problems.error(
            "reuse_should_not_create_task",
            f"{task_dir.name} exists while its intake says the request reuses "
            f"{decision.get('reused_task_id')}. A reuse must continue the existing task and must not "
            "allocate a new one.",
            "intake.json",
        )

    # 7. `supersede` must actually retire the superseded task.
    if outcome == "supersede":
        superseded = decision.get("superseded_task_id")
        if not superseded:
            problems.error("supersede_names_task", "outcome is supersede but superseded_task_id is absent", "intake.json")
        else:
            still_active = (REPO_ROOT / "tasks" / "active" / superseded).is_dir()
            if still_active:
                problems.error(
                    "supersede_not_archived",
                    f"outcome is supersede for {superseded}, but that task is still in tasks/active/. "
                    "A superseded task left active keeps two divergent requirement sets looking "
                    "authoritative. Move it to tasks/archive/ or tasks/completed/.",
                    "intake.json",
                )

    # 8. An override must justify itself.
    if isinstance(override, dict) and not (override.get("reason") or "").strip():
        problems.error("override_needs_reason", "an override is recorded without a reason", "intake.json")

    # 9. If nothing was recorded, say so explicitly rather than leaving it blank.
    if outcome is None:
        problems.error(
            "overlap_decision_missing",
            "overlap_check has no decision. State new | reuse | supersede | no_overlap even when no "
            "match was found.",
            "intake.json",
        )

    if recomputed:
        summary = ", ".join(f"{m['task_id']}={m['score']:.2f}({m['level']})" for m in recomputed)
        problems.note(f"independent overlap scoring: {summary}")
    else:
        problems.note("independent overlap scoring: no task scored at or above the possible threshold")


# --------------------------------------------------------------------------------------
# Stage orchestration
# --------------------------------------------------------------------------------------

_STAGE_PRIMARY_ARTIFACT = {
    "duplicate_check": "intake.json",
    "plan": "plan.json",
    "implementation": "worker-result.json",
    "implement": "worker-result.json",
    "qa": "qa-report.json",
    "test": "qa-report.json",
    "review": "review-report.json",
}


def check_trivial_classification_gate(intake: dict, problems: Report) -> None:
    """C3: trivial may cut process only after an explicit human confirmation."""
    if intake.get("complexity") != "trivial":
        return
    confirmation = intake.get("classification_confirmation")
    if not isinstance(confirmation, dict) or confirmation.get("decided_by") != "human":
        problems.error(
            "trivial_needs_human",
            "complexity is trivial but classification_confirmation.decided_by is not 'human'. "
            "A trivial classification removes design, plan, and review; only a human may confirm "
            "that cut. Record classification_confirmation before implementation or QA.",
            "intake.json",
        )


_INHERIT_SLUG = "inherit"


def load_model_catalog(root: Path | None = None) -> dict | None:
    """Load `.agent/models/available.yaml`. Returns None when absent."""
    base = root or REPO_ROOT
    path = base / ".agent" / "models" / "available.yaml"
    if not path.is_file():
        return None
    data = parse_yaml(path.read_text(encoding="utf-8"))
    return data if isinstance(data, dict) else None


def catalog_ide_slugs(catalog: dict | None) -> set[str]:
    if not isinstance(catalog, dict):
        return set()
    models = catalog.get("models")
    if not isinstance(models, list):
        return set()
    slugs: set[str] = set()
    for item in models:
        if isinstance(item, dict):
            slug = item.get("ide_slug") or item.get("id")
            if isinstance(slug, str) and slug:
                slugs.add(slug)
    return slugs


def triangle_roles_for_intake(intake: dict) -> list[str]:
    """Roles that must carry pairwise-distinct assigned_model for this task."""
    roles = ["qa", "reviewer"]
    activated = intake.get("activated_specialists") or []
    gates = intake.get("blocking_gates") or []
    if "security" in activated or "security" in gates:
        roles.append("security")
    return roles


def assignment_slug(entry: object) -> str | None:
    if not isinstance(entry, dict):
        return None
    model = entry.get("assigned_model")
    if isinstance(model, str) and model.strip():
        return model.strip()
    return None


def check_model_assignments(intake: dict, problems: Report, *, catalog: dict | None = None) -> None:
    """C1: non-trivial tasks need model_assignments; qa/reviewer/security pairwise distinct."""
    if intake.get("complexity") == "trivial":
        return

    assignments = intake.get("model_assignments")
    if not isinstance(assignments, dict):
        problems.error(
            "model_assignments_required",
            "complexity is not trivial but model_assignments is missing. Orchestrator must record "
            "per-role assigned_model slugs (qa/reviewer/security pairwise distinct) before dispatch.",
            "intake.json",
        )
        return

    if "orchestrator" in assignments:
        problems.error(
            "model_assignments_orchestrator",
            "model_assignments must not include orchestrator; the root model is chosen in the UI",
            "intake.json",
        )

    roles = triangle_roles_for_intake(intake)
    catalog = catalog if catalog is not None else load_model_catalog()
    known = catalog_ide_slugs(catalog)
    slugs: dict[str, str] = {}

    for role in roles:
        entry = assignments.get(role)
        slug = assignment_slug(entry)
        if not slug:
            problems.error(
                "model_assignment_missing",
                f"model_assignments.{role}.assigned_model is required for this task's review triangle",
                "intake.json",
            )
            continue
        if slug == _INHERIT_SLUG:
            problems.error(
                "model_assignment_inherit",
                f"model_assignments.{role}.assigned_model must not be 'inherit' "
                "(inherit collapses independent review)",
                "intake.json",
            )
            continue
        if isinstance(entry, dict) and entry.get("unavailable_in_ide") is True:
            problems.error(
                "model_assignment_unavailable",
                f"model_assignments.{role} is marked unavailable_in_ide; pick a dispatchable slug "
                "from the catalog ∩ session allow-list",
                "intake.json",
            )
            continue
        if known and slug not in known:
            problems.error(
                "model_assignment_unknown",
                f"model_assignments.{role}.assigned_model {slug!r} is not in "
                ".agent/models/available.yaml; run init --refresh-models or fix the slug",
                "intake.json",
            )
            continue
        slugs[role] = slug

    if len(slugs) < 2:
        return

    escalation = assignments.get("escalation") if isinstance(assignments.get("escalation"), dict) else {}
    allow_same = (
        escalation.get("decided_by") == "human"
        and escalation.get("allow_same_model") is True
    )

    pairs = [(a, b) for i, a in enumerate(roles) for b in roles[i + 1 :] if a in slugs and b in slugs]
    collisions = [(a, b) for a, b in pairs if slugs[a] == slugs[b]]
    if collisions and not allow_same:
        detail = ", ".join(f"{a}/{b}={slugs[a]}" for a, b in collisions)
        problems.error(
            "model_triangle_not_distinct",
            f"qa/reviewer/security assigned_model values must be pairwise distinct "
            f"(collisions: {detail}). Escalate to a human with escalation.allow_same_model "
            "if fewer than enough IDE-dispatchable models exist — never silently share a model.",
            "intake.json",
        )

    developer = assignment_slug(assignments.get("developer"))
    if developer and developer in slugs.values() and developer != _INHERIT_SLUG:
        problems.warn(
            "model_developer_overlaps_triangle",
            f"developer assigned_model {developer!r} overlaps the review triangle; prefer a "
            "different model when the catalog has spare capacity",
            "intake.json",
        )


def check_models_catalog(problems: Report) -> None:
    """C1 setup: seed + available catalogs must exist and list enough non-inherit slugs."""
    seed = REPO_ROOT / ".agent" / "models" / "seed.yaml"
    available = REPO_ROOT / ".agent" / "models" / "available.yaml"
    if not seed.is_file():
        problems.error(
            "models_seed_missing",
            "missing .agent/models/seed.yaml (manual_seed adapter for init --refresh-models)",
            ".agent/models/seed.yaml",
        )
    if not available.is_file():
        problems.error(
            "models_catalog_missing",
            "missing .agent/models/available.yaml. Run: python .agent/tools/init_project.py --refresh-models",
            ".agent/models/available.yaml",
        )
        return
    try:
        catalog = load_model_catalog()
    except Exception as exc:  # noqa: BLE001
        problems.error("models_catalog_parse", f"cannot parse model catalog: {exc}", ".agent/models/available.yaml")
        return
    if not isinstance(catalog, dict):
        problems.error("models_catalog_shape", "available.yaml must be a mapping", ".agent/models/available.yaml")
        return
    slugs = {s for s in catalog_ide_slugs(catalog) if s != _INHERIT_SLUG}
    if len(slugs) < 3:
        problems.warn(
            "models_catalog_thin",
            f"catalog has only {len(slugs)} non-inherit slug(s); qa/reviewer/security need three "
            "distinct models or a human escalation.allow_same_model",
            ".agent/models/available.yaml",
        )
    else:
        problems.note(f"model catalog: {len(slugs)} non-inherit slug(s), source={catalog.get('source')!r}")
    fetched = catalog.get("fetched_at")
    if isinstance(fetched, str) and fetched:
        try:
            fetched_date = datetime.strptime(fetched[:10], "%Y-%m-%d").date()
            age_days = (datetime.now(timezone.utc).date() - fetched_date).days
            if age_days > 30:
                problems.warn(
                    "models_catalog_stale",
                    f"available.yaml fetched_at is {age_days} days old; consider "
                    "python .agent/tools/init_project.py --refresh-models",
                    ".agent/models/available.yaml",
                )
        except ValueError:
            problems.warn(
                "models_catalog_fetched_at",
                f"fetched_at {fetched!r} is not YYYY-MM-DD",
                ".agent/models/available.yaml",
            )


def task_artifact_hashes(task_dir: Path) -> dict[str, str]:
    """SHA-256 of known task artifacts present on disk (C4 anchors)."""
    names = {
        "intake.json",
        "requirements.json",
        "design.json",
        "plan.json",
        "worker-result.json",
        "qa-report.json",
        "review-report.json",
        "security-report.json",
        "ux-report.json",
        "db-report.json",
        "perf-report.json",
        "data-report.json",
        "delivery-report.json",
    }
    hashes: dict[str, str] = {}
    for name in sorted(names):
        path = task_dir / name
        if path.is_file():
            hashes[name] = hashlib.sha256(path.read_bytes()).hexdigest()
    for path in sorted(task_dir.glob("consultation-*.json")):
        hashes[path.name] = hashlib.sha256(path.read_bytes()).hexdigest()
    return hashes


def git_head_for_repo() -> str | None:
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        return None
    return (result.stdout or "").strip() or None


def write_validate_log(task_dir: Path, stage: str, report: Report) -> Path | None:
    """Write tasks/<id>/logs/validate-<uuid>.json for a stage run. Best-effort; never fails the gate."""
    if not task_dir.is_dir():
        return None
    log_dir = task_dir / "logs"
    try:
        log_dir.mkdir(parents=True, exist_ok=True)
    except OSError:
        return None
    log_uuid = str(uuid.uuid4())
    payload = {
        "uuid": log_uuid,
        "task_id": task_dir.name,
        "stage": stage,
        "exit_code": 1 if report.errors else 0,
        "error_count": len(report.errors),
        "warning_count": len(report.warnings),
        "created_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "git_head": git_head_for_repo(),
        "artifacts": task_artifact_hashes(task_dir),
    }
    path = log_dir / f"validate-{log_uuid}.json"
    try:
        path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        try:
            # Best-effort read-only on POSIX. On Windows chmod often blocks later cleanup in tests.
            if os.name != "nt":
                path.chmod(stat.S_IRUSR | stat.S_IRGRP | stat.S_IROTH)
        except OSError:
            pass
        return path
    except OSError:
        return None


def load_validate_logs(task_dir: Path) -> list[dict]:
    log_dir = task_dir / "logs"
    if not log_dir.is_dir():
        return []
    logs: list[dict] = []
    for path in sorted(log_dir.glob("validate-*.json")):
        try:
            data = load_json(path)
        except (json.JSONDecodeError, OSError):
            continue
        if isinstance(data, dict):
            data = dict(data)
            data["_path"] = path.name
            logs.append(data)
    return logs


def log_hashes_match(log: dict, current: dict[str, str], ignore_keys: set[str] | None = None) -> bool:
    """True when every artifact hash recorded in the log still matches the file on disk.

    `ignore_keys` skips named artifacts (QA cites an earlier-stage log, then updates
    qa-report.json to include the uuid — that file's hash must not invalidate the citation).
    """
    recorded = log.get("artifacts")
    if not isinstance(recorded, dict) or not recorded:
        return False
    skip = ignore_keys or set()
    for name, digest in recorded.items():
        if name in skip:
            continue
        if current.get(name) != digest:
            return False
    return True


def check_validate_log_citations(qa: dict, task_dir: Path, problems: Report) -> None:
    """C4: a QA PASS must cite at least one successful validate log by uuid."""
    if qa.get("verdict") != "PASS":
        return
    ids = qa.get("validate_log_ids")
    if not isinstance(ids, list) or not ids:
        problems.error(
            "qa_missing_validate_log",
            "verdict is PASS but validate_log_ids is missing or empty. Cite the uuid of a "
            "validate.py log under tasks/<TASK-ID>/logs/ (prefer an earlier stage such as "
            "duplicate_check or implementation; then re-run validate --stage qa).",
            "qa-report.json",
        )
        return
    by_uuid = {log.get("uuid"): log for log in load_validate_logs(task_dir) if log.get("uuid")}
    current = task_artifact_hashes(task_dir)
    for log_id in ids:
        log = by_uuid.get(log_id)
        if not isinstance(log, dict):
            problems.error(
                "qa_validate_log_unknown",
                f"validate_log_ids cites unknown uuid {log_id!r}; no matching file under logs/",
                "qa-report.json",
            )
            continue
        if log.get("exit_code") != 0:
            problems.error(
                "qa_validate_log_failed",
                f"validate log {log_id} has exit_code={log.get('exit_code')}; cite a passing run",
                "qa-report.json",
            )
            continue
        # Ignore qa-report.json: the report is updated to cite the log after the log was written.
        if not log_hashes_match(log, current, ignore_keys={"qa-report.json"}):
            problems.error(
                "qa_validate_log_stale",
                f"validate log {log_id} no longer matches artifact hashes on disk; re-run validate",
                "qa-report.json",
            )


def check_validate_logs_for_completion(task_dir: Path, stages: list[str], problems: Report) -> None:
    """C4: completion requires a fresh exit_code 0 log for each prior applicable stage."""
    logs = load_validate_logs(task_dir)
    current = task_artifact_hashes(task_dir)
    needed = [s for s in stages if s != "completion" and s in _STAGE_PRIMARY_ARTIFACT]
    for stage in needed:
        primary = _STAGE_PRIMARY_ARTIFACT[stage]
        if not (task_dir / primary).is_file():
            continue
        matching = []
        for log in logs:
            if log.get("stage") != stage or log.get("exit_code") != 0:
                continue
            recorded = log.get("artifacts") if isinstance(log.get("artifacts"), dict) else {}
            # Freshness is judged on the stage's primary artifact only. Logs also snapshot
            # sibling files; later stages may rewrite those without invalidating this stage.
            if recorded.get(primary) == current.get(primary):
                matching.append(log)
        if not matching:
            problems.error(
                "validate_log_missing",
                f"no fresh validate log for stage '{stage}' (exit_code 0, hashes match). "
                f"Run: python .agent/tools/validate.py --task {task_dir.name} --stage {stage}",
                f"logs/",
            )


def stage_plan(task_dir: Path, problems: Report) -> None:
    plan_path = task_dir / "plan.json"
    if not plan_path.exists():
        problems.error("plan_exists", "plan.json is missing; the plan stage has not run", str(task_dir.name))
        return
    plan = load_json(plan_path)
    check_plan(plan, problems)
    check_plan_against_repository(plan, problems)
    check_design_time_consultation(task_dir, plan, problems)
    requirements_path = task_dir / "requirements.json"
    if requirements_path.exists():
        requirements = load_json(requirements_path)
        # Unanswered product questions are checked here, at the last stage before implementation,
        # because this is the point of no return: guessing a product decision propagates into the
        # design, the plan, the code, and every gate that verifies it. The check existed for a long
        # time without being called from anywhere, which is why it is now wired rather than merely
        # defined — and why its canary drives this function instead of the checker.
        check_requirements(requirements, problems)
        check_plan_covers_requirements(plan, requirements, problems)
    else:
        problems.warn("requirements_missing", "no requirements.json, so acceptance mapping is unverifiable", str(task_dir.name))


def stage_implementation(task_dir: Path, problems: Report) -> None:
    intake_path = task_dir / "intake.json"
    if intake_path.exists():
        try:
            intake = load_json(intake_path)
        except (json.JSONDecodeError, OSError):
            intake = {}
        if isinstance(intake, dict):
            check_trivial_classification_gate(intake, problems)
            check_model_assignments(intake, problems)
    plan_path = task_dir / "plan.json"
    worker_path = task_dir / "worker-result.json"
    if not plan_path.exists():
        problems.error("plan_exists", "plan.json is missing; implementation has no approved scope", str(task_dir.name))
        return
    if not worker_path.exists():
        problems.error("worker_result_exists", "worker-result.json is missing; implementation has not reported", str(task_dir.name))
        return
    check_artifact(worker_path, problems)
    check_implementation(task_dir, load_json(plan_path), problems)


def stage_qa(task_dir: Path, problems: Report) -> None:
    intake_path = task_dir / "intake.json"
    if intake_path.exists():
        try:
            intake = load_json(intake_path)
        except (json.JSONDecodeError, OSError):
            intake = {}
        if isinstance(intake, dict):
            check_trivial_classification_gate(intake, problems)
            check_model_assignments(intake, problems)
    qa_path = task_dir / "qa-report.json"
    if not qa_path.exists():
        problems.error("qa_report_exists", "qa-report.json is missing; verification has not run", str(task_dir.name))
        return
    qa = load_json(qa_path)
    if isinstance(qa, dict):
        check_validate_log_citations(qa, task_dir, problems)
    requirements_path = task_dir / "requirements.json"
    if requirements_path.exists():
        check_qa_covers_requirements(qa, load_json(requirements_path), problems)
    # Phase gating: a critical failure must not be reported alongside a PASS.
    if isinstance(qa, dict) and qa.get("verdict") == "PASS":
        failed = [c for c in (qa.get("criteria") or []) if isinstance(c, dict) and c.get("verdict") == "FAIL"]
        if failed:
            problems.error(
                "verdict_consistent",
                f"verdict is PASS but {len(failed)} criterion/criteria failed",
                "qa-report.json",
            )


def stage_review(task_dir: Path, problems: Report) -> None:
    review_path = task_dir / "review-report.json"
    if not review_path.exists():
        problems.error("review_report_exists", "review-report.json is missing; review has not run", str(task_dir.name))
        return
    review = load_json(review_path)
    if review.get("verdict") == "PASS" and review.get("blockers"):
        problems.error("verdict_consistent", "verdict is PASS but blockers is non-empty", "review-report.json")
    if review.get("verdict") == "PASS" and review.get("concerns"):
        problems.error(
            "verdict_consistent",
            "verdict is PASS but concerns is non-empty; only nits may remain for a PASS",
            "review-report.json",
        )
    for bucket in ("blockers", "concerns"):
        for index, finding in enumerate(review.get(bucket) or []):
            if not isinstance(finding, dict):
                problems.error("finding_shape", f"{bucket}[{index}] must be an object", "review-report.json")
                continue
            if not finding.get("file"):
                problems.error("finding_has_file", f"{bucket}[{index}] has no file", "review-report.json")
            if not finding.get("fix"):
                problems.error("finding_has_fix", f"{bucket}[{index}] has no actionable fix", "review-report.json")


def required_gates(intake: dict) -> list[str]:
    """Derive the gates a task must clear, from its risk profile and activated specialists.

    Mirrors `.agent/config.yaml`. Kept in one place so the derivation is auditable and cannot
    drift between callers.
    """
    complexity = intake.get("complexity")
    risk = intake.get("risk")
    activated = set(intake.get("activated_specialists") or [])

    gates = ["qa"]
    # Trivial work has no design and no review gate (config.yaml: review_required: false).
    if complexity != "trivial":
        gates.append("review")
    if risk == "high":
        gates.append("security")
    for specialist in activated:
        if specialist != "security":
            gates.append(specialist)
    return [g for g in GATE_ORDER if g in gates]


def stage_completion(task_dir: Path, problems: Report) -> None:
    """The whole-gate check: every gate the task required must have actually run and passed."""
    intake_path = task_dir / "intake.json"
    if not intake_path.exists():
        problems.error("intake_exists", "intake.json is missing; routing decisions are unverifiable", str(task_dir.name))
        return
    intake = load_json(intake_path)
    activated = set(intake.get("activated_specialists") or [])
    risk = intake.get("risk")
    complexity = intake.get("complexity")

    gates = required_gates(intake)

    # A task must also have cleared the duplicate check before it can close.
    overlap = intake.get("overlap_check")
    if not isinstance(overlap, dict):
        problems.error(
            "overlap_check_missing",
            "intake.json has no overlap_check, so the request was never compared against active "
            "tasks. Without it, two active tasks describing one request can both look authoritative.",
            "intake.json",
        )
    else:
        decision = overlap.get("decision") or {}
        if decision.get("outcome") == "supersede":
            superseded = decision.get("superseded_task_id")
            if superseded and (REPO_ROOT / "tasks" / "active" / superseded).is_dir():
                problems.error(
                    "supersede_not_archived",
                    f"outcome is supersede for {superseded}, but that task is still in tasks/active/",
                    "intake.json",
                )

    skipped = {s.get("specialist") for s in (intake.get("skipped_specialists") or []) if isinstance(s, dict)}
    expected = set(activated) | ({"security"} if risk == "high" else set())
    unexplained = {g for g in gates if g in skipped and g not in expected}
    if unexplained:
        problems.warn(
            "skip_without_reason",
            f"gates recorded as skipped without appearing in activated_specialists: {sorted(unexplained)}",
            "intake.json",
        )

    # A trivial task that nevertheless carries a specialist should be re-classified, not quietly gated.
    if complexity == "trivial" and activated:
        problems.warn(
            "trivial_with_specialists",
            f"complexity is trivial but specialists are activated: {sorted(activated)}. "
            "Either the classification is too low or the activation is unnecessary.",
            "intake.json",
        )

    check_gate_presence(task_dir, gates, problems)
    check_validate_logs_for_completion(task_dir, applicable_stages(task_dir), problems)
    problems.note(f"required gates: {gates} (complexity={complexity}, risk={risk})")


STAGE_CHECKERS = {
    "duplicate_check": stage_duplicate_check,
    "plan": stage_plan,
    "implementation": stage_implementation,
    "implement": stage_implementation,
    "qa": stage_qa,
    "test": stage_qa,
    "review": stage_review,
    "completion": stage_completion,
}

ALL_STAGES = ["duplicate_check", "plan", "implementation", "qa", "review", "completion"]


def applicable_stages(task_dir: Path) -> list[str]:
    """Stages that actually apply to this task, given its classification.

    `--all` should not report a trivial copy change as failing the plan stage, because a trivial
    task has no plan by design (`.agent/config.yaml -> complexity.trivial.plan_required: false`).
    Reporting a stage as failed when the framework deliberately skips it trains people to ignore
    the validator, which costs more than the check is worth.
    """
    intake_path = task_dir / "intake.json"
    if not intake_path.exists():
        return ALL_STAGES

    try:
        intake = load_json(intake_path)
    except (json.JSONDecodeError, OSError):
        return ALL_STAGES

    if not isinstance(intake, dict):
        return ALL_STAGES

    complexity = intake.get("complexity")
    # The duplicate check applies to every task regardless of classification: whether a request
    # duplicates another active task has nothing to do with how much process it needs.
    stages = ["duplicate_check", "qa", "completion"]

    # A plan-bearing task is one that is not trivial, or that has a plan on disk anyway.
    has_plan = (task_dir / "plan.json").exists()
    if complexity != "trivial" or has_plan:
        stages = ["plan", "implementation"] + stages

    if complexity != "trivial":
        stages.insert(stages.index("completion"), "review")

    return [s for s in ALL_STAGES if s in stages]


# --------------------------------------------------------------------------------------
# Setup lint — keeps the team's own configuration from drifting
# --------------------------------------------------------------------------------------


def declared_roles_from_config(config_text: str) -> set[str]:
    """Extract the roster from the `team:` block of config.yaml.

    Scoped to the `team:` block on purpose. Scanning the whole file would also pick up
    enum value lists (complexity levels, artifact names, gate ids) and every one of those
    would then be reported as a role with no agent definition.
    """
    roles: set[str] = set()
    in_team = False
    for line in config_text.splitlines():
        if re.match(r"^team:\s*$", line):
            in_team = True
            continue
        if not in_team:
            continue
        # A new top-level key ends the block.
        if line and not line[0].isspace():
            break
        item = re.match(r"^\s+-\s+([a-z][a-z0-9-]*)\s*$", line)
        if item:
            roles.add(item.group(1))
            continue
        # Scalar entries inside the block: `  orchestrator: orchestrator`
        scalar = re.match(r"^\s+([a-z][a-z0-9-]*):\s*([a-z][a-z0-9-]*)\s*$", line)
        if scalar:
            roles.add(scalar.group(2))
    return roles


def check_setup(problems: Report) -> None:
    agents_dir = REPO_ROOT / ".cursor" / "agents"
    if not agents_dir.is_dir():
        problems.error("setup", f"missing agents directory: {agents_dir}")
        return

    agent_files = sorted(agents_dir.rglob("*.md"))
    if not agent_files:
        problems.error("setup", "no agent definitions found under .cursor/agents/")
        return

    config_path = REPO_ROOT / ".agent" / "config.yaml"
    config_text = config_path.read_text(encoding="utf-8") if config_path.exists() else ""
    if not config_text:
        problems.error("setup", f"missing or empty routing config: {config_path}")

    declared_roles = declared_roles_from_config(config_text)

    seen_names: dict[str, str] = {}

    for path in agent_files:
        rel = path.relative_to(REPO_ROOT).as_posix()
        text = path.read_text(encoding="utf-8")
        fields, body = read_frontmatter(text)

        if not fields:
            problems.error("agent_frontmatter", "no YAML frontmatter found", rel)
            continue

        for required_field in ("name", "description"):
            if not fields.get(required_field):
                problems.error("agent_frontmatter", f"missing required frontmatter field '{required_field}'", rel)

        for field in fields:
            if field not in AGENT_FRONTMATTER_FIELDS:
                problems.warn(
                    "agent_frontmatter",
                    f"unknown frontmatter field '{field}'. Cursor recognises: {sorted(AGENT_FRONTMATTER_FIELDS)}",
                    rel,
                )

        name = fields.get("name")
        if isinstance(name, str):
            if name in seen_names:
                problems.error(
                    "agent_name_unique",
                    f"agent name '{name}' is already used by {seen_names[name]}",
                    rel,
                )
            else:
                seen_names[name] = rel
            if name not in declared_roles:
                problems.error(
                    "agent_registered",
                    f"agent '{name}' is not listed in .agent/config.yaml",
                    rel,
                )

        description = fields.get("description")
        if isinstance(description, str) and "Use " not in description and "use " not in description:
            problems.warn(
                "agent_description",
                "description does not state when to use this agent; it is the only auto-routing trigger surface",
                rel,
            )

        for section in REQUIRED_AGENT_SECTIONS:
            if section not in body:
                problems.error("agent_section", f"missing required section '{section}'", rel)

        if "## NON-GOALS" in body:
            non_goals = body.split("## NON-GOALS", 1)[1]
            if len([line for line in non_goals.splitlines() if line.strip().startswith("-")]) < 3:
                problems.warn(
                    "agent_non_goals",
                    "fewer than 3 explicit NON-GOALS; this is a role's primary authority boundary",
                    rel,
                )

        if fields.get("readonly") is True:
            for pattern in ("Edit ", "Write the file", "modify application code"):
                if pattern in body:
                    problems.note(f"{name}: readonly agent mentioning writes ({pattern}) — verify intent")

            # The check that matters: a readonly role cannot write the artifact the pipeline
            # requires of it. Catch it here rather than at dispatch time.
            required_artifacts = ARTIFACT_WRITERS.get(name, ())
            if required_artifacts:
                problems.error(
                    "readonly_cannot_write_artifact",
                    f"agent '{name}' is readonly: true but is the sole writer of "
                    f"{list(required_artifacts)}. Cursor's readonly flag removes write tools entirely "
                    f"(no file edits, no state-changing shell commands), so this role would be "
                    f"dispatched and fail on its first write. Set readonly: false and enforce "
                    f"'does not write application code' through NON-GOALS instead.",
                    rel,
                )
        elif isinstance(name, str) and name not in ARTIFACT_WRITERS:
            problems.warn(
                "agent_unmapped",
                f"agent '{name}' has no entry in ARTIFACT_WRITERS in .agent/tools/validate.py; "
                "add one so the readonly/artifact-write conflict can be checked",
                rel,
            )

    # Every role the pipeline depends on must exist as an agent definition.
    for role, artifacts in ARTIFACT_WRITERS.items():
        if role in declared_roles and role not in seen_names:
            problems.error(
                "artifact_writer_missing",
                f"'{role}' is declared as the sole writer of {list(artifacts)} but has no agent definition",
                ".agent/tools/validate.py",
            )

    for role in sorted(declared_roles):
        if role not in seen_names:
            problems.warn(
                "agent_missing",
                f"config.yaml declares role '{role}' with no matching agent definition",
                ".agent/config.yaml",
            )

    for schema_path in sorted((REPO_ROOT / ".agent" / "schemas").glob("*.json")):
        try:
            schema = load_json(schema_path)
        except (json.JSONDecodeError, OSError) as exc:
            problems.error("schema_parse", f"invalid schema: {exc}", schema_path.name)
            continue
        if not isinstance(schema, dict) or "$schema" not in schema:
            problems.warn("schema_shape", "schema has no $schema declaration", schema_path.name)

    for workflow_path in sorted((REPO_ROOT / ".agent" / "workflows").glob("*.yaml")):
        text = workflow_path.read_text(encoding="utf-8")
        for role in re.findall(r"^\s+agent:\s*([a-z][a-z0-9-]*)\s*$", text, re.MULTILINE):
            if role not in seen_names:
                problems.error(
                    "workflow_agent_exists",
                    f"workflow references unknown agent '{role}'",
                    workflow_path.name,
                )

    # The environment gate is enforced against worker-result.json, so the rule that documents it
    # must exist. A gate whose rule has been deleted is a requirement with no explanation.
    rules_dir = REPO_ROOT / ".cursor" / "rules"
    rule_names = {p.stem for p in rules_dir.glob("*.mdc")} if rules_dir.is_dir() else set()
    if "environment" not in rule_names:
        problems.error(
            "environment_rule_missing",
            "worker-result.json requires a human-confirmed environment, but .cursor/rules/environment.mdc "
            "does not exist. The gate must be explained somewhere the agent can read.",
            ".cursor/rules/",
        )
    if "00-global" not in rule_names:
        problems.error(
            "global_rule_missing",
            ".cursor/rules/00-global.mdc is absent; the pre-action gate and evidence rules are not injected",
            ".cursor/rules/",
        )

    check_project_baseline(problems)
    check_models_catalog(problems)
    check_seeded_from(problems)

    problems.note(f"{len(agent_files)} agent definitions, {len(declared_roles)} roles declared in config, "
                  f"{len(rule_names)} rules")

    check_portability(problems)


_BASELINE_STATUSES = frozenset({"template", "established", "framework_meta"})


def check_seeded_from(problems: Report) -> None:
    """Product repos should record how they were seeded; the framework repo itself need not."""
    baseline_path = REPO_ROOT / ".agent" / "project-baseline.yaml"
    status = None
    if baseline_path.is_file():
        try:
            data = parse_yaml(baseline_path.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                status = data.get("status")
        except Exception:  # noqa: BLE001
            status = None
    if status == "framework_meta":
        manifest = REPO_ROOT / ".agent" / "framework-manifest.yaml"
        if not manifest.is_file():
            problems.error(
                "framework_manifest_missing",
                "this repository is framework_meta but .agent/framework-manifest.yaml is missing",
                ".agent/framework-manifest.yaml",
            )
        else:
            problems.note("framework manifest present (this repository is the agent framework)")
        return

    seeded = REPO_ROOT / ".agent" / "seeded-from.yaml"
    rel = ".agent/seeded-from.yaml"
    if not seeded.is_file():
        problems.warn(
            "seeded_from_missing",
            "no .agent/seeded-from.yaml — project may predate seed_framework, or was copied by hand. "
            "Re-seed or run upgrade from a framework checkout to record release metadata.",
            rel,
        )
        return
    try:
        data = parse_yaml(seeded.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        problems.error("seeded_from_parse", f"cannot parse seeded-from: {exc}", rel)
        return
    if not isinstance(data, dict) or not data.get("release"):
        problems.warn("seeded_from_incomplete", "seeded-from.yaml missing release field", rel)
    else:
        problems.note(f"seeded-from release={data.get('release')!r} op={data.get('last_operation')!r}")


def check_project_baseline(problems: Report) -> None:
    """Require a structured project baseline (C6). Markdown project-memory is summary only."""
    path = REPO_ROOT / ".agent" / "project-baseline.yaml"
    rel = ".agent/project-baseline.yaml"
    if not path.is_file():
        problems.error(
            "project_baseline_missing",
            "missing .agent/project-baseline.yaml. Product stack and authoritative commands belong "
            "in this structured baseline (filled by human + product + tech-lead at project-level "
            "spec/design), not in a hand-written markdown ceremony. Copy "
            ".agent/templates/project-baseline.yaml to start.",
            rel,
        )
        return
    try:
        data = parse_yaml(path.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001 — surface parse failures as setup errors
        problems.error("project_baseline_parse", f"cannot parse project baseline: {exc}", rel)
        return
    if not isinstance(data, dict):
        problems.error("project_baseline_shape", "project baseline must be a mapping", rel)
        return
    status = data.get("status")
    if status not in _BASELINE_STATUSES:
        problems.error(
            "project_baseline_status",
            f"status must be one of {sorted(_BASELINE_STATUSES)}, got {status!r}",
            rel,
        )
        return
    if status == "template":
        problems.warn(
            "project_baseline_unfilled",
            "project baseline status is template. Before product implementation, run a project-level "
            "spec/design with human + product + tech-lead and set status to established.",
            rel,
        )
        return
    if status == "framework_meta":
        problems.note("project baseline: framework_meta (this repository is the agent framework)")
        return
    # established — require the fields environment gates need
    stack = data.get("stack") if isinstance(data.get("stack"), dict) else {}
    commands = data.get("commands") if isinstance(data.get("commands"), dict) else {}
    for key in ("language", "runtime", "environment_manager"):
        if not stack.get(key):
            problems.error(
                "project_baseline_incomplete",
                f"established baseline missing stack.{key}",
                rel,
            )
    for key in ("test",):
        if not commands.get(key):
            problems.error(
                "project_baseline_incomplete",
                f"established baseline missing commands.{key}",
                rel,
            )
    decided = data.get("decided_by") if isinstance(data.get("decided_by"), dict) else {}
    if decided.get("human") is not True:
        problems.error(
            "project_baseline_unapproved",
            "established baseline must record decided_by.human: true",
            rel,
        )


# Machine-specific absolute paths. Deliberately narrow, so documented API routes such as
# `/invitations/{token}` and placeholder examples such as `/path/to/thing` are not flagged.
_MACHINE_PATH_PATTERNS = [
    (re.compile(r"\b[A-Za-z]:[\\/](?!\*)"), "a Windows drive path"),
    (re.compile(r"\\\\[A-Za-z0-9._-]+\\"), "a UNC network path"),
    (re.compile(r"/(?:home|Users)/[A-Za-z0-9._-]+/"), "a user home directory path"),
    (re.compile(r"\bC:/"), "a Windows drive path"),
]

# Portability scans *framework source*, not run records. Task artifacts under `tasks/` are a run's
# evidence and will name real interpreters; scanning them puts "report what you ran" and "stay
# portable" in conflict. `refers/` quotes other repos' paths by design.
_PORTABILITY_EXEMPT_PREFIXES = (
    "tasks/",
    "refers/",
    ".rgents/",
    ".agent/.selftest",
)

# Only these surfaces are framework code for this check. Everything else (README, product src, …)
# is out of scope for the portability rule.
_PORTABILITY_SCAN_PREFIXES = (
    ".agent/",
    ".cursor/",
    "docs/agents/",
    "docs/architecture/",
)


def _portability_rel_is_scanned(rel: str) -> bool:
    if any(rel == p.rstrip("/") or rel.startswith(p) for p in _PORTABILITY_EXEMPT_PREFIXES):
        return False
    if any(rel == p.rstrip("/") or rel.startswith(p) for p in _PORTABILITY_SCAN_PREFIXES):
        return True
    return rel in ("AGENTS.md",)


def _portability_scan_files() -> list[Path]:
    """Framework files the portability scan inspects (not task run records).

    `run_selftest` builds known-bad inputs under a scratch tree; those trees are scanned when
    REPO_ROOT is pointed at them. The selftest region inside validate.py itself is stripped so
    canary strings do not fail the live repository check.
    """
    scan_suffixes = (".py", ".yaml", ".yml", ".json")
    files: list[Path] = []
    for path in sorted(REPO_ROOT.rglob("*")):
        if not path.is_file():
            continue
        rel = path.relative_to(REPO_ROOT).as_posix()
        if path.suffix not in scan_suffixes and path.name != "AGENTS.md":
            continue
        if not _portability_rel_is_scanned(rel):
            continue
        files.append(path)
    return files


def _strip_selftest_region(path: Path, text: str) -> str:
    """Return only the framework part of validate.py, dropping the selftest apparatus."""
    if path.name != "validate.py":
        return text
    lines = text.splitlines()
    for index, line in enumerate(lines):
        if line.startswith("def run_selftest("):
            return "\n".join(lines[:index])
    return text


def check_portability(problems: Report) -> None:
    """The framework must be project-agnostic and must not assume any project's layout.

    This is the automated half of that promise. Two things are checked:

      1. No machine-specific absolute path in the framework's own files. The framework is meant to
         be copied into any repository; a hard-coded root would silently tie it to one machine.
      2. Every path the framework itself owns resolves from a root discovered at runtime, so the
         tool behaves identically no matter which directory it is invoked from.
    """
    findings = 0
    for path in _portability_scan_files():
        rel = path.relative_to(REPO_ROOT).as_posix()
        try:
            text = _strip_selftest_region(path, path.read_text(encoding="utf-8"))
        except (UnicodeDecodeError, OSError):
            continue
        for number, line in enumerate(text.splitlines(), 1):
            if path.suffix in (".py", ".yaml", ".yml") and line.lstrip().startswith("#"):
                continue
            for pattern, description in _MACHINE_PATH_PATTERNS:
                if pattern.search(line):
                    findings += 1
                    problems.error(
                        "machine_specific_path",
                        f"{description} at line {number}. The framework must be portable: resolve "
                        f"paths from the repository root discovered at runtime, or take them as "
                        f"arguments. Offending text: {line.strip()[:70]!r}",
                        rel,
                    )
                    break

    # The root must be derived from this file's location, not from the working directory, and no
    # working-directory API may be called in the framework region. Checked by parsing the syntax
    # tree rather than matching text, because a text search also matches the wording of this check
    # itself — which is how the first version of it reported two false positives against itself.
    validation_source = Path(__file__).read_text(encoding="utf-8")
    framework_region = _strip_selftest_region(Path(__file__), validation_source)
    try:
        tree = ast.parse(framework_region)
    except SyntaxError:
        tree = None

    if tree is not None:
        terminal_names: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
                terminal_names.add(node.func.attr)
        if "getcwd" in terminal_names or "cwd" in terminal_names:
            problems.error(
                "cwd_dependency",
                "the tool calls a working-directory API. Relative paths must resolve against the "
                "repository root instead, so that invoking it from a subdirectory, an editor task, "
                "or a CI step gives identical results",
                ".agent/tools/validate.py",
            )
        if not any(isinstance(node, ast.Attribute) and node.attr == "parents" for node in ast.walk(tree)):
            problems.error(
                "root_not_derived",
                "the repository root is not derived from this file's own location, so the tool would "
                "behave differently depending on where it was invoked from",
                ".agent/tools/validate.py",
            )

    if not findings and not problems.errors:
        problems.note("portability: no machine-specific absolute paths, root derived at runtime")


# --------------------------------------------------------------------------------------
# Selftest — proves the invariants actually fire
# --------------------------------------------------------------------------------------


def run_selftest() -> int:
    """Prove each invariant actually fires on known-bad input.

    Two design notes:
      * Artifact rules are exercised in memory, so the selftest needs no scratch files.
      * The one directory-based check uses a scratch directory inside the repository, because
        sandboxed environments do not always permit writes to the system temp directory.
    """
    print("== selftest")
    failures = 0

    def canary(title: str, condition: bool, detail: str = "") -> None:
        nonlocal failures
        if condition:
            print(f"   ok   {title}")
        else:
            print(f"   FAIL {title}" + (f" -- {detail}" if detail else ""))
            failures += 1

    def artifact(name: str, payload: object) -> Report:
        """Validate one in-memory document against the contract registered for its filename.

        Resolved through contract_for() rather than by indexing ARTIFACT_CONTRACTS, so a canary can
        exercise a dynamically-named artifact (consultation-<role>.json) as well as a fixed one.
        """
        report = Report(f"canary: {name}")
        contract = contract_for(name)
        if contract is None:
            report.error("known_artifact", f"{name} has no registered contract")
            return report
        validate_artifact_data(name, payload, contract[0], report, name)
        return report

    # 1. plan/step two-way consistency, parallel group validity -----------------------------
    drifted_plan = {
        "task_id": "TASK-001",
        "affected_files": ["src/a.ts", "src/b.ts"],
        "steps": [
            {"order": 1, "action": "modify", "file": "src/a.ts", "description": "change a"},
            {"order": 2, "action": "create", "file": "src/c.ts", "description": "add c"},
        ],
        "acceptance_mapping": {"AC-1": "step 1"},
        "parallel_groups": [{"group": "g1", "steps": [9]}],
    }
    report = Report("canary")
    check_plan(drifted_plan, report)
    checks = {p.check for p in report.problems}
    canary(
        "plan drift, step/affected mismatch, and an invalid parallel group are all detected",
        {"file_has_step", "step_in_affected", "parallel_group_steps"} <= checks,
        f"got {sorted(checks)}",
    )

    # 2. a consistent plan passes -----------------------------------------------------------
    good_plan = {
        "task_id": "TASK-001",
        "affected_files": ["src/a.ts"],
        "steps": [{"order": 1, "action": "modify", "file": "src/a.ts", "description": "change a"}],
        "acceptance_mapping": {"AC-1": "step 1"},
    }
    report = Report("canary")
    check_plan(good_plan, report)
    canary("a consistent plan passes with no errors", not report.errors,
           str([p.message for p in report.errors]))

    # 2b. parallel_groups claimed_paths must be disjoint (C2) --------------------------------
    overlap_plan = {
        "task_id": "TASK-001",
        "affected_files": ["src/a.ts", "src/b.ts"],
        "steps": [
            {"order": 1, "action": "modify", "file": "src/a.ts", "description": "change a",
             "parallel_group": "g1"},
            {"order": 2, "action": "modify", "file": "src/b.ts", "description": "change b",
             "parallel_group": "g1"},
        ],
        "acceptance_mapping": {"AC-1": "step 1"},
        "parallel_groups": [
            {
                "group": "g1",
                "steps": [1, 2],
                "streams": [
                    {"step": 1, "claimed_paths": ["src/a.ts", "src/shared.ts"]},
                    {"step": 2, "claimed_paths": ["src/b.ts", "src/shared.ts"]},
                ],
            }
        ],
    }
    report = Report("canary")
    check_plan(overlap_plan, report)
    ok_parallel = {
        "task_id": "TASK-001",
        "affected_files": ["src/a.ts", "src/b.ts"],
        "steps": [
            {"order": 1, "action": "modify", "file": "src/a.ts", "description": "change a"},
            {"order": 2, "action": "modify", "file": "src/b.ts", "description": "change b"},
        ],
        "acceptance_mapping": {"AC-1": "step 1"},
        "parallel_groups": [
            {
                "group": "g1",
                "steps": [1, 2],
                "streams": [
                    {"step": 1, "claimed_paths": ["src/a.ts"]},
                    {"step": 2, "claimed_paths": ["src/b.ts"]},
                ],
            }
        ],
    }
    report_ok = Report("canary")
    check_plan(ok_parallel, report_ok)
    canary(
        "intersecting parallel claimed_paths are rejected; disjoint streams pass",
        any(p.check == "parallel_claimed_paths" for p in report.errors) and not report_ok.errors,
        f"bad={sorted({p.check for p in report.errors})} good={sorted({p.check for p in report_ok.errors})}",
    )

    # 2c. path lease acquire/release against a scratch task (C2) -----------------------------
    tools_dir = Path(__file__).resolve().parent
    if str(tools_dir) not in sys.path:
        sys.path.insert(0, str(tools_dir))
    import parallel_worktree as pwt  # noqa: WPS433

    lock_scratch = REPO_ROOT / ".agent" / ".selftest-parallel" / "TASK-910"
    lock_scratch.mkdir(parents=True, exist_ok=True)
    (lock_scratch / "plan.json").write_text(
        json.dumps(ok_parallel) + "\n",
        encoding="utf-8",
    )
    # Point the tool at this scratch without polluting real tasks/ — use --task-dir.
    acquired = pwt.acquire_paths("TASK-910", 1, ["src/a.ts"], ttl_hours=1, task_dir=lock_scratch)
    conflict = None
    try:
        pwt.acquire_paths("TASK-911", 1, ["src/a.ts"], ttl_hours=1, task_dir=lock_scratch)
    except SystemExit as exc:
        conflict = str(exc)
    released = pwt.release_paths("TASK-910", 1, task_dir=lock_scratch)
    canary(
        "path lease blocks a second holder on the same path, then releases cleanly",
        bool(acquired.get("paths")) and conflict is not None and "already leased" in conflict and released >= 1,
        f"acquired={acquired} conflict={conflict!r} released={released}",
    )
    for stale in sorted(lock_scratch.rglob("*"), reverse=True):
        try:
            if stale.is_file():
                stale.unlink()
            else:
                stale.rmdir()
        except OSError:
            pass

    # 3. an irreversible or high-risk step must carry a rollback ----------------------------
    report = Report("canary")
    check_plan(
        {
            "task_id": "TASK-001",
            "affected_files": ["src/a.ts"],
            "steps": [{"order": 1, "action": "modify", "file": "src/a.ts",
                       "description": "drop a column", "risk_level": "high", "reversible": False}],
            "acceptance_mapping": {"AC-1": "step 1"},
        },
        report,
    )
    canary(
        "a high-risk irreversible step without a rollback procedure is an error",
        {"high_risk_rollback", "irreversible_rollback"} <= {p.check for p in report.errors},
    )

    # 4. verdict_consistent: review PASS carrying blockers ----------------------------------
    report = artifact("review-report.json", {
        "task_id": "TASK-001", "verdict": "PASS",
        "blockers": [{"file": "src/a.ts", "line": 3, "description": "token leak", "fix": "redact"}],
        "concerns": [], "nits": [],
    })
    canary("a review PASS carrying blockers is rejected",
           any(p.check == "verdict_consistent" for p in report.errors))

    # 5. review PASS carrying concerns is rejected -------------------------------------------
    scratch = REPO_ROOT / ".agent" / ".selftest-scratch" / "TASK-EMPTY"
    scratch.mkdir(parents=True, exist_ok=True)
    for stale in scratch.glob("*.json"):
        stale.unlink()
    (scratch / "review-report.json").write_text(json.dumps({
        "task_id": "TASK-001", "verdict": "PASS", "blockers": [],
        "concerns": [{"file": "src/a.ts", "description": "accidental coupling", "fix": "invert the dependency"}],
        "nits": [],
    }), encoding="utf-8")
    report = Report("canary")
    stage_review(scratch, report)
    canary("a review PASS carrying concerns is rejected — only nits may remain",
           any(p.check == "verdict_consistent" for p in report.errors))

    # 6. security PASS hiding an open critical finding ---------------------------------------
    report = artifact("security-report.json", {
        "task_id": "TASK-001", "verdict": "PASS",
        "findings": [{
            "id": "SEC-1", "severity": "critical", "title": "broken object-level authorization",
            "description": "user A can read user B's invoice",
            "attack_scenario": "change the invoice id in the request",
            "remediation": "authorize the resource server-side",
        }],
    })
    canary("a security PASS hiding an open critical finding is rejected",
           any(p.check == "verdict_consistent" for p in report.errors))

    # 7. a gate with no artifact is not a passed gate ----------------------------------------
    (scratch / "intake.json").write_text(json.dumps({
        "task_id": "TASK-001", "type": "feature", "complexity": "standard", "risk": "high",
        "layers": ["backend"], "workflow": "feature",
        "activated_specialists": ["security"], "skipped_specialists": [],
    }), encoding="utf-8")
    report = Report("canary")
    stage_completion(scratch, report)
    canary("a gate with no artifact is reported as not run, never inferred as passed",
           any(p.check == "gate_not_run" for p in report.errors))

    # 8. an unmapped acceptance criterion is an error ----------------------------------------
    requirements = {
        "task_id": "TASK-001", "goal": "let an organization admin invite a teammate",
        "actors": [{"name": "org admin", "description": "manages the organization"}],
        "user_stories": [{"id": "US-1", "story": "As an org admin I want to invite a teammate"}],
        "acceptance_criteria": [
            {"id": "AC-1", "text": "an invitation can be sent"},
            {"id": "AC-2", "text": "an invitation expires after 7 days"},
        ],
        "out_of_scope": ["bulk invitations"],
    }
    report = Report("canary")
    check_plan_covers_requirements(good_plan, requirements, report)
    canary("an acceptance criterion with no plan mapping is an error",
           any(p.check == "acceptance_unmapped" and "AC-2" in p.message for p in report.errors))

    # 9. unresolved product questions block the workflow -------------------------------------
    #
    #    Deliberately NOT canaried here against check_requirements() in memory. A canary that calls
    #    the checker proved only that the checker worked, while nothing called it: open_questions
    #    went unreported for as long as the function was unreachable, and `--artifact
    #    requirements.json` returned PASS on a file carrying four unanswered product decisions.
    #    The wiring is canaried below, through stage_plan, where removing the call site is visible.

    # 10. QA must issue a verdict for every criterion -----------------------------------------
    report = Report("canary")
    check_qa_covers_requirements(
        {"task_id": "TASK-001", "verdict": "FAIL",
         "criteria": [{"criterion_id": "AC-1", "verdict": "PASS", "evidence": "ran the invite flow"}],
         "findings": [], "tests": {"commands_run": [{"command": "pytest", "result": "pass"}]}},
        requirements, report)
    canary("an acceptance criterion with no QA verdict is an error",
           any(p.check == "qa_criteria_incomplete" and "AC-2" in p.message for p in report.errors))

    # 11. an artifact with no contract is rejected ---------------------------------------------
    report = Report("canary")
    problems_before = len(report.problems)
    report2 = Report("canary")
    report2.error("known_artifact", "lint-result.json is not a registered artifact")
    probe = Report("canary")
    contract_probe = contract_for("lint-result.json")
    canary("an artifact name with no registered contract has no contract (the reference repo's blind spot)",
           contract_probe is None and problems_before == 0)

    # 11b. an existing but unregistered artifact must be *reported*, not raised ------------------
    #      This drives check_artifact() against a real file on disk. The canary above only proves
    #      the lookup returns None, so it cannot catch a defect inside the reporting path itself —
    #      which is exactly how an undefined `where` in check_artifact() survived every canary and
    #      surfaced only when a caller passed an artifact whose name is not in ARTIFACT_CONTRACTS.
    unregistered = scratch / "lint-result.json"
    unregistered.write_text("{}", encoding="utf-8")
    report = Report("canary")
    raised: Exception | None = None
    try:
        check_artifact(unregistered, report)
    except Exception as exc:  # noqa: BLE001 - the point of the canary is that nothing escapes
        raised = exc
    canary("an existing but unregistered artifact is reported as an error, not raised",
           raised is None and any(p.check == "known_artifact" for p in report.errors),
           f"raised {raised!r}" if raised is not None else "no known_artifact error was produced")

    # 11c. a design-time consultation the plan claims must exist on disk ------------------------
    #      Drives stage_plan(), not check_design_time_consultation() directly, and that distinction
    #      is the whole point. A canary that calls the checker proves the checker works; it cannot
    #      prove the checker is wired to a stage, which is exactly how check_requirements() sat
    #      unreachable and reported nothing while requirements.json carried unanswered product
    #      questions. Going through stage_plan means removing the call site fails this canary.
    for stale in scratch.glob("*.json"):
        stale.unlink()
    (scratch / "requirements.json").write_text(json.dumps({
        "task_id": "TASK-001",
        "acceptance_criteria": [{"id": "AC-1", "text": "the criterion this canary maps"}],
        "open_questions": [],
    }), encoding="utf-8")
    (scratch / "plan.json").write_text(json.dumps({
        "task_id": "TASK-001",
        "affected_files": ["app/a.py"],
        "steps": [{"order": 1, "action": "create", "file": "app/a.py", "description": "add it"}],
        "acceptance_mapping": {"AC-1": "step 1"},
        "specialists_required": [
            {"specialist": "security", "reason": "untrusted input", "design_time_consultation": True},
        ],
    }), encoding="utf-8")

    report = Report("canary")
    stage_plan(scratch, report)
    missing_consultation_reported = any(p.check == "consultation_recorded" for p in report.errors)

    (scratch / "consultation-security.json").write_text(json.dumps({
        "task_id": "TASK-001", "role": "security", "phase": "design", "verdict": "PASS",
        "artifacts_reviewed": ["design.json"], "binding_constraints": [],
    }), encoding="utf-8")
    report = Report("canary")
    stage_plan(scratch, report)
    accepted_when_present = not any(p.check.startswith("consultation_") for p in report.problems)

    canary("stage_plan rejects a claimed design-time consultation with no artifact, and accepts "
           "one written by the specialist",
           missing_consultation_reported and accepted_when_present,
           f"missing={missing_consultation_reported} present={accepted_when_present}")

    # 11d. a design consultation may not be a post-implementation gate report in disguise --------
    bad_phase = artifact("consultation-security.json", {
        "task_id": "TASK-001", "role": "security", "phase": "implementation",
        "verdict": "PASS", "artifacts_reviewed": ["design.json"], "binding_constraints": [],
    })
    canary("a consultation whose phase is not 'design' is rejected by its schema",
           bool(bad_phase.errors) and all(p.check in ("enum", "const") for p in bad_phase.errors),
           f"got {sorted({p.check for p in bad_phase.errors})}")

    # 11e. unresolved product questions must block the workflow, through the stage ---------------
    #      Same shape as 11c and for the same reason. check_requirements() existed and was correct
    #      and was called by nothing, so a requirements.json with four open product decisions
    #      validated as PASS. Driving stage_plan is what makes the wiring itself testable.
    (scratch / "requirements.json").write_text(json.dumps({
        "task_id": "TASK-001",
        "acceptance_criteria": [{"id": "AC-1", "text": "a criterion that is answered"}],
        "open_questions": [{"question": "do shares expire in 24 hours or 30 days?"}],
    }), encoding="utf-8")
    (scratch / "plan.json").write_text(json.dumps({
        "task_id": "TASK-001",
        "affected_files": ["app/a.py"],
        "steps": [{"order": 1, "action": "create", "file": "app/a.py", "description": "add it"}],
        "acceptance_mapping": {"AC-1": "step 1"},
        "specialists_required": [],
    }), encoding="utf-8")
    report = Report("canary")
    stage_plan(scratch, report)
    canary("stage_plan reports an unresolved product question instead of letting it through",
           any(p.check == "open_questions" for p in report.errors),
           f"got {sorted({p.check for p in report.problems})}")

    for stale in scratch.glob("*.json"):
        stale.unlink()

    # 12. blocked status and not_run results must carry a reason --------------------------------
    report = artifact("worker-result.json", {
        "task_id": "TASK-001", "status": "blocked", "files_changed": [],
        "tests_run": [{"command": "npm test", "result": "not_run"}],
        "acceptance_addressed": [{"criterion_id": "AC-1", "how": "n/a"}],
        "unresolved_concerns": [], "blockers": [],
    })
    canary("blocked status and not_run results both require a stated reason",
           {"blocked_has_reason", "not_run_reason"} <= {p.check for p in report.errors})

    # 12b. the environment must be confirmed before verification runs ----------------------------
    #      A build or test failure caused by the wrong runtime is indistinguishable from a code
    #      defect, so an unconfirmed environment produces false findings and a wasted rework cycle.
    base_worker = {
        "task_id": "TASK-001", "status": "completed", "files_changed": ["src/a.ts"],
        "tests_run": [{"command": "npm test", "result": "pass"}],
        "acceptance_addressed": [{"criterion_id": "AC-1", "how": "implemented"}],
        "unresolved_concerns": [],
    }
    no_env = artifact("worker-result.json", dict(base_worker))
    unconfirmed = artifact("worker-result.json", dict(
        base_worker, environment={"confirmed_by_user": False, "runtime": "Node 20"}))
    confirmed = artifact("worker-result.json", dict(
        base_worker, environment={"confirmed_by_user": True, "runtime": "Node 20",
                                  "commands_confirmed": ["npm test"]}))
    canary(
        "an implementation report without a human-confirmed environment is rejected",
        any(p.check == "environment_unconfirmed" for p in no_env.errors)
        and any(p.check == "environment_unconfirmed" for p in unconfirmed.errors)
        and not confirmed.errors,
        f"no_env={sorted({p.check for p in no_env.errors})} "
        f"unconfirmed={sorted({p.check for p in unconfirmed.errors})} "
        f"confirmed={sorted({p.check for p in confirmed.errors})}",
    )

    # 13. a specialist role must match its artifact ----------------------------------------------
    report = artifact("ux-report.json",
                      {"task_id": "TASK-001", "role": "database", "verdict": "FAIL", "findings": []})
    canary("a specialist report whose role does not match its filename is rejected",
           any(p.check == "role_writer_match" for p in report.errors))

    # 14. a SKIP verdict must be justified ---------------------------------------------------------
    report = artifact("perf-report.json",
                      {"task_id": "TASK-001", "role": "performance", "verdict": "SKIP", "findings": []})
    canary("a SKIP verdict without a reason is rejected",
           any(p.check == "skip_justified" for p in report.errors))

    # 15. a valid review report passes cleanly -----------------------------------------------------
    report = artifact("review-report.json", {
        "task_id": "TASK-001", "verdict": "PASS", "blockers": [], "concerns": [],
        "nits": [{"file": "src/a.ts", "line": 12, "description": "naming", "fix": "rename to inviteMember"}],
    })
    canary("a review PASS with only nits is accepted", not report.errors,
           str([p.message for p in report.errors]))

    # 16. trivial work does not require the review gate -----------------------------------------------
    trivial = required_gates({"complexity": "trivial", "risk": "low", "activated_specialists": []})
    standard = required_gates({"complexity": "standard", "risk": "low", "activated_specialists": []})
    high = required_gates({"complexity": "standard", "risk": "high",
                           "activated_specialists": ["security", "database"]})
    canary("the required gates follow the classification: trivial skips review, high risk adds security",
           trivial == ["qa"] and standard == ["qa", "review"]
           and high == ["qa", "security", "database", "review"],
           f"trivial={trivial} standard={standard} high={high}")

    # 17. no role may be readonly while being a required artifact writer -------------------------------
    #     Regression test for a real defect: product, tech-lead and reviewer were declared
    #     readonly: true while being the sole writers of their artifacts. Cursor removes write tools
    #     entirely for readonly subagents, so each was dispatched and then failed on its first write.
    #     This exact shape is now a configuration-time error (check_setup -> readonly_cannot_write_artifact),
    #     and canary 18 exercises check_setup against the real repository, so reintroducing it fails here.
    conflicts = []
    for path in sorted((REPO_ROOT / ".cursor" / "agents").rglob("*.md")):
        fields, _body = read_frontmatter(path.read_text(encoding="utf-8"))
        if fields.get("readonly") is True and ARTIFACT_WRITERS.get(fields.get("name", "")):
            conflicts.append((fields.get("name"), ARTIFACT_WRITERS[fields["name"]]))
    canary("no role is readonly while being required to write an artifact", not conflicts,
           f"conflicts: {conflicts}")

    # 18. the YAML reader and the duplicate-detection vocabulary actually load -------------------------
    #     Regression test for a real defect: the first implementation of the section reader returned
    #     the `team:` block when asked for `duplicate_detection`, so the stopword list silently loaded
    #     as zero entries and every common English word counted towards similarity. A configuration
    #     reader that silently returns the wrong section is worse than one that fails loudly.
    try:
        parsed_config = parse_yaml((REPO_ROOT / ".agent" / "config.yaml").read_text(encoding="utf-8"))
    except OSError:
        parsed_config = {}
    dedupe = parsed_config.get("duplicate_detection") if isinstance(parsed_config, dict) else None
    dedupe = dedupe if isinstance(dedupe, dict) else {}
    stopword_list = dedupe.get("stopwords")
    alias_map = dedupe.get("aliases")
    threshold_map = dedupe.get("thresholds")
    canary(
        "config.yaml parses: duplicate_detection thresholds, stopwords and aliases all load",
        bool(parsed_config) and isinstance(dedupe, dict)
        and isinstance(threshold_map, dict) and isinstance(threshold_map.get("likely"), (int, float))
        and isinstance(stopword_list, list) and len(stopword_list) >= 30
        and isinstance(alias_map, dict) and len(alias_map) >= 10,
        f"thresholds={threshold_map} stopwords={len(stopword_list) if isinstance(stopword_list, list) else stopword_list} "
        f"aliases={len(alias_map) if isinstance(alias_map, dict) else alias_map}",
    )

    dedupe_settings = load_duplicate_detection_config()
    canary(
        "stopwords are actually applied, and cross-language aliases fold onto one token",
        "the" not in tokenize("the colleague is able to invite", dedupe_settings)
        and {"invite"} <= tokenize("邀请", dedupe_settings)
        and tokenize("邀请", dedupe_settings) == tokenize("invite", dedupe_settings),
        f"cjk->{sorted(tokenize('邀请', dedupe_settings))} en->{sorted(tokenize('invite', dedupe_settings))}",
    )

    # 19. the duplicate detector separates a real duplicate from an unrelated task ----------------------
    #     The measured band in this repository: an identical request scores 1.00 on the narrow
    #     comparison, the same feature described differently scores 0.27-0.37 on the broad one, and an
    #     unrelated task scores 0.01 or below. Thresholds sit inside that gap.
    identical_score, _ = text_similarity(
        "用户应该能邀请同事加入组织", "用户应该能邀请同事加入组织", dedupe_settings)
    same_feature_score, _ = text_similarity(
        "let organization admins invite teammates by email, invitations expire after 7 days",
        "用户应该能邀请同事加入组织并接受邀请加入组织成为普通成员",
        dedupe_settings,
    )
    unrelated_score, _ = text_similarity(
        "the empty project list says no projects which is confusing, make it tell people what to do",
        "用户应该能邀请同事加入组织",
        dedupe_settings,
    )
    canary(
        "similarity separates an identical request from an unrelated one by a wide margin",
        identical_score >= dedupe_settings["likely"]
        and unrelated_score < dedupe_settings["possible"]
        and identical_score >= unrelated_score + 0.5,
        f"identical={identical_score:.3f} same_feature={same_feature_score:.3f} unrelated={unrelated_score:.3f} "
        f"likely={dedupe_settings['likely']} possible={dedupe_settings['possible']}",
    )

    # 20. a request overlapping an active task must be adjudicated -------------------------------------
    #     The failure this whole mechanism exists for: TASK-003 and TASK-004 were created from the same
    #     words and nothing detected it. Exercise stage_duplicate_check against a real pair of task
    #     directories with and without a recorded adjudication.
    duplicate_scratch = REPO_ROOT / ".agent" / ".selftest-dup"
    if duplicate_scratch.exists():
        for stale in sorted(duplicate_scratch.rglob("*"), reverse=True):
            stale.unlink() if stale.is_file() else stale.rmdir()
    home = duplicate_scratch / "tasks" / "active"
    (home / "TASK-900").mkdir(parents=True, exist_ok=True)
    (home / "TASK-901").mkdir(parents=True, exist_ok=True)
    shared_request = "用户应该能邀请同事加入组织"
    for task_id in ("TASK-900", "TASK-901"):
        (home / task_id / "intake.json").write_text(json.dumps({
            "task_id": task_id, "title": shared_request, "request": shared_request,
            "type": "feature", "complexity": "standard", "risk": "low",
            "layers": ["backend"], "workflow": "feature",
            "activated_specialists": [], "skipped_specialists": [],
        }, ensure_ascii=False), encoding="utf-8")

    original_root = globals()["REPO_ROOT"]
    try:
        globals()["REPO_ROOT"] = duplicate_scratch
        silent = Report("canary")
        stage_duplicate_check(home / "TASK-900", silent)
        canary(
            "an unrecorded overlap with another active task is an error",
            any(p.check == "overlap_check_missing" for p in silent.errors),
            f"checks={sorted({p.check for p in silent.errors})}",
        )

        # Now record the overlap but let the orchestrator adjudicate it instead of the human.
        (home / "TASK-900" / "intake.json").write_text(json.dumps({
            "task_id": "TASK-900", "title": shared_request, "request": shared_request,
            "type": "feature", "complexity": "standard", "risk": "low",
            "layers": ["backend"], "workflow": "feature",
            "activated_specialists": [], "skipped_specialists": [],
            "overlap_check": {
                "checked_against": ["TASK-901"], "method": "token_overlap", "highest_score": 1.0,
                "matches": [{"task_id": "TASK-901", "score": 1.0, "level": "likely",
                             "method": "request_narrow", "narrow_score": 1.0, "broad_score": 1.0,
                             "location": "active", "relationship": "same_request"}],
                "decision": {"outcome": "new", "decided_by": "orchestrator",
                             "rationale": "proceeding anyway"},
            },
        }, ensure_ascii=False), encoding="utf-8")
        self_decided = Report("canary")
        stage_duplicate_check(home / "TASK-900", self_decided)
        canary(
            "a likely overlap decided by the orchestrator instead of the human is an error",
            any(p.check == "overlap_needs_human" for p in self_decided.errors),
            f"checks={sorted({p.check for p in self_decided.errors})}",
        )

        # Finally, a human adjudication that supersedes a task still sitting in active/.
        (home / "TASK-900" / "intake.json").write_text(json.dumps({
            "task_id": "TASK-900", "title": shared_request, "request": shared_request,
            "type": "feature", "complexity": "standard", "risk": "low",
            "layers": ["backend"], "workflow": "feature",
            "activated_specialists": [], "skipped_specialists": [],
            "overlap_check": {
                "checked_against": ["TASK-901"], "method": "token_overlap", "highest_score": 1.0,
                "matches": [{"task_id": "TASK-901", "score": 1.0, "level": "likely",
                             "method": "request_narrow", "narrow_score": 1.0, "broad_score": 1.0,
                             "location": "active", "relationship": "same_request"}],
                "decision": {"outcome": "supersede", "decided_by": "human",
                             "superseded_task_id": "TASK-901",
                             "rationale": "the same request, created twice"},
            },
        }, ensure_ascii=False), encoding="utf-8")
        unarchived = Report("canary")
        stage_duplicate_check(home / "TASK-900", unarchived)
        canary(
            "superseding a task that is still active is an error",
            any(p.check == "supersede_not_archived" for p in unarchived.errors),
            f"checks={sorted({p.check for p in unarchived.errors})}",
        )
    finally:
        globals()["REPO_ROOT"] = original_root
        for stale in sorted(duplicate_scratch.rglob("*"), reverse=True):
            if stale.is_file():
                stale.unlink()
            else:
                try:
                    stale.rmdir()
                except OSError:
                    pass
        try:
            duplicate_scratch.rmdir()
        except OSError:
            pass

    # cleanup
    try:
        for stale in scratch.glob("*.json"):
            stale.unlink()
        scratch.rmdir()
        scratch.parent.rmdir()
    except OSError:
        pass

    # 21. the framework must stay project-agnostic and cwd-independent -----------------------------
    #     Two properties that are easy to lose and expensive to notice:
    #       * relative paths resolve against the project root, not the working directory, so the
    #         tool behaves identically from a subdirectory, an editor task, or a CI step;
    #       * no framework file carries a machine-specific absolute path, because the framework is
    #         meant to be copied into any repository on any machine.
    resolved = resolve_artifact_path("tasks/completed/TASK-002/qa-report.json")
    cwd_independent = resolved.is_absolute() and REPO_ROOT in resolved.parents
    canary(
        "a relative artifact path resolves against the project root, not the working directory",
        cwd_independent,
        f"resolved to {resolved}",
    )

    portability_scratch = REPO_ROOT / ".agent" / ".selftest-portability"
    portability_scratch.mkdir(parents=True, exist_ok=True)
    (portability_scratch / "intake.json").write_text(
        json.dumps({"task_id": "TASK-901"}, ensure_ascii=False), encoding="utf-8")

    original_root = globals()["REPO_ROOT"]
    try:
        globals()["REPO_ROOT"] = portability_scratch
        from_anywhere = resolve_artifact_path("intake.json")
        expected = (portability_scratch / "intake.json").resolve()
        # The resolved path is anchored to the project root and contains no element of the working
        # directory, which is what makes the tool behave identically from any invocation point.
        # Asserting that relationship is enough; changing directory would only be needed to prove
        # an implementation that consults the working directory, which this one must not have.
        cwd_elements = set(Path.cwd().parts)
        independent = from_anywhere == expected and not (set(from_anywhere.parts) - set(expected.parts))
        canary(
            "path resolution is anchored to the project root, not the working directory",
            independent,
            f"resolved {from_anywhere} with {len(cwd_elements)} cwd elements irrelevant",
        )
    finally:
        globals()["REPO_ROOT"] = original_root

    # The portability scan, run over a scratch tree so it is a real assertion rather than a
    # reliance on the repository currently being clean. Framework surfaces only: plant under
    # `.agent/`; run records under `tasks/` must not be scanned.
    (portability_scratch / ".agent").mkdir(parents=True, exist_ok=True)
    planted = portability_scratch / ".agent" / "config.yaml"
    planted.write_text("root: " + chr(34) + "H:" + chr(92) * 2 + "work" + chr(92) * 2
                       + "project" + chr(92) * 2 + "src" + chr(34) + "\n", encoding="utf-8")
    original_root = globals()["REPO_ROOT"]
    scan_report = Report("canary")
    try:
        globals()["REPO_ROOT"] = portability_scratch
        check_portability(scan_report)
    finally:
        globals()["REPO_ROOT"] = original_root
    canary("a machine-specific absolute path in a framework file is an error",
           any(p.check == "machine_specific_path" for p in scan_report.errors),
           f"checks={sorted({p.check for p in scan_report.errors})}")

    # Run records under tasks/ may name the machine; that is their job. A path there must not
    # trip the framework portability rule.
    for stale in sorted(portability_scratch.rglob("*"), reverse=True):
        if stale.is_file():
            stale.unlink()
    task_record = portability_scratch / "tasks" / "active" / "TASK-001"
    task_record.mkdir(parents=True, exist_ok=True)
    (task_record / "worker-result.json").write_text(
        "{\n"
        '  "command": "E:' + chr(92) * 2 + 'Conda' + chr(92) * 2 + 'envs' + chr(92) * 2
        + 'vi' + chr(92) * 2 + 'python.exe -m pytest -q",\n'
        '  "note": "run from E:' + chr(92) * 2 + 'Conda' + chr(92) * 2 + 'envs"\n'
        "}\n",
        encoding="utf-8",
    )
    # Also plant a framework file that is clean, so the scan still has something to walk.
    (portability_scratch / ".agent").mkdir(parents=True, exist_ok=True)
    (portability_scratch / ".agent" / "config.yaml").write_text("version: 1\n", encoding="utf-8")
    scan_report = Report("canary")
    try:
        globals()["REPO_ROOT"] = portability_scratch
        check_portability(scan_report)
    finally:
        globals()["REPO_ROOT"] = original_root
    flagged = [p for p in scan_report.errors if p.check == "machine_specific_path"]
    canary("a machine path under tasks/ is not a portability error",
           len(flagged) == 0,
           f"flagged={[p.message.split('Offending text: ')[-1] for p in flagged]}")

    for stale in sorted(portability_scratch.rglob("*"), reverse=True):
        if stale.is_file():
            stale.unlink()
        else:
            try:
                stale.rmdir()
            except OSError:
                pass
    try:
        portability_scratch.rmdir()
    except OSError:
        pass

    # 22. a plan written for a different codebase must be caught before implementation -----------------
    #     Regression test for a real incident: TASK-004's plan assumed an existing organization
    #     service, and every `modify` step pointed at files that do not exist in this repository.
    #     The developer agent noticed by reasoning and correctly refused to manufacture the missing
    #     surface, but nothing in the validator caught it. It does now.
    repo_scratch = REPO_ROOT / ".agent" / ".selftest-repo-check"
    (repo_scratch / "src").mkdir(parents=True, exist_ok=True)
    (repo_scratch / "src" / "existing.ts").write_text("// present\n", encoding="utf-8")
    original_root = globals()["REPO_ROOT"]
    try:
        globals()["REPO_ROOT"] = repo_scratch
        mismatch_plan = {
            "task_id": "TASK-001",
            "affected_files": ["src/existing.ts", "src/absent.ts"],
            "steps": [
                {"order": 1, "action": "modify", "file": "src/existing.ts", "description": "extend it"},
                {"order": 2, "action": "modify", "file": "src/absent.ts", "description": "extend a file that is not here"},
            ],
            "acceptance_mapping": {"AC-1": "step 1"},
        }
        mismatch_report = Report("canary")
        check_plan_against_repository(mismatch_plan, mismatch_report)

        # A file created by an earlier step is legitimately absent until that step runs.
        staged_plan = {
            "task_id": "TASK-001",
            "affected_files": ["src/new.ts"],
            "steps": [
                {"order": 1, "action": "create", "file": "src/new.ts", "description": "add it"},
                {"order": 2, "action": "modify", "file": "src/new.ts", "description": "then extend it"},
            ],
            "acceptance_mapping": {"AC-1": "step 1"},
        }
        staged_report = Report("canary")
        check_plan_against_repository(staged_plan, staged_report)
    finally:
        globals()["REPO_ROOT"] = original_root
    canary(
        "a plan step targeting a file that does not exist is an error, but a file created by an "
        "earlier step is not",
        any(p.check == "step_target_missing" and "src/absent.ts" in p.message for p in mismatch_report.errors)
        and not staged_report.errors,
        f"mismatch={sorted({p.check for p in mismatch_report.errors})} "
        f"staged={sorted({p.check for p in staged_report.errors})}",
    )

    for stale in sorted(repo_scratch.rglob("*"), reverse=True):
        if stale.is_file():
            stale.unlink()
        else:
            try:
                stale.rmdir()
            except OSError:
                pass
    try:
        repo_scratch.rmdir()
    except OSError:
        pass

    # 23. trivial classification requires human confirmation (C3) ---------------------------------
    report = Report("canary")
    check_trivial_classification_gate({"complexity": "trivial"}, report)
    report_ok = Report("canary")
    check_trivial_classification_gate(
        {"complexity": "trivial", "classification_confirmation": {"decided_by": "human"}},
        report_ok,
    )
    canary(
        "trivial without human confirmation is rejected; with decided_by human it passes",
        any(p.check == "trivial_needs_human" for p in report.errors) and not report_ok.errors,
        f"bad={[p.check for p in report.errors]} good={[p.check for p in report_ok.errors]}",
    )

    # 23b. model_assignments triangle (C1) ---------------------------------------------------------
    catalog_stub = {
        "models": [
            {"id": "m-a", "ide_slug": "m-a"},
            {"id": "m-b", "ide_slug": "m-b"},
            {"id": "m-c", "ide_slug": "m-c"},
        ]
    }
    missing_assign = Report("canary")
    check_model_assignments(
        {
            "complexity": "standard",
            "activated_specialists": ["security"],
            "blocking_gates": ["qa", "security", "review"],
        },
        missing_assign,
        catalog=catalog_stub,
    )
    same_model = Report("canary")
    check_model_assignments(
        {
            "complexity": "standard",
            "activated_specialists": ["security"],
            "blocking_gates": ["qa", "security", "review"],
            "model_assignments": {
                "qa": {"assigned_model": "m-a"},
                "reviewer": {"assigned_model": "m-a"},
                "security": {"assigned_model": "m-b"},
            },
        },
        same_model,
        catalog=catalog_stub,
    )
    distinct_ok = Report("canary")
    check_model_assignments(
        {
            "complexity": "standard",
            "activated_specialists": ["security"],
            "blocking_gates": ["qa", "security", "review"],
            "model_assignments": {
                "qa": {"assigned_model": "m-a"},
                "reviewer": {"assigned_model": "m-b"},
                "security": {"assigned_model": "m-c"},
                "developer": {"assigned_model": "m-a"},
            },
        },
        distinct_ok,
        catalog=catalog_stub,
    )
    canary(
        "model_assignments required; triangle must be distinct; soft warn when developer overlaps",
        any(p.check == "model_assignments_required" for p in missing_assign.errors)
        and any(p.check == "model_triangle_not_distinct" for p in same_model.errors)
        and not distinct_ok.errors
        and any(p.check == "model_developer_overlaps_triangle" for p in distinct_ok.warnings),
        f"missing={sorted({p.check for p in missing_assign.errors})} "
        f"same={sorted({p.check for p in same_model.errors})} "
        f"ok_err={sorted({p.check for p in distinct_ok.errors})} "
        f"ok_warn={sorted({p.check for p in distinct_ok.warnings})}",
    )

    # 24. QA PASS must cite a validate log; completion needs fresh stage logs (C4) ----------------
    log_scratch = REPO_ROOT / ".agent" / ".selftest-validate-log" / f"TASK-{uuid.uuid4().hex[:8]}"
    log_scratch.mkdir(parents=True, exist_ok=True)
    (log_scratch / "intake.json").write_text('{"task_id":"TASK-900"}\n', encoding="utf-8")
    qa_body = {
        "task_id": "TASK-900",
        "verdict": "PASS",
        "criteria": [{"criterion_id": "AC-1", "verdict": "PASS", "evidence": "ran it"}],
        "findings": [],
        "tests": {"commands_run": [{"command": "true", "result": "pass"}]},
    }
    (log_scratch / "qa-report.json").write_text(json.dumps(qa_body) + "\n", encoding="utf-8")
    report = Report("canary")
    check_validate_log_citations(qa_body, log_scratch, report)
    canary(
        "a QA PASS without validate_log_ids is rejected",
        any(p.check == "qa_missing_validate_log" for p in report.errors),
        f"checks={sorted({p.check for p in report.errors})}",
    )
    # Cite an earlier-stage log (duplicate_check), then update qa-report — qa-report hash is ignored.
    dup_log = write_validate_log(log_scratch, "duplicate_check", Report("canary"))
    assert dup_log is not None
    dup_uuid = load_json(dup_log)["uuid"]
    qa_body["validate_log_ids"] = [dup_uuid]
    (log_scratch / "qa-report.json").write_text(json.dumps(qa_body) + "\n", encoding="utf-8")
    report = Report("canary")
    check_validate_log_citations(qa_body, log_scratch, report)
    canary(
        "a QA PASS that cites a fresh earlier-stage validate log is accepted",
        not report.errors,
        "; ".join(p.message for p in report.errors[:3]),
    )
    missing = Report("canary")
    check_validate_logs_for_completion(log_scratch, ["duplicate_check", "qa", "completion"], missing)
    canary(
        "completion without a fresh qa-stage validate log is rejected",
        any(p.check == "validate_log_missing" for p in missing.errors),
        f"checks={sorted({p.check for p in missing.errors})}",
    )
    write_validate_log(log_scratch, "qa", Report("canary"))
    ok_completion = Report("canary")
    check_validate_logs_for_completion(log_scratch, ["duplicate_check", "qa", "completion"], ok_completion)
    canary(
        "completion with fresh duplicate_check and qa logs passes the log gate",
        not any(p.check == "validate_log_missing" for p in ok_completion.errors),
        "; ".join(p.message for p in ok_completion.errors[:3]),
    )
    # Best-effort cleanup; leave leftovers if the OS locks a file.
    for stale in sorted(log_scratch.rglob("*"), reverse=True):
        try:
            if stale.is_file():
                stale.chmod(stat.S_IWRITE | stat.S_IREAD)
                stale.unlink()
            else:
                stale.rmdir()
        except OSError:
            pass

    # 24b. ci-changed path → active task id extraction --------------------------------------------
    extracted = active_task_ids_from_paths(
        [
            "tasks/active/TASK-010/intake.json",
            "tasks/active/TASK-010/plan.json",
            "tasks/completed/TASK-002/qa-report.json",
            "tasks/archive/TASK-003/intake.json",
            "README.md",
            "tasks/active/TASK-011/worker-result.json",
        ]
    )
    canary(
        "ci-changed extracts unique active TASK ids and ignores completed/archive",
        extracted == ["TASK-010", "TASK-011"],
        f"got {extracted}",
    )

    # 25. the repository's own setup must be self-consistent ----------------------------------------
    report = Report("canary")
    check_setup(report)
    canary(f"repository setup is self-consistent ({len(report.warnings)} warning(s))",
           not report.errors, "; ".join(p.message for p in report.errors[:4]))

    print()
    if failures:
        print(f"SELFTEST: {failures} canary failure(s) - FAIL")
        return 1
    print("SELFTEST: all invariants verified - PASS")
    return 0


# --------------------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------------------


def resolve_task_dir(task_id: str, explicit: str | None) -> Path:
    """Resolve a task directory. Relative paths resolve against the REPO ROOT, not the cwd.

    Resolving against the current working directory would make the tool behave differently
    depending on where it was invoked from — a shell inside a subdirectory, an editor task, or a
    CI step. The root is discovered from this file's own location, so the tool works from
    anywhere without any path configuration.
    """
    if explicit:
        path = Path(explicit)
        return path.resolve() if path.is_absolute() else (REPO_ROOT / path).resolve()
    for base in ("active", "completed", "archive"):
        candidate = REPO_ROOT / "tasks" / base / task_id
        if candidate.is_dir():
            return candidate
    return REPO_ROOT / "tasks" / "active" / task_id


def resolve_artifact_path(raw: str) -> Path:
    """Resolve an artifact path against the repository root when it is relative."""
    path = Path(raw)
    return path.resolve() if path.is_absolute() else (REPO_ROOT / path).resolve()


_ACTIVE_TASK_PATH = re.compile(r"^tasks/active/(TASK-\d+)(?:/|$)")


def active_task_ids_from_paths(paths: list[str]) -> list[str]:
    """Return unique TASK-IDs under tasks/active/ mentioned by the given repo-relative paths."""
    found: list[str] = []
    seen: set[str] = set()
    for raw in paths:
        normalized = raw.replace("\\", "/").lstrip("./")
        match = _ACTIVE_TASK_PATH.match(normalized)
        if not match:
            continue
        task_id = match.group(1)
        if task_id not in seen:
            seen.add(task_id)
            found.append(task_id)
    return found


def git_diff_name_only(base_ref: str) -> tuple[list[str] | None, str | None]:
    """Return paths changed between base_ref and HEAD, or (None, reason) on failure."""
    if not base_ref or re.fullmatch(r"0+", base_ref):
        return None, "base ref is empty or an all-zero SHA (nothing to diff against)"
    result = subprocess.run(
        ["git", "diff", "--name-only", f"{base_ref}...HEAD"],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        result = subprocess.run(
            ["git", "diff", "--name-only", base_ref, "HEAD"],
            cwd=str(REPO_ROOT),
            capture_output=True,
            text=True,
            check=False,
        )
    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "").strip()
        return None, f"git diff failed against {base_ref!r}: {detail}"
    paths = [line.strip() for line in (result.stdout or "").splitlines() if line.strip()]
    return paths, None


def run_ci_changed(base_ref: str) -> int:
    """CI job C: shape-check every active task touched since base_ref (``--all`` per task).

    Does not re-run product tests. Trusts developer/QA reports; only enforces artifact invariants.
    """
    print(f"== ci-changed (base={base_ref})")
    paths, err = git_diff_name_only(base_ref)
    if err:
        print(f"ERROR: {err}", file=sys.stderr)
        return 2
    assert paths is not None
    task_ids = active_task_ids_from_paths(paths)
    if not task_ids:
        print("   no tasks/active/TASK-* paths changed; skip")
        return 0
    print(f"   changed active tasks: {', '.join(task_ids)}")
    exit_code = 0
    for task_id in task_ids:
        task_dir = REPO_ROOT / "tasks" / "active" / task_id
        if not task_dir.is_dir():
            print(
                f"ERROR: changed path names {task_id} but directory missing: {task_dir}",
                file=sys.stderr,
            )
            exit_code = max(exit_code, 1)
            continue
        stages = applicable_stages(task_dir)
        print(f"   applicable stages for {task_id}: {stages}")
        for stage in stages:
            report = Report(f"task {task_id} :: stage {stage}")
            STAGE_CHECKERS[stage](task_dir, report)
            log_path = write_validate_log(task_dir, stage, report)
            if log_path is not None:
                report.note(f"validate log: {log_path.relative_to(REPO_ROOT).as_posix()}")
            exit_code = max(exit_code, report.emit())
    return exit_code


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Rgents artifact validator, gate invariant checker, and setup linter.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--artifact", help="validate a single artifact file against its schema")
    parser.add_argument("--task", help="task ID, e.g. TASK-001")
    parser.add_argument("--task-dir", help="explicit path to a task directory")
    parser.add_argument("--stage", choices=sorted(STAGE_CHECKERS), help="run the invariants for one stage")
    parser.add_argument("--all", action="store_true", help="run every stage check for the task")
    parser.add_argument("--check-setup", action="store_true", help="lint the repository's team configuration")
    parser.add_argument("--selftest", action="store_true", help="prove the invariants fire on known-bad input")
    parser.add_argument(
        "--ci-changed",
        action="store_true",
        help="CI: run --all on each tasks/active/TASK-* touched since --base (shape only; no product tests)",
    )
    parser.add_argument(
        "--base",
        default="origin/main",
        help="git ref for --ci-changed (default: origin/main). Use the PR base or previous push SHA in CI.",
    )
    args = parser.parse_args()

    if args.selftest:
        return run_selftest()

    if args.ci_changed:
        return run_ci_changed(args.base)

    exit_code = 0

    if args.artifact:
        path = resolve_artifact_path(args.artifact)
        if not path.exists():
            print(f"ERROR: artifact not found: {path}", file=sys.stderr)
            return 2
        report = Report(f"artifact {path.name}")
        check_artifact(path, report)
        exit_code = max(exit_code, report.emit())

    if args.check_setup:
        report = Report("setup lint")
        check_setup(report)
        exit_code = max(exit_code, report.emit())

    if args.task or args.task_dir:
        if not (args.task or args.task_dir):
            print("ERROR: --task or --task-dir is required", file=sys.stderr)
            return 2
        task_dir = resolve_task_dir(args.task or "", args.task_dir)
        if not task_dir.is_dir():
            print(f"ERROR: task directory not found: {task_dir}", file=sys.stderr)
            return 2
        stages = applicable_stages(task_dir) if args.all else ([args.stage] if args.stage else ALL_STAGES)
        if args.all:
            print(f"   applicable stages for this task: {stages}")
        for stage in stages:
            report = Report(f"task {task_dir.name} :: stage {stage}")
            STAGE_CHECKERS[stage](task_dir, report)
            log_path = write_validate_log(task_dir, stage, report)
            if log_path is not None:
                report.note(f"validate log: {log_path.relative_to(REPO_ROOT).as_posix()}")
            exit_code = max(exit_code, report.emit())

    if not any([args.artifact, args.check_setup, args.task, args.task_dir, args.all, args.ci_changed]):
        parser.print_help()
        return 0

    return exit_code


if __name__ == "__main__":
    sys.exit(main())
