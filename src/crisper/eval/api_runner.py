"""CE-Bench API Runner — uses Anthropic API for all LLM steps.

Fair comparison: same model (Opus 4.6) evaluates all conditions.
Breaks work into multiple API calls instead of one giant call.
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path

import anthropic

from .rubric import COMPACT_RUBRIC as RUBRIC


DEFAULT_MODEL = "claude-opus-4-6"
MAX_CONTEXT_CHARS = 400_000  # ~100K tokens, safe for 200K window


def _client(api_key: str | None = None) -> anthropic.Anthropic:
    key = api_key or os.environ.get("CRISPER_API_KEY") or os.environ.get("ANTHROPIC_API_KEY")
    if not key:
        raise ValueError("No API key. Set CRISPER_API_KEY or ANTHROPIC_API_KEY.")
    return anthropic.Anthropic(api_key=key)


def _call(client: anthropic.Anthropic, system: str, user: str, model: str = DEFAULT_MODEL, max_tokens: int = 8192) -> str:
    """Single API call with retry."""
    for attempt in range(3):
        try:
            resp = client.messages.create(
                model=model,
                max_tokens=max_tokens,
                system=system,
                messages=[{"role": "user", "content": user}],
            )
            return resp.content[0].text
        except Exception as e:
            if attempt < 2:
                time.sleep(2 ** attempt)
                continue
            raise


def _read_condition(path: Path) -> str:
    """Read a condition file, truncating if too large."""
    text = path.read_text(encoding="utf-8")
    if len(text) <= MAX_CONTEXT_CHARS:
        return text
    # For large files: first 40% + last 40% (simulating attention to edges)
    first = int(MAX_CONTEXT_CHARS * 0.4)
    last = int(MAX_CONTEXT_CHARS * 0.4)
    return text[:first] + "\n\n[... middle portion truncated due to context limits ...]\n\n" + text[-last:]


# ─── Step 1: Generate questions ──────────────────────────────────────────────

def generate_questions(workspace: Path, api_key: str | None = None, model: str = DEFAULT_MODEL, mode: str = "compact") -> list[dict]:
    """Generate 10 test questions from the session analysis."""
    client = _client(api_key)
    analysis = (workspace / "analysis.json").read_text(encoding="utf-8")

    from .rubric import build_question_generation_prompt
    prompt = build_question_generation_prompt(analysis, mode=mode)

    system = (
        "You are generating benchmark questions for CE-Bench. "
        "Questions must be SPECIFIC — reference actual file paths, version numbers, error codes, decision rationale. "
        "Generic questions that any session could answer are worthless. "
        "Questions should distinguish between approaches that preserve information and those that lose it."
    )
    user = f"""Given this session analysis, generate exactly 10 test questions.

Each question should target a different dimension and reference SPECIFIC details from the analysis (file paths, version numbers, error messages, URLs).

Dimensions: artifact_trail, decision_rationale, error_chain, current_state, session_intent, failed_attempts, references, deployment_state, continuity, constraints

Output ONLY valid JSON array:
[{{"id": "q1", "dimension": "artifact_trail", "text": "...specific question..."}}, ...]

Analysis:
{analysis[:MAX_CONTEXT_CHARS]}"""

    result = _call(client, system, user, model)
    # Extract JSON from response
    start = result.find("[")
    end = result.rfind("]") + 1
    questions = json.loads(result[start:end])

    (workspace / "questions.json").write_text(json.dumps(questions, indent=2), encoding="utf-8")
    print(f"  Step 1: {len(questions)} questions generated")
    return questions


# ─── Step 2: Generate ground truth ───────────────────────────────────────────

def generate_ground_truth(workspace: Path, api_key: str | None = None, model: str = DEFAULT_MODEL) -> list[dict]:
    """Generate ground truth answers from the full analysis."""
    client = _client(api_key)
    analysis = (workspace / "analysis.json").read_text(encoding="utf-8")
    questions = json.loads((workspace / "questions.json").read_text(encoding="utf-8"))

    q_text = "\n".join(f"{i+1}. [{q['dimension']}] {q['text']}" for i, q in enumerate(questions))

    system = "You are generating reference answers. Be maximally specific — include every file path, version number, error code, URL, and decision rationale."
    user = f"""Answer each question using the COMPLETE session analysis below. These are GROUND TRUTH answers.

