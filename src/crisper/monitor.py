"""Feedback Monitor — detects when the gene failed to serve the model.

Runs after cultivation via hooks. Detects:
- Re-reads: model re-read a file that's in the gene file map
- Contradictions: model output contradicts a gene decision
- Repetitions: model tried an approach listed in the failure log
- Gaps: model needed information the gene doesn't have

Signals feed into the next Reflector cycle to improve cultivation.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from datetime import datetime

from .cultivator import is_cultivated, find_gene_boundary
from .analyzer import _load_messages, _get_type, _get_content_blocks, _all_text


FEEDBACK_FILE = ".crisper-feedback.json"


def get_feedback_path(session_path: Path) -> Path:
    """Get the feedback file path for a session."""
    return session_path.parent / FEEDBACK_FILE


def load_feedback(session_path: Path) -> list[dict]:
    """Load accumulated feedback signals."""
    fb_path = get_feedback_path(session_path)
    if fb_path.exists():
        try:
            return json.loads(fb_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            pass
    return []


def save_feedback(session_path: Path, signals: list[dict]) -> None:
    """Save feedback signals."""
    fb_path = get_feedback_path(session_path)
    fb_path.write_text(json.dumps(signals, indent=2), encoding="utf-8")


def add_signal(session_path: Path, signal_type: str, detail: str, turn: int = 0) -> None:
    """Add a single feedback signal."""
    signals = load_feedback(session_path)
    signals.append({
        "type": signal_type,
        "detail": detail,
        "turn": turn,
        "timestamp": datetime.now().isoformat(),
    })
    # Keep last 50 signals
    if len(signals) > 50:
        signals = signals[-50:]
    save_feedback(session_path, signals)


def detect_reread(session_path: Path, tool_name: str, file_path: str, turn: int) -> bool:
    """Detect if a Read tool call is re-reading a file in the gene.

    Called from PostToolUse hook. Returns True if this is a re-read
    (file already in gene file map).
    """
    if not is_cultivated(session_path):
        return False

    if tool_name not in ("Read", "read"):
        return False

    # Check if file is in the gene's file state map
    messages = _load_messages(session_path)
    gene_boundary = find_gene_boundary(session_path)

    for idx, msg in messages[:gene_boundary]:
        text = _all_text(msg)
        if file_path in text and ("File State Map" in text or "File:" in text):
            add_signal(session_path, "reread", f"Re-read {file_path} — already in gene file map", turn)
            return True

    return False


def detect_failed_approach_repetition(
    session_path: Path,
    tool_name: str,
    command: str,
    turn: int,
) -> bool:
    """Detect if a command/approach matches something in the failure log.

    Called from PostToolUse hook. Returns True if this looks like a
    repeated failed approach.
    """
    if not is_cultivated(session_path):
        return False

    messages = _load_messages(session_path)
    gene_boundary = find_gene_boundary(session_path)

    # Get failure log content
    failure_text = ""
    for idx, msg in messages[:gene_boundary]:
        text = _all_text(msg)
        if "Failure Log" in text or "Failed Approach" in text:
            failure_text += text

    if not failure_text:
        return False

    # Check if current command/approach matches any failure
    cmd_keywords = set(re.findall(r'\b\w{4,}\b', command.lower()))
    failure_keywords = set(re.findall(r'\b\w{4,}\b', failure_text.lower()))
    overlap = cmd_keywords & failure_keywords

    if len(overlap) >= 3:  # Threshold: 3+ shared keywords suggests repetition
        add_signal(
            session_path, "repetition",
            f"Approach may repeat failure: {command[:100]} (shared: {', '.join(list(overlap)[:5])})",
            turn,
        )
        return True

    return False


def analyze_tail_for_feedback(session_path: Path) -> list[dict]:
    """Analyze the uncultivated tail for feedback signals.

    Run before cultivation to detect issues in the tail that indicate
    the gene needs improvement.
    """
    if not is_cultivated(session_path):
        return []

    messages = _load_messages(session_path)
    gene_boundary = find_gene_boundary(session_path)
    tail = messages[gene_boundary:]
    signals = []

    # Get gene content for comparison
    gene_text = ""
    for idx, msg in messages[:gene_boundary]:
        gene_text += _all_text(msg) + "\n"

    for pos, (idx, msg) in enumerate(tail):
        mtype = _get_type(msg)
        blocks = _get_content_blocks(msg)

        for block in blocks:
            # Detect re-reads
            if block.get("type") == "tool_use" and block.get("name") in ("Read", "read"):
                fp = block.get("input", {}).get("file_path", "")
                if fp and fp in gene_text:
                    signals.append({
                        "type": "reread",
                        "detail": f"Re-read {fp} at tail position {pos}",
                        "turn": gene_boundary + pos,
                    })

            # Detect user corrections
            if mtype == "user":
                text = _all_text(msg)
                correction_patterns = [
                    r"i already (told|said|mentioned)",
                    r"no,? (i meant|that's not|i said)",
                    r"we already (decided|discussed|did)",
                    r"remember (when|that|we)",
                ]
                for pattern in correction_patterns:
                    if re.search(pattern, text, re.I):
                        signals.append({
                            "type": "user_correction",
                            "detail": f"User correction detected: {text[:100]}",
                            "turn": gene_boundary + pos,
                        })
                        break

    return signals


def get_feedback_summary(session_path: Path) -> dict:
    """Get a summary of feedback signals for the Reflector."""
    signals = load_feedback(session_path)
    tail_signals = analyze_tail_for_feedback(session_path)
    all_signals = signals + tail_signals

    summary = {
        "total_signals": len(all_signals),
        "rereads": [s for s in all_signals if s["type"] == "reread"],
        "repetitions": [s for s in all_signals if s["type"] == "repetition"],
        "user_corrections": [s for s in all_signals if s["type"] == "user_correction"],
        "contradictions": [s for s in all_signals if s["type"] == "contradiction"],
        "gaps": [s for s in all_signals if s["type"] == "gap"],
    }

    # Generate improvement suggestions
    suggestions = []
    if summary["rereads"]:
        files = [s["detail"] for s in summary["rereads"]]
        suggestions.append(f"Gene file map needs more detail for: {', '.join(set(f[:50] for f in files[:5]))}")
    if summary["repetitions"]:
        suggestions.append("Failure log not prominent enough — model is repeating failed approaches")
    if summary["user_corrections"]:
        suggestions.append("Gene is missing information the user expects to be remembered")

    summary["suggestions"] = suggestions
    return summary
