"""Stage 4: Reviewer — post-assembly gene quality review.

Reads the complete assembled gene + sample of raw conversation and checks
for completeness, contradictions, hallucinations, language quality, and
missing dimensions. Returns issues and approval status.

Runs BEFORE writing — gives the pipeline a chance to fix problems.
Max 2 review cycles to prevent infinite loops.
"""

from __future__ import annotations

import json


REVIEWER_SYSTEM_PROMPT = """\
You are a gene quality reviewer for the Crisper cultivation pipeline.

You review a cultivated context gene BEFORE it's written to the session file. \
Your job is to catch what the synthesis step missed: lost information, \
contradictions, hallucinations, poor language, missing dimensions, and \
structural problems.

You are the last line of defense. If you approve a gene with missing context, \
it's gone forever. Be thorough but practical — flag real issues, not style preferences."""


REVIEWER_USER_TEMPLATE = """\
## Complete Gene to Review

{gene_sections}

## Raw Conversation Sample (for verification)

{raw_sample}

## Classified Chunks Summary (what was found in the raw conversation)

{classifications_summary}

## Review Checklist

### 1. COMPLETENESS
Compare the gene against the classified chunks summary. Check:
- Every decision (explicit AND implicit) from classifications → should be in live_state
- Every error/failure → should be in failure_log
- Every file change → should be in live_state file map
- Every design discussion conclusion → should be in live_state or compressed_history
- Every knowledge item → should be in knowledge_base
- Every cross-cutting concern (architecture, preferences, environment, testing, etc.) → \
should be in the appropriate section
- User preferences and constraints → should be in system_identity

### 2. CONTRADICTIONS
- Does any section contradict another?
- Are there superseded decisions still present in live_state?
- Does the file map match actual file changes?
- Does the subgoal tree match actual progress?
- Do objectives reflect current state?

### 3. HALLUCINATION CHECK
- Are there claims in the gene not supported by the raw conversation or classifications?
- Are [augmented] items clearly marked?
- Are documentation links real and well-known URLs?
- Are rationale inferences plausible given the context?

### 4. LANGUAGE & STRUCTURE
- Is the language precise and unambiguous?
- Are structured formats consistent? (Decision/Rationale/Dependencies pattern)
- Is information density high? (no filler words, no redundancy)
- Are cross-references between sections explicit? ("see live_state > Decision X")

### 5. MISSING DIMENSIONS
Check if these are present WHERE RELEVANT:
- Architecture map (module relationships, data flow)
- Environment inventory (env vars, paths, configs — names only)
- Credentials inventory (API keys, tokens — names only, NO VALUES)
- Testing strategy (what's tested, how, coverage)
- Documentation requirements (what needs docs, API contracts)
- Product/build ideology (design principles, constraints)
- Research references (papers, benchmarks cited)
- Events/hooks/listeners (signal patterns, hook configs)

### 6. BREADCRUMB ACCURACY
- Do archive line references match the archive content description?
- Are retrieval instructions present and correct?

## Output (JSON only)

{{
  "issues": [
    {{
      "section": "live_state | failure_log | system_identity | ...",
      "type": "missing | contradiction | hallucination | language | structure | dimension",
      "severity": "critical | major | minor",
      "description": "what's wrong",
      "fix": "specific fix to apply",
      "evidence": "what in the raw conversation or classifications supports this"
    }}
  ],
  "score": 0-10,
  "approved": true | false,
  "summary": "one paragraph: overall gene quality assessment"
}}

Approval criteria:
- **approved: true** if score >= 7 and no critical issues
- **approved: false** if score < 7 OR any critical issues exist

Critical issues: missing decisions, active contradictions, hallucinated claims.
Major issues: missing dimensions, poor structure, weak cross-references.
Minor issues: language tweaks, formatting inconsistencies."""


def build_reviewer_prompt(
    gene_sections: dict[str, str],
    raw_sample: str,
    classifications_summary: str,
) -> tuple[str, str]:
    """Build system + user prompts for gene review.

    Args:
        gene_sections: Dict of section_name → content for all gene sections.
        raw_sample: Readable excerpt of raw conversation for verification.
        classifications_summary: Summary of what the classifier found.

    Returns:
        (system_prompt, user_prompt)
    """
    # Format gene sections
    sections_text = "\n\n".join(
        f"### {name}\n{content}"
        for name, content in gene_sections.items()
    )

    # Truncate if needed (reviewer needs to see everything, but within limits)
    if len(sections_text) > 50000:
        sections_text = sections_text[:50000] + "\n\n[...gene truncated...]"
    if len(raw_sample) > 30000:
        raw_sample = raw_sample[:15000] + "\n\n[...sample truncated...]\n\n" + raw_sample[-15000:]
    if len(classifications_summary) > 20000:
        classifications_summary = classifications_summary[:20000] + "\n\n[...summary truncated...]"

    user_prompt = REVIEWER_USER_TEMPLATE.format(
        gene_sections=sections_text,
        raw_sample=raw_sample,
        classifications_summary=classifications_summary,
    )
    return REVIEWER_SYSTEM_PROMPT, user_prompt


