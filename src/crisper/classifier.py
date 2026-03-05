"""Stage 2: LLM Classifier — semantic classification of session chunks.

Replaces regex-based extraction with LLM intelligence. Classifies each chunk
across multiple dimensions: type, content, semantics, and cross-cutting concerns.
Designed to be called via Claude Code subagents (no BYOK).
"""

from __future__ import annotations

import json


CLASSIFIER_SYSTEM_PROMPT = """\
You are a context classifier for the Crisper cultivation pipeline.

You classify chunks from a Claude Code session into structured categories. \
Your classification determines what goes into the cultivated gene — miss something \
and it's lost forever. Be thorough.

You detect what regex cannot: implicit decisions, design discussions without \
"decision" keywords, subtle preference signals, emerging conventions, and \
knowledge that was shared but never explicitly labeled."""


CLASSIFIER_USER_TEMPLATE = """\
Classify each chunk below. For each chunk, provide a structured classification.

## Chunks to Classify

{chunks_text}

## Classification Schema (for EACH chunk)

```json
{{
  "chunk_index": N,

  "primary_type": "decision | exploration | debugging | implementation | \
design_discussion | knowledge_transfer | review | planning | configuration | ceremony",
  "secondary_types": ["..."],

  "content": {{
    "decisions": [
      {{
        "what": "the decision made",
        "rationale": "why — infer from context if not stated explicitly",
        "implicit_or_explicit": "implicit | explicit",
        "supersedes": "what it replaces, if anything",
        "confidence": 0.0-1.0
      }}
    ],
    "errors": [
      {{
        "error": "what went wrong",
        "cause": "root cause if known",
        "fix": "how it was fixed, if fixed",
        "status": "occurred | investigating | resolved"
      }}
    ],
    "file_changes": [
      {{
        "path": "file path",
        "action": "created | modified | deleted | renamed | read",
        "what_changed": "what was changed and why",
        "purpose": "what this file does in the project"
      }}
    ],
    "failed_attempts": [
      {{
        "what": "what was tried",
        "why_failed": "specific reason it didn't work",
        "lesson": "what to do instead"
      }}
    ],
    "knowledge_items": [
      {{
        "topic": "what the knowledge is about",
        "content": "the knowledge itself",
        "source": "conversation | research | documentation | model_knowledge"
      }}
    ]
  }},

  "semantic": {{
    "topic": "semantic topic name (e.g., 'hot-swap cultivation design', not keywords)",
    "phase": "planning | executing | debugging | reviewing | configuring",
    "information_density": 0-10,
    "novelty": 0-10,
    "keep_value": 0-10
  }},

  "cross_cutting": {{
    "architecture": "any architecture decisions, patterns, constraints, module relationships — or null",
    "preferences": "user workflow preferences, style choices, build ideology — or null",
    "environment": "env vars, keys, credentials, secrets, paths, configs mentioned — or null",
    "testing": "test strategy, results, coverage, what to test — or null",
    "documentation": "doc requirements, API contracts, schemas — or null",
    "permissions": "access control, auth, security policies — or null",
    "goals": "macro/micro goals, milestones, progress markers — or null",
    "product_ideology": "product philosophy, design principles — or null",
    "external_knowledge": "research papers, docs, URLs, referenced materials — or null",
    "events_hooks": "event flow, hook configuration, signal patterns — or null"
  }}
}}
```

## Rules

1. **Never skip a chunk.** Every chunk gets a classification, even if it's "ceremony" with keep_value 0.
2. **Infer rationale.** If a decision was made casually ("yeah let's use JWT"), infer WHY from surrounding context.
3. **Detect implicit decisions.** Code changes that imply architectural choices are decisions even without "decided" keywords.
4. **Design discussions are high value.** Conversations weighing options, pros/cons, trade-offs — these are often MORE valuable than the final decision because they capture WHY alternatives were rejected.
5. **Cross-cutting concerns are sparse.** Most chunks won't have all 10. Only include what's ACTUALLY present, set others to null.
6. **Keep value scoring:**
   - 0-2: ceremony, progress updates, trivial acknowledgments
   - 3-4: routine file reads, standard tool output
   - 5-6: implementation work, standard code changes
   - 7-8: decisions, error resolutions, architecture discussions
   - 9-10: critical decisions, user preferences, constraints, design philosophy

## Output

Return a JSON array of classifications, one per chunk:
```json
[
  {{ "chunk_index": 0, ... }},
  {{ "chunk_index": 1, ... }},
  ...
]
```"""


