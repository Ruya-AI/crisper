"""Phase 2: Engineer — prepare context for subagent restructuring.

This module does NOT call an LLM. It:
1. Formats AnalysisResult into structured text the subagent consumes
2. Separates messages into restructurable and sacred (recent) sets
3. Provides the 5-section template and rules

The LLM intelligence comes from the Claude Code subagent spawned by SKILL.md.
"""

from __future__ import annotations

import json
from pathlib import Path

from .types import AnalysisResult, TopicSegment, MessageScore
from .analyzer import _load_messages


# ─── Templates ───────────────────────────────────────────────────────────────

FIVE_SECTION_TEMPLATE = """\
Section 1: SYSTEM STATE (position: TOP — stable, KV-cacheable)
  - Project architecture
  - Tool configurations
  - User preferences and constraints

Section 2: STRUCTURED STATE (position: NEAR TOP — reference material)
  - Session intent / original requirements
  - File modifications (every path + what changed)
  - Decisions made (every decision + rationale + what was rejected)
  - Current state (deployed, pending, blocked)

Section 3: COMPRESSED HISTORY (position: MIDDLE — by topic, NOT chronological)
  - Group by topic/task
  - Preserve failed attempts with why they failed
  - Preserve causal chains: error → investigation → root cause → fix
  - Keep URLs, drop fetched content
  - Error messages verbatim, surrounding discussion compressed

Section 4: RECENT TURNS (position: NEAR END — sacred, verbatim)
  - Last N turns exactly as they appeared
  - Full tool_use/tool_result pairs intact
  - No modification

Section 5: OBJECTIVES + NEXT STEPS (position: VERY END — highest attention)
  - Current task + acceptance criteria
  - Agent team state (if active)
  - Pending items, blockers, next actions
"""


RESTRUCTURING_RULES = """\
CRITICAL RULES:
1. Every decision from the analysis MUST appear in Section 2
2. Every file path from the analysis MUST appear in Section 2
3. Every URL/reference MUST be preserved in Section 2 or 3
4. Failed attempts MUST be preserved in Section 3
5. Recent turns are SACRED — Section 4 is byte-identical to original
6. Output MUST be valid JSONL — each line is a valid JSON message object
7. uuid/parentUuid chain MUST stay valid
8. All tool_use blocks MUST have matching tool_result blocks
9. NEVER invent information not in the original session
10. Output token count MUST be less than input token count
"""


# ─── Formatting ──────────────────────────────────────────────────────────────

def build_analysis_text(
    analysis: AnalysisResult,
    topics: list[TopicSegment] | None = None,
    scores: list[MessageScore] | None = None,
) -> str:
    """Format AnalysisResult as structured text for the subagent."""
    parts = []
    parts.append("# Session Analysis\n")
    parts.append(f"**Session ID**: {analysis.session_id}")
    parts.append(f"**Intent**: {analysis.session_intent}")
    parts.append(f"**Model**: {analysis.model or 'unknown'}")
    parts.append(f"**Tokens**: {analysis.token_count:,}")
    parts.append(f"**Total turns**: {analysis.total_turns}")
    parts.append(f"**Recent turns start at**: message index {analysis.recent_turn_start}")
    parts.append("")

    if analysis.decisions:
        parts.append(f"## Decisions ({len(analysis.decisions)})")
        for d in analysis.decisions:
            parts.append(f"- [turn {d.turn_index}] {d.summary}")
            if d.rationale:
                parts.append(f"  Rationale: {d.rationale}")
        parts.append("")

    if analysis.file_changes:
        parts.append(f"## File Changes ({len(analysis.file_changes)})")
        for fc in analysis.file_changes:
            parts.append(f"- [{fc.action}] {fc.path}")
        parts.append("")

    if analysis.error_chains:
        parts.append(f"## Error Chains ({len(analysis.error_chains)})")
        for ec in analysis.error_chains:
            parts.append(f"- [turn {ec.turn_index}] {ec.error}")
            if ec.cause:
                parts.append(f"  Cause: {ec.cause}")
            if ec.fix:
                parts.append(f"  Fix: {ec.fix}")
        parts.append("")

    if analysis.references:
        parts.append(f"## References ({len(analysis.references)})")
        for ref in analysis.references:
            parts.append(f"- {ref.url}")
            if ref.context:
                parts.append(f"  Context: {ref.context[:100]}")
        parts.append("")

    if analysis.failed_attempts:
        parts.append(f"## Failed Attempts ({len(analysis.failed_attempts)})")
        for fa in analysis.failed_attempts:
            parts.append(f"- [turn {fa.turn_index}] {fa.what}")
            if fa.why_failed:
                parts.append(f"  Why: {fa.why_failed}")
        parts.append("")

    if topics:
        parts.append(f"## Topics ({len(topics)})")
        for t in topics:
            parts.append(f"- {t.topic} (turns {t.start_index}-{t.end_index}, {len(t.message_indices)} messages)")
        parts.append("")

    if analysis.agent_team_state:
        parts.append(f"## Agent Team State\n{analysis.agent_team_state}\n")

    if analysis.current_task:
        parts.append(f"## Current Task\n{analysis.current_task}\n")

    if analysis.next_steps:
        parts.append("## Next Steps")
        for step in analysis.next_steps:
            parts.append(f"- {step}")
        parts.append("")

    return "\n".join(parts)


def split_messages(path: Path, recent_turn_start: int) -> tuple[str, str]:
    """Split session into restructurable and sacred portions.

    Returns (older_messages_jsonl, sacred_messages_jsonl).
    """
    messages = _load_messages(path)

    older_lines = []
    sacred_lines = []

    for pos, (idx, msg) in enumerate(messages):
        line = json.dumps(msg, separators=(",", ":"))
        if pos >= recent_turn_start and recent_turn_start > 0:
            sacred_lines.append(line)
        else:
            older_lines.append(line)

    return "\n".join(older_lines), "\n".join(sacred_lines)


def build_full_analysis_json(analysis: AnalysisResult) -> str:
    """Serialize AnalysisResult to JSON for CLI output / subagent consumption."""
    return json.dumps({
        "session_id": analysis.session_id,
        "session_intent": analysis.session_intent,
        "model": analysis.model,
        "token_count": analysis.token_count,
        "context_window": analysis.context_window,
        "total_turns": analysis.total_turns,
        "recent_turn_start": analysis.recent_turn_start,
        "current_task": analysis.current_task,
        "current_state": analysis.current_state,
        "agent_team_state": analysis.agent_team_state,
        "decisions": [
            {"summary": d.summary, "rationale": d.rationale, "turn": d.turn_index}
            for d in analysis.decisions
        ],
        "file_changes": [
            {"path": fc.path, "action": fc.action, "turn": fc.turn_index}
            for fc in analysis.file_changes
        ],
        "error_chains": [
            {"error": ec.error, "cause": ec.cause, "fix": ec.fix, "turn": ec.turn_index}
            for ec in analysis.error_chains
        ],
        "references": [
            {"url": r.url, "context": r.context}
            for r in analysis.references
        ],
        "failed_attempts": [
            {"what": fa.what, "why_failed": fa.why_failed, "turn": fa.turn_index}
            for fa in analysis.failed_attempts
        ],
        "topics": [
            {"topic": t.topic, "start": t.start_index, "end": t.end_index, "keywords": t.keywords}
            for t in analysis.topics
        ],
        "next_steps": analysis.next_steps,
    }, indent=2)