Questions:
{q_text}

Output ONLY valid JSON array:
[{{"id": "q1", "answer": "...detailed specific answer..."}}, ...]

Full Analysis:
{analysis[:MAX_CONTEXT_CHARS]}"""

    result = _call(client, system, user, model, max_tokens=16384)
    start = result.find("[")
    end = result.rfind("]") + 1
    ground_truth = json.loads(result[start:end])

    (workspace / "ground_truth.json").write_text(json.dumps(ground_truth, indent=2), encoding="utf-8")
    print(f"  Step 2: {len(ground_truth)} ground truth answers generated")
    return ground_truth


# ─── Step 3: Test each condition (one API call per condition) ─────────────────

def test_condition(
    workspace: Path,
    condition_id: str,
    api_key: str | None = None,
    model: str = DEFAULT_MODEL,
) -> list[dict]:
    """Answer all questions from one condition's context. One API call."""
    client = _client(api_key)
    questions = json.loads((workspace / "questions.json").read_text(encoding="utf-8"))
    condition_path = workspace / f"condition_{condition_id}.jsonl"

    context = _read_condition(condition_path)
    q_text = "\n".join(f"{i+1}. {q['text']}" for i, q in enumerate(questions))

    system = "You are a Claude Code assistant. You have been given a session context. Answer questions ONLY from what you can see in this context. If information is missing, say so explicitly."
    user = f"""Answer these 10 questions using ONLY the session context below. Be specific — include file paths, versions, error details where the context provides them. If the context doesn't contain enough information, say exactly what's missing.

Questions:
{q_text}

Output ONLY valid JSON array:
[{{"id": "q1", "answer": "...answer from this context only..."}}, ...]

Session Context:
{context}"""

    result = _call(client, system, user, model, max_tokens=16384)
    start = result.find("[")
    end = result.rfind("]") + 1
    answers = json.loads(result[start:end])

    (workspace / f"answers_{condition_id}.json").write_text(json.dumps(answers, indent=2), encoding="utf-8")
    size_kb = condition_path.stat().st_size / 1024
    truncated = " (truncated)" if len(context) >= MAX_CONTEXT_CHARS else ""
    print(f"  Step 3-{condition_id}: {len(answers)} answers from {size_kb:.1f}KB context{truncated}")
    return answers


# ─── Step 4: Judge each condition (one API call per condition) ────────────────

