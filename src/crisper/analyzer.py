"""Phase 1: Analyze — extract structured pieces from JSONL session.

This phase is entirely local (no LLM calls). It reads the session file
and extracts decisions, file changes, error chains, references, failed
attempts, current state, and task boundaries.

This does 80% of the work — the LLM in Phase 2 only needs to compose
these pieces into optimal structure.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from .types import (
    AnalysisResult,
    Decision,
    ErrorChain,
    FailedAttempt,
    FileChange,
    Reference,
)


# ─── Message helpers (minimal, avoid depending on cozempic) ──────────────────

def _get_type(msg: dict) -> str:
    return msg.get("type", "unknown")


def _get_content_blocks(msg: dict) -> list[dict]:
    inner = msg.get("message", {})
    content = inner.get("content", [])
    if isinstance(content, str):
        return [{"type": "text", "text": content}]
    if isinstance(content, list):
        return content
    return []


def _text_of(block: dict) -> str:
    return block.get("text", "") or block.get("thinking", "") or ""


def _load_messages(path: Path) -> list[tuple[int, dict]]:
    """Load JSONL file. Returns list of (line_index, message_dict)."""
    messages = []
    with open(path, "r", encoding="utf-8") as f:
        for i, line in enumerate(f):
            line = line.strip()
            if not line:
                continue
            try:
                messages.append((i, json.loads(line)))
            except json.JSONDecodeError:
                continue
    return messages


# ─── Extraction patterns ─────────────────────────────────────────────────────

_URL_RE = re.compile(r'https?://[^\s<>"\')\]]+')
_FILE_PATH_RE = re.compile(r'(?:/[\w./-]+\.[\w]+)')
_DECISION_WORDS = re.compile(
    r'\b(decided|chose|going with|will use|switched to|opted for|'
    r'let\'s go with|using|selected|picked|settled on)\b',
    re.IGNORECASE,
)
_ERROR_WORDS = re.compile(
    r'\b(error|failed|exception|traceback|bug|issue|crash|broken|'
    r'fix|fixed|resolved|workaround)\b',
    re.IGNORECASE,
)


def analyze_session(path: Path, recent_window: int = 10) -> AnalysisResult:
    """Extract structured pieces from a session JSONL file.

    Args:
        path: Path to the JSONL session file.
        recent_window: Number of recent turns to preserve verbatim (default 10).

    Returns:
        AnalysisResult with all extracted pieces.
    """
    messages = _load_messages(path)
    result = AnalysisResult(total_turns=len(messages))

    # Detect model
    for _, msg in reversed(messages):
        if _get_type(msg) == "assistant":
            inner = msg.get("message", {})
            model = inner.get("model", "")
            if model:
                result.model = model
                break

    # Token count from last assistant usage
    for _, msg in reversed(messages):
        if _get_type(msg) == "assistant" and not msg.get("isSidechain"):
            usage = msg.get("message", {}).get("usage", {})
            if usage:
                result.token_count = (
                    usage.get("input_tokens", 0)
                    + usage.get("cache_creation_input_tokens", 0)
                    + usage.get("cache_read_input_tokens", 0)
                )
                break

    # Recent turn boundary
    user_turn_indices = []
    for i, (idx, msg) in enumerate(messages):
        if _get_type(msg) == "user" and not msg.get("isSidechain"):
            user_turn_indices.append(i)

    if len(user_turn_indices) > recent_window:
        result.recent_turn_start = user_turn_indices[-recent_window]
    else:
        result.recent_turn_start = 0

    # Extract session intent from first user message
    for _, msg in messages:
        if _get_type(msg) == "user":
            blocks = _get_content_blocks(msg)
            for b in blocks:
                text = _text_of(b)
                if text and len(text) > 10:
                    result.session_intent = text[:500]
                    break
            if result.session_intent:
                break

    # Scan all messages for structured pieces
    for pos, (idx, msg) in enumerate(messages):
        mtype = _get_type(msg)
        blocks = _get_content_blocks(msg)

        for block in blocks:
            btype = block.get("type", "")

            # File changes from tool_use
            if btype == "tool_use":
                name = block.get("name", "")
                inp = block.get("input", {})

                if name in ("Write", "write"):
                    fp = inp.get("file_path", "")
                    if fp:
                        result.file_changes.append(FileChange(
                            path=fp, action="created", turn_index=pos,
                        ))
                elif name in ("Edit", "edit"):
                    fp = inp.get("file_path", "")
                    if fp:
                        result.file_changes.append(FileChange(
                            path=fp, action="modified", turn_index=pos,
                        ))

            # Text analysis
            text = _text_of(block)
            if not text or len(text) < 10:
                continue

            # Decisions
            if _DECISION_WORDS.search(text) and mtype in ("assistant", "user"):
                # Extract the sentence containing the decision word
                for sentence in re.split(r'[.!?\n]', text):
                    if _DECISION_WORDS.search(sentence) and len(sentence.strip()) > 15:
                        result.decisions.append(Decision(
                            summary=sentence.strip()[:300],
                            turn_index=pos,
                        ))
                        break

            # Error chains
            if _ERROR_WORDS.search(text) and mtype == "assistant":
                for sentence in re.split(r'[.!?\n]', text):
                    if _ERROR_WORDS.search(sentence) and len(sentence.strip()) > 15:
                        result.error_chains.append(ErrorChain(
                            error=sentence.strip()[:300],
                            turn_index=pos,
                        ))
                        break

            # URLs / references
            urls = _URL_RE.findall(text)
            for url in urls:
                if not any(r.url == url for r in result.references):
                    context_match = re.search(
                        rf'.{{0,50}}{re.escape(url)}.{{0,50}}', text,
                    )
                    result.references.append(Reference(
                        url=url,
                        context=context_match.group(0) if context_match else "",
                        turn_index=pos,
                    ))

    # Extract current task from last user message
    for _, msg in reversed(messages):
        if _get_type(msg) == "user" and not msg.get("isSidechain"):
            blocks = _get_content_blocks(msg)
            for b in blocks:
                text = _text_of(b)
                # Skip system-reminder content
                if text and "<system-reminder>" not in text and len(text) > 5:
                    result.current_task = text[:300]
                    break
            if result.current_task:
                break

    # Deduplicate file changes — keep last action per path
    seen_files: dict[str, FileChange] = {}
    for fc in result.file_changes:
        seen_files[fc.path] = fc
    result.file_changes = list(seen_files.values())

    return result
