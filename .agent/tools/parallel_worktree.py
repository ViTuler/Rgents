#!/usr/bin/env python3
"""C2 — path leases, merge lock, and git worktrees for parallel_group steps.

Process analogy
---------------
  worktree + branch  ≈ process address space
  path exclusive lease ≈ mutex on a resource
  merge lock           ≈ critical-section mutex when integrating

Default remains sequential. Use this only when ``plan.json`` declares a
``parallel_group`` with pairwise-disjoint ``streams[].claimed_paths``.

Usage
-----
    python .agent/tools/parallel_worktree.py check-plan --task TASK-001
    python .agent/tools/parallel_worktree.py acquire-paths --task TASK-001 --step 2
    python .agent/tools/parallel_worktree.py add-worktree --task TASK-001 --step 2
    python .agent/tools/parallel_worktree.py acquire-merge --task TASK-001
    python .agent/tools/parallel_worktree.py release-paths --task TASK-001 --step 2
    python .agent/tools/parallel_worktree.py release-merge --task TASK-001
    python .agent/tools/parallel_worktree.py remove-worktree --task TASK-001 --step 2
    python .agent/tools/parallel_worktree.py reclaim-expired
    python .agent/tools/parallel_worktree.py status [--task TASK-001]

Lock tables
-----------
  tasks/<id>/locks/path-leases.json   — leases held by this task's steps
  tasks/<id>/locks/merge-lock.json    — merge critical section for this task
  .rgents/locks/index.json            — repo-wide path index (cross-task)

Worktrees live under ``.rgents/worktrees/<task>/<step>/`` (gitignored).
Branches: ``rgents/<task>/<step>`` and integrate ``rgents/<task>/integrate``.

Never stores credentials. Uses only the standard library + ``git`` on PATH.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

TOOLS_DIR = Path(__file__).resolve().parent
REPO_ROOT = TOOLS_DIR.parents[1]

DEFAULT_TTL_HOURS = 8
LOCK_VERSION = 1


# --------------------------------------------------------------------------------------
# Paths & IO
# --------------------------------------------------------------------------------------


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _parse_iso(raw: str) -> datetime | None:
    if not isinstance(raw, str) or not raw:
        return None
    text = raw.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        return datetime.fromisoformat(text)
    except ValueError:
        return None


def normalize_repo_path(raw: str) -> str:
    """Return a repo-relative POSIX path; reject absolutes and escapes."""
    if not isinstance(raw, str) or not raw.strip():
        raise ValueError("path must be a non-empty string")
    text = raw.strip().replace("\\", "/")
    while text.startswith("./"):
        text = text[2:]
    if text.startswith("/") or (len(text) > 1 and text[1] == ":"):
        raise ValueError(f"path must be repository-relative, got {raw!r}")
    parts = [p for p in text.split("/") if p not in ("", ".")]
    if any(p == ".." for p in parts):
        raise ValueError(f"path must not contain '..': {raw!r}")
    if not parts:
        raise ValueError(f"path is empty after normalization: {raw!r}")
    return "/".join(parts)


def atomic_write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=path.name + ".", dir=str(path.parent))
    tmp_path = Path(tmp_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2, ensure_ascii=True)
            handle.write("\n")
        os.replace(tmp_path, path)
    finally:
        if tmp_path.exists():
            try:
                tmp_path.unlink()
            except OSError:
                pass


def load_json_file(path: Path, default: dict) -> dict:
    if not path.is_file():
        return dict(default)
    with path.open("r", encoding="utf-8-sig") as handle:
        data = json.load(handle)
    if not isinstance(data, dict):
        raise SystemExit(f"lock file must be an object: {path}")
    return data


def resolve_task_dir(task_id: str, explicit: str | None = None) -> Path:
    if explicit:
        path = Path(explicit)
        return path.resolve() if path.is_absolute() else (REPO_ROOT / path).resolve()
    for base in ("active", "completed", "archive"):
        candidate = REPO_ROOT / "tasks" / base / task_id
        if candidate.is_dir():
            return candidate
    return REPO_ROOT / "tasks" / "active" / task_id


def task_locks_dir(task_dir: Path) -> Path:
    return task_dir / "locks"


def path_leases_path(task_dir: Path) -> Path:
    return task_locks_dir(task_dir) / "path-leases.json"


def merge_lock_path(task_dir: Path) -> Path:
    return task_locks_dir(task_dir) / "merge-lock.json"


def repo_index_path() -> Path:
    return REPO_ROOT / ".rgents" / "locks" / "index.json"


def worktree_path(task_id: str, step: int) -> Path:
    return REPO_ROOT / ".rgents" / "worktrees" / task_id / str(step)


def step_branch(task_id: str, step: int) -> str:
    return f"rgents/{task_id}/{step}"


def integrate_branch(task_id: str) -> str:
    return f"rgents/{task_id}/integrate"


def holder_id(task_id: str, step: int) -> str:
    return f"{task_id}/step-{step}"


# --------------------------------------------------------------------------------------
# Plan helpers
# --------------------------------------------------------------------------------------


def load_plan(task_dir: Path) -> dict:
    plan_path = task_dir / "plan.json"
    if not plan_path.is_file():
        raise SystemExit(f"plan.json missing under {task_dir}")
    with plan_path.open("r", encoding="utf-8-sig") as handle:
        plan = json.load(handle)
    if not isinstance(plan, dict):
        raise SystemExit("plan.json must be an object")
    return plan


def streams_for_parallel_groups(plan: dict) -> list[dict]:
    """Flatten parallel_groups[].streams into validated stream dicts (no intersection check)."""
    steps_by_order = {
        s["order"]: s
        for s in (plan.get("steps") or [])
        if isinstance(s, dict) and isinstance(s.get("order"), int)
    }
    out: list[dict] = []
    for group in plan.get("parallel_groups") or []:
        if not isinstance(group, dict):
            continue
        group_name = group.get("group") or "?"
        step_orders = [s for s in (group.get("steps") or []) if isinstance(s, int)]
        streams = group.get("streams")
        if not isinstance(streams, list):
            streams = []
        for stream in streams:
            if not isinstance(stream, dict):
                continue
            step = stream.get("step")
            paths_raw = stream.get("claimed_paths") or []
            if not isinstance(step, int) or not isinstance(paths_raw, list):
                continue
            paths = [normalize_repo_path(p) for p in paths_raw if isinstance(p, str)]
            out.append(
                {
                    "group": group_name,
                    "step": step,
                    "claimed_paths": paths,
                    "step_file": (steps_by_order.get(step) or {}).get("file"),
                }
            )
        # Synthesize streams from step.file when a multi-step group omitted streams —
        # validate.py rejects that; the tool still surfaces a clear error via check-plan.
        if len(step_orders) >= 2 and not streams:
            for order in step_orders:
                step = steps_by_order.get(order) or {}
                file_ref = step.get("file")
                out.append(
                    {
                        "group": group_name,
                        "step": order,
                        "claimed_paths": [normalize_repo_path(file_ref)] if isinstance(file_ref, str) else [],
                        "step_file": file_ref,
                        "synthesized": True,
                    }
                )
    return out


def find_stream_paths(plan: dict, step: int) -> list[str]:
    for stream in streams_for_parallel_groups(plan):
        if stream["step"] == step and stream.get("claimed_paths"):
            return list(stream["claimed_paths"])
    steps = plan.get("steps") or []
    for item in steps:
        if isinstance(item, dict) and item.get("order") == step and isinstance(item.get("file"), str):
            return [normalize_repo_path(item["file"])]
    raise SystemExit(f"no claimed_paths or step.file found for step {step}")


def check_plan_disjoint(plan: dict) -> list[str]:
    """Return human-readable errors for intersecting claimed_paths / parallel depends_on."""
    errors: list[str] = []
    steps_by_order = {
        s["order"]: s
        for s in (plan.get("steps") or [])
        if isinstance(s, dict) and isinstance(s.get("order"), int)
    }

    for group in plan.get("parallel_groups") or []:
        if not isinstance(group, dict):
            continue
        group_name = group.get("group") or "?"
        step_orders = [s for s in (group.get("steps") or []) if isinstance(s, int)]
        if len(step_orders) < 2:
            continue

        streams = group.get("streams")
        if not isinstance(streams, list) or len(streams) < 2:
            errors.append(
                f"parallel group '{group_name}' has {len(step_orders)} steps but no streams[] "
                "with claimed_paths (C2 requires per-step path leases)"
            )
            continue

        stream_steps = []
        owned: dict[int, set[str]] = {}
        for stream in streams:
            if not isinstance(stream, dict):
                errors.append(f"parallel group '{group_name}' has a non-object stream")
                continue
            step = stream.get("step")
            paths_raw = stream.get("claimed_paths")
            if not isinstance(step, int):
                errors.append(f"parallel group '{group_name}' stream missing integer step")
                continue
            if step not in step_orders:
                errors.append(
                    f"parallel group '{group_name}' stream step {step} is not in group.steps"
                )
            if not isinstance(paths_raw, list) or not paths_raw:
                errors.append(
                    f"parallel group '{group_name}' step {step} needs non-empty claimed_paths"
                )
                continue
            try:
                paths = {normalize_repo_path(p) for p in paths_raw if isinstance(p, str)}
            except ValueError as exc:
                errors.append(f"parallel group '{group_name}' step {step}: {exc}")
                continue
            step_meta = steps_by_order.get(step) or {}
            step_file = step_meta.get("file")
            if isinstance(step_file, str):
                try:
                    normalized_file = normalize_repo_path(step_file)
                except ValueError as exc:
                    errors.append(f"step {step} file: {exc}")
                    normalized_file = None
                if normalized_file and normalized_file not in paths:
                    errors.append(
                        f"parallel group '{group_name}' step {step} claimed_paths must include "
                        f"step.file ({normalized_file})"
                    )
            owned[step] = paths
            stream_steps.append(step)

        missing = [s for s in step_orders if s not in owned]
        if missing:
            errors.append(
                f"parallel group '{group_name}' missing streams for step(s) {missing}"
            )

        orders = sorted(owned)
        for i, left in enumerate(orders):
            for right in orders[i + 1 :]:
                overlap = sorted(owned[left] & owned[right])
                if overlap:
                    errors.append(
                        f"parallel group '{group_name}' claimed_paths intersect between "
                        f"steps {left} and {right}: {overlap}"
                    )

        # No depends_on edges inside the parallel set (would serialize / deadlock intent).
        parallel_set = set(step_orders)
        for order in step_orders:
            step = steps_by_order.get(order) or {}
            for dep in step.get("depends_on") or []:
                if dep in parallel_set:
                    errors.append(
                        f"parallel group '{group_name}': step {order} depends_on {dep}, "
                        "but both are in the same parallel group"
                    )

    return errors


# --------------------------------------------------------------------------------------
# Lock operations
# --------------------------------------------------------------------------------------


def _empty_leases() -> dict:
    return {"version": LOCK_VERSION, "leases": []}


def _empty_index() -> dict:
    return {"version": LOCK_VERSION, "entries": []}


def _lease_expired(lease: dict, now: datetime) -> bool:
    expires = _parse_iso(lease.get("expires_at") or "")
    return expires is not None and expires <= now


def reclaim_expired_locked(now: datetime | None = None) -> int:
    """Drop expired leases from all task lock files and the repo index. Returns count removed."""
    now = now or _utc_now()
    removed = 0

    index = load_json_file(repo_index_path(), _empty_index())
    keep_entries = []
    for entry in index.get("entries") or []:
        if isinstance(entry, dict) and _lease_expired(entry, now):
            removed += 1
            continue
        if isinstance(entry, dict):
            keep_entries.append(entry)
    if removed:
        index["entries"] = keep_entries
        atomic_write_json(repo_index_path(), index)

    for base in ("active", "completed", "archive"):
        root = REPO_ROOT / "tasks" / base
        if not root.is_dir():
            continue
        for task_dir in root.iterdir():
            if not task_dir.is_dir():
                continue
            leases_path = path_leases_path(task_dir)
            if not leases_path.is_file():
                continue
            data = load_json_file(leases_path, _empty_leases())
            keep = []
            changed = False
            for lease in data.get("leases") or []:
                if isinstance(lease, dict) and _lease_expired(lease, now):
                    removed += 1
                    changed = True
                    continue
                if isinstance(lease, dict):
                    keep.append(lease)
            if changed:
                data["leases"] = keep
                atomic_write_json(leases_path, data)

            merge_path = merge_lock_path(task_dir)
            if merge_path.is_file():
                merge = load_json_file(merge_path, {})
                if merge.get("held_by") and _lease_expired(merge, now):
                    atomic_write_json(
                        merge_path,
                        {"version": LOCK_VERSION, "held_by": None, "released_reason": "expired"},
                    )
                    removed += 1

    return removed


def acquire_paths(
    task_id: str,
    step: int,
    paths: list[str],
    *,
    ttl_hours: int = DEFAULT_TTL_HOURS,
    task_dir: Path | None = None,
) -> dict:
    reclaim_expired_locked()
    task_dir = task_dir or resolve_task_dir(task_id)
    now = _utc_now()
    expires = now + timedelta(hours=ttl_hours)
    holder = holder_id(task_id, step)
    wt = worktree_path(task_id, step).relative_to(REPO_ROOT).as_posix()
    normalized = [normalize_repo_path(p) for p in paths]

    index = load_json_file(repo_index_path(), _empty_index())
    for entry in index.get("entries") or []:
        if not isinstance(entry, dict):
            continue
        if entry.get("path") in normalized and entry.get("holder") != holder:
            if not _lease_expired(entry, now):
                raise SystemExit(
                    f"path {entry['path']!r} already leased by {entry.get('holder')} "
                    f"(task {entry.get('task_id')})"
                )

    leases = load_json_file(path_leases_path(task_dir), _empty_leases())
    existing = [lease for lease in (leases.get("leases") or []) if isinstance(lease, dict)]
    # Drop this holder's previous leases (re-acquire).
    existing = [lease for lease in existing if lease.get("holder") != holder]
    new_leases = []
    for path in normalized:
        new_leases.append(
            {
                "path": path,
                "mode": "exclusive",
                "holder": holder,
                "task_id": task_id,
                "step": step,
                "acquired_at": _iso(now),
                "expires_at": _iso(expires),
                "worktree": wt,
            }
        )
    leases["version"] = LOCK_VERSION
    leases["leases"] = existing + new_leases
    atomic_write_json(path_leases_path(task_dir), leases)

    index_entries = [
        e
        for e in (index.get("entries") or [])
        if isinstance(e, dict) and e.get("holder") != holder
    ]
    for path in normalized:
        index_entries.append(
            {
                "path": path,
                "mode": "exclusive",
                "holder": holder,
                "task_id": task_id,
                "step": step,
                "acquired_at": _iso(now),
                "expires_at": _iso(expires),
                "worktree": wt,
            }
        )
    index["version"] = LOCK_VERSION
    index["entries"] = index_entries
    atomic_write_json(repo_index_path(), index)
    return {"holder": holder, "paths": normalized, "expires_at": _iso(expires), "worktree": wt}


def release_paths(task_id: str, step: int, *, task_dir: Path | None = None) -> int:
    task_dir = task_dir or resolve_task_dir(task_id)
    holder = holder_id(task_id, step)
    removed = 0

    leases = load_json_file(path_leases_path(task_dir), _empty_leases())
    keep = []
    for lease in leases.get("leases") or []:
        if isinstance(lease, dict) and lease.get("holder") == holder:
            removed += 1
            continue
        if isinstance(lease, dict):
            keep.append(lease)
    leases["leases"] = keep
    atomic_write_json(path_leases_path(task_dir), leases)

    index = load_json_file(repo_index_path(), _empty_index())
    keep_i = []
    for entry in index.get("entries") or []:
        if isinstance(entry, dict) and entry.get("holder") == holder:
            continue
        if isinstance(entry, dict):
            keep_i.append(entry)
    index["entries"] = keep_i
    atomic_write_json(repo_index_path(), index)
    return removed


def acquire_merge(task_id: str, *, ttl_hours: int = DEFAULT_TTL_HOURS, task_dir: Path | None = None) -> dict:
    reclaim_expired_locked()
    task_dir = task_dir or resolve_task_dir(task_id)
    now = _utc_now()
    path = merge_lock_path(task_dir)
    current = load_json_file(path, {"version": LOCK_VERSION, "held_by": None})
    held = current.get("held_by")
    if held and held != task_id and not _lease_expired(current, now):
        raise SystemExit(f"merge lock held by {held} until {current.get('expires_at')}")
    payload = {
        "version": LOCK_VERSION,
        "held_by": task_id,
        "mode": "exclusive",
        "acquired_at": _iso(now),
        "expires_at": _iso(now + timedelta(hours=ttl_hours)),
        "target_branch": integrate_branch(task_id),
    }
    atomic_write_json(path, payload)
    return payload


def release_merge(task_id: str, *, task_dir: Path | None = None) -> None:
    task_dir = task_dir or resolve_task_dir(task_id)
    path = merge_lock_path(task_dir)
    current = load_json_file(path, {"version": LOCK_VERSION, "held_by": None})
    if current.get("held_by") and current.get("held_by") != task_id:
        raise SystemExit(f"merge lock held by {current.get('held_by')}, not {task_id}")
    atomic_write_json(
        path,
        {
            "version": LOCK_VERSION,
            "held_by": None,
            "released_at": _iso(_utc_now()),
            "released_by": task_id,
        },
    )


# --------------------------------------------------------------------------------------
# Git worktree
# --------------------------------------------------------------------------------------


def _run_git(args: list[str], *, cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        cwd=str(cwd or REPO_ROOT),
        check=False,
        capture_output=True,
        text=True,
    )


def add_worktree(task_id: str, step: int) -> dict:
    if not (REPO_ROOT / ".git").exists():
        raise SystemExit("repository has no .git; run init_project.py first")
    dest = worktree_path(task_id, step)
    branch = step_branch(task_id, step)
    if dest.exists():
        raise SystemExit(f"worktree path already exists: {dest}")
    dest.parent.mkdir(parents=True, exist_ok=True)
    # Prefer creating a new branch from HEAD; if branch exists, just attach.
    show = _run_git(["show-ref", "--verify", "--quiet", f"refs/heads/{branch}"])
    if show.returncode == 0:
        result = _run_git(["worktree", "add", str(dest), branch])
    else:
        result = _run_git(["worktree", "add", "-b", branch, str(dest), "HEAD"])
    if result.returncode != 0:
        raise SystemExit(
            f"git worktree add failed: {(result.stderr or result.stdout).strip()}"
        )
    return {
        "worktree": dest.relative_to(REPO_ROOT).as_posix(),
        "branch": branch,
        "absolute": str(dest),
    }


def remove_worktree(task_id: str, step: int, *, force: bool = False) -> dict:
    dest = worktree_path(task_id, step)
    if not dest.exists():
        return {"removed": False, "reason": "path absent"}
    args = ["worktree", "remove"]
    if force:
        args.append("--force")
    args.append(str(dest))
    result = _run_git(args)
    if result.returncode != 0:
        raise SystemExit(
            f"git worktree remove failed: {(result.stderr or result.stdout).strip()}. "
            "Conflict? Keep the worktree and escalate to a human."
        )
    return {"removed": True, "worktree": dest.relative_to(REPO_ROOT).as_posix()}


# --------------------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------------------


def cmd_check_plan(args: argparse.Namespace) -> int:
    task_dir = resolve_task_dir(args.task, args.task_dir)
    plan = load_plan(task_dir)
    errors = check_plan_disjoint(plan)
    if errors:
        for err in errors:
            print(f"ERROR: {err}", file=sys.stderr)
        return 1
    groups = plan.get("parallel_groups") or []
    multi = sum(1 for g in groups if isinstance(g, dict) and len(g.get("steps") or []) >= 2)
    print(f"ok: parallel claimed_paths disjoint ({multi} multi-step group(s))")
    return 0


def cmd_acquire_paths(args: argparse.Namespace) -> int:
    task_dir = resolve_task_dir(args.task, args.task_dir)
    plan = load_plan(task_dir)
    paths = [p.strip() for p in (args.paths or "").split(",") if p.strip()]
    if not paths:
        paths = find_stream_paths(plan, args.step)
    info = acquire_paths(args.task, args.step, paths, ttl_hours=args.ttl_hours, task_dir=task_dir)
    print(json.dumps(info, indent=2))
    return 0


def cmd_release_paths(args: argparse.Namespace) -> int:
    task_dir = resolve_task_dir(args.task, args.task_dir)
    n = release_paths(args.task, args.step, task_dir=task_dir)
    print(f"released {n} lease(s) for {holder_id(args.task, args.step)}")
    return 0


def cmd_acquire_merge(args: argparse.Namespace) -> int:
    task_dir = resolve_task_dir(args.task, args.task_dir)
    print(json.dumps(acquire_merge(args.task, ttl_hours=args.ttl_hours, task_dir=task_dir), indent=2))
    return 0


def cmd_release_merge(args: argparse.Namespace) -> int:
    task_dir = resolve_task_dir(args.task, args.task_dir)
    release_merge(args.task, task_dir=task_dir)
    print(f"merge lock released for {args.task}")
    return 0


def cmd_add_worktree(args: argparse.Namespace) -> int:
    print(json.dumps(add_worktree(args.task, args.step), indent=2))
    return 0


def cmd_remove_worktree(args: argparse.Namespace) -> int:
    print(json.dumps(remove_worktree(args.task, args.step, force=args.force), indent=2))
    return 0


def cmd_reclaim(args: argparse.Namespace) -> int:
    n = reclaim_expired_locked()
    print(f"reclaimed {n} expired lease(s)/lock(s)")
    return 0


def cmd_status(args: argparse.Namespace) -> int:
    index = load_json_file(repo_index_path(), _empty_index())
    print("== repo path index")
    print(json.dumps(index, indent=2))
    if args.task:
        task_dir = resolve_task_dir(args.task, args.task_dir)
        print(f"== task {args.task} path leases")
        print(json.dumps(load_json_file(path_leases_path(task_dir), _empty_leases()), indent=2))
        print(f"== task {args.task} merge lock")
        print(json.dumps(load_json_file(merge_lock_path(task_dir), {"held_by": None}), indent=2))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Rgents parallel worktree + path/merge locks (C2)")
    sub = parser.add_subparsers(dest="command", required=True)

    def add_task(p: argparse.ArgumentParser) -> None:
        p.add_argument("--task", required=True, help="TASK-ID")
        p.add_argument("--task-dir", default=None, help="explicit task directory")

    p = sub.add_parser("check-plan", help="verify parallel_groups streams claimed_paths are disjoint")
    add_task(p)
    p.set_defaults(func=cmd_check_plan)

    p = sub.add_parser("acquire-paths", help="acquire exclusive path leases for a step")
    add_task(p)
    p.add_argument("--step", type=int, required=True)
    p.add_argument("--paths", default="", help="comma-separated repo paths (default: from plan streams)")
    p.add_argument("--ttl-hours", type=int, default=DEFAULT_TTL_HOURS)
    p.set_defaults(func=cmd_acquire_paths)

    p = sub.add_parser("release-paths", help="release path leases for a step")
    add_task(p)
    p.add_argument("--step", type=int, required=True)
    p.set_defaults(func=cmd_release_paths)

    p = sub.add_parser("acquire-merge", help="acquire the task merge lock")
    add_task(p)
    p.add_argument("--ttl-hours", type=int, default=DEFAULT_TTL_HOURS)
    p.set_defaults(func=cmd_acquire_merge)

    p = sub.add_parser("release-merge", help="release the task merge lock")
    add_task(p)
    p.set_defaults(func=cmd_release_merge)

    p = sub.add_parser("add-worktree", help="git worktree add for a parallel step")
    add_task(p)
    p.add_argument("--step", type=int, required=True)
    p.set_defaults(func=cmd_add_worktree)

    p = sub.add_parser("remove-worktree", help="git worktree remove for a parallel step")
    add_task(p)
    p.add_argument("--step", type=int, required=True)
    p.add_argument("--force", action="store_true")
    p.set_defaults(func=cmd_remove_worktree)

    p = sub.add_parser("reclaim-expired", help="drop expired leases from lock tables")
    p.set_defaults(func=cmd_reclaim)

    p = sub.add_parser("status", help="print lock tables")
    p.add_argument("--task", default=None)
    p.add_argument("--task-dir", default=None)
    p.set_defaults(func=cmd_status)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