def build_classifications_summary(classifications: list[dict]) -> str:
    """Build a readable summary of classifications for the reviewer.

    Focuses on what was FOUND (decisions, errors, knowledge items, cross-cutting)
    so the reviewer can check completeness against the gene.
    """
    parts = []

    # Collect all extracted content across chunks
    all_decisions: list[dict] = []
    all_errors: list[dict] = []
    all_files: list[dict] = []
    all_failures: list[dict] = []
    all_knowledge: list[dict] = []
    all_cross_cutting: dict[str, list[str]] = {}
    topic_map: dict[str, list[int]] = {}

    for cls in classifications:
        idx = cls.get("chunk_index", -1)
        content = cls.get("content", {})
        semantic = cls.get("semantic", {})
        cc = cls.get("cross_cutting", {})

        # Content items
        for d in content.get("decisions", []):
            d["_chunk"] = idx
            all_decisions.append(d)
        for e in content.get("errors", []):
            e["_chunk"] = idx
            all_errors.append(e)
        for f in content.get("file_changes", []):
            f["_chunk"] = idx
            all_files.append(f)
        for fa in content.get("failed_attempts", []):
            fa["_chunk"] = idx
            all_failures.append(fa)
        for k in content.get("knowledge_items", []):
            k["_chunk"] = idx
            all_knowledge.append(k)

        # Topics
        topic = semantic.get("topic", "")
        if topic:
            topic_map.setdefault(topic, []).append(idx)

        # Cross-cutting
        for key, value in cc.items():
            if value and value != "null":
                all_cross_cutting.setdefault(key, []).append(
                    f"[chunk {idx}] {value}"
                )

    # Build summary
    if all_decisions:
        parts.append("## Decisions Found")
        for d in all_decisions:
            parts.append(
                f"- [chunk {d['_chunk']}] {d.get('what', '?')} "
                f"({'implicit' if d.get('implicit_or_explicit') == 'implicit' else 'explicit'})"
            )

    if all_errors:
        parts.append("\n## Errors Found")
        for e in all_errors:
            parts.append(
                f"- [chunk {e['_chunk']}] {e.get('error', '?')} "
                f"(status: {e.get('status', '?')})"
            )

    if all_files:
        parts.append("\n## File Changes Found")
        for f in all_files:
            parts.append(
                f"- [chunk {f['_chunk']}] {f.get('path', '?')} "
                f"({f.get('action', '?')})"
            )

    if all_failures:
        parts.append("\n## Failed Attempts Found")
        for fa in all_failures:
            parts.append(f"- [chunk {fa['_chunk']}] {fa.get('what', '?')}")

    if all_knowledge:
        parts.append("\n## Knowledge Items Found")
        for k in all_knowledge:
            parts.append(
                f"- [chunk {k['_chunk']}] {k.get('topic', '?')}: "
                f"{k.get('content', '?')[:100]}"
            )

    if topic_map:
        parts.append("\n## Topics Identified")
        for topic, chunks in topic_map.items():
            parts.append(f"- {topic} (chunks: {chunks})")

    if all_cross_cutting:
        parts.append("\n## Cross-Cutting Concerns Found")
        for key, items in all_cross_cutting.items():
            parts.append(f"\n### {key}")
            for item in items:
                parts.append(f"- {item}")

    return "\n".join(parts) if parts else "(no classifications available)"


def parse_reviewer_output(raw_output: str) -> dict:
    """Parse the reviewer's JSON output."""
    text = raw_output.strip()

    # Strip markdown code block
    if text.startswith("```"):
        lines = text.split("\n")
        text = "\n".join(lines[1:])
        if text.endswith("```"):
            text = text[:-3]
        text = text.strip()

    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # Try to find JSON object
    start = text.find("{")
    end = text.rfind("}") + 1
    if start >= 0 and end > start:
        try:
            return json.loads(text[start:end])
        except json.JSONDecodeError:
            pass

    # Fallback: not approved (force review)
    return {
        "issues": [
            {
                "section": "unknown",
                "type": "structure",
                "severity": "critical",
                "description": "Reviewer output could not be parsed",
                "fix": "Re-run review",
                "evidence": raw_output[:200],
            }
        ],
        "score": 0,
        "approved": False,
        "summary": "Review failed — output could not be parsed.",
        "_parse_error": True,
    }


def issues_to_snipe_instructions(issues: list[dict]) -> dict[str, list[dict]]:
    """Convert reviewer issues into per-section snipe instructions.

    Groups issues by section so each affected section can be sniped
    with its specific fixes.

    Returns:
        Dict of section_name → list of issues to fix.
    """
    by_section: dict[str, list[dict]] = {}
    for issue in issues:
        section = issue.get("section", "unknown")
        if section == "unknown":
            continue
        by_section.setdefault(section, []).append(issue)
    return by_section
