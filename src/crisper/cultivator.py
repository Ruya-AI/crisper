"""GoF Cultivator — continuous context cultivation via gene model.

The gene model:
  - The session JSONL IS the gene (primary source of truth)
  - Gene = [9 cultivated sections] + [raw uncultivated tail]
  - Archive = all raw turns ever, indexed for breadcrumb retrieval
  - Cultivation: absorb tail into sections → move tail to archive → write updated gene

This module handles:
  1. Detecting whether a session has been cultivated (has gene sections)
  2. Splitting the gene from the uncultivated tail
  3. Moving raw turns to the archive
  4. Preparing the cultivation prompt for the subagent
  5. Writing the updated gene back to the session file
  6. Kill + resume (daemon mode, like cozempic reload)
"""

from __future__ import annotations

import json
import os
import platform
import shutil
import subprocess
import uuid as uuid_mod
from datetime import datetime
from pathlib import Path

from .analyzer import analyze_session, _load_messages
from .writer import create_backup, atomic_write

# Gene section markers — these identify cultivated content
GENE_MARKER = "gene:"  # Matches "[gene:v1]" in user messages
GENE_VERSION = "v1"
SECTION_MARKERS = [
    "System Identity",
    "Live State Document",
    "Failure Log",
    "Subgoal Tree",
    "Compressed History",
    "Knowledge Base",
    "Breadcrumbs",
    "Recent Turns",
    "Objectives",
]


def is_cultivated(session_path: Path) -> bool:
    """Check if a session has been cultivated (contains gene sections)."""
    try:
        with open(session_path, "r", encoding="utf-8") as f:
            for line in f:
                if GENE_MARKER in line:
                    return True
                # Only check first 10 lines
                break
        # Check first message content
        first_line = session_path.read_text(encoding="utf-8").split("\n")[0]
        if first_line.strip():
            msg = json.loads(first_line)
            content = msg.get("message", {}).get("content", "")
            if isinstance(content, str) and GENE_MARKER in content:
                return True
            if isinstance(content, list):
                for block in content:
                    if isinstance(block, dict):
                        text = block.get("text", "")
                        if isinstance(text, str) and GENE_MARKER in text:
                            return True
    except (OSError, json.JSONDecodeError):
        pass
    return False


def find_gene_boundary(session_path: Path) -> int:
    """Find the line index where cultivated sections end and raw tail begins.

    Returns the line number of the first non-gene message.
    If not cultivated, returns 0 (everything is raw).

    Gene sections come in user/assistant pairs. The user message has the
    gene: marker, the assistant message has the content. Both are gene lines.
    """
    if not is_cultivated(session_path):
        return 0

    with open(session_path, "r", encoding="utf-8") as f:
        lines = f.readlines()

    def _has_marker(line_text: str) -> bool:
        try:
            msg = json.loads(line_text)
        except json.JSONDecodeError:
            return False
        content = msg.get("message", {}).get("content", "")
        if isinstance(content, str):
            return GENE_MARKER in content or any(m in content for m in SECTION_MARKERS)
        if isinstance(content, list):
            for block in content:
                if isinstance(block, dict):
                    text = block.get("text", "")
                    if isinstance(text, str) and (GENE_MARKER in text or any(m in text for m in SECTION_MARKERS)):
                        return True
        return False

    # Find the last consecutive line that's part of the gene
    # Gene = user/assistant pairs where the USER has the marker
    # The assistant response after a marked user is also gene
    last_gene_line = -1
    prev_was_marker = False

    for i, line in enumerate(lines):
        line = line.strip()
        if not line:
            continue

        if _has_marker(line):
            last_gene_line = i
            prev_was_marker = True
        elif prev_was_marker:
            # Assistant response after a gene user message — also gene
            last_gene_line = i
            prev_was_marker = False
        else:
            # Neither marker nor response to marker — this is raw tail
            break

    return last_gene_line + 1 if last_gene_line >= 0 else 0


def get_archive_path(session_path: Path) -> Path:
    """Get the archive file path for a session."""
    return session_path.with_suffix(".archive.jsonl")


def move_tail_to_archive(session_path: Path, gene_boundary: int) -> int:
    """Move uncultivated tail from the gene to the archive.

    Returns the number of lines moved.
    """
    archive_path = get_archive_path(session_path)

    with open(session_path, "r", encoding="utf-8") as f:
        lines = f.readlines()

    tail_lines = lines[gene_boundary:]
    if not tail_lines:
        return 0

    # Append to archive
    with open(archive_path, "a", encoding="utf-8") as f:
        for line in tail_lines:
            f.write(line)

    return len(tail_lines)


