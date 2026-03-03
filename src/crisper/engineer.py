"""Phase 2: Engineer — use LLM to restructure context into optimal form.

One API call. Takes the AnalysisResult from Phase 1 and the raw session,
produces a restructured JSONL with the 5-section optimal layout.

Research grounding:
- Factory.ai: Structured summaries score 3.70 vs 3.44 (Anthropic) on retention
- JetBrains: 10-turn recent window is optimal
- Manus AI: Stable prefix for KV-cache, objectives in recency window
- Liu et al.: Critical info at beginning + end (lost-in-the-middle)
- Chroma: Topic-based > chronological for compressed history
"""

from __future__ import annotations

import json
import os
from pathlib import Path

from .types import AnalysisResult, EngineerResult, QualityScore


ENGINEER_SYSTEM_PROMPT = """\
You are a context engineering specialist. Your job is to restructure a Claude Code \
conversation into the scientifically optimal format for maximum model performance.

You will receive:
1. An analysis of the session (extracted decisions, file changes, errors, references, etc.)
2. The raw conversation messages

Produce a restructured conversation that follows this exact 5-section layout:

## Section 1: System State (top — stable, KV-cacheable)
- Project architecture overview
- Key constraints and user preferences
- Tool configurations mentioned

## Section 2: Structured State (Factory's 4 anchors)
- **Session Intent**: What the user is trying to accomplish
- **File Modifications**: Every file path created/modified with what changed
- **Decisions Made**: Every decision with rationale (keep "why", not just "what")
- **Current State**: What's deployed, pending, blocked

## Section 3: Compressed History (by topic, NOT chronological)
- Group related exchanges by topic/task
- Preserve failed attempts ("wrong turns") — these prevent repetition
- Preserve causal chains: error → investigation → root cause → fix
- Keep URLs/links, drop fetched content (reversible)
- Keep error messages verbatim, compress surrounding discussion

## Section 4: Recent Turns (verbatim, untouched)
- Last N turns exactly as they appeared — do NOT modify these
- Include full tool_use/tool_result pairs

## Section 5: Objectives + Next Steps (end — recency attention window)
- Current task + acceptance criteria
- Agent team state if active
- Pending items, blockers, next actions

CRITICAL RULES:
- Every decision from the analysis MUST appear in the output
- Every file path from the analysis MUST appear in the output
- Every URL/reference MUST be preserved
- Failed attempts MUST be preserved (models learn from wrong turns)
- Recent turns are SACRED — copy them verbatim, byte-for-byte
- Output valid JSONL — each line is a valid JSON message
- Maintain uuid/parentUuid chain integrity
- NEVER invent information not present in the original
"""


def build_engineer_prompt(analysis: AnalysisResult, messages_json: str) -> str:
    """Build the prompt for the LLM engineering call."""
    parts = []
    parts.append("# Session Analysis\n")
    parts.append(f"**Intent**: {analysis.session_intent}\n")
    parts.append(f"**Model**: {analysis.model}")
    parts.append(f"**Tokens**: {analysis.token_count:,}")
    parts.append(f"**Total turns**: {analysis.total_turns}")
    parts.append(f"**Recent turns start at**: message {analysis.recent_turn_start}")
    parts.append("")

    if analysis.decisions:
        parts.append(f"## Decisions ({len(analysis.decisions)})")
        for d in analysis.decisions:
            parts.append(f"- [turn {d.turn_index}] {d.summary}")
        parts.append("")

    if analysis.file_changes:
        parts.append(f"## File Changes ({len(analysis.file_changes)})")
        for fc in analysis.file_changes:
            parts.append(f"- [{fc.action}] {fc.path}")
        parts.append("")

    if analysis.error_chains:
        parts.append(f"## Errors ({len(analysis.error_chains)})")
        for ec in analysis.error_chains[:20]:
            parts.append(f"- [turn {ec.turn_index}] {ec.error}")
        parts.append("")

    if analysis.references:
        parts.append(f"## References ({len(analysis.references)})")
        for ref in analysis.references:
            parts.append(f"- {ref.url}")
            if ref.context:
                parts.append(f"  Context: {ref.context[:100]}")
        parts.append("")

    if analysis.current_task:
        parts.append(f"## Current Task\n{analysis.current_task}\n")

    if analysis.next_steps:
        parts.append("## Next Steps")
        for step in analysis.next_steps:
            parts.append(f"- {step}")
        parts.append("")

    parts.append("# Raw Conversation Messages\n")
    parts.append(messages_json)

    return "\n".join(parts)


def engineer_context(
    analysis: AnalysisResult,
    session_path: Path,
    model: str = "claude-sonnet-4-6",
    api_key: str | None = None,
    dry_run: bool = False,
) -> EngineerResult | str:
    """Phase 2: Call LLM to restructure context.

    Args:
        analysis: Result from Phase 1 (analyzer).
        session_path: Path to the JSONL session file.
        model: LLM model to use for restructuring (default: Sonnet for speed/cost).
        api_key: Anthropic API key. Falls back to ANTHROPIC_API_KEY or CRISPER_API_KEY env.
        dry_run: If True, return the prompt without calling the API.

    Returns:
        EngineerResult on success, or the prompt string if dry_run=True.
    """
    # Resolve API key
    key = api_key or os.environ.get("CRISPER_API_KEY") or os.environ.get("ANTHROPIC_API_KEY")
    if not key and not dry_run:
        return "Error: No API key. Set CRISPER_API_KEY or ANTHROPIC_API_KEY environment variable."

    # Read raw messages
    raw = session_path.read_text(encoding="utf-8")

    # Build prompt
    prompt = build_engineer_prompt(analysis, raw)

    if dry_run:
        return prompt

    # Call Anthropic API
    import anthropic

    client = anthropic.Anthropic(api_key=key)

    response = client.messages.create(
        model=model,
        max_tokens=16384,
        system=ENGINEER_SYSTEM_PROMPT,
        messages=[
            {"role": "user", "content": prompt},
        ],
    )

    # Extract the restructured content
    output_text = ""
    for block in response.content:
        if block.type == "text":
            output_text += block.text

    # Calculate cost
    input_tokens = response.usage.input_tokens
    output_tokens = response.usage.output_tokens
    # Sonnet 4.6 pricing: $3/M input, $15/M output
    cost = (input_tokens * 3 / 1_000_000) + (output_tokens * 15 / 1_000_000)

    return EngineerResult(
        original_tokens=analysis.token_count,
        engineered_tokens=input_tokens,  # approximate
        quality_before=QualityScore(0, 0, 0, 0, 0, 0),  # TODO: implement scoring
        quality_after=QualityScore(0, 0, 0, 0, 0, 0),
        sections_generated=5,
        llm_model_used=model,
        llm_cost_usd=round(cost, 4),
    )
