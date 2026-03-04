"""Archive — retrievable storage for raw turns moved out of the gene.

The archive grows monotonically as cultivation cycles move raw turns
out of the active gene. Content is retrievable via line numbers or
keyword search (breadcrumbs point here).
"""

from __future__ import annotations

import json
import re
from pathlib import Path


def get_archive_path(session_path: Path) -> Path:
    """Get the archive file path for a session."""
    return session_path.with_suffix(".archive.jsonl")


def archive_exists(session_path: Path) -> bool:
    """Check if an archive file exists for this session."""
    return get_archive_path(session_path).exists()


def archive_stats(session_path: Path) -> dict:
    """Get archive statistics."""
    archive = get_archive_path(session_path)
    if not archive.exists():
        return {"exists": False, "lines": 0, "bytes": 0}

    lines = 0
    with open(archive, "r", encoding="utf-8") as f:
        for _ in f:
            lines += 1

    return {
        "exists": True,
        "lines": lines,
        "bytes": archive.stat().st_size,
        "path": str(archive),
    }


def retrieve_lines(session_path: Path, start: int, end: int | None = None) -> list[dict]:
    """Retrieve specific lines from the archive.

    Args:
        session_path: The session JSONL (archive path derived from it).
        start: Starting line number (1-indexed).
        end: Ending line number (inclusive). None = just the start line.

    Returns:
        List of parsed message dicts.
    """
    archive = get_archive_path(session_path)
    if not archive.exists():
        return []

    if end is None:
        end = start

    results = []
    with open(archive, "r", encoding="utf-8") as f:
        for i, line in enumerate(f, 1):
            if i < start:
                continue
            if i > end:
                break
            line = line.strip()
            if line:
                try:
                    results.append(json.loads(line))
                except json.JSONDecodeError:
                    results.append({"_raw": line, "_line": i})

    return results


def retrieve_search(session_path: Path, query: str, max_results: int = 10) -> list[dict]:
    """Search the archive for lines containing a keyword.

    Returns list of dicts with: line_number, type, preview, content.
    """
    archive = get_archive_path(session_path)
    if not archive.exists():
        return []

    results = []
    query_lower = query.lower()

    with open(archive, "r", encoding="utf-8") as f:
        for i, line in enumerate(f, 1):
            if query_lower in line.lower():
                line = line.strip()
                try:
                    msg = json.loads(line)
                    mtype = msg.get("type", "unknown")
                    # Extract text content for preview
                    inner = msg.get("message", {})
                    content = inner.get("content", "")
                    if isinstance(content, list):
                        texts = []
                        for block in content:
                            if isinstance(block, dict):
                                t = block.get("text", "") or block.get("content", "")
                                if isinstance(t, str):
                                    texts.append(t)
                        content = " ".join(texts)
                    preview = content[:200] if isinstance(content, str) else str(content)[:200]

                    results.append({
                        "line": i,
                        "type": mtype,
                        "preview": preview,
                    })
                except json.JSONDecodeError:
                    results.append({
                        "line": i,
                        "type": "unparseable",
                        "preview": line[:200],
                    })

                if len(results) >= max_results:
                    break

    return results


def retrieve_context(session_path: Path, line: int, context: int = 5) -> list[dict]:
    """Retrieve a line from the archive with surrounding context.

    Returns lines [line-context, line+context] with the target line marked.
    """
    start = max(1, line - context)
    end = line + context
    lines = retrieve_lines(session_path, start, end)

    results = []
    for i, msg in enumerate(lines):
        actual_line = start + i
        results.append({
            "line": actual_line,
            "is_target": actual_line == line,
            "message": msg,
        })

    return results
