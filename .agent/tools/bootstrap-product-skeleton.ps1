# Optional product skeleton for a seeded Rgents project.
#
# This file is NOT part of the framework. It encodes one product's opinions -- FastAPI, SQLite,
# pytest, an api/service/repository split -- and the framework has no business holding an opinion
# about a product's stack. It is kept here only so a test project can be stood up repeatably;
# a real product repository should write its own skeleton and delete this.
#
# Called by bootstrap-project.ps1 -WithProductSkeleton, or directly:
#   ./.agent/tools/bootstrap-product-skeleton.ps1 -Target <path-to-seeded-project>
#
# Carries no machine-specific path: the target is an argument, and every generated file resolves
# its own root at runtime.

[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$Target
)

$ErrorActionPreference = 'Stop'
$utf8 = New-Object System.Text.UTF8Encoding($false)
$Target = (Resolve-Path $Target).Path

function Write-File {
    param([string]$RelativePath, [string]$Content)
    $full = Join-Path $Target $RelativePath
    $dir = Split-Path -Parent $full
    if (-not (Test-Path $dir)) { New-Item -ItemType Directory -Force -Path $dir | Out-Null }
    [System.IO.File]::WriteAllText($full, $Content, $utf8)
    Write-Output "  wrote $RelativePath"
}

$dirs = @(
    'app/api', 'app/service', 'app/repository', 'app/config',
    'db/migrations', 'tests', 'var', 'docs/product'
)
foreach ($d in $dirs) { New-Item -ItemType Directory -Force -Path (Join-Path $Target $d) | Out-Null }

Write-File '.gitignore' @'
__pycache__/
*.py[cod]
.pytest_cache/
.coverage
htmlcov/
var/
*.db
.venv/
'@

Write-File 'pytest.ini' @'
[pytest]
testpaths = tests
addopts = -q
'@

Write-File 'requirements.txt' @'
# Pinned to what the confirmed environment already provides.
# Never install a new package to satisfy a task: if one is genuinely needed, that is a new task
# plus an environment re-confirmation, not something a developer decides quietly.
fastapi==0.135.3
starlette==1.0.0
uvicorn==0.42.0
pydantic==2.11.10
pydantic-settings==2.13.1
redis==7.4.0
pytest==9.0.2
httpx==0.28.1
'@

Write-File 'app/__init__.py' @'
"""Application package."""
'@

Write-File 'app/api/__init__.py' @'
"""HTTP routes. One module per resource, registered in app/main.py."""
'@

Write-File 'app/service/__init__.py' @'
"""Business rules. Knows nothing about HTTP and nothing about SQL."""
'@

Write-File 'app/repository/__init__.py' @'
"""Persistence. The only layer that speaks SQL."""
'@

Write-File 'app/config/__init__.py' @'
"""Configuration, read once from the environment at import time.

Nothing here may hard-code a machine path. Anything machine-specific is read from an environment
variable and has a repo-relative default, because the framework's portability check scans every
.py/.yaml/.json file in the repository and treats a drive letter as an error.
"""

from __future__ import annotations

import os
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]

# Storage. Relative by design: resolved against the project root, not the working directory.
SQLITE_PATH = Path(os.environ.get("APP_SQLITE_PATH", str(PROJECT_ROOT / "var" / "app.db")))

# Redis is opt-in unless a server is confirmed to exist. Nothing may depend on it being
# reachable, so an absent cache is reported as a state and never as a failure.
REDIS_URL = os.environ.get("APP_REDIS_URL", "").strip()


def redis_enabled() -> bool:
    return bool(REDIS_URL)


def ensure_runtime_dirs() -> None:
    SQLITE_PATH.parent.mkdir(parents=True, exist_ok=True)
'@

Write-File 'app/db.py' @'
"""SQLite access and the migration runner.

The migration runner is infrastructure, not product code: it stays generic so that a feature adds
a numbered .sql file instead of editing this module.
"""

from __future__ import annotations

import re
import sqlite3
from pathlib import Path

from app.config import SQLITE_PATH

MIGRATIONS_DIR = Path(__file__).resolve().parents[1] / "db" / "migrations"
_BASE_SCHEMA = Path(__file__).resolve().parents[1] / "db" / "schema.sql"
_MIGRATION_NAME = re.compile(r"^(\d{4})_.+\.sql$")


def connect(path: Path | str | None = None) -> sqlite3.Connection:
    """Open a connection with foreign keys on and row access by column name."""
    target = Path(path) if path is not None else SQLITE_PATH
    target.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(target))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def _migration_files() -> list[tuple[str, Path]]:
    if not MIGRATIONS_DIR.is_dir():
        return []
    found: list[tuple[str, Path]] = []
    for path in sorted(MIGRATIONS_DIR.glob("*.sql")):
        match = _MIGRATION_NAME.match(path.name)
        if not match:
            raise RuntimeError(f"migration filename must look like 0001_name.sql: {path.name}")
        found.append((match.group(1), path))
    return found


def init_db(path: Path | str | None = None) -> list[str]:
    """Apply the base schema and every pending migration. Idempotent.

    Returns the migration versions applied during this call, so a test can assert that a repeat
    call applies nothing.
    """
    conn = connect(path)
    applied: list[str] = []
    try:
        conn.execute(
            "CREATE TABLE IF NOT EXISTS schema_migrations ("
            "  version TEXT PRIMARY KEY,"
            "  applied_at TEXT NOT NULL DEFAULT (datetime('now'))"
            ")"
        )
        if _BASE_SCHEMA.is_file():
            conn.executescript(_BASE_SCHEMA.read_text(encoding="utf-8"))
        known = {row["version"] for row in conn.execute("SELECT version FROM schema_migrations")}
        for version, migration in _migration_files():
            if version in known:
                continue
            conn.executescript(migration.read_text(encoding="utf-8"))
            conn.execute("INSERT INTO schema_migrations (version) VALUES (?)", (version,))
            applied.append(version)
        conn.commit()
    finally:
        conn.close()
    return applied
