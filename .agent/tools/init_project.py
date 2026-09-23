#!/usr/bin/env python3
"""Initialize a seeded Rgents project for local work.

Batch A / C7: run ``git init`` when needed. Does **not** add a remote and does **not**
create the first commit (those stay human acts).

Batch C / C1: ``--refresh-models`` writes ``.agent/models/available.yaml`` from the Cursor
API when ``CURSOR_API_KEY`` is set, otherwise from ``.agent/models/seed.yaml``. Never writes
the API key into the catalog.

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


def _fetch_cursor_api_models() -> list[dict] | None:
    """Return catalog entries from Cursor API, or None if no key / request failed."""
    api_key = os.environ.get("CURSOR_API_KEY", "").strip()
    if not api_key:
        return None
    request = urllib.request.Request(
        CURSOR_MODELS_URL,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Accept": "application/json",
            "User-Agent": "rgents-init-project/1",
        },
        method="GET",
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:  # noqa: S310 — fixed HTTPS URL
            payload = json.loads(response.read().decode("utf-8"))
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, json.JSONDecodeError, OSError) as exc:
        print(f"models: cursor_api failed ({exc}); falling back to seed", file=sys.stderr)
        return None

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
    for item in raw_models:
        if isinstance(item, str):
            model_id = item
            display = item
        elif isinstance(item, dict):
            model_id = str(item.get("id") or item.get("slug") or item.get("name") or "").strip()
            display = str(item.get("display_name") or item.get("name") or model_id)
        else:
            continue
        if not model_id or model_id in seen:
            continue
        seen.add(model_id)
        entries.append(_catalog_entry(model_id, display))
    return entries or None


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
    api_models = _fetch_cursor_api_models()
    if api_models:
        path = _write_available_yaml(root, api_models, "cursor_api")
        return f"wrote {path.as_posix()} from cursor_api ({len(api_models)} models)"
    seed_models = _load_seed_models(root)
    path = _write_available_yaml(root, seed_models, "seed")
    return f"wrote {path.as_posix()} from seed ({len(seed_models)} models)"


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
        help="write .agent/models/available.yaml from CURSOR_API_KEY or seed.yaml (never stores the key)",
    )
    args = parser.parse_args(argv)
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