def build_gene_jsonl(
    sections: dict[str, str],
    session_id: str,
    recent_turns: list[str] | None = None,
) -> str:
    """Build the gene JSONL from section contents.

    Each section becomes a user/assistant message pair.
    Returns the complete JSONL string.
    """
    lines = []
    prev_uuid = "00000000-0000-0000-0000-000000000000"
    timestamp = datetime.now().isoformat()

    section_order = [
        ("System Identity", sections.get("system_identity", "")),
        ("Live State Document", sections.get("live_state", "")),
        ("Failure Log", sections.get("failure_log", "")),
        ("Subgoal Tree", sections.get("subgoal_tree", "")),
        ("Compressed History", sections.get("compressed_history", "")),
        ("Knowledge Base", sections.get("knowledge_base", "")),
        ("Breadcrumbs", sections.get("breadcrumbs", "")),
    ]

    for i, (section_name, content) in enumerate(section_order):
        if not content:
            content = "(empty)"

        user_uuid = str(uuid_mod.uuid4())
        asst_uuid = str(uuid_mod.uuid4())

        # Attention sink: first message starts with high-information project name
        # StreamingLLM (ICLR 2024): first 4 tokens get disproportionate attention
        if i == 0:
            # Extract project name from content for the attention anchor
            project_hint = content.split("\n")[0][:80] if content else "Project Context"
            user_content = f"{project_hint} — {section_name} [gene:{GENE_VERSION}]"
        else:
            user_content = f"[gene:{GENE_VERSION}] {section_name}"

        user_msg = {
            "type": "user",
            "uuid": user_uuid,
            "parentUuid": prev_uuid,
            "sessionId": session_id,
            "timestamp": timestamp,
            "isSidechain": False,
            "userType": "external",
            "message": {
                "role": "user",
                "content": user_content,
            },
        }

        asst_msg = {
            "type": "assistant",
            "uuid": asst_uuid,
            "parentUuid": user_uuid,
            "sessionId": session_id,
            "timestamp": timestamp,
            "isSidechain": False,
            "message": {
                "role": "assistant",
                "content": [{"type": "text", "text": content}],
            },
        }

        lines.append(json.dumps(user_msg, separators=(",", ":")))
        lines.append(json.dumps(asst_msg, separators=(",", ":")))
        prev_uuid = asst_uuid

    # Recent turns (sacred, copied verbatim)
    if recent_turns:
        # Fix the parentUuid chain: first recent turn connects to last gene section
        for i, turn_line in enumerate(recent_turns):
            try:
                msg = json.loads(turn_line)
                if i == 0:
                    msg["parentUuid"] = prev_uuid
                lines.append(json.dumps(msg, separators=(",", ":")))
                prev_uuid = msg.get("uuid", prev_uuid)
            except json.JSONDecodeError:
                lines.append(turn_line.strip())

    # Objectives section (at the very end — highest attention position)
    objectives = sections.get("objectives", "(no objectives set)")
    user_uuid = str(uuid_mod.uuid4())
    asst_uuid = str(uuid_mod.uuid4())

    user_msg = {
        "type": "user",
        "uuid": user_uuid,
        "parentUuid": prev_uuid,
        "sessionId": session_id,
        "timestamp": timestamp,
        "isSidechain": False,
        "userType": "external",
        "message": {
            "role": "user",
            "content": f"[CRISPER GENE {GENE_VERSION} — Objectives + Next Steps]",
        },
    }

    asst_msg = {
        "type": "assistant",
        "uuid": asst_uuid,
        "parentUuid": user_uuid,
        "sessionId": session_id,
        "timestamp": timestamp,
        "isSidechain": False,
        "message": {
            "role": "assistant",
            "content": [{"type": "text", "text": objectives}],
        },
    }

    lines.append(json.dumps(user_msg, separators=(",", ":")))
    lines.append(json.dumps(asst_msg, separators=(",", ":")))

    return "\n".join(lines) + "\n"


def prepare_cultivation_prompt(
    session_path: Path,
    recent_window: int = 10,
) -> dict:
    """Prepare everything the subagent needs for cultivation.

    Returns a dict with:
      - analysis: the structured analysis (JSON string)
      - gene_sections: current gene sections (if cultivated before)
      - raw_tail: the uncultivated turns (JSONL string)
      - recent_turns: the sacred recent turns (list of JSONL lines)
      - session_id: for building the new gene
      - archive_path: where raw turns should go
    """
    analysis = analyze_session(session_path, recent_window=recent_window)
    messages = _load_messages(session_path)

    session_id = session_path.stem

    # Split into gene sections + raw tail + recent turns
    gene_boundary = find_gene_boundary(session_path)

    with open(session_path, "r", encoding="utf-8") as f:
        all_lines = f.readlines()

    # Gene sections (if cultivated)
    gene_lines = all_lines[:gene_boundary] if gene_boundary > 0 else []

    # Raw tail (uncultivated)
    tail_lines = all_lines[gene_boundary:]

    # Recent turns from tail (last N user messages + their responses)
    recent_start = max(0, len(tail_lines) - recent_window * 3)  # ~3 lines per turn
    recent_lines = tail_lines[recent_start:]
    cultivatable_lines = tail_lines[:recent_start]

    from .engineer import build_full_analysis_json
    analysis_json = build_full_analysis_json(analysis)

    return {
        "analysis": analysis_json,
        "gene_sections_text": "".join(gene_lines),
        "raw_tail": "".join(cultivatable_lines),
        "recent_turns": [l.strip() for l in recent_lines if l.strip()],
        "session_id": session_id,
        "archive_path": str(get_archive_path(session_path)),
        "session_path": str(session_path),
        "total_tail_lines": len(tail_lines),
        "cultivatable_lines": len(cultivatable_lines),
        "recent_lines": len(recent_lines),
    }


