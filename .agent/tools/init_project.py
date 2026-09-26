#!/usr/bin/env python3
"""Initialize a seeded Rgents project for local work.

Batch A / C7: run ``git init`` when needed. Does **not** add a remote and does **not**
create the first commit (those stay human acts).

Batch C / C1: ``--refresh-models`` writes ``.agent/models/available.yaml``. Prefer the
Cursor Agent CLI account catalog (full IDE-dispatchable set), then the Cursor SDK /
Cloud Agents API (often a narrowed subset), then ``seed.yaml``. Never writes the API
key into the catalog.

Usage
-----
    python .agent/tools/init_project.py
    python .agent/tools/init_project.py --target <path>
    python .agent/tools/init_project.py --ensure-baseline
    python .agent/tools/init_project.py --refresh-models

The script root is discovered from this file's location when --target is omitted, so it
carries no machine-specific path.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import urllib.error
import urllib.request
from datetime import date
from pathlib import Path

TOOLS_DIR = Path(__file__).resolve().parent
FRAMEWORK_OR_PROJECT_ROOT = TOOLS_DIR.parents[1]

CURSOR_MODELS_URL = "https://api.cursor.com/v1/models"
CURSOR_MODELS_URL_V0 = "https://api.cursor.com/v0/models"

# Multiline CLI rows look like: `composer-2.5-fast - Composer 2.5 Fast`
_AGENT_MODEL_LINE_RE = re.compile(
    r"^\s*([A-Za-z0-9][A-Za-z0-9._+/-]*)\s+-\s+(.+?)\s*$"
)
_AGENT_SKIP_IDS = frozenset({"available", "tip", "use", "model"})


def _run_git(args: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        cwd=str(cwd),
        check=False,
        capture_output=True,
        text=True,
    )


def ensure_git_repo(root: Path) -> str:
    git_dir = root / ".git"
    if git_dir.exists():
        return "already_initialized"
    if shutil.which("git") is None:
        raise SystemExit("git not found on PATH; install git, then re-run init_project")
    result = _run_git(["init"], root)
    if result.returncode != 0:
        raise SystemExit(f"git init failed: {result.stderr.strip() or result.stdout.strip()}")
    remotes = _run_git(["remote"], root)
    if remotes.stdout.strip():
        # We never add remotes; if something else did, leave them alone and report.
        return "initialized_with_existing_remotes"
    return "initialized"


def ensure_baseline(root: Path) -> str:
    dest = root / ".agent" / "project-baseline.yaml"
    if dest.is_file():
        return "baseline_present"
    template = root / ".agent" / "templates" / "project-baseline.yaml"
    if not template.is_file():
        raise SystemExit(f"missing template: {template}")
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(template.read_text(encoding="utf-8"), encoding="utf-8")
    return "baseline_copied_from_template"


def _catalog_entry(model_id: str, display_name: str | None = None, notes: str | None = None) -> dict:
    entry = {
        "id": model_id,
        "display_name": display_name or model_id,
        "ide_slug": model_id,
    }
    if notes:
        entry["notes"] = notes
    return entry


def _load_seed_models(root: Path) -> list[dict]:
    seed_path = root / ".agent" / "models" / "seed.yaml"
    if not seed_path.is_file():
        raise SystemExit(f"missing seed catalog: {seed_path}")
    # Local import keeps init usable before validate is on PYTHONPATH.
    sys.path.insert(0, str(TOOLS_DIR))
    from validate import parse_yaml  # noqa: WPS433 — intentional sibling import

    data = parse_yaml(seed_path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise SystemExit(f"seed catalog must be a mapping: {seed_path}")
    models = data.get("models")
    if not isinstance(models, list) or not models:
        raise SystemExit(f"seed catalog has no models list: {seed_path}")
    out: list[dict] = []
    for item in models:
        if not isinstance(item, dict) or not item.get("id"):
            raise SystemExit(f"seed model entry must be an object with id: {item!r}")
        out.append(_catalog_entry(str(item["id"]), item.get("display_name"), item.get("notes")))
    return out


def _merge_catalogs(*groups: list[dict]) -> list[dict]:
    """Union by id, first occurrence wins (prefer earlier, richer sources)."""
    merged: list[dict] = []
    seen: set[str] = set()
    for group in groups:
        for entry in group:
            model_id = str(entry.get("id") or "").strip()
            if not model_id or model_id in seen:
                continue
            seen.add(model_id)
            merged.append(entry)
    return merged


def _ensure_inherit(models: list[dict], root: Path) -> list[dict]:
    """C1 always needs inherit in the catalog for soft assignments / documentation."""
    if any(str(m.get("id")) == "inherit" for m in models):
        return models
    seed_inherit = next((m for m in _load_seed_models(root) if m.get("id") == "inherit"), None)
    if seed_inherit:
        return [seed_inherit, *models]
    return [
        _catalog_entry(
            "inherit",
            "Inherit parent session model",
            "Do not use for qa/reviewer/security assignments; inherit collapses the review triangle.",
        ),
        *models,
    ]


def parse_agent_cli_models_text(text: str) -> list[dict]:
    """Parse ``agent models`` / ``--list-models`` human output into catalog entries."""
    entries: list[dict] = []
    seen: set[str] = set()
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.lower().startswith(("available model", "tip:", "use ")):
            continue
        match = _AGENT_MODEL_LINE_RE.match(line)
        if not match:
            continue
        model_id = match.group(1).strip()
        display = match.group(2).strip()
        # Drop trailing markers like "(default)" from display only; keep id clean.
        display = re.sub(r"\s*\(default\)\s*$", "", display, flags=re.I).strip() or model_id
        if not model_id or model_id.lower() in _AGENT_SKIP_IDS or model_id in seen:
            continue
        seen.add(model_id)
        entries.append(_catalog_entry(model_id, display))
    return entries


def _agent_cli_candidates() -> list[str]:
    """Resolve agent / cursor-agent binaries from PATH and common install locations."""
    names = ("agent", "agent.exe", "cursor-agent", "cursor-agent.exe")
    found: list[str] = []
    seen: set[str] = set()

    def _add(path: str | None) -> None:
        if not path:
            return
        resolved = str(Path(path).resolve()) if Path(path).exists() else path
        key = resolved.lower()
        if key in seen:
            return
        if shutil.which(path) or Path(path).is_file():
            seen.add(key)
            found.append(path if Path(path).is_file() else (shutil.which(path) or path))

    for name in ("agent", "cursor-agent"):
        _add(shutil.which(name))

    cursor_bin = shutil.which("cursor")
    if cursor_bin:
        parent = Path(cursor_bin).resolve().parent
        for name in names:
            _add(str(parent / name))

    home = Path.home()
    local_app = os.environ.get("LOCALAPPDATA", "")
    extra_dirs = [
        home / ".local" / "bin",
        home / ".cursor" / "bin",
        home / "AppData" / "Local" / "cursor-agent",
        Path(local_app) / "cursor-agent" if local_app else None,
        Path(local_app) / "Programs" / "cursor-agent" if local_app else None,
    ]
    for directory in extra_dirs:
        if directory is None or not directory.is_dir():
            continue
        for name in names:
            _add(str(directory / name))

    return found


def _run_agent_models_command(binary: str) -> str | None:
    """Run one CLI listing invocation; return stdout+stderr text on success."""
    invocations = (
        [binary, "models"],
        [binary, "--list-models"],
        [binary, "models", "--output-format", "text"],
    )
    for command in invocations:
        try:
            completed = subprocess.run(
                command,
                capture_output=True,
                text=True,
                timeout=60,
                check=False,
                env={**os.environ, "NO_COLOR": "1", "CI": "1"},
            )
        except (OSError, subprocess.SubprocessError) as exc:
            print(f"models: agent_cli {command!r} failed ({exc})", file=sys.stderr)
            continue
        text = (completed.stdout or "") + ("\n" + completed.stderr if completed.stderr else "")
        if completed.returncode != 0 and not text.strip():
            continue
        if parse_agent_cli_models_text(text):
            return text
        lowered = text.lower()
        if "authentication required" in lowered or "not logged in" in lowered:
            print(
                "models: agent_cli is installed but not logged in; run `agent login`, "
                "then re-run --refresh-models",
                file=sys.stderr,
            )
            return None
    return None


def _fetch_agent_cli_models() -> list[dict] | None:
    """Full account catalog from Cursor Agent CLI (preferred over Cloud Agents API)."""
    binaries = _agent_cli_candidates()
    if not binaries:
        print(
            "models: agent_cli not found on PATH "
            "(install Cursor Agent CLI: https://cursor.com/docs/cli/overview)",
            file=sys.stderr,
        )
        return None
    for binary in binaries:
        text = _run_agent_models_command(binary)
        if not text:
            continue
        entries = parse_agent_cli_models_text(text)
        if entries:
            return entries
    print("models: agent_cli produced no parseable model rows; falling back", file=sys.stderr)
    return None


def _fetch_cursor_sdk_models() -> list[dict] | None:
    """Optional: Cursor Python SDK account catalog when cursor_sdk is installed."""
    try:
        from cursor_sdk import Cursor  # type: ignore[import-not-found]
    except ImportError:
        return None
    try:
        listed = Cursor.models.list()
    except Exception as exc:  # noqa: BLE001 — any SDK/auth failure falls through
        print(f"models: cursor_sdk failed ({exc}); falling back", file=sys.stderr)
        return None

    entries: list[dict] = []
    seen: set[str] = set()
    for item in listed or []:
        model_id = str(getattr(item, "id", None) or "").strip()
        if not model_id or model_id in seen:
            continue
        display = str(getattr(item, "display_name", None) or getattr(item, "name", None) or model_id)
        seen.add(model_id)
        entries.append(_catalog_entry(model_id, display))
        for alias in getattr(item, "aliases", None) or []:
            alias_id = str(alias).strip()
            if alias_id and alias_id not in seen:
                seen.add(alias_id)
                entries.append(_catalog_entry(alias_id, display, notes=f"alias of {model_id}"))
    return entries or None


def _http_get_json(url: str, api_key: str) -> object | None:
    request = urllib.request.Request(
        url,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Accept": "application/json",
            "User-Agent": "rgents-init-project/1",
        },
        method="GET",
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:  # noqa: S310 — fixed HTTPS URL
            return json.loads(response.read().decode("utf-8"))
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, json.JSONDecodeError, OSError) as exc:
        print(f"models: GET {url} failed ({exc})", file=sys.stderr)
        return None


def _entries_from_api_payload(payload: object) -> list[dict]:
    raw_models: list = []
    if isinstance(payload, dict):
        for key in ("data", "models", "items"):
            if isinstance(payload.get(key), list):
                raw_models = payload[key]
                break
    elif isinstance(payload, list):
        raw_models = payload

    entries: list[dict] = []
    seen: set[str] = set()

    def _add(model_id: str, display: str, notes: str | None = None) -> None:
        model_id = model_id.strip()
        if not model_id or model_id in seen:
            return
        seen.add(model_id)
        entries.append(_catalog_entry(model_id, display, notes))

    for item in raw_models:
        if isinstance(item, str):
            _add(item, item)
            continue
        if not isinstance(item, dict):
            continue
        model_id = str(item.get("id") or item.get("slug") or item.get("name") or "").strip()
        display = str(
            item.get("displayName")
            or item.get("display_name")
            or item.get("name")
            or model_id
        )
        if not model_id:
            continue
        _add(model_id, display)
        for alias in item.get("aliases") or []:
            if isinstance(alias, str):
                _add(alias, display, notes=f"alias of {model_id}")
        # Variants share the same id; record display variants as notes only when distinct.
        for variant in item.get("variants") or []:
            if not isinstance(variant, dict):
                continue
            variant_name = str(variant.get("displayName") or variant.get("display_name") or "").strip()
            if variant_name and variant_name != display:
                # Keep the base id once; variants are param presets, not separate Task slugs.
                continue
    return entries


def _fetch_cursor_api_models() -> list[dict] | None:
    """Cloud Agents recommended set — often narrower than the IDE/CLI catalog."""
    api_key = os.environ.get("CURSOR_API_KEY", "").strip()
    if not api_key:
        return None

    combined: list[dict] = []
    for url in (CURSOR_MODELS_URL, CURSOR_MODELS_URL_V0):
        payload = _http_get_json(url, api_key)
        if payload is None:
            continue
        combined = _merge_catalogs(combined, _entries_from_api_payload(payload))
    if not combined:
        print("models: cursor_api returned no models; falling back to seed", file=sys.stderr)
        return None
    return combined


def _write_available_yaml(root: Path, models: list[dict], source: str) -> Path:
    dest = root / ".agent" / "models" / "available.yaml"
    dest.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# Machine-readable model catalog (C1). Written by init --refresh-models.",
        f"# source: {source}. Never store API keys here.",
        "# Orchestrator assigns Task models from ide_slug values that are dispatchable in-session.",
        "",
        "version: 1",
        f"source: {source}",
        f'fetched_at: "{date.today().isoformat()}"',
        "models:",
    ]
    for model in models:
        lines.append(f"  - {json.dumps(model, ensure_ascii=True, sort_keys=True)}")
    lines.append("")
    dest.write_text("\n".join(lines), encoding="utf-8")
    return dest


def refresh_models(root: Path) -> str:
    """Refresh available.yaml: agent_cli → cursor_sdk → cursor_api → seed.

    Cloud Agents ``/v1/models`` is a recommended subset and often omits third-party
    IDE models. The Agent CLI ``models`` / ``--list-models`` listing is the account's
    full dispatchable catalog. API/SDK results are unioned with seed so known IDE
    slugs are not dropped when the CLI is unavailable.
    """
    seed_models = _load_seed_models(root)

    cli_models = _fetch_agent_cli_models()
    if cli_models:
        models = _ensure_inherit(_merge_catalogs(cli_models, seed_models), root)
        path = _write_available_yaml(root, models, "agent_cli")
        return f"wrote {path.as_posix()} from agent_cli ({len(models)} models)"

    sdk_models = _fetch_cursor_sdk_models()
    if sdk_models:
        models = _ensure_inherit(_merge_catalogs(sdk_models, seed_models), root)
        path = _write_available_yaml(root, models, "cursor_sdk+seed")
        return f"wrote {path.as_posix()} from cursor_sdk+seed ({len(models)} models)"

    api_models = _fetch_cursor_api_models()
    if api_models:
        models = _ensure_inherit(_merge_catalogs(api_models, seed_models), root)
        path = _write_available_yaml(root, models, "cursor_api+seed")
        return (
            f"wrote {path.as_posix()} from cursor_api+seed ({len(models)} models; "
            "install/login Agent CLI for the full account catalog)"
        )

    models = _ensure_inherit(seed_models, root)
    path = _write_available_yaml(root, models, "seed")
    return f"wrote {path.as_posix()} from seed ({len(models)} models)"


def _selftest_parser() -> int:
    sample = """
        Available models

        auto - Auto (default)
        composer-2.5-fast - Composer 2.5 Fast
        claude-opus-5-thinking-high - Claude Opus 5 Thinking High
        gpt-5.6-luna-medium - GPT-5.6 Luna Medium
        Tip: use --model <id> to select a model
    """
    parsed = parse_agent_cli_models_text(sample)
    ids = [m["id"] for m in parsed]
    expected = [
        "auto",
        "composer-2.5-fast",
        "claude-opus-5-thinking-high",
        "gpt-5.6-luna-medium",
    ]
    if ids != expected:
        print(f"parser selftest FAIL: got {ids!r}", file=sys.stderr)
        return 1
    if parsed[0]["display_name"] != "Auto":
        print(f"parser selftest FAIL: display={parsed[0]!r}", file=sys.stderr)
        return 1
    print("parser selftest: PASS")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Initialize local git (no remote) for an Rgents project")
    parser.add_argument(
        "--target",
        type=Path,
        default=None,
        help="project root (default: repository containing this script)",
    )
    parser.add_argument(
        "--ensure-baseline",
        action="store_true",
        help="copy .agent/templates/project-baseline.yaml if .agent/project-baseline.yaml is missing",
    )
    parser.add_argument(
        "--refresh-models",
        action="store_true",
        help=(
            "write .agent/models/available.yaml from Agent CLI (preferred), else "
            "cursor_sdk / CURSOR_API_KEY / seed.yaml (never stores the key)"
        ),
    )
    parser.add_argument(
        "--selftest-models-parser",
        action="store_true",
        help="verify Agent CLI model-list text parsing and exit",
    )
    args = parser.parse_args(argv)

    if args.selftest_models_parser:
        return _selftest_parser()

    root = (args.target or FRAMEWORK_OR_PROJECT_ROOT).resolve()
    if not root.is_dir():
        print(f"target is not a directory: {root}", file=sys.stderr)
        return 2

    print(f"target: {root}")
    git_status = ensure_git_repo(root)
    print(f"git:    {git_status}")
    if git_status.startswith("initialized"):
        print("        no remote added; create the first commit yourself when ready")

    if args.ensure_baseline:
        print(f"baseline: {ensure_baseline(root)}")

    if args.refresh_models:
        print(f"models: {refresh_models(root)}")
    elif not (root / ".agent" / "models" / "available.yaml").is_file():
        # First-run convenience: seed the catalog without requiring an explicit flag.
        print(f"models: {refresh_models(root)} (auto — available.yaml was missing)")

    print("done. next: fill .agent/project-baseline.yaml via project-level spec/design when status is template")
    print("      then: python .agent/tools/validate.py --check-setup")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
