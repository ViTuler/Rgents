#!/usr/bin/env python3
"""Archive a task directory from tasks/active/ into completed/ or archive/.

Why this exists
---------------
`/ship` used to say "archive the task" with no tool. Agents typically *copied*
active → completed and then tried to delete active. On Cursor/Windows, deletes
often need human approval; copy succeeds, delete fails, and both trees remain.
``validate.resolve_task_dir`` prefers ``active/``, so residual copies keep looking
"live".

This tool makes archive a single, checkable operation:

1. Prefer atomic rename/replace when the destination does not exist.
2. If both trees already exist, require them to match (or ``--force`` after
   human review), then remove the active copy.
3. Never report success while ``tasks/active/<ID>`` still exists.
4. After a successful archive, rewrite ``tasks/active/<ID>/`` path prefixes inside
   ``task.yaml`` ``artifact_path`` fields to ``tasks/<lane>/<ID>/``.

Usage
-----
    python .agent/tools/archive_task.py TASK-010
    python .agent/tools/archive_task.py TASK-010 --lane archive
    python .agent/tools/archive_task.py TASK-010 --dry-run
    python .agent/tools/archive_task.py TASK-010 --force   # both exist; remove active after match check skipped
    python .agent/tools/archive_task.py TASK-010 --rewrite-paths   # already archived; fix stale artifact_path only

Exit codes: 0 success, 1 usage/state error, 2 I/O failure.
"""

from __future__ import annotations

import argparse
import filecmp
import re
import shutil
import sys
from pathlib import Path


def _configure_stdio_utf8() -> None:
    for stream in (sys.stdout, sys.stderr):
        reconf = getattr(stream, "reconfigure", None)
        if not callable(reconf):
            continue
        try:
            reconf(encoding="utf-8", errors="replace")
        except Exception:
            pass


_configure_stdio_utf8()

TOOLS_DIR = Path(__file__).resolve().parent
REPO_ROOT = TOOLS_DIR.parents[1]

_ACTIVE_PATH_PREFIX = re.compile(
    r"tasks[/\\]active[/\\](TASK-\d+)",
    re.IGNORECASE,
)


def _trees_equal(left: Path, right: Path) -> tuple[bool, str]:
    """Deep compare two task directories. Returns (ok, detail)."""
    mismatch: list[str] = []

    def walk(a: Path, b: Path, rel: str = "") -> None:
        a_names = {p.name for p in a.iterdir()} if a.is_dir() else set()
        b_names = {p.name for p in b.iterdir()} if b.is_dir() else set()
        only_a = sorted(a_names - b_names)
        only_b = sorted(b_names - a_names)
        if only_a:
            mismatch.append(f"only in active{('/' + rel) if rel else ''}: {only_a}")
        if only_b:
            mismatch.append(f"only in dest{('/' + rel) if rel else ''}: {only_b}")
        for name in sorted(a_names & b_names):
            pa, pb = a / name, b / name
            sub = f"{rel}/{name}" if rel else name
            if pa.is_dir() and pb.is_dir():
                walk(pa, pb, sub)
            elif pa.is_file() and pb.is_file():
                if not filecmp.cmp(pa, pb, shallow=False):
                    mismatch.append(f"differ: {sub}")
            else:
                mismatch.append(f"type mismatch: {sub}")

    walk(left, right)
    if mismatch:
        return False, "; ".join(mismatch[:8]) + ("…" if len(mismatch) > 8 else "")

    dir_file_count = lambda path: sum(1 for p in path.rglob("*") if p.is_file())
    return True, f"trees match ({dir_file_count(left)} files)"


def rewrite_task_yaml_artifact_paths(dest: Path, lane: str) -> str:
    """Rewrite tasks/active/<id>/ prefixes in task.yaml to tasks/<lane>/<id>/."""
    yaml_path = dest / "task.yaml"
    if not yaml_path.is_file():
        return "no task.yaml to rewrite"

    text = yaml_path.read_text(encoding="utf-8")
    task_id = dest.name
    count = 0

    def _sub(match: re.Match[str]) -> str:
        nonlocal count
        found_id = match.group(1)
        if found_id.upper() != task_id.upper():
            return match.group(0)
        count += 1
        return f"tasks/{lane}/{found_id}"

    new_text = _ACTIVE_PATH_PREFIX.sub(_sub, text)
    if new_text == text:
        return "task.yaml had no active artifact_path prefixes"
    yaml_path.write_text(new_text, encoding="utf-8")
    return f"rewrote {count} active path prefix(es) → tasks/{lane}/"


