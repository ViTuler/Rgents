#!/usr/bin/env python3
"""Create or upgrade a product repository's Rgents framework surfaces.

Create (empty directory only)
-----------------------------
    python .agent/tools/seed_framework.py create --target <path> [--with-product-skeleton]

Upgrade (existing seeded project)
---------------------------------
    python .agent/tools/seed_framework.py upgrade --target <path> [--dry-run] [--yes]

Design
------
* **Framework-owned** paths come from ``.agent/framework-manifest.yaml → replaceable``.
* **Product-owned** paths (baseline, knowledge, tasks, available.yaml, …) are never replaced.
* Provisioning tools (bootstrap / this script) are not left inside the product.
* ``.agent/seeded-from.yaml`` records release + git HEAD at seed/upgrade time.
* Does **not** create the first commit or add a remote.

This script lives in the framework checkout and acts *on* a target. It is listed under
``provisioning_tools`` so create/upgrade never install it into the product.
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from datetime import date
from pathlib import Path

TOOLS_DIR = Path(__file__).resolve().parent
FRAMEWORK_ROOT = TOOLS_DIR.parents[1]

# Minimal YAML subset via validate.parse_yaml (stdlib only).
sys.path.insert(0, str(TOOLS_DIR))
from validate import parse_yaml  # noqa: E402


def _run_git(args: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        cwd=str(cwd),
        check=False,
        capture_output=True,
        text=True,
    )


def git_head(root: Path) -> str | None:
    result = _run_git(["rev-parse", "HEAD"], root)
    if result.returncode != 0:
        return None
    return (result.stdout or "").strip() or None


def load_manifest(root: Path | None = None) -> dict:
    path = (root or FRAMEWORK_ROOT) / ".agent" / "framework-manifest.yaml"
    if not path.is_file():
        raise SystemExit(f"missing framework manifest: {path}")
    data = parse_yaml(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise SystemExit(f"manifest must be a mapping: {path}")
    return data


def never_copy_names(manifest: dict) -> set[str]:
    names = manifest.get("never_copy_names") or []
    return {n for n in names if isinstance(n, str)}


def should_skip(path: Path, skip_names: set[str]) -> bool:
    return any(part in skip_names for part in path.parts)


def copy_tree(src: Path, dst: Path, skip_names: set[str]) -> int:
    """Copy file or directory, skipping never_copy names. Returns files copied."""
    if not src.exists():
        raise SystemExit(f"framework source missing: {src}")
    count = 0
    if src.is_file():
        if should_skip(src, skip_names):
            return 0
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
        return 1
    for path in src.rglob("*"):
        if path.is_dir():
            continue
        rel = path.relative_to(src)
        if should_skip(rel, skip_names) or should_skip(path, skip_names):
            continue
        target = dst / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, target)
        count += 1
    return count


def remove_provisioning_tools(target: Path, manifest: dict) -> list[str]:
    removed: list[str] = []
    tools = target / ".agent" / "tools"
    for name in manifest.get("provisioning_tools") or []:
        if not isinstance(name, str):
            continue
        path = tools / name
        if path.is_file():
            path.unlink()
            removed.append(f".agent/tools/{name}")
    return removed


def prune_never_copy(target: Path, skip_names: set[str]) -> list[str]:
    """Delete any never_copy directories/files that slipped into the target."""
    removed: list[str] = []
    agent = target / ".agent"
    if not agent.is_dir():
        return removed
    for path in sorted(agent.rglob("*"), reverse=True):
        if path.name in skip_names:
            if path.is_dir():
                shutil.rmtree(path, ignore_errors=True)
            elif path.is_file():
                path.unlink(missing_ok=True)
            removed.append(path.relative_to(target).as_posix())
    return removed


def scaffold_knowledge_and_baseline(framework: Path, target: Path) -> None:
    template_dir = framework / ".agent" / "templates" / "knowledge"
    for name, dest_rel in (
        ("known-issues.md", Path("docs") / "knowledge" / "known-issues.md"),
        ("project-memory.md", Path("docs") / "knowledge" / "project-memory.md"),
    ):
        src = template_dir / name
        if not src.is_file():
            raise SystemExit(f"framework template missing: {src}")
        dst = target / dest_rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)

    baseline_tpl = framework / ".agent" / "templates" / "project-baseline.yaml"
    if not baseline_tpl.is_file():
        raise SystemExit(f"framework template missing: {baseline_tpl}")
    baseline_dst = target / ".agent" / "project-baseline.yaml"
    baseline_dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(baseline_tpl, baseline_dst)


def write_seeded_from(target: Path, manifest: dict, *, operation: str) -> Path:
    head = git_head(FRAMEWORK_ROOT)
    payload = {
        "version": 1,
        "framework_id": manifest.get("framework_id", "rgents"),
        "release": manifest.get("release"),
        "seeded_from_commit": head,
        "seeded_at": date.today().isoformat(),
        "last_operation": operation,
        "framework_root_note": "path not stored — machine-specific; upgrade from a framework checkout",
    }
    # Keep YAML simple and parse_yaml-friendly (JSON scalars).
    lines = [
        "# Written by seed_framework.py. Product-owned; upgrade rewrites this file only.",
        "version: 1",
        f"framework_id: {json.dumps(payload['framework_id'])}",
        f"release: {json.dumps(payload['release'])}",
        f"seeded_from_commit: {json.dumps(payload['seeded_from_commit'])}",
        f"seeded_at: {json.dumps(payload['seeded_at'])}",
        f"last_operation: {json.dumps(payload['last_operation'])}",
        "framework_root_note: \"path not stored - machine-specific; upgrade from a framework checkout\"",
        "",
    ]
    path = target / ".agent" / "seeded-from.yaml"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def ensure_task_lanes(target: Path) -> None:
    for lane in ("active", "completed", "archive"):
        (target / "tasks" / lane).mkdir(parents=True, exist_ok=True)


def cmd_create(args: argparse.Namespace) -> int:
    manifest = load_manifest()
    skip = never_copy_names(manifest)
    target = Path(args.target).expanduser()
    if target.exists():
        if any(target.iterdir()):
            raise SystemExit(f"target exists and is not empty: {target}")
    else:
        target.mkdir(parents=True)

    target = target.resolve()
    print(f"framework root : {FRAMEWORK_ROOT}")
    print(f"target         : {target}")
    print(f"release        : {manifest.get('release')}")

    print("\n== 1. framework surfaces")
    for surface in manifest.get("create_surfaces") or []:
        if not isinstance(surface, str):
            continue
        src = FRAMEWORK_ROOT / surface
        dst = target / surface
        n = copy_tree(src, dst, skip)
        print(f"  copied {surface} ({n} files)")

    ensure_task_lanes(target)
    print("  created empty tasks/{active,completed,archive}")

    removed = remove_provisioning_tools(target, manifest)
    for item in removed:
        print(f"  removed {item}")
    pruned = prune_never_copy(target, skip)
    for item in pruned[:20]:
        print(f"  pruned {item}")
    if len(pruned) > 20:
        print(f"  pruned … {len(pruned) - 20} more")

    print("\n== 2. knowledge + baseline from templates")
    scaffold_knowledge_and_baseline(FRAMEWORK_ROOT, target)
    print("  docs/knowledge/* from templates")
    print("  .agent/project-baseline.yaml (status: template)")

    seeded = write_seeded_from(target, manifest, operation="create")
    print(f"  wrote {seeded.relative_to(target).as_posix()}")

    # Ensure available.yaml exists for C1 (seed copy if missing).
    avail = target / ".agent" / "models" / "available.yaml"
    seed_models = target / ".agent" / "models" / "seed.yaml"
    if not avail.is_file() and seed_models.is_file():
        shutil.copy2(seed_models, avail)
        print("  .agent/models/available.yaml copied from seed")

    if args.with_product_skeleton:
        print("\n== 3. optional product skeleton")
        skeleton = TOOLS_DIR / "bootstrap-product-skeleton.ps1"
        if skeleton.is_file():
            result = subprocess.run(
                ["powershell", "-NoProfile", "-File", str(skeleton), "-Target", str(target)],
                check=False,
            )
            if result.returncode != 0:
                raise SystemExit(f"product skeleton failed with exit {result.returncode}")
        else:
            print("  skipped: bootstrap-product-skeleton.ps1 not present")
    else:
        print("\n== 3. product skeleton skipped (pass --with-product-skeleton)")

    print("\n== 4. local git init (no remote)")
    init_py = TOOLS_DIR / "init_project.py"
    if init_py.is_file():
        result = subprocess.run(
            [sys.executable, str(init_py), "--target", str(target)],
            check=False,
        )
        if result.returncode != 0:
            raise SystemExit(f"init_project failed with exit {result.returncode}")
    else:
        print("  skipped: init_project.py missing")

    print("\n== done (create) ==")
    print("Next (human):")
    print("  1. First commit when ready (init does not commit).")
    print("  2. Project-level spec/design → fill .agent/project-baseline.yaml → status: established.")
    print("  3. python .agent/tools/validate.py --check-setup")
    return 0


def _iter_replaceable_sources(manifest: dict) -> list[tuple[str, Path]]:
    items: list[tuple[str, Path]] = []
    for raw in manifest.get("replaceable") or []:
        if not isinstance(raw, str):
            continue
        rel = raw.rstrip("/")
        src = FRAMEWORK_ROOT / rel
        if not src.exists():
            raise SystemExit(f"replaceable path missing in framework: {raw}")
        items.append((rel, src))
    return items


def _backup_dir(target: Path) -> Path:
    stamp = date.today().isoformat()
    base = target / ".rgents" / "upgrade-backups" / stamp
    index = 1
    path = base
    while path.exists():
        path = Path(f"{base}-{index}")
        index += 1
    path.mkdir(parents=True, exist_ok=False)
    return path


def cmd_upgrade(args: argparse.Namespace) -> int:
    manifest = load_manifest()
    skip = never_copy_names(manifest)
    target = Path(args.target).expanduser().resolve()
    if not target.is_dir():
        raise SystemExit(f"target is not a directory: {target}")
    if not (target / ".agent").is_dir():
        raise SystemExit(f"target does not look seeded (no .agent/): {target}")

    seeded_path = target / ".agent" / "seeded-from.yaml"
    previous_release = None
    if seeded_path.is_file():
        try:
            prev = parse_yaml(seeded_path.read_text(encoding="utf-8"))
            if isinstance(prev, dict):
                previous_release = prev.get("release")
        except Exception:  # noqa: BLE001
            previous_release = None

    replaceable = _iter_replaceable_sources(manifest)
    print(f"framework root : {FRAMEWORK_ROOT}")
    print(f"target         : {target}")
    print(f"from release   : {previous_release!r}")
    print(f"to release     : {manifest.get('release')!r}")
    print(f"dry_run        : {bool(args.dry_run)}")

    print("\n== plan (replaceable)")
    for rel, src in replaceable:
        kind = "dir" if src.is_dir() else "file"
        print(f"  {kind:4} {rel}")

    product_owned = [p for p in (manifest.get("product_owned") or []) if isinstance(p, str)]
    print("\n== product-owned (will not touch)")
    for rel in product_owned:
        print(f"  keep {rel}")

    if args.dry_run:
        print("\n== dry-run complete (no changes) ==")
        return 0

    if not args.yes:
        print("\nRefusing to upgrade without --yes (after reviewing the plan). Re-run with --yes.")
        return 2

    backup = _backup_dir(target)
    print(f"\n== backup → {backup.relative_to(target).as_posix()}")
    for rel, src in replaceable:
        dst = target / rel
        if not dst.exists():
            continue
        bak = backup / rel
        bak.parent.mkdir(parents=True, exist_ok=True)
        if dst.is_dir():
            shutil.copytree(dst, bak, dirs_exist_ok=True)
        else:
            shutil.copy2(dst, bak)

    print("\n== replace")
    for rel, src in replaceable:
        dst = target / rel
        if src.is_dir():
            if dst.exists():
                shutil.rmtree(dst)
            n = copy_tree(src, dst, skip)
            print(f"  replaced dir  {rel}/ ({n} files)")
        else:
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)
            print(f"  replaced file {rel}")

    removed = remove_provisioning_tools(target, manifest)
    for item in removed:
        print(f"  removed {item}")
    prune_never_copy(target, skip)

    seeded = write_seeded_from(target, manifest, operation="upgrade")
    print(f"\n  wrote {seeded.relative_to(target).as_posix()}")
    print("\n== done (upgrade) ==")
    print("Next: python .agent/tools/validate.py --check-setup")
    print("      (from the product repo). Review the backup under .rgents/upgrade-backups/ if needed.")
    return 0


def cmd_show(args: argparse.Namespace) -> int:
    manifest = load_manifest()
    print(json.dumps(
        {
            "framework_root": str(FRAMEWORK_ROOT),
            "release": manifest.get("release"),
            "replaceable": manifest.get("replaceable"),
            "product_owned": manifest.get("product_owned"),
        },
        indent=2,
    ))
    target = getattr(args, "target", None)
    if target:
        path = Path(target).expanduser().resolve() / ".agent" / "seeded-from.yaml"
        if path.is_file():
            print("--- seeded-from ---")
            print(path.read_text(encoding="utf-8"))
        else:
            print(f"(no seeded-from.yaml under {path.parent})")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Create or upgrade Rgents framework surfaces in a product repo")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("create", help="seed an empty directory")
    p.add_argument("--target", required=True)
    p.add_argument("--with-product-skeleton", action="store_true")
    p.set_defaults(func=cmd_create)

    p = sub.add_parser("upgrade", help="replace framework-owned surfaces in an existing seeded project")
    p.add_argument("--target", required=True)
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--yes", action="store_true", help="apply the upgrade (required unless --dry-run)")
    p.set_defaults(func=cmd_upgrade)

    p = sub.add_parser("show", help="print manifest / seeded-from")
    p.add_argument("--target", default=None)
    p.set_defaults(func=cmd_show)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
