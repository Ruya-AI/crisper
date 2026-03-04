"""LLM-based Analyzer — detects ALL forms of change in new turns.

Replaces the heuristic regex analyzer for cultivation. Detects categorical,
semantic, and subtle changes using LLM intelligence.

The heuristic analyzer.py is kept for fast local analysis (CE-Bench, scoring).
This module is used by the cultivation pipeline where quality matters more than speed.
"""

from __future__ import annotations

import json
from pathlib import Path

from .analyzer import _load_messages, _get_type, _get_content_blocks, _all_text


ANALYZER_SYSTEM_PROMPT = """\
You are a context change analyzer for the Crisper GoF cultivation pipeline.

You analyze new turns from a Claude Code session and detect EVERY form of change \
that should be reflected in the cultivated gene. You detect what heuristic regex \
cannot: semantic shifts, implicit patterns, subtle assumptions, and emerging conventions.

You are thorough. You miss nothing. A missed change means the gene becomes stale."""


ANALYZER_USER_TEMPLATE = """\
Analyze these new turns from a Claude Code session. The gene was last cultivated \
at turn {last_cultivation_turn}. These are turns {start_turn} through {end_turn}.

## Current Gene State (summary)
{gene_summary}

## New Turns to Analyze
{raw_tail}

## Detect ALL of these:

### CATEGORICAL (explicit, factual changes)
- New decisions: any choice made (explicit "let's use X" OR implicit "started using X")
- File changes: created, modified, deleted, renamed (from tool_use blocks AND bash commands)
- Errors: occurred, investigated, resolved
- Subgoal changes: started, completed, blocked, abandoned
- Tool patterns: new tools used, repeated tool failures, tool switches

### SEMANTIC (meaning and intent changes)
- Phase transitions: exploring → deciding → implementing → debugging → reviewing
- Scope changes: scope creep, scope reduction, pivot, new requirements
- Tone/urgency shifts: casual → urgent → frustrated → confident
- Quality shifts: deep technical → surface level → meta-discussion
- User preference signals: repeated choices that reveal a pattern

### SUBTLE (what's between the lines)
- Assumptions made without validation
- Decisions by default (not discussing = accepting status quo)
- Contradictions between stated intent and actual behavior
- Drift from original requirements
- Conventions forming (naming patterns, code style, architecture patterns)
- Knowledge gaps the model is working around
- Things the user corrected (signals what they care about)

## Output Format (JSON only)
{{
  "categorical": {{
    "decisions": [
      {{"what": "...", "type": "explicit|implicit", "rationale_stated": true|false, "turn": N}}
    ],
    "file_changes": [
      {{"path": "...", "action": "created|modified|deleted|renamed", "what_changed": "...", "turn": N}}
    ],
    "errors": [
      {{"error": "...", "status": "occurred|investigating|resolved", "turn": N}}
    ],
    "subgoal_changes": [
      {{"subgoal": "...", "status": "started|completed|blocked|abandoned", "turn": N}}
    ],
    "tool_patterns": [
      {{"pattern": "...", "significance": "..."}}
    ]
  }},
  "semantic": {{
    "phase": "planning|executing|debugging|reviewing",
    "phase_confidence": 0.0-1.0,
    "scope_changes": ["..."],
    "tone": "casual|focused|urgent|frustrated|confident",
    "preference_signals": ["..."],
    "quality_shift": "..."
  }},
  "subtle": {{
    "assumptions": ["..."],
    "default_decisions": ["..."],
    "contradictions": ["..."],
    "drift": ["..."],
    "forming_conventions": ["..."],
    "knowledge_gaps": ["..."],
    "user_corrections": ["..."]
  }},
  "affected_sections": ["system_identity", "live_state", "failure_log", ...],
  "urgency": "normal|high",
  "summary": "One paragraph: what happened in these turns and what it means for the gene"
}}"""


