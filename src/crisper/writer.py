"""Writer — atomic file writes with timestamped backups."""

from __future__ import annotations

import json
import os
import shutil
from datetime import datetime
from pathlib import Path

from .types import WriteResult


def create_backup(original_path: Path) -> Path:
    """Create a timestamped backup."""
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup = original_path.with_suffix(f".{ts}.jsonl.bak")
    shutil.copy2(original_path, backup)
    return backup


def atomic_write(target_path: Path, content: str) -> None:
    """Write via temp file + atomic rename."""
    tmp_path = target_path.with_suffix(".tmp")
    with open(tmp_path, "w", encoding="utf-8") as f:
        f.write(content)
        f.flush()
        os.fsync(f.fileno())
    os.rename(tmp_path, target_path)


def write_restructured(
    original_path: Path,
    restructured_path: Path,
    create_backup_flag: bool = True,
) -> WriteResult:
    """Replace original session with restructured version."""
    if not restructured_path.exists():
        return WriteResult(
            success=False,
            original_path=str(original_path),
            error=f"Restructured file not found: {restructured_path}",
        )

    # Verify valid JSONL
    content = restructured_path.read_text(encoding="utf-8")
    for i, line in enumerate(content.strip().split("\n")):
        if line.strip():
            try:
                json.loads(line)
            except json.JSONDecodeError as e:
                return WriteResult(
                    success=False,
                    original_path=str(original_path),
                    error=f"Invalid JSON on line {i + 1}: {e}",
                )

    bytes_before = original_path.stat().st_size
    bytes_after = len(content.encode("utf-8"))

    backup_path = ""
    if create_backup_flag:
        bp = create_backup(original_path)
        backup_path = str(bp)

    atomic_write(original_path, content)

    return WriteResult(
        success=True,
        original_path=str(original_path),
        backup_path=backup_path,
        bytes_before=bytes_before,
        bytes_after=bytes_after,
    )
