"""CE-Bench scoring rubric — 8 dimensions, 20 criteria.

Two benchmark modes:
- COMPACT_RUBRIC: Tests information retention after one-shot compression (CE-Bench v1)
- GOF_RUBRIC: Tests output quality improvement from continuous cultivation (CE-Bench v2)
"""

from __future__ import annotations

# ─── CE-Bench v1: Compact (information retention) ────────────────────────────

COMPACT_RUBRIC = {
    "description": "Measures how much task-relevant information survives after compression",
    "dimensions": [
        {
            "id": "accuracy",
            "name": "Accuracy",
            "weight": 1.0,
            "source": "Factory.ai",
            "criteria": [
                {"id": "accuracy_factual", "desc": "Technical details (file paths, version numbers, error codes) are correct — not hallucinated or confused with similar facts"},
                {"id": "accuracy_technical", "desc": "Function names, API endpoints, config values match ground truth exactly"},
            ],
        },
        {
            "id": "context_awareness",
            "name": "Context Awareness",
            "weight": 1.0,
            "source": "Factory.ai",
            "criteria": [
                {"id": "context_conversation", "desc": "Reflects awareness of the full conversation arc — what was tried, what was decided, what changed"},
                {"id": "context_artifact", "desc": "Knows the current state of files, deployments, and dependencies — not a stale snapshot"},
            ],
        },
        {
            "id": "artifact_trail",
            "name": "Artifact Trail",
            "weight": 1.5,
            "source": "Factory.ai",
            "criteria": [
                {"id": "artifact_files", "desc": "Can list EVERY file created, modified, or deleted — not just the recent ones. This is the dimension all existing approaches fail at (2.19-2.45/5)"},
                {"id": "artifact_details", "desc": "Knows WHAT changed in each file, not just that it was touched"},
            ],
        },
        {
            "id": "completeness",
            "name": "Completeness",
            "weight": 1.0,
            "source": "Factory.ai",
            "criteria": [
                {"id": "complete_answer", "desc": "Addresses ALL parts of the question — not just the parts that survived compression"},
                {"id": "complete_context", "desc": "Includes surrounding context that makes the answer useful (rationale, alternatives considered, constraints)"},
            ],
        },
        {
            "id": "continuity",
            "name": "Continuity",
            "weight": 1.0,
            "source": "Factory.ai",
            "criteria": [
                {"id": "continuity_work", "desc": "Could seamlessly continue the task without re-fetching files or re-asking questions"},
                {"id": "continuity_todo", "desc": "Knows what's pending, what's blocked, and what's next"},
                {"id": "continuity_reasoning", "desc": "The reasoning chain is intact — can explain WHY decisions were made, not just WHAT"},
            ],
        },
        {
            "id": "instruction_following",
            "name": "Instruction Following",
            "weight": 1.0,
            "source": "Factory.ai",
            "criteria": [
                {"id": "instruction_constraints", "desc": "Respects constraints stated earlier (e.g., 'zero deps', 'use PostgreSQL', 'no external APIs')"},
                {"id": "instruction_format", "desc": "Follows conventions and formats established in the session"},
            ],
        },
        {
            "id": "token_efficiency",
            "name": "Token Efficiency",
            "weight": 0.5,
            "source": "CE-Bench",
            "criteria": [
                {"id": "density", "desc": "Ratio of useful information to total tokens. High-entropy tokens (decisions, errors, state) vs low-entropy (boilerplate, progress). Research: only 20% of tokens drive reasoning (MI Reasoning Dynamics)"},
                {"id": "compression_quality", "desc": "Quality-per-token-removed. Did compression remove noise or signal?"},
            ],
        },
        {
            "id": "cache_friendliness",
            "name": "Cache Friendliness",
            "weight": 0.5,
            "source": "CE-Bench",
            "criteria": [
                {"id": "prefix_stability", "desc": "What percentage of context would remain identical between consecutive turns? Stable prefixes save ~75% on inference cost (BentoML 2025). Unstructured conversation: ~0% stable. 5-section with stable header: ~30-40% stable"},
                {"id": "append_only", "desc": "Does the structure support append-only growth? Manus AI: append-only context is critical for KV-cache. Reordering invalidates all downstream cache"},
            ],
        },
    ],
}


# ─── CE-Bench v2: GoF (output quality improvement) ───────────────────────────