def judge_condition(
    workspace: Path,
    condition_id: str,
    api_key: str | None = None,
    model: str = DEFAULT_MODEL,
) -> list[dict]:
    """Judge one condition's answers against ground truth. One API call."""
    client = _client(api_key)
    questions = json.loads((workspace / "questions.json").read_text(encoding="utf-8"))
    ground_truth = json.loads((workspace / "ground_truth.json").read_text(encoding="utf-8"))
    answers = json.loads((workspace / f"answers_{condition_id}.json").read_text(encoding="utf-8"))

    # Build comparison for all 10 questions
    comparisons = []
    for i, (q, gt, ans) in enumerate(zip(questions, ground_truth, answers)):
        comparisons.append(
            f"Q{i+1} [{q['dimension']}]: {q['text']}\n"
            f"GROUND TRUTH: {gt['answer'][:500]}\n"
            f"CANDIDATE: {ans['answer'][:500]}"
        )
    comp_text = "\n\n---\n\n".join(comparisons)

    # Condition-specific efficiency/cache scores
    cond_meta = {
        "A": "0% compression, unstructured raw session",
        "B": "36% compression via noise pruning, still unstructured",
        "C": "99.9% compression, narrative summary (Anthropic /compact style)",
        "D": "99.8% compression, 4-anchor structured (Factory.ai style)",
        "E": "98.8% compression, 5-section optimal layout (Crisper)",
    }

    dims = "\n".join(f"- {d['name']}: {', '.join(c['desc'] for c in d['criteria'])}" for d in RUBRIC["dimensions"])

    system = "You are an expert judge for CE-Bench. Score rigorously. If the candidate answer is missing details that ground truth has, dock points. If it says 'not found', score 1-2 on content dimensions."
    user = f"""Score Condition {condition_id} ({cond_meta.get(condition_id, '')}).

For each of the 10 questions, compare CANDIDATE vs GROUND TRUTH on 8 dimensions (1-5 scale):
{dims}

Scoring: 1=completely fails, 2=major gaps, 3=adequate, 4=good minor gaps, 5=excellent matches ground truth

For token_efficiency: score based on compression ratio ({cond_meta.get(condition_id, '')}).
For cache_friendliness: A,B=1 (unstructured), C=2 (narrative), D=4 (structured anchors), E=5 (optimal 5-section).

{comp_text}

Output ONLY valid JSON array:
[{{"question_id": "q1", "scores": {{"accuracy": {{"score": N, "reason": "..."}}, "context_awareness": {{"score": N, "reason": "..."}}, "artifact_trail": {{"score": N, "reason": "..."}}, "completeness": {{"score": N, "reason": "..."}}, "continuity": {{"score": N, "reason": "..."}}, "instruction_following": {{"score": N, "reason": "..."}}, "token_efficiency": {{"score": N, "reason": "..."}}, "cache_friendliness": {{"score": N, "reason": "..."}}}}}}, ...]"""

    result = _call(client, system, user, model, max_tokens=16384)
    start = result.find("[")
    end = result.rfind("]") + 1
    scores = json.loads(result[start:end])

    (workspace / f"scores_{condition_id}.json").write_text(json.dumps(scores, indent=2), encoding="utf-8")
    print(f"  Step 4-{condition_id}: {len(scores)} questions scored")
    return scores


# ─── Full pipeline ───────────────────────────────────────────────────────────

def run_full_benchmark(
    workspace: Path,
    conditions: list[str] | None = None,
    api_key: str | None = None,
    model: str = DEFAULT_MODEL,
) -> dict:
    """Run the complete CE-Bench pipeline via API.

    Total API calls: 2 (questions + ground truth) + N conditions × 2 (test + judge)
    For 5 conditions: 12 API calls total.
    """
    if conditions is None:
        conditions = ["A", "B", "C", "D", "E"]

    print(f"\n  CE-BENCH (API mode, model={model})")
    print(f"  {'=' * 60}")
    print(f"  Workspace: {workspace}")
    print(f"  Conditions: {', '.join(conditions)}")
    print()

    # Ensure analysis exists
    if not (workspace / "analysis.json").exists():
        print("  ERROR: analysis.json not found. Run 'crisper eval-prepare' first.")
        return {}

    # Step 1: Questions
    if not (workspace / "questions.json").exists():
        generate_questions(workspace, api_key, model)
    else:
        print(f"  Step 1: questions.json exists, skipping")

    # Step 2: Ground truth
    if not (workspace / "ground_truth.json").exists():
        generate_ground_truth(workspace, api_key, model)
    else:
        print(f"  Step 2: ground_truth.json exists, skipping")

    # Step 3: Test each condition
    for cid in conditions:
        if not (workspace / f"condition_{cid}.jsonl").exists():
            print(f"  Step 3-{cid}: SKIPPED (condition file missing)")
            continue
        if (workspace / f"answers_{cid}.json").exists():
            print(f"  Step 3-{cid}: answers exist, skipping")
            continue
        test_condition(workspace, cid, api_key, model)

    # Step 4: Judge each condition
    for cid in conditions:
        if not (workspace / f"answers_{cid}.json").exists():
            print(f"  Step 4-{cid}: SKIPPED (no answers)")
            continue
        judge_condition(workspace, cid, api_key, model)

    # Step 5: Aggregate
    from .runner import step6_aggregate, format_results
    results = step6_aggregate(workspace)
    print()
    print(format_results(workspace))

    return results
