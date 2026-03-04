"""Cross-Session Persister — extract learnings that survive session boundaries.

At session end, extracts:
1. User patterns (preferences, style)
2. Project conventions (naming, structure)
3. Recurring failure modes
4. Architecture insights
5. Reflector meta-learnings

Writes to persistent files that seed the next session's gene bootstrap.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from .cultivator import is_cultivated, find_gene_boundary
from .analyzer import _load_messages, _all_text
from .session import get_claude_dir


PERSIST_DIR = ".crisper"
PERSIST_FILES = {
    "patterns": "user-patterns.md",
    "conventions": "conventions.md",
    "failures": "recurring-failures.md",
    "architecture": "architecture-insights.md",
    "meta": "reflector-learnings.md",
}


def get_persist_dir(session_path: Path) -> Path:
    """Get the persistence directory (project-level)."""
    project_dir = session_path.parent
    persist = project_dir / PERSIST_DIR
    persist.mkdir(exist_ok=True)
    return persist


def get_persist_path(session_path: Path, category: str) -> Path:
    """Get the path for a specific persistence file."""
    filename = PERSIST_FILES.get(category, f"{category}.md")
    return get_persist_dir(session_path) / filename


def load_persistent(session_path: Path, category: str) -> str:
    """Load existing persistent learnings for a category."""
    path = get_persist_path(session_path, category)
    if path.exists():
        return path.read_text(encoding="utf-8")
    return ""


def save_persistent(session_path: Path, category: str, content: str) -> Path:
    """Save persistent learnings for a category."""
    path = get_persist_path(session_path, category)
    path.write_text(content, encoding="utf-8")
    return path


def build_persist_prompt(gene_text: str, feedback_summary: dict, existing: dict[str, str]) -> tuple[str, str]:
    """Build the prompt for extracting persistent learnings.

    Args:
        gene_text: Full text of the cultivated gene.
        feedback_summary: Accumulated feedback signals.
        existing: Current persistent files content (category → text).

    Returns (system_prompt, user_prompt).
    """
    system = """\
You are extracting cross-session learnings from a cultivated context gene. \
These learnings will persist to disk and seed the NEXT session's gene bootstrap.

Extract ONLY insights that are:
- Stable (unlikely to change between sessions)
- General (apply beyond this specific task)
- Actionable (the model can use them to produce better output)

Do NOT extract:
- Session-specific state (current task, pending items)
- Temporary decisions (may change tomorrow)
- Raw facts without insight (file paths without context)"""

    existing_text = "\n\n".join(
        f"### Existing {cat}\n{content[:500]}"
        for cat, content in existing.items()
        if content
    )

    user = f"""## Cultivated Gene
{gene_text[:15000]}

## Feedback Signals
{json.dumps(feedback_summary, indent=2)[:3000]}

## Existing Persistent Learnings (update, don't duplicate)
{existing_text[:5000]}

## Extract These Categories

### 1. User Patterns
Preferences revealed across decisions:
- Technology preferences (simpler vs scalable, zero-dep vs full-featured)
- Communication style (terse vs detailed, asks questions vs gives instructions)
- Working patterns (TDD vs test-after, plan-first vs dive-in)

### 2. Project Conventions
Standards that formed during the session:
- Naming conventions (files, functions, variables)
- Architecture patterns (module structure, dependency direction)
- Code style (error handling approach, logging conventions)

### 3. Recurring Failure Modes
Failures that are likely to recur in future sessions:
- Technical pitfalls specific to this stack
- Patterns of failure (not specific incidents)

### 4. Architecture Insights
Structural understanding of the project:
- Module dependency graph
- Key abstractions and their purposes
- Integration points and boundaries

### 5. Reflector Meta-Learnings
What the cultivation process itself learned:
- Which sections needed the most updates (signals what's volatile)
- Which augmentation dimensions were most useful
- What the feedback signals say about gene quality

## Output (JSON)
{{
  "patterns": "markdown text for user-patterns.md",
  "conventions": "markdown text for conventions.md",
  "failures": "markdown text for recurring-failures.md",
  "architecture": "markdown text for architecture-insights.md",
  "meta": "markdown text for reflector-learnings.md"
}}"""

    return system, user


def parse_persist_output(raw_output: str) -> dict[str, str]:
    """Parse the persister's JSON output."""
    text = raw_output.strip()
    if text.startswith("```"):
        lines = text.split("\n")
        text = "\n".join(lines[1:])
        if text.endswith("```"):
            text = text[:-3]
        text = text.strip()

    try:
        data = json.loads(text)
        return {k: v for k, v in data.items() if isinstance(v, str)}
    except json.JSONDecodeError:
        start = text.find("{")
        end = text.rfind("}") + 1
        if start >= 0 and end > start:
            try:
                data = json.loads(text[start:end])
                return {k: v for k, v in data.items() if isinstance(v, str)}
            except json.JSONDecodeError:
                pass

    return {}


def persist_learnings(session_path: Path, learnings: dict[str, str]) -> dict[str, str]:
    """Write persistent learnings to disk.

    Returns dict of category → file path written.
    """
    written = {}
    for category, content in learnings.items():
        if content and category in PERSIST_FILES:
            path = save_persistent(session_path, category, content)
            written[category] = str(path)
    return written


def load_all_persistent(session_path: Path) -> dict[str, str]:
    """Load all persistent files for seeding a new gene bootstrap."""
    existing = {}
    for category in PERSIST_FILES:
        content = load_persistent(session_path, category)
        if content:
            existing[category] = content
    return existing


def format_bootstrap_context(persistent: dict[str, str]) -> str:
    """Format persistent learnings for injection into gene bootstrap.

    This text is prepended to the Reflector's first cultivation
    so it seeds the gene with cross-session knowledge.
    """
    if not persistent:
        return ""

    parts = ["## Cross-Session Knowledge (from previous sessions)\n"]
    for category, content in persistent.items():
        label = category.replace("_", " ").title()
        parts.append(f"### {label}")
        parts.append(content[:1000])
        parts.append("")

    return "\n".join(parts)
