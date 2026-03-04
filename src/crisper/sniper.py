"""Sniper — surgical section updates with reflector insights.

One LLM call per affected section. Untouched sections stay byte-identical.
Embeds reflector insights (evaluation, enrichment, augmentation) into updates.
"""

from __future__ import annotations

import json


SNIPER_SYSTEM_PROMPT = """\
You are a surgical context editor. You update ONE specific section of a cultivated \
context gene. You receive the current section content, what changed, and enrichment \
insights from the Reflector.

Your output REPLACES the section content entirely. You must:
- Preserve ALL existing information unless explicitly superseded
- ENRICH with Reflector insights (rationale, cross-references, best practices)
- Mark augmented knowledge as [augmented]
- Be concise but complete — every fact matters, no filler

If a fact is superseded by a change, REMOVE the old version. One clean truth per topic."""


SNIPER_SECTION_RULES = {
    "system_identity": """\
This is the stable project header. Changes here are RARE.
- Project name and purpose (FIRST — these are the attention sink tokens)
- Architecture overview
- Hard constraints
- Gene index (section counts, last cultivated timestamp)
Only update if a fundamental project fact changed.""",

    "live_state": """\
This is the evolving state document. Update aggressively:
- Decisions: add new, REMOVE superseded, enrich with rationale/alternatives/dependencies
- File map: current state only (not history), include purpose and key contents
- Dependency graph: link decisions ↔ files ↔ topics
- External feedback: REPLACE with most recent (not a log)
- Anticipated needs: what will the model need for likely next steps?
Make this so complete the model never needs to re-read a file or re-ask a question.""",

    "failure_log": """\
First-class failed approach log. Add new failures with:
- What was tried, why it failed, lesson learned, what to do instead
- If a failure's lesson is now captured in a successful decision in live_state, compress to one line
- NEVER delete failures entirely — they prevent repetition
Research: models cannot self-correct without failure context (Huang et al., TACL 2024)""",

    "subgoal_tree": """\
Hierarchical goal tracking. Update:
- Completed subgoals: compress to ONE LINE (outcome only)
- Active subgoal: EXPAND with full context, blockers, approach
- New subgoals: add with brief description
- Abandoned subgoals: mark and note why
Research: subgoal-based memory doubles success rate (HiAgent, ACL 2025)""",

    "compressed_history": """\
Topic-grouped reference material. This goes in the MIDDLE (lowest attention zone).
- Group by TOPIC, not chronologically
- DISTILL: extract the insight, not the process
- Causal chains must be complete: error → investigation → root cause → fix
- Error messages VERBATIM (never summarize error text)
- Add lessons learned and cross-references to other topics
- Include archive breadcrumbs: [archive:LINE-LINE]
Research: shuffled/topic-based outperforms chronological (Chroma 2025)""",

    "breadcrumbs": """\
Archive index. Add new entries for any content moved to archive.
Format: description + [archive:LINE-LINE]
Include the retrieval instructions.""",

    "objectives": """\
This goes at the VERY END for maximum attention.
- Current task with acceptance criteria, approach, context needed, risks
- Next steps: prioritized, with which files to touch
- Blockers and what would unblock
- Proactive context: what the model will need in the next few turns
Research: recency attention effect + Manus todo.md pattern""",
}


def build_snipe_prompt(
    section_name: str,
    current_content: str,
    changes: dict,
    reflector_insights: dict,
) -> tuple[str, str]:
    """Build prompt for sniping one section.

    Args:
        section_name: Which section to update.
        current_content: Current content of this section.
        changes: Relevant changes from the analyzer (filtered to this section).
        reflector_insights: Relevant insights from the reflector.

    Returns (system_prompt, user_prompt).
    """
    rules = SNIPER_SECTION_RULES.get(section_name, "Update this section appropriately.")

    # Filter reflector insights relevant to this section
    relevant_insights = _filter_insights_for_section(section_name, reflector_insights)

    user_prompt = f"""## Section to Update: {section_name}

## Current Content
{current_content if current_content else "(empty — first cultivation)"}

## Changes to Apply
{json.dumps(changes, indent=2)[:5000]}

## Reflector Insights to Embed
{json.dumps(relevant_insights, indent=2)[:5000]}

## Section Rules
{rules}

## Instructions
Output ONLY the updated section content (markdown text). Do not include the section name header — just the content.

If this is the first cultivation (current content empty), create the section from scratch using the changes and insights.

If updating, preserve all existing facts unless explicitly superseded. Add new information. Embed reflector insights inline where relevant. Mark augmented knowledge as [augmented].

Anti-collapse check: count the facts (decisions, files, errors, etc.) in your output. It should be >= the count in the current content (unless something was explicitly superseded/deleted)."""

    return SNIPER_SYSTEM_PROMPT, user_prompt


def _filter_insights_for_section(section_name: str, insights: dict) -> dict:
    """Extract reflector insights relevant to a specific section."""
    relevant = {}

    evaluate = insights.get("evaluate", {})
    enrich = insights.get("enrich", {})
    augment = insights.get("augment", {})

    if section_name == "live_state":
        relevant["decisions"] = evaluate.get("decisions", [])
        relevant["patterns"] = evaluate.get("patterns", [])
        relevant["cross_references"] = enrich.get("cross_references", [])
        relevant["dependency_chains"] = enrich.get("dependency_chains", [])
        relevant["risks"] = enrich.get("risks", [])
        relevant["augmentation"] = augment.get("items", [])

    elif section_name == "failure_log":
        relevant["lessons"] = evaluate.get("lessons", [])
        relevant["pattern_violations"] = enrich.get("pattern_violations", [])

    elif section_name == "subgoal_tree":
        relevant["lessons"] = evaluate.get("lessons", [])

    elif section_name == "compressed_history":
        relevant["cross_references"] = enrich.get("cross_references", [])
        relevant["lessons"] = evaluate.get("lessons", [])

    elif section_name == "objectives":
        relevant["risks"] = enrich.get("risks", [])
        relevant["augmentation"] = [
            item for item in augment.get("items", [])
            if item.get("dimension") in ("testing", "deployment", "performance")
        ]

    elif section_name == "system_identity":
        relevant["patterns"] = evaluate.get("patterns", [])
        relevant["augmentation"] = [
            item for item in augment.get("items", [])
            if item.get("dimension") == "architecture"
        ]

    return relevant


def parse_snipe_output(raw_output: str) -> str:
    """Parse the sniper's output — just the section content text."""
    text = raw_output.strip()
    # Remove any markdown code blocks the LLM might wrap it in
    if text.startswith("```"):
        lines = text.split("\n")
        text = "\n".join(lines[1:])
        if text.endswith("```"):
            text = text[:-3]
        text = text.strip()
    return text