def cultivate(
    session_path: Path,
    sections: dict[str, str],
    recent_turns: list[str],
    recent_window: int = 10,
) -> dict:
    """Execute the cultivation: write gene, archive tail, backup.

    Args:
        session_path: The session JSONL file.
        sections: Dict of section_name → content (from subagent).
        recent_turns: List of JSONL lines to preserve verbatim.
        recent_window: Number of recent turns to keep.

    Returns:
        Dict with: success, backup_path, archive_lines, gene_lines, bytes_before, bytes_after
    """
    session_id = session_path.stem
    bytes_before = session_path.stat().st_size

    # 1. Backup
    backup_path = create_backup(session_path)

    # 2. Move raw tail to archive (before overwriting)
    gene_boundary = find_gene_boundary(session_path)
    archived = move_tail_to_archive(session_path, gene_boundary)

    # 3. Build new gene
    gene_content = build_gene_jsonl(sections, session_id, recent_turns)

    # 4. Atomic write
    atomic_write(session_path, gene_content)

    bytes_after = session_path.stat().st_size
    gene_lines = len(gene_content.strip().split("\n"))

    return {
        "success": True,
        "backup_path": str(backup_path),
        "archive_lines": archived,
        "gene_lines": gene_lines,
        "bytes_before": bytes_before,
        "bytes_after": bytes_after,
    }


def prepare_chunks(
    session_path: Path,
    recent_window: int = 10,
) -> dict:
    """Prepare cultivation data using the structural slicer (v2 pipeline).

    Returns a dict with:
      - chunks: serialized chunk list for LLM classification
      - sacred_lines: recent turns to preserve verbatim
      - session_id: for building the new gene
      - stats: slicing statistics
    """
    from .slicer import slice_session, chunks_to_json

    gene_boundary = find_gene_boundary(session_path)
    result = slice_session(session_path, gene_boundary, recent_window)

    return {
        "chunks": chunks_to_json(result.chunks),
        "sacred_lines": result.sacred_lines,
        "sacred_start_index": result.sacred_start_index,
        "session_id": session_path.stem,
        "session_path": str(session_path),
        "archive_path": str(get_archive_path(session_path)),
        "gene_boundary": gene_boundary,
        "is_cultivated": gene_boundary > 0,
        "stats": {
            "total_messages": result.total_messages,
            "chunks": len(result.chunks),
            "sacred_lines": len(result.sacred_lines),
            "dropped": result.dropped_count,
        },
    }


def find_claude_pid() -> int | None:
    """Find the Claude Code process PID."""
    try:
        from cozempic.session import find_claude_pid as coz_find
        return coz_find()
    except ImportError:
        pass
    # Standalone fallback
    ppid = os.getppid()
    return ppid if ppid > 1 else None


def spawn_resume_watcher(claude_pid: int, project_dir: str, session_id: str) -> None:
    """Spawn a detached watcher that resumes Claude after exit."""
    system = platform.system()
    resume_flag = f"--resume {session_id}"

    if system == "Darwin":
        inner = f"cd '{project_dir}' && claude {resume_flag}"
        resume_cmd = f"osascript -e 'tell application \"Terminal\" to do script \"{inner}\"'"
    elif system == "Linux":
        inner = f"cd '{project_dir}' && claude {resume_flag}; exec bash"
        resume_cmd = (
            f"if command -v gnome-terminal >/dev/null 2>&1; then "
            f"gnome-terminal -- bash -c '{inner}'; "
            f"elif command -v xterm >/dev/null 2>&1; then "
            f"xterm -e '{inner}' & fi"
        )
    else:
        return

    watcher = (
        f"while kill -0 {claude_pid} 2>/dev/null; do sleep 1; done; "
        f"sleep 1; {resume_cmd}"
    )

    subprocess.Popen(
        ["bash", "-c", watcher],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        stdin=subprocess.DEVNULL,
        start_new_session=True,
    )
