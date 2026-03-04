"""Reflector — evaluate, enrich, and augment changes with LLM intelligence.

Three modes:
  EVALUATE: why did this happen? what patterns? what lessons?
  ENRICH: cross-references, dependency chains, risks
  AUGMENT: surface parametric knowledge the conversation never had
"""

from __future__ import annotations

import json


REFLECTOR_SYSTEM_PROMPT = """\
You are the Reflector in the Crisper GoF cultivation pipeline.

Your job is NOT to record facts — the Analyzer already did that. Your job is to \
produce INSIGHTS that make the gene richer than the raw conversation:

1. EVALUATE: understand WHY things happened, detect patterns, extract lessons
2. ENRICH: connect the dots — dependencies, risks, cross-references
3. AUGMENT: bring in relevant knowledge the conversation never contained

You are an expert in software engineering. When a decision is made about a technology, \
you know the best practices, common pitfalls, and relevant documentation. Surface this \
knowledge proactively — don't wait to be asked.

Your output makes the difference between a gene that merely records facts and one that \
gives the model everything it needs to produce excellent output on the next turn."""


REFLECTOR_USER_TEMPLATE = """\
## Changes Detected by Analyzer
{change_set_json}

## Current Gene Sections (affected only)
{affected_sections_content}

## Raw Turns (for context)
{raw_tail_excerpt}

## Produce Three Categories of Insights

### EVALUATE
For each decision: WHY was it made? If the conversation was casual ("yeah let's \
do JWT"), infer the rationale from context (stateless, scales horizontally, fits \
the serverless architecture being built).

For patterns: what preferences is the user showing across decisions? (simplicity \
vs scalability? speed vs correctness? convention vs innovation?)

For lessons: what worked, what failed, what should be done differently next time?

### ENRICH
Cross-references: which decisions relate to which files and topics? If Decision A \
affects File B which was created for Subgoal C — link them.

Dependency chains: if Decision X changes, what else is affected? Be specific.

Risks: contradictions between decisions, technical debt accumulating, scaling \
concerns, security gaps. Don't be generic — be specific to THIS project state.

Pattern violations: is a new decision inconsistent with the user's established \
preferences?

### AUGMENT (10 dimensions — only include what's DIRECTLY relevant)

For each technology/decision in the changes, surface:

1. **Best practices** specific to THIS use case and stack
2. **Architecture implications** — what does this decision mean for the system?
3. **Common failure modes** — what typically goes wrong with this approach?
4. **Documentation links** — official docs, not random blogs (e.g., docs.python.org, fastapi.tiangolo.com)
5. **Code patterns** — idiomatic patterns for this stack/framework
6. **Testing guidance** — what should be tested given these changes?
7. **Deployment considerations** — operational implications
8. **Dependency awareness** — compatibility issues, version constraints
9. **Performance implications** — bottlenecks, optimization opportunities
10. **Security considerations** — attack vectors, hardening needed

Only include dimensions that are DIRECTLY relevant. If the change is "renamed a file," \
you don't need all 10 dimensions.

## Output (JSON)
{{
  "evaluate": {{
    "decisions": [
      {{"decision": "...", "inferred_rationale": "...", "confidence": 0.0-1.0}}
    ],
    "patterns": [
      {{"pattern": "...", "evidence": ["..."], "implication": "..."}}
    ],
    "lessons": [
      {{"lesson": "...", "from": "...", "applies_to": "..."}}
    ]
  }},
  "enrich": {{
    "cross_references": [
      {{"from": "...", "to": "...", "relationship": "..."}}
    ],
    "dependency_chains": [
      {{"if_changes": "...", "then_affected": ["..."], "why": "..."}}
    ],
    "risks": [
      {{"risk": "...", "severity": "low|medium|high", "mitigation": "..."}}
    ],
    "pattern_violations": [
      {{"violation": "...", "established_pattern": "...", "recommendation": "..."}}
    ]
  }},
  "augment": {{
    "items": [
      {{
        "for_decision": "...",
        "dimension": "best_practices|architecture|failure_modes|docs|patterns|testing|deployment|dependencies|performance|security",
        "content": "...",
        "source": "general knowledge|framework docs|common practice"
      }}
    ]
  }}
}}"""


def build_reflector_prompt(
    change_set: dict,
    affected_sections: dict[str, str],
    raw_tail_excerpt: str,
) -> tuple[str, str]:
    """Build the system + user prompts for the Reflector.

    Args:
        change_set: Output from the LLM analyzer.
        affected_sections: Dict of section_name → current content for affected sections.
        raw_tail_excerpt: Readable excerpt of the raw tail for context.

    Returns (system_prompt, user_prompt).
    """
    sections_text = "\n\n".join(
        f"### {name}\n{content[:2000]}"
        for name, content in affected_sections.items()
    )

    user_prompt = REFLECTOR_USER_TEMPLATE.format(
        change_set_json=json.dumps(change_set, indent=2)[:10000],
        affected_sections_content=sections_text[:5000],
        raw_tail_excerpt=raw_tail_excerpt[:5000],
    )
    return REFLECTOR_SYSTEM_PROMPT, user_prompt


def parse_reflector_output(raw_output: str) -> dict:
    """Parse the Reflector's JSON output."""
    text = raw_output.strip()
    if text.startswith("```"):
        lines = text.split("\n")
        text = "\n".join(lines[1:])
        if text.endswith("```"):
            text = text[:-3]
        text = text.strip()

    try:
        return json.loads(text)
    except json.JSONDecodeError:
        start = text.find("{")
        end = text.rfind("}") + 1
        if start >= 0 and end > start:
            try:
                return json.loads(text[start:end])
            except json.JSONDecodeError:
                pass

    return {
        "evaluate": {"decisions": [], "patterns": [], "lessons": []},
        "enrich": {"cross_references": [], "dependency_chains": [], "risks": []},
        "augment": {"items": []},
        "_parse_error": True,
    }