GOF_RUBRIC = {
    "description": "Measures whether continuous cultivation improves the model's output quality on subsequent turns",
    "dimensions": [
        {
            "id": "instruction_adherence",
            "name": "Instruction Adherence Over Time",
            "weight": 1.5,
            "source": "CE-Bench v2",
            "criteria": [
                {"id": "constraint_memory", "desc": "Does the model remember and respect constraints from early turns (turn 5) when working at late turns (turn 40)? Research: multi-turn reliability degrades 112% (LLMs Get Lost 2025). Cultivation should reduce this."},
                {"id": "preference_consistency", "desc": "Are user preferences (naming conventions, architecture choices, tool preferences) maintained consistently?"},
                {"id": "instruction_drift", "desc": "Score INVERSELY: how much has the model drifted from original instructions? Lower drift = higher score"},
            ],
        },
        {
            "id": "error_non_repetition",
            "name": "Error Non-Repetition",
            "weight": 1.5,
            "source": "CE-Bench v2",
            "criteria": [
                {"id": "failure_awareness", "desc": "Does the model avoid approaches that previously failed? Research: models cannot self-correct without seeing failure context (TACL 2024). The failure log should prevent repetition."},
                {"id": "error_learning", "desc": "Does the model apply LESSONS from past failures to new situations (not just avoid the exact same error)?"},
            ],
        },
        {
            "id": "decision_consistency",
            "name": "Decision Consistency",
            "weight": 1.0,
            "source": "CE-Bench v2",
            "criteria": [
                {"id": "no_contradictions", "desc": "Does the model make decisions consistent with earlier decisions? Research: contradictory information in context causes confused blended responses (Knowledge Conflicts, EMNLP 2024)"},
                {"id": "rationale_awareness", "desc": "When making a new decision, does the model reference the rationale for related earlier decisions?"},
            ],
        },
        {
            "id": "state_accuracy",
            "name": "State Accuracy",
            "weight": 1.0,
            "source": "CE-Bench v2",
            "criteria": [
                {"id": "file_state_current", "desc": "Does the model know the CURRENT state of files (not a stale version from 100 turns ago)?"},
                {"id": "deployment_state", "desc": "Does the model know what's deployed vs pending vs blocked?"},
                {"id": "dependency_awareness", "desc": "Does the model understand dependencies between components?"},
            ],
        },
        {
            "id": "continuity_quality",
            "name": "Continuity Quality",
            "weight": 1.0,
            "source": "CE-Bench v2",
            "criteria": [
                {"id": "no_refetching", "desc": "Does the model work without re-reading files it already knows about?"},
                {"id": "task_progression", "desc": "Does the model advance the task rather than revisiting completed work?"},
            ],
        },
        {
            "id": "phase_adaptation",
            "name": "Phase Adaptation",
            "weight": 1.0,
            "source": "CE-Bench v2",
            "criteria": [
                {"id": "debugging_behavior", "desc": "During debugging: does the model preserve raw error output and avoid premature summarization? Research: summaries cause 13-15% trajectory elongation (JetBrains)"},
                {"id": "execution_focus", "desc": "During execution: is the model focused on the current task without being distracted by historical exploration?"},
            ],
        },
        {
            "id": "artifact_trail",
            "name": "Artifact Trail",
            "weight": 1.0,
            "source": "Factory.ai + CE-Bench v2",
            "criteria": [
                {"id": "file_tracking", "desc": "Can the model accurately list all files modified in the session?"},
                {"id": "change_awareness", "desc": "Does it know what changed in each file and why?"},
            ],
        },
        {
            "id": "retrieval_effectiveness",
            "name": "Retrieval Effectiveness",
            "weight": 0.5,
            "source": "CE-Bench v2",
            "criteria": [
                {"id": "breadcrumb_usage", "desc": "When the model needs detail that was archived, does it use breadcrumbs to retrieve it rather than hallucinating?"},
                {"id": "archive_accuracy", "desc": "Are the retrieved details correct and relevant?"},
            ],
        },
    ],
}


# ─── Prompt builders ─────────────────────────────────────────────────────────