def build_classifier_batches(
    chunks_json: list[dict],
    max_batch_tokens: int = 20000,
) -> list[list[dict]]:
    """Split chunks into batches for LLM classification.

    Estimates ~4 chars per token. Each batch stays under max_batch_tokens
    of text_preview content.

    Args:
        chunks_json: Serialized chunks from slicer.chunks_to_json().
        max_batch_tokens: Approximate token budget per batch.

    Returns:
        List of batches, each batch is a list of chunk dicts.
    """
    max_chars = max_batch_tokens * 4
    batches: list[list[dict]] = []
    current_batch: list[dict] = []
    current_chars = 0

    for chunk in chunks_json:
        preview_len = len(chunk.get("text_preview", ""))
        if current_chars + preview_len > max_chars and current_batch:
            batches.append(current_batch)
            current_batch = []
            current_chars = 0
        current_batch.append(chunk)
        current_chars += preview_len

    if current_batch:
        batches.append(current_batch)

    return batches


def build_classifier_prompt(batch: list[dict]) -> tuple[str, str]:
    """Build system + user prompts for classifying a batch of chunks.

    Args:
        batch: List of serialized chunk dicts (from chunks_to_json).

    Returns:
        (system_prompt, user_prompt)
    """
    chunks_text_parts = []
    for chunk in batch:
        header = f"### Chunk {chunk['index']} ({chunk['chunk_type']})"
        meta = chunk.get("metadata", {})
        meta_str = ""
        if meta.get("tool_names"):
            meta_str += f"  Tools: {', '.join(meta['tool_names'])}\n"
        if meta.get("file_paths"):
            paths = [p for p in meta["file_paths"] if not p.startswith("bash:")]
            if paths:
                meta_str += f"  Files: {', '.join(paths[:5])}\n"
        if meta.get("has_error"):
            meta_str += "  Has error: yes\n"

        preview = chunk.get("text_preview", "(empty)")
        chunks_text_parts.append(f"{header}\n{meta_str}{preview}")

    chunks_text = "\n\n---\n\n".join(chunks_text_parts)

    user_prompt = CLASSIFIER_USER_TEMPLATE.format(chunks_text=chunks_text)
    return CLASSIFIER_SYSTEM_PROMPT, user_prompt


def parse_classifier_output(raw_output: str) -> list[dict]:
    """Parse the classifier's JSON array output.

    Handles markdown code blocks and common LLM output wrapping.
    """
    text = raw_output.strip()

    # Strip markdown code block
    if text.startswith("```"):
        lines = text.split("\n")
        text = "\n".join(lines[1:])
        if text.endswith("```"):
            text = text[:-3]
        text = text.strip()

    try:
        result = json.loads(text)
        if isinstance(result, list):
            return result
        if isinstance(result, dict) and "classifications" in result:
            return result["classifications"]
        return [result]
    except json.JSONDecodeError:
        pass

    # Try to find JSON array in output
    start = text.find("[")
    end = text.rfind("]") + 1
    if start >= 0 and end > start:
        try:
            return json.loads(text[start:end])
        except json.JSONDecodeError:
            pass

    # Fallback: return empty classifications
    return []


def merge_classifications(batches_results: list[list[dict]]) -> list[dict]:
    """Merge classification results from multiple batches into one list.

    Sorts by chunk_index to maintain order.
    """
    all_classifications = []
    for batch_result in batches_results:
        all_classifications.extend(batch_result)

    all_classifications.sort(key=lambda c: c.get("chunk_index", 0))
    return all_classifications


def extract_cross_cutting(classifications: list[dict]) -> dict:
    """Aggregate cross-cutting concerns across all classified chunks.

    Returns a dict keyed by concern name, each containing a list of
    extracted items with their source chunk index.
    """
    concerns: dict[str, list[dict]] = {
        "architecture": [],
        "preferences": [],
        "environment": [],
        "testing": [],
        "documentation": [],
        "permissions": [],
        "goals": [],
        "product_ideology": [],
        "external_knowledge": [],
        "events_hooks": [],
    }

    for cls in classifications:
        cc = cls.get("cross_cutting", {})
        chunk_idx = cls.get("chunk_index", -1)
        for key in concerns:
            value = cc.get(key)
            if value and value != "null":
                concerns[key].append({
                    "chunk_index": chunk_idx,
                    "content": value,
                    "topic": cls.get("semantic", {}).get("topic", ""),
                })

    # Remove empty concern lists
    return {k: v for k, v in concerns.items() if v}


def extract_high_value_chunks(
    classifications: list[dict],
    min_keep_value: int = 5,
) -> list[dict]:
    """Filter to chunks worth preserving in the gene.

    Returns classifications with keep_value >= min_keep_value,
    sorted by keep_value descending.
    """
    high_value = [
        c for c in classifications
        if c.get("semantic", {}).get("keep_value", 0) >= min_keep_value
    ]
    high_value.sort(
        key=lambda c: c.get("semantic", {}).get("keep_value", 0),
        reverse=True,
    )
    return high_value
