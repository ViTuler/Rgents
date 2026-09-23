#!/usr/bin/env bash
# Initialize local git for an Rgents project (no remote). See init_project.py.
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
exec python "$SCRIPT_DIR/init_project.py" "$@"
