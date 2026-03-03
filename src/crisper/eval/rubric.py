"""CE-Bench scoring rubric — 8 dimensions, 20 criteria."""

from __future__ import annotations

RUBRIC = {
    "dimensions": [
        {
            "id": "accuracy",
            "name": "Accuracy",
            "weight": 1.0,
            "source": "Factory.ai",
            "criteria": [
                {"id": "accuracy_factual", "desc": "Factual correctness of technical details"},
                {"id": "accuracy_technical", "desc": "File paths, function names, error codes correct"},
            ],
        },
        {
            "id": "context_awareness",
            "name": "Context Awareness",
            "weight": 1.0,
            "source": "Factory.ai",
            "criteria": [
                {"id": "context_conversation", "desc": "Reflects current conversation state"},
                {"id": "context_artifact", "desc": "Awareness of file/artifact state"},
            ],
        },
        {
            "id": "artifact_trail",
            "name": "Artifact Trail",
            "weight": 1.5,
            "source": "Factory.ai",
            "criteria": [
                {"id": "artifact_files", "desc": "Knows which files were created/modified"},
                {"id": "artifact_details", "desc": "Remembers key details of file changes"},
            ],
        },
        {
            "id": "completeness",
            "name": "Completeness",
            "weight": 1.0,
            "source": "Factory.ai",
            "criteria": [
                {"id": "complete_answer", "desc": "Addresses all parts of the question"},
                {"id": "complete_context", "desc": "Includes relevant surrounding context"},
            ],
        },
        {
            "id": "continuity",
            "name": "Continuity",
            "weight": 1.0,
            "source": "Factory.ai",
            "criteria": [
                {"id": "continuity_work", "desc": "Can continue work without re-fetching"},
                {"id": "continuity_todo", "desc": "Knows pending items and next steps"},
                {"id": "continuity_reasoning", "desc": "Reasoning chain intact"},
            ],
        },
        {
            "id": "instruction_following",
            "name": "Instruction Following",
            "weight": 1.0,
            "source": "Factory.ai",
            "criteria": [
                {"id": "instruction_constraints", "desc": "Respects user constraints from earlier"},
                {"id": "instruction_format", "desc": "Follows specified formats/conventions"},
            ],
        },
        {
            "id": "token_efficiency",
            "name": "Token Efficiency",
            "weight": 0.5,
            "source": "CE-Bench",
            "criteria": [
                {"id": "density", "desc": "Information pieces per 1K tokens"},
                {"id": "compression_quality", "desc": "Quality retained per token removed"},
            ],
        },
        {
            "id": "cache_friendliness",
            "name": "Cache Friendliness",
            "weight": 0.5,
            "source": "CE-Bench",
            "criteria": [
                {"id": "prefix_stability", "desc": "Percentage of context stable between turns"},
                {"id": "append_only", "desc": "Whether context follows append-only pattern"},
            ],
        },
    ],
}

# Question templates for auto-generation
QUESTION_TEMPLATES = [
    {"id": "artifact_trail", "template": "What files were created or modified during this session?"},
    {"id": "decision_rationale", "template": "Why was {decision} made? What alternatives were considered?"},
    {"id": "error_chain", "template": "What caused {error} and how was it resolved?"},
    {"id": "current_state", "template": "What are the current blockers or pending items?"},
    {"id": "intent", "template": "What was the user's original goal for this session?"},
    {"id": "failed_attempts", "template": "What approaches were tried and failed?"},
    {"id": "references", "template": "What external URLs or documents were referenced?"},
    {"id": "deployment_state", "template": "What is currently deployed vs still pending?"},
    {"id": "continuity", "template": "Continue the task from where it left off."},
    {"id": "constraints", "template": "What constraints or preferences did the user specify?"},
]


def build_question_generation_prompt(session_text: str) -> str:
    """Build prompt for generating 10 test questions from a session."""
    return f"""Given this complete Claude Code session transcript, generate exactly 10 questions
that test whether critical information is preserved. Each question should target
a different dimension of context quality.

Question types to cover:
1. Artifact trail — what files were modified
2. Decision rationale — why specific choices were made
3. Error chain — what caused errors and how they were fixed
4. Current state — blockers, pending items
5. Session intent — original user goal
6. Failed attempts — what didn't work
7. References — URLs, docs cited
8. Deployment state — what's live vs pending
9. Continuity — ability to continue the task
10. Constraints — user-specified preferences

Output as JSON array:
[
  {{"id": "q1", "dimension": "artifact_trail", "text": "What files were created or modified?"}},
  ...
]

SESSION TRANSCRIPT:
{session_text[:50000]}
"""


def build_judge_prompt(question: str, ground_truth: str, candidate: str) -> str:
    """Build the LLM judge prompt for scoring one answer."""
    dims = "\n".join(
        f"- **{d['name']}**: {', '.join(c['desc'] for c in d['criteria'])}"
        for d in RUBRIC["dimensions"]
    )

    return f"""You are an expert judge evaluating context preservation quality.

Score the candidate answer against the ground truth on each dimension (1-5).

## Question
{question}

## Ground Truth Answer (from complete session)
{ground_truth}

## Candidate Answer (from compressed/restructured context)
{candidate}

## Scoring Dimensions
{dims}

## Scoring Scale
1 = Completely fails
2 = Major gaps
3 = Adequate
4 = Good, minor gaps
5 = Excellent, complete

## Output (JSON)
{{
  "scores": {{
    "accuracy": {{"score": N, "reason": "..."}},
    "context_awareness": {{"score": N, "reason": "..."}},
    "artifact_trail": {{"score": N, "reason": "..."}},
    "completeness": {{"score": N, "reason": "..."}},
    "continuity": {{"score": N, "reason": "..."}},
    "instruction_following": {{"score": N, "reason": "..."}},
    "token_efficiency": {{"score": N, "reason": "..."}},
    "cache_friendliness": {{"score": N, "reason": "..."}}
  }}
}}
"""