def prepare_analyzer_input(
    session_path: Path,
    gene_boundary: int,
    recent_window: int = 10,
) -> dict:
    """Prepare input for the LLM analyzer.

    Returns dict with: gene_summary, raw_tail_text, start_turn, end_turn, last_cultivation_turn
    """
    messages = _load_messages(session_path)

    # Gene summary (just section headers + key facts, not full content)
    gene_lines = []
    for idx, msg in messages[:gene_boundary]:
        content = _all_text(msg)
        if content and "[CRISPER GENE" in content:
            gene_lines.append(content[:200])
        elif content:
            gene_lines.append(content[:300])
    gene_summary = "\n".join(gene_lines[:20]) if gene_lines else "(no existing gene — first cultivation)"

    # Raw tail (uncultivated turns)
    tail_messages = messages[gene_boundary:]

    # Separate sacred recent turns
    user_indices = [
        i for i, (idx, msg) in enumerate(tail_messages)
        if _get_type(msg) == "user" and not msg.get("isSidechain")
    ]
    if len(user_indices) > recent_window:
        sacred_start = user_indices[-recent_window]
    else:
        sacred_start = 0

    cultivatable = tail_messages[:sacred_start] if sacred_start > 0 else tail_messages

    # Format tail as readable text (not raw JSONL — the LLM needs to understand it)
    tail_text_parts = []
    for idx, msg in cultivatable:
        mtype = _get_type(msg)
        if mtype in ("progress", "file-history-snapshot"):
            continue
        content = _all_text(msg)
        if not content or len(content) < 5:
            continue

        # Extract tool info
        tool_info = ""
        for block in _get_content_blocks(msg):
            if block.get("type") == "tool_use":
                name = block.get("name", "")
                inp = block.get("input", {})
                fp = inp.get("file_path", inp.get("command", ""))
                tool_info = f" [tool: {name}" + (f" {fp[:100]}" if fp else "") + "]"
            elif block.get("type") == "tool_result":
                is_err = block.get("is_error", False)
                if is_err:
                    tool_info = " [tool_result: ERROR]"

        tail_text_parts.append(f"[{mtype}]{tool_info} {content[:500]}")

    raw_tail_text = "\n".join(tail_text_parts)

    # Truncate if too long for LLM input
    if len(raw_tail_text) > 50000:
        raw_tail_text = raw_tail_text[:25000] + "\n\n[...truncated...]\n\n" + raw_tail_text[-25000:]

    return {
        "gene_summary": gene_summary,
        "raw_tail": raw_tail_text,
        "start_turn": gene_boundary,
        "end_turn": gene_boundary + len(cultivatable),
        "last_cultivation_turn": gene_boundary,
        "tail_count": len(cultivatable),
    }


def build_analyzer_prompt(input_data: dict) -> tuple[str, str]:
    """Build the system + user prompts for the LLM analyzer.

    Returns (system_prompt, user_prompt).
    """
    user_prompt = ANALYZER_USER_TEMPLATE.format(
        last_cultivation_turn=input_data["last_cultivation_turn"],
        start_turn=input_data["start_turn"],
        end_turn=input_data["end_turn"],
        gene_summary=input_data["gene_summary"],
        raw_tail=input_data["raw_tail"],
    )
    return ANALYZER_SYSTEM_PROMPT, user_prompt


def parse_analyzer_output(raw_output: str) -> dict:
    """Parse the LLM analyzer's JSON output.

    Handles cases where the LLM wraps JSON in markdown code blocks.
    """
    text = raw_output.strip()

    # Strip markdown code block if present
    if text.startswith("```"):
        lines = text.split("\n")
        text = "\n".join(lines[1:])
        if text.endswith("```"):
            text = text[:-3]
        text = text.strip()

    try:
        return json.loads(text)
    except json.JSONDecodeError:
        # Try to find JSON in the output
        start = text.find("{")
        end = text.rfind("}") + 1
        if start >= 0 and end > start:
            try:
                return json.loads(text[start:end])
            except json.JSONDecodeError:
                pass

    # Fallback: return minimal change set
    return {
        "categorical": {"decisions": [], "file_changes": [], "errors": [], "subgoal_changes": [], "tool_patterns": []},
        "semantic": {"phase": "unknown", "phase_confidence": 0.0},
        "subtle": {},
        "affected_sections": ["live_state"],
        "urgency": "normal",
        "summary": "Analyzer could not parse changes — defaulting to live_state update",
        "_parse_error": True,
        "_raw": raw_output[:500],
    }
