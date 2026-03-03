"""Message importance scoring for context engineering.

Scores each message 0.0-1.0 based on information value.
Used by subagent to prioritize what to preserve vs compress.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from .analyzer import _get_type, _get_content_blocks, _all_text, _load_messages
from .types import AnalysisResult, MessageScore

# Category base scores
_BASE_SCORES: dict[str, float] = {
    "user_request": 0.8,
    "decision": 0.9,
    "error_fix": 0.85,
    "file_change": 0.7,
    "file_read": 0.2,
    "tool_output_large": 0.15,
    "tool_output_small": 0.4,
    "progress": 0.0,
    "file_history": 0.0,
    "system_reminder": 0.1,
    "thinking": 0.0,
    "conversation": 0.5,
    "team_coordination": 0.85,
}


def _categorize(pos: int, msg: dict, analysis: AnalysisResult) -> str:
    """Categorize a message for scoring."""
    mtype = _get_type(msg)

    if mtype == "progress":
        return "progress"
    if mtype == "file-history-snapshot":
        return "file_history"

    # Check if this turn is associated with extracted pieces
    decision_turns = {d.turn_index for d in analysis.decisions}
    error_turns = {e.turn_index for e in analysis.error_chains}
    file_turns = {f.turn_index for f in analysis.file_changes}

    if pos in decision_turns:
        return "decision"
    if pos in error_turns:
        return "error_fix"
    if pos in file_turns:
        return "file_change"

    # Check content blocks
    blocks = _get_content_blocks(msg)
    for block in blocks:
        btype = block.get("type", "")
        if btype == "tool_use":
            name = block.get("name", "")
            if name in ("Read", "read", "Glob", "glob", "Grep", "grep"):
                return "file_read"
            if name in ("Task", "TaskCreate", "TeamCreate", "SendMessage"):
                return "team_coordination"
        if btype == "tool_result":
            content = block.get("content", "")
            if isinstance(content, str) and len(content) > 4096:
                return "tool_output_large"
            return "tool_output_small"

    text = _all_text(msg)
    if text and "<system-reminder>" in text:
        return "system_reminder"

    if mtype == "user":
        return "user_request"

    return "conversation"


def score_messages(
    path: Path,
    analysis: AnalysisResult,
    recent_window: int = 10,
) -> list[MessageScore]:
    """Score every message in the session by importance."""
    messages = _load_messages(path)
    scores = []

    for pos, (idx, msg) in enumerate(messages):
        category = _categorize(pos, msg, analysis)
        base = _BASE_SCORES.get(category, 0.5)
        score = base

        # Boost for messages referenced by decisions
        if any(d.turn_index == pos for d in analysis.decisions):
            score = min(score + 0.1, 1.0)

        # Boost for error chain messages
        if any(e.turn_index == pos for e in analysis.error_chains):
            score = min(score + 0.1, 1.0)

        # Boost for user messages with clear instructions
        if _get_type(msg) == "user":
            text = _all_text(msg)
            if text and len(text) > 20 and "<system-reminder>" not in text:
                score = min(score + 0.15, 1.0)

        # Age decay: older messages lose 0.01 per 10 positions from end
        distance = len(messages) - pos
        decay = min(distance / 10 * 0.01, 0.2)
        score = max(score - decay, 0.0)

        # Sacred: recent window
        is_sacred = pos >= analysis.recent_turn_start and analysis.recent_turn_start > 0
        if is_sacred:
            score = 1.0

        scores.append(MessageScore(
            line_index=idx,
            score=round(score, 3),
            category=category,
            reason=f"base={base:.2f}, sacred={is_sacred}",
            is_sacred=is_sacred,
        ))

    return scores


def format_scores_report(scores: list[MessageScore]) -> str:
    """Format a human-readable scoring report."""
    lines = []
    lines.append("\n  CONTEXT QUALITY SCORE")
    lines.append("  " + "=" * 60)

    # Category breakdown
    cats: dict[str, list[float]] = {}
    for s in scores:
        cats.setdefault(s.category, []).append(s.score)

    lines.append(f"\n  Messages: {len(scores)}")
    lines.append(f"  Sacred (recent window): {sum(1 for s in scores if s.is_sacred)}")
    lines.append(f"\n  Category Breakdown:")

    for cat, cat_scores in sorted(cats.items(), key=lambda x: -sum(x[1]) / len(x[1])):
        avg = sum(cat_scores) / len(cat_scores)
        lines.append(f"    {cat:<25} {len(cat_scores):>4} msgs  avg={avg:.2f}")

    # Distribution
    bins = [0, 0.2, 0.4, 0.6, 0.8, 1.01]
    labels = ["0-0.2 (low)", "0.2-0.4", "0.4-0.6", "0.6-0.8", "0.8-1.0 (high)"]
    lines.append(f"\n  Score Distribution:")
    for i in range(len(bins) - 1):
        count = sum(1 for s in scores if bins[i] <= s.score < bins[i + 1])
        bar = "█" * (count * 40 // len(scores)) if scores else ""
        lines.append(f"    {labels[i]:<18} {count:>4}  {bar}")

    # Overall density
    info_count = sum(1 for s in scores if s.score >= 0.6)
    noise_count = sum(1 for s in scores if s.score < 0.2)
    lines.append(f"\n  Information: {info_count} messages ({info_count * 100 // len(scores)}%)")
    lines.append(f"  Noise:       {noise_count} messages ({noise_count * 100 // len(scores)}%)")

    assessment = "LOW" if noise_count > info_count else "MODERATE" if noise_count > info_count / 2 else "HIGH"
    lines.append(f"\n  Assessment: {assessment}")
    if assessment in ("LOW", "MODERATE"):
        lines.append(f"  Recommendation: Run /crisper:engineer to restructure")

    lines.append("")
    return "\n".join(lines)