'@

Write-File 'app/redis_client.py' @'
"""Optional Redis client.

Redis must not be a hard dependency: there is no guarantee that a server exists in the confirmed
environment. Every entry point tolerates Redis being unconfigured or unreachable, and reports
that state instead of raising.
"""

from __future__ import annotations

import logging

from app.config import REDIS_URL

logger = logging.getLogger(__name__)

try:
    import redis as _redis
except ImportError:  # pragma: no cover - keeps the stack honest if the environment changes
    _redis = None


def available() -> bool:
    return _redis is not None and bool(REDIS_URL)


def get_client():
    """Return a client, or None when Redis is not configured.

    Does not open a connection: callers decide whether a failed ping is fatal.
    """
    if not available():
        return None
    return _redis.Redis.from_url(REDIS_URL, decode_responses=True)


def ping() -> str:
    """One of: 'disabled' (not configured), 'ok', or 'unreachable'."""
    client = get_client()
    if client is None:
        return "disabled"
    try:
        client.ping()
        return "ok"
    except Exception as exc:  # noqa: BLE001 - any connection failure is the same fact here
        logger.warning("redis unreachable: %s", exc)
        return "unreachable"
'@

Write-File 'app/main.py' @'
"""Application entry point.

Grows one router per resource. The skeleton ships only liveness and readiness so that a feature
task adds routes instead of restructuring the app.
"""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI

from app import redis_client
from app.config import ensure_runtime_dirs, redis_enabled
from app.db import init_db


@asynccontextmanager
async def lifespan(_: FastAPI):
    ensure_runtime_dirs()
    init_db()
    yield


app = FastAPI(title="app", lifespan=lifespan)


@app.get("/healthz")
def healthz() -> dict[str, str]:
    """Liveness. Never touches a dependency, so it cannot fail because the cache is down."""
    return {"status": "ok"}


@app.get("/readyz")
def readyz() -> dict[str, str]:
    """Readiness. Reports each dependency truthfully rather than hiding a gap."""
    return {
        "storage": "sqlite",
        "redis": redis_client.ping() if redis_enabled() else "disabled",
    }
'@

Write-File 'db/schema.sql' @'
-- Base schema. Applied on first initialisation, before any numbered migration.
-- Keep this file additive and idempotent: it runs on every start.
--
-- Feature work adds a numbered file under db/migrations/ instead of editing this one.
'@

Write-File 'db/migrations/0001_init.sql' @'
-- 0001_init -- migration scaffold, intentionally empty.
--
-- It exists so the migration convention is demonstrated rather than described, and so the first
-- feature task starts by filling in a migration instead of inventing the layout.
-- Naming: 0001_short_description.sql. Applied in ascending order, once, recorded in the
-- schema_migrations table.
--
-- Contrast with db/schema.sql, which is the idempotent base applied on every start.
'@

Write-File 'tests/__init__.py' @'
'@

Write-File 'tests/conftest.py' @'
from __future__ import annotations

import pytest
from starlette.testclient import TestClient

from app.db import init_db
from app.main import app


@pytest.fixture()
def db_path(tmp_path, monkeypatch):
    """A throwaway database per test. Never touch the developer's var/app.db."""
    path = tmp_path / "test.db"
    monkeypatch.setenv("APP_SQLITE_PATH", str(path))
    monkeypatch.setattr("app.config.SQLITE_PATH", path)
    monkeypatch.setattr("app.db.SQLITE_PATH", path)
    init_db(path)
    return path


@pytest.fixture()
def client(tmp_path, monkeypatch):
    """App client with a throwaway database and the cache explicitly off.

    The cache is off because no server is guaranteed: a test that needed one would be reporting
    an environment problem as a code defect.
    """
    path = tmp_path / "test.db"
    monkeypatch.setattr("app.config.SQLITE_PATH", path)
    monkeypatch.setattr("app.db.SQLITE_PATH", path)
    monkeypatch.setenv("APP_SQLITE_PATH", str(path))
    monkeypatch.delenv("APP_REDIS_URL", raising=False)
    with TestClient(app) as c:
        yield c
'@

Write-File 'tests/test_skeleton.py' @'
"""Skeleton tests. They assert the wiring, not the product.

A feature task replaces these with real tests; it does not delete the arrangement that lets a
test run without a network or a running service.
"""

from __future__ import annotations

import sqlite3

from app.config import PROJECT_ROOT
from app.db import init_db


def test_healthz_is_liveness_only(client):
    response = client.get("/healthz")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_readyz_reports_cache_as_disabled_without_config(client):
    response = client.get("/readyz")
    assert response.status_code == 200
    assert response.json() == {"storage": "sqlite", "redis": "disabled"}


def test_init_db_is_idempotent(db_path):
    """A second run must record nothing new.

    `db_path` already initialised the database, so the scaffold migration 0001 is recorded and
    unchanged content is left alone. This asserts the runner's contract: applied once, never
    silently re-applied.
    """
    applied = init_db(db_path)
    assert applied == [], "nothing may be re-applied on a second run"
    conn = sqlite3.connect(str(db_path))
    try:
        versions = [row[0] for row in conn.execute("SELECT version FROM schema_migrations")]
    finally:
        conn.close()
    assert versions == ["0001"], f"expected the scaffold migration only, got {versions}"


def test_paths_resolve_against_the_project_root_not_the_cwd():
    assert (PROJECT_ROOT / "app").is_dir()
    assert (PROJECT_ROOT / "db").is_dir()
'@

Write-Output '  product skeleton done'