def archive_task(
    task_id: str,
    *,
    lane: str = "completed",
    dry_run: bool = False,
    force: bool = False,
    root: Path | None = None,
) -> tuple[int, str]:
    """Move tasks/active/<id> → tasks/<lane>/<id>. Returns (exit_code, message)."""
    if lane not in ("completed", "archive"):
        return 1, f"lane must be 'completed' or 'archive', got {lane!r}"

    root = root or REPO_ROOT
    active = root / "tasks" / "active" / task_id
    dest = root / "tasks" / lane / task_id

    if not active.is_dir():
        if dest.is_dir():
            if dry_run:
                return 0, f"dry-run: would rewrite paths in tasks/{lane}/{task_id}/task.yaml"
            note = rewrite_task_yaml_artifact_paths(dest, lane)
            return 0, f"{task_id}: already archived at tasks/{lane}/{task_id}/ (no active copy); {note}"
        return 1, f"{task_id}: tasks/active/{task_id}/ does not exist"

    if dest.is_dir():
        equal, detail = _trees_equal(active, dest)
        if not equal and not force:
            return (
                1,
                f"{task_id}: both active and tasks/{lane}/{task_id}/ exist and differ ({detail}). "
                "Reconcile manually, or re-run with --force after human review to remove active.",
            )
        if dry_run:
            action = "remove active (trees match)" if equal else "FORCE remove active (trees differ)"
            return 0, f"dry-run: would {action}: tasks/active/{task_id}/; then rewrite task.yaml paths"
        try:
            shutil.rmtree(active)
        except OSError as exc:
            return (
                2,
                f"{task_id}: could not remove tasks/active/{task_id}/: {exc}. "
                "Deletion may require human approval in this environment; do not report /ship "
                "complete until active is gone.",
            )
        if active.exists():
            return (
                2,
                f"{task_id}: tasks/active/{task_id}/ still present after rmtree. "
                "Human must delete it before /ship is complete.",
            )
        note = detail if equal else f"force-removed despite: {detail}"
        path_note = rewrite_task_yaml_artifact_paths(dest, lane)
        return 0, f"{task_id}: removed residual active copy ({note}); {path_note}"

    # Destination missing — prefer atomic replace/rename.
    if dry_run:
        return 0, f"dry-run: would move tasks/active/{task_id}/ → tasks/{lane}/{task_id}/; rewrite paths"

    dest.parent.mkdir(parents=True, exist_ok=True)
    try:
        active.replace(dest)
    except OSError:
        # Cross-device or locked — copy then remove.
        try:
            shutil.copytree(active, dest)
        except OSError as exc:
            return 2, f"{task_id}: copy to tasks/{lane}/{task_id}/ failed: {exc}"
        equal, detail = _trees_equal(active, dest)
        if not equal:
            return 2, f"{task_id}: copy incomplete ({detail}); left active in place"
        try:
            shutil.rmtree(active)
        except OSError as exc:
            return (
                2,
                f"{task_id}: copied to tasks/{lane}/{task_id}/ but could not remove active: {exc}. "
                f"Human must delete tasks/active/{task_id}/; /ship is not complete while it remains.",
            )
        if active.exists():
            return (
                2,
                f"{task_id}: copied OK but active residual remains. "
                f"Human must delete tasks/active/{task_id}/.",
            )
        path_note = rewrite_task_yaml_artifact_paths(dest, lane)
        return 0, f"{task_id}: copied then removed active → tasks/{lane}/{task_id}/; {path_note}"

    if active.exists() or not dest.is_dir():
        return 2, f"{task_id}: rename reported success but paths are inconsistent"
    path_note = rewrite_task_yaml_artifact_paths(dest, lane)
    return 0, f"{task_id}: moved tasks/active/{task_id}/ → tasks/{lane}/{task_id}/; {path_note}"


def rewrite_only(task_id: str, *, lane: str | None = None, root: Path | None = None) -> tuple[int, str]:
    """Rewrite artifact_path prefixes for an already-archived task (no move)."""
    root = root or REPO_ROOT
    lanes = [lane] if lane else ["completed", "archive"]
    for candidate in lanes:
        dest = root / "tasks" / candidate / task_id
        if dest.is_dir():
            note = rewrite_task_yaml_artifact_paths(dest, candidate)
            return 0, f"{task_id}: tasks/{candidate}/{task_id}/; {note}"
    return 1, f"{task_id}: not found under tasks/completed/ or tasks/archive/"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("task_id", help="e.g. TASK-010")
    parser.add_argument(
        "--lane",
        choices=("completed", "archive"),
        default="completed",
        help="destination under tasks/ (default: completed)",
    )
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument(
        "--force",
        action="store_true",
        help="when both trees exist and differ, still remove active after human review",
    )
    parser.add_argument(
        "--rewrite-paths",
        action="store_true",
        help="only rewrite task.yaml active→lane prefixes (task already archived)",
    )
    parser.add_argument(
        "--root",
        type=Path,
        default=None,
        help="project root (default: repository containing this tool)",
    )
    args = parser.parse_args(argv)
    root = args.root.resolve() if args.root else None
    if args.rewrite_paths:
        # Search completed then archive unless the caller pinned --lane on the command line.
        explicit_lane = any(
            a == "--lane" or a.startswith("--lane=") for a in (argv if argv is not None else sys.argv[1:])
        )
        code, message = rewrite_only(
            args.task_id,
            lane=args.lane if explicit_lane else None,
            root=root,
        )
    else:
        code, message = archive_task(
            args.task_id,
            lane=args.lane,
            dry_run=args.dry_run,
            force=args.force,
            root=root,
        )
    print(message)
    return code


if __name__ == "__main__":
    sys.exit(main())
