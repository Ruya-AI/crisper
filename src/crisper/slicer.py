"""Stage 1: Structural Slicer — parse raw JSONL into typed chunks.

Pure JSON parsing, no LLM. Groups messages into meaningful chunks
(turn pairs, tool sequences, sidechains) and extracts metadata.
Drops zero-value messages (progress, file-history-snapshot).
Separates sacred recent window.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from .analyzer import _get_type, _get_content_blocks, _all_text, _load_messages


@dataclass
class Chunk:
    """A structural unit from a raw JSONL session."""

    index: int
    chunk_type: str  # "turn_pair" | "tool_sequence" | "sidechain" | "system"
    messages: list[dict] = field(default_factory=list)
    line_indices: list[int] = field(default_factory=list)
    metadata: dict = field(default_factory=dict)
    text_preview: str = ""

    def byte_count(self) -> int:
        return sum(len(json.dumps(m, separators=(",", ":"))) for m in self.messages)


@dataclass
class SliceResult:
    """Output of the slicer."""

    chunks: list[Chunk]
    sacred_lines: list[str]  # raw JSONL lines for sacred recent window
    sacred_start_index: int  # line index where sacred window begins
    dropped_count: int  # progress + file-history messages dropped
    total_messages: int


# Message types that carry zero information value
_DROP_TYPES = frozenset({"progress", "file-history-snapshot"})


def slice_session(
    session_path: Path,
    gene_boundary: int = 0,
    recent_window: int = 10,
) -> SliceResult:
    """Slice a session JSONL into structural chunks.

    Args:
        session_path: Path to session JSONL file.
        gene_boundary: Line index where gene ends (0 = no gene, all raw).
        recent_window: Number of recent user turns to keep sacred.

    Returns:
        SliceResult with chunks, sacred lines, and stats.
    """
    messages = _load_messages(session_path)
    total = len(messages)

    # Split gene / tail
    tail = [(idx, msg) for idx, msg in messages if idx >= gene_boundary]

    # Find sacred boundary (last N user turns)
    user_positions = [
        i for i, (idx, msg) in enumerate(tail)
        if _get_type(msg) == "user"
        and not msg.get("isSidechain")
        and "<system-reminder>" not in _all_text(msg)[:50]
    ]
    if len(user_positions) > recent_window:
        sacred_pos = user_positions[-recent_window]
    else:
        sacred_pos = 0

    # Extract sacred lines (raw JSONL)
    sacred_lines = []
    sacred_start_index = tail[sacred_pos][0] if sacred_pos < len(tail) else -1
    with open(session_path, "r", encoding="utf-8") as f:
        for i, line in enumerate(f):
            if i >= sacred_start_index and sacred_start_index >= 0:
                line = line.strip()
                if line:
                    sacred_lines.append(line)

    # Process cultivatable portion (before sacred window)
    cultivatable = tail[:sacred_pos] if sacred_pos > 0 else []

    chunks: list[Chunk] = []
    dropped = 0
    chunk_idx = 0
    i = 0

    while i < len(cultivatable):
        idx, msg = cultivatable[i]
        mtype = _get_type(msg)

        # Drop zero-value messages
        if mtype in _DROP_TYPES:
            dropped += 1
            i += 1
            continue

        # Sidechain grouping
        if msg.get("isSidechain"):
            chunk, consumed = _collect_sidechain(cultivatable, i, chunk_idx)
            chunks.append(chunk)
            chunk_idx += 1
            i += consumed
            continue

        # System reminder
        if mtype == "user" and _is_system_reminder(msg):
            chunks.append(_make_chunk(chunk_idx, "system", [(idx, msg)]))
            chunk_idx += 1
            i += 1
            continue

        # Turn pair: user → assistant (possibly with tool sequences between)
        if mtype == "user":
            chunk, consumed = _collect_turn_pair(cultivatable, i, chunk_idx)
            chunks.append(chunk)
            chunk_idx += 1
            i += consumed
            continue

        # Assistant message without preceding user (continuation)
        if mtype == "assistant":
            chunk, consumed = _collect_tool_sequence(cultivatable, i, chunk_idx)
            chunks.append(chunk)
            chunk_idx += 1
            i += consumed
            continue

        # Fallback: single message chunk
        chunks.append(_make_chunk(chunk_idx, "turn_pair", [(idx, msg)]))
        chunk_idx += 1
        i += 1

    return SliceResult(
        chunks=chunks,
        sacred_lines=sacred_lines,
        sacred_start_index=sacred_start_index,
        dropped_count=dropped,
        total_messages=total,
    )


def _collect_turn_pair(
    messages: list[tuple[int, dict]], start: int, chunk_idx: int
) -> tuple[Chunk, int]:
    """Collect a user message + its assistant response + any tool sequences."""
    collected = [messages[start]]
    i = start + 1

    while i < len(messages):
        idx, msg = messages[i]
        mtype = _get_type(msg)

        if mtype in _DROP_TYPES:
            i += 1
            continue

        if msg.get("isSidechain"):
            break

        if mtype == "assistant":
            collected.append((idx, msg))
            i += 1
            # Continue collecting tool results that follow
            while i < len(messages):
                next_type = _get_type(messages[i][1])
                if next_type in _DROP_TYPES:
                    i += 1
                    continue
                if next_type == "assistant" and not messages[i][1].get("isSidechain"):
                    collected.append(messages[i])
                    i += 1
                else:
                    break
            break

        # Skip system reminders between user and assistant
        if mtype == "user" and _is_system_reminder(msg):
            i += 1
            continue

        # Another user message = new turn
        if mtype == "user":
            break

        i += 1

    return _make_chunk(chunk_idx, "turn_pair", collected), i - start


def _collect_tool_sequence(
    messages: list[tuple[int, dict]], start: int, chunk_idx: int
) -> tuple[Chunk, int]:
    """Collect consecutive assistant messages (tool calls + responses)."""
    collected = [messages[start]]
    i = start + 1

    while i < len(messages):
        idx, msg = messages[i]
        mtype = _get_type(msg)

        if mtype in _DROP_TYPES:
            i += 1
            continue

        if mtype == "assistant" and not msg.get("isSidechain"):
            collected.append((idx, msg))
            i += 1
        else:
            break

    return _make_chunk(chunk_idx, "tool_sequence", collected), i - start


def _collect_sidechain(
    messages: list[tuple[int, dict]], start: int, chunk_idx: int
) -> tuple[Chunk, int]:
    """Collect consecutive sidechain messages."""
    collected = [messages[start]]
    i = start + 1

    while i < len(messages):
        idx, msg = messages[i]
        if msg.get("isSidechain"):
            collected.append((idx, msg))
            i += 1
        else:
            break

    return _make_chunk(chunk_idx, "sidechain", collected), i - start


def _is_system_reminder(msg: dict) -> bool:
    """Check if a user message is a system reminder."""
    text = _all_text(msg)
    return text.strip().startswith("<system-reminder>")


def _make_chunk(
    index: int, chunk_type: str, indexed_messages: list[tuple[int, dict]]
) -> Chunk:
    """Build a Chunk from indexed messages, extracting metadata."""
    line_indices = [idx for idx, _ in indexed_messages]
    messages = [msg for _, msg in indexed_messages]

    # Extract metadata
    tool_names: list[str] = []
    file_paths: list[str] = []
    has_error = False

    for msg in messages:
        for block in _get_content_blocks(msg):
            btype = block.get("type", "")
            if btype == "tool_use":
                name = block.get("name", "")
                if name:
                    tool_names.append(name)
                inp = block.get("input", {})
                fp = inp.get("file_path") or inp.get("path") or ""
                if fp:
                    file_paths.append(fp)
                cmd = inp.get("command", "")
                if cmd:
                    file_paths.append(f"bash:{cmd[:80]}")
            elif btype == "tool_result":
                if block.get("is_error"):
                    has_error = True

    # Build text preview (readable content for LLM classification)
    preview_parts = []
    for msg in messages:
        mtype = _get_type(msg)
        text = _all_text(msg)
        if text and len(text) > 5:
            prefix = f"[{mtype}]"
            if tool_names:
                prefix += f" [{','.join(list(set(tool_names))[:3])}]"
            preview_parts.append(f"{prefix} {text[:500]}")

    text_preview = "\n".join(preview_parts)[:2000]

    metadata = {
        "tool_names": list(set(tool_names)),
        "file_paths": list(set(file_paths)),
        "has_error": has_error,
        "message_count": len(messages),
    }

    return Chunk(
        index=index,
        chunk_type=chunk_type,
        messages=messages,
        line_indices=line_indices,
        metadata=metadata,
        text_preview=text_preview,
    )


def chunks_to_json(chunks: list[Chunk]) -> list[dict]:
    """Serialize chunks for JSON output (CLI + subagent consumption)."""
    return [
        {
            "index": c.index,
            "chunk_type": c.chunk_type,
            "line_range": [c.line_indices[0], c.line_indices[-1]] if c.line_indices else [],
            "metadata": c.metadata,
            "text_preview": c.text_preview,
        }
        for c in chunks
    ]
