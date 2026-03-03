"""Session discovery — reuses cozempic if installed, falls back to standalone."""

from __future__ import annotations

import os
import sys
from pathlib import Path


def get_claude_dir() -> Path:
    config_dir = os.environ.get("CLAUDE_CONFIG_DIR")
    if config_dir:
        return Path(config_dir)
    return Path.home() / ".claude"


def resolve_session(session_arg: str) -> Path:
    """Resolve a session argument to a JSONL file path.

    Tries cozempic's session resolution first (if installed), falls back
    to standalone discovery.
    """
    # Try cozempic first (richer detection: PID, lsof, text matching)
    try:
        from cozempic.session import resolve_session as cozempic_resolve
        return cozempic_resolve(session_arg)
    except ImportError:
        pass

    # Standalone fallback
    if session_arg == "current":
        return _find_current_session()

    p = Path(session_arg)
    if p.exists() and p.suffix == ".jsonl":
        return p

    # Search by ID/prefix
    projects = get_claude_dir() / "projects"
    if projects.exists():
        for f in projects.rglob("*.jsonl"):
            if f.stem == session_arg or f.stem.startswith(session_arg):
                return f

    print(f"Error: Cannot find session '{session_arg}'", file=sys.stderr)
    sys.exit(1)


def _find_current_session() -> Path:
    """Find the most recently modified session for the current directory."""
    cwd = os.getcwd()
    slug = cwd.replace("/", "-")
    projects = get_claude_dir() / "projects"

    if not projects.exists():
        print("Error: No Claude projects found.", file=sys.stderr)
        sys.exit(1)

    # Match by CWD slug
    candidates = []
    for proj_dir in projects.iterdir():
        if not proj_dir.is_dir():
            continue
        if slug in proj_dir.name:
            for f in proj_dir.glob("*.jsonl"):
                if ".bak" not in f.name:
                    candidates.append(f)

    # Fallback: most recent across all projects
    if not candidates:
        for f in projects.rglob("*.jsonl"):
            if ".bak" not in f.name:
                candidates.append(f)

    if not candidates:
        print("Error: No sessions found.", file=sys.stderr)
        sys.exit(1)

    return max(candidates, key=lambda f: f.stat().st_mtime)
