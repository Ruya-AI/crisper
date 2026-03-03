"""Phase 1: Analyze — extract structured pieces from JSONL session.

Entirely local (no LLM calls). Extracts decisions, file changes, error chains,
references, failed attempts, topic boundaries, agent team state.
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
    TopicSegment,
)


# ─── Message helpers ─────────────────────────────────────────────────────────

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


def _all_text(msg: dict) -> str:
    """Get all text content from a message."""
    blocks = _get_content_blocks(msg)
    parts = []
    for b in blocks:
        if b.get("type") in ("text", "tool_result"):
            t = _text_of(b)
            if not t and isinstance(b.get("content"), str):
                t = b["content"]
            if t:
                parts.append(t)
    return " ".join(parts)


def _load_messages(path: Path) -> list[tuple[int, dict]]:
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

_DECISION_WORDS = re.compile(
    r'\b(decided|chose|going with|will use|switched to|opted for|'
    r"let's go with|using|selected|picked|settled on|"
    r"I'll|let's|we should|the plan is|approach will be)\b",
    re.IGNORECASE,
)

_ERROR_WORDS = re.compile(
    r'\b(error|failed|exception|traceback|bug|issue|crash|broken|'
    r'fix|fixed|resolved|workaround|root cause)\b',
    re.IGNORECASE,
)

_FAILED_WORDS = re.compile(
    r"\b(didn't work|not working|still broken|still failing|try again|"
    r"different approach|let me try|instead|revert|rollback|undo|"
    r"that failed|doesn't fix|wrong approach|back to|start over|"
    r"scratch that|never mind|nope)\b",
    re.IGNORECASE,
)

_NEXT_STEP_WORDS = re.compile(
    r'\b(next|todo|remaining|pending|need to|should|will|plan to|'
    r'after that|then we|upcoming)\b',
    re.IGNORECASE,
)

_STOP_WORDS = frozenset(
    "the a an is are was were be been being have has had do does did will "
    "would could should may might shall can need to of in for on with at "
    "by from as into through during before after above below between out "
    "off over under again further then once here there when where why how "
    "all both each few more most other some such no nor not only own same "
    "so than too very just don now and but or if while because until it "
    "its this that these those i me my we us our you your he him his she "
    "her they them their what which who let see get got make go going "
    "come take give say said know think want look use find tell ask work "
    "seem feel try leave call keep put show also well back even still way "
    "new one two first last".split()
)


# ─── Extractors ──────────────────────────────────────────────────────────────

def _extract_decisions(messages: list[tuple[int, dict]]) -> list[Decision]:
    decisions = []
    for pos, (idx, msg) in enumerate(messages):
        if _get_type(msg) not in ("assistant", "user"):
            continue
        text = _all_text(msg)
        if not text or not _DECISION_WORDS.search(text):
            continue
        for sentence in re.split(r'[.!?\n]', text):
            sentence = sentence.strip()
            if _DECISION_WORDS.search(sentence) and len(sentence) > 15:
                # Get next sentence for rationale
                sentences = re.split(r'[.!?\n]', text)
                idx_in_text = next(
                    (i for i, s in enumerate(sentences) if sentence in s), -1
                )
                rationale = ""
                if idx_in_text >= 0 and idx_in_text + 1 < len(sentences):
                    rationale = sentences[idx_in_text + 1].strip()[:200]
                decisions.append(Decision(
                    summary=sentence[:300],
                    rationale=rationale,
                    turn_index=pos,
                ))
                break
    return decisions


def _extract_file_changes(messages: list[tuple[int, dict]]) -> list[FileChange]:
    changes: dict[str, FileChange] = {}
    for pos, (idx, msg) in enumerate(messages):
        for block in _get_content_blocks(msg):
            if block.get("type") != "tool_use":
                continue
            name = block.get("name", "")
            inp = block.get("input", {})
            if name in ("Write", "write"):
                fp = inp.get("file_path", "")
                if fp:
                    changes[fp] = FileChange(path=fp, action="created", turn_index=pos)
            elif name in ("Edit", "edit"):
                fp = inp.get("file_path", "")
                if fp:
                    changes[fp] = FileChange(path=fp, action="modified", turn_index=pos)
            elif name in ("Bash", "bash"):
                cmd = inp.get("command", "")
                if cmd and ("rm " in cmd or "rm -" in cmd):
                    # Try to extract file path from rm command
                    parts = cmd.split()
                    for p in parts:
                        if p.startswith("/") and not p.startswith("-"):
                            changes[p] = FileChange(path=p, action="deleted", turn_index=pos)
    return list(changes.values())


def _extract_error_chains(messages: list[tuple[int, dict]]) -> list[ErrorChain]:
    chains = []
    for pos, (idx, msg) in enumerate(messages):
        if _get_type(msg) != "assistant":
            continue
        text = _all_text(msg)
        if not text or not _ERROR_WORDS.search(text):
            continue
        for sentence in re.split(r'[.!?\n]', text):
            sentence = sentence.strip()
            if _ERROR_WORDS.search(sentence) and len(sentence) > 15:
                # Look for fix in same message or nearby
                fix = ""
                cause = ""
                if re.search(r'\b(because|caused by|due to|root cause)\b', text, re.I):
                    for s in re.split(r'[.!?\n]', text):
                        if re.search(r'\b(because|caused by|due to|root cause)\b', s, re.I):
                            cause = s.strip()[:200]
                            break
                if re.search(r'\b(fix|fixed|resolved|solution|workaround)\b', text, re.I):
                    for s in re.split(r'[.!?\n]', text):
                        if re.search(r'\b(fix|fixed|resolved|solution|workaround)\b', s, re.I):
                            fix = s.strip()[:200]
                            break
                chains.append(ErrorChain(
                    error=sentence[:300],
                    cause=cause,
                    fix=fix,
                    turn_index=pos,
                ))
                break
    return chains


def _extract_references(messages: list[tuple[int, dict]]) -> list[Reference]:
    refs: dict[str, Reference] = {}
    for pos, (idx, msg) in enumerate(messages):
        text = _all_text(msg)
        if not text:
            continue
        for url in _URL_RE.findall(text):
            if url not in refs:
                context_match = re.search(rf'.{{0,50}}{re.escape(url)}.{{0,50}}', text)
                refs[url] = Reference(
                    url=url,
                    context=context_match.group(0)[:150] if context_match else "",
                    turn_index=pos,
                )
    return list(refs.values())


def _extract_failed_attempts(messages: list[tuple[int, dict]]) -> list[FailedAttempt]:
    attempts = []
    for pos, (idx, msg) in enumerate(messages):
        text = _all_text(msg)
        if not text or not _FAILED_WORDS.search(text):
            continue
        for sentence in re.split(r'[.!?\n]', text):
            sentence = sentence.strip()
            if _FAILED_WORDS.search(sentence) and len(sentence) > 10:
                # Get context of what was being tried
                why = ""
                for s in re.split(r'[.!?\n]', text):
                    s = s.strip()
                    if s != sentence and len(s) > 10:
                        why = s[:200]
                        break
                attempts.append(FailedAttempt(
                    what=sentence[:300],
                    why_failed=why,
                    turn_index=pos,
                ))
                break
    return attempts


def _extract_topics(messages: list[tuple[int, dict]], min_segment: int = 3) -> list[TopicSegment]:
    """Detect topic boundaries via keyword shift between user messages."""
    user_turns = []
    for pos, (idx, msg) in enumerate(messages):
        if _get_type(msg) == "user" and not msg.get("isSidechain"):
            text = _all_text(msg)
            if text and "<system-reminder>" not in text and len(text) > 5:
                words = set(re.findall(r'[a-z][a-z_-]+', text.lower())) - _STOP_WORDS
                words = {w for w in words if len(w) > 2}
                user_turns.append((pos, words))

    if len(user_turns) < 2:
        return []

    # Detect boundaries via Jaccard similarity drop
    boundaries = [0]
    for i in range(1, len(user_turns)):
        prev_words = user_turns[i - 1][1]
        curr_words = user_turns[i][1]
        if not prev_words and not curr_words:
            continue
        intersection = prev_words & curr_words
        union = prev_words | curr_words
        similarity = len(intersection) / len(union) if union else 0
        if similarity < 0.15:
            boundaries.append(i)

    # Build segments
    segments = []
    for i, start in enumerate(boundaries):
        end = boundaries[i + 1] if i + 1 < len(boundaries) else len(user_turns)
        if end - start < min_segment and i > 0:
            continue
        # Collect keywords for this segment
        all_words: dict[str, int] = {}
        indices = []
        for j in range(start, end):
            pos = user_turns[j][0]
            indices.append(pos)
            for w in user_turns[j][1]:
                all_words[w] = all_words.get(w, 0) + 1
        top_keywords = sorted(all_words.items(), key=lambda x: x[1], reverse=True)[:5]
        topic = ", ".join(k for k, _ in top_keywords) if top_keywords else f"segment-{i}"
        segments.append(TopicSegment(
            topic=topic,
            start_index=user_turns[start][0],
            end_index=user_turns[end - 1][0] if end > start else user_turns[start][0],
            message_indices=indices,
            keywords=[k for k, _ in top_keywords],
        ))

    return segments


def _extract_agent_team_state(messages: list[tuple[int, dict]]) -> str:
    """Extract agent team state. Uses cozempic if available."""
    try:
        from cozempic.team import extract_team_state
        cozempic_msgs = [
            (idx, msg, len(json.dumps(msg, separators=(",", ":")).encode()))
            for idx, msg in messages
        ]
        state = extract_team_state(cozempic_msgs)
        if not state.is_empty():
            return state.to_recovery_text()
    except ImportError:
        pass

    # Standalone fallback: scan for Task/TeamCreate
    team_info = []
    for pos, (idx, msg) in enumerate(messages):
        for block in _get_content_blocks(msg):
            if block.get("type") == "tool_use":
                name = block.get("name", "")
                if name in ("Task", "TeamCreate", "TaskCreate", "SendMessage"):
                    inp = block.get("input", {})
                    desc = inp.get("description", inp.get("name", ""))
                    if desc:
                        team_info.append(f"{name}: {desc[:100]}")
    return "\n".join(team_info[-10:]) if team_info else ""


def _extract_next_steps(messages: list[tuple[int, dict]]) -> list[str]:
    """Extract pending next steps from recent messages."""
    steps = []
    # Check last 10 assistant messages
    recent_assistant = [
        (pos, msg) for pos, (idx, msg) in enumerate(messages)
        if _get_type(msg) == "assistant"
    ][-10:]

    for pos, msg in recent_assistant:
        text = _all_text(msg)
        if not text or not _NEXT_STEP_WORDS.search(text):
            continue
        for sentence in re.split(r'[.!?\n]', text):
            sentence = sentence.strip()
            if _NEXT_STEP_WORDS.search(sentence) and len(sentence) > 10 and len(sentence) < 200:
                steps.append(sentence)

    return steps[-5:]  # Last 5 next steps


# ─── Main analyzer ───────────────────────────────────────────────────────────

def analyze_session(path: Path, recent_window: int = 10) -> AnalysisResult:
    """Extract structured pieces from a session JSONL file."""
    messages = _load_messages(path)
    result = AnalysisResult(total_turns=len(messages))

    # Session ID from path
    result.session_id = path.stem

    # Model detection
    for _, msg in reversed(messages):
        if _get_type(msg) == "assistant" and not msg.get("isSidechain"):
            inner = msg.get("message", {})
            model = inner.get("model", "")
            if model:
                result.model = model
                break

    # Token count
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
    user_indices = [
        i for i, (idx, msg) in enumerate(messages)
        if _get_type(msg) == "user" and not msg.get("isSidechain")
    ]
    if len(user_indices) > recent_window:
        result.recent_turn_start = user_indices[-recent_window]

    # Session intent
    for _, msg in messages:
        if _get_type(msg) == "user":
            text = _all_text(msg)
            if text and "<system-reminder>" not in text and len(text) > 10:
                result.session_intent = text[:500]
                break

    # Current task
    for _, msg in reversed(messages):
        if _get_type(msg) == "user" and not msg.get("isSidechain"):
            text = _all_text(msg)
            if text and "<system-reminder>" not in text and len(text) > 5:
                result.current_task = text[:300]
                break

    # All extractions
    result.decisions = _extract_decisions(messages)
    result.file_changes = _extract_file_changes(messages)
    result.error_chains = _extract_error_chains(messages)
    result.references = _extract_references(messages)
    result.failed_attempts = _extract_failed_attempts(messages)
    result.topics = _extract_topics(messages)
    result.agent_team_state = _extract_agent_team_state(messages)
    result.next_steps = _extract_next_steps(messages)

    return result