def build_question_generation_prompt(session_text: str, mode: str = "compact") -> str:
    """Build prompt for generating test questions."""
    rubric = COMPACT_RUBRIC if mode == "compact" else GOF_RUBRIC
    dims = "\n".join(f"- {d['name']}: {d['criteria'][0]['desc'][:100]}" for d in rubric["dimensions"])

    return f"""You are generating test questions for CE-Bench ({rubric['description']}).

Given this session, generate exactly 10 questions that rigorously test context quality. Each question must:
- Target a SPECIFIC detail from the session (file paths, version numbers, error codes, decision rationale)
- Be answerable from complete context but potentially LOST in compressed/degraded context
- Test a different dimension of context quality

Dimensions to cover:
{dims}

Make questions HARD — they should distinguish between approaches that preserve information and those that lose it. Ask for specific file paths, exact error messages, decision rationale, and dependency chains.

Output ONLY valid JSON array:
[{{"id": "q1", "dimension": "{rubric['dimensions'][0]['id']}", "text": "...specific, detailed question..."}}, ...]

Session:
{session_text[:50000]}"""


def build_judge_prompt(question: str, ground_truth: str, candidate: str, mode: str = "compact") -> str:
    """Build the LLM judge prompt."""
    rubric = COMPACT_RUBRIC if mode == "compact" else GOF_RUBRIC

    dims = "\n".join(
        f"- **{d['name']}** (weight {d['weight']}): {', '.join(c['desc'][:80] for c in d['criteria'])}"
        for d in rubric["dimensions"]
    )

    return f"""You are an expert judge for CE-Bench. Score rigorously against ground truth.

The research context for your scoring:
- Information in the middle of context has 24.6pp lower retrieval accuracy (Liu et al.)
- Models attend disproportionately to beginning and end of context
- Only 20% of tokens drive reasoning output (MI Reasoning Dynamics)
- Multi-turn reliability degrades 112% (LLMs Get Lost 2025)
- Self-correction without external feedback does not work (TACL 2024)

## Question
{question}

## Ground Truth (from complete session — the CORRECT answer)
{ground_truth}

## Candidate (from compressed/cultivated context — score THIS)
{candidate}

## Scoring (1-5 per dimension)
{dims}

1 = Completely wrong or missing
2 = Major gaps, key details lost
3 = Adequate, gets the gist but misses specifics
4 = Good, minor details missing
5 = Excellent, matches ground truth on specifics

If the candidate says "not found" or "information not available" → score 1-2 on content dimensions.
If the candidate has the right idea but wrong specifics (file path, version number) → score 2-3.
If the candidate matches ground truth on specifics → score 4-5.

Output ONLY valid JSON:
{{
  "scores": {{
    {', '.join(f'"{d["id"]}": {{"score": "N", "reason": "..."}}' for d in rubric["dimensions"])}
  }}
}}"""


# ─── Question templates ──────────────────────────────────────────────────────

COMPACT_QUESTION_TEMPLATES = [
    {"dimension": "artifact_trail", "template": "List every file that was created or modified. Include paths and what changed."},
    {"dimension": "accuracy", "template": "Why was {decision} made? What were the alternatives and why were they rejected?"},
    {"dimension": "context_awareness", "template": "What caused {error} and how was it fixed? Trace the full causal chain."},
    {"dimension": "continuity", "template": "What are the current blockers and pending items?"},
    {"dimension": "completeness", "template": "What was the original goal and how did it evolve?"},
    {"dimension": "instruction_following", "template": "What constraints did the user specify?"},
    {"dimension": "accuracy", "template": "What external URLs or documents were referenced?"},
    {"dimension": "continuity", "template": "What is deployed vs pending?"},
    {"dimension": "continuity", "template": "Continue from where we left off."},
    {"dimension": "instruction_following", "template": "What approaches failed and why?"},
]

GOF_QUESTION_TEMPLATES = [
    {"dimension": "instruction_adherence", "template": "What constraints were specified at the start? Are they still being followed?"},
    {"dimension": "error_non_repetition", "template": "What approaches failed? Would the model avoid repeating them?"},
    {"dimension": "decision_consistency", "template": "List all decisions and check for contradictions."},
    {"dimension": "state_accuracy", "template": "What is the current state of {file}? When was it last modified and why?"},
    {"dimension": "continuity_quality", "template": "What's the next step? Can it be done without re-reading any files?"},
    {"dimension": "phase_adaptation", "template": "We're debugging {error}. What's the raw error output?"},
    {"dimension": "artifact_trail", "template": "List every file modified with what changed in each."},
    {"dimension": "retrieval_effectiveness", "template": "We need the full discussion about {topic}. How would you retrieve it?"},
    {"dimension": "decision_consistency", "template": "Decision X depends on Decision Y. If Y changed, what else needs to change?"},
    {"dimension": "instruction_adherence", "template": "The user said {constraint}. Is the current approach consistent with it?"},
]
