"""CE-Bench main benchmark runner.

Orchestrates the evaluation pipeline. Generates prompt files that
Claude Code subagents execute for LLM-dependent steps.
"""

from __future__ import annotations

import json
import math
import os
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class BenchmarkConfig:
    corpus_path: Path = Path(".")
    conditions: list[str] = field(default_factory=lambda: ["A", "B", "C", "D", "E"])
    output_path: Path | None = None
    num_questions: int = 10
    recent_window: int = 10


@dataclass
class ConditionResult:
    condition_id: str
    compressed_path: str = ""
    compressed_bytes: int = 0
    answers: list[dict] = field(default_factory=list)
    scores: dict[str, float] = field(default_factory=dict)


@dataclass
class SessionResult:
    session_path: str
    session_tokens: int = 0
    session_model: str = ""
    questions: list[dict] = field(default_factory=list)
    ground_truth: list[dict] = field(default_factory=list)
    condition_results: dict[str, ConditionResult] = field(default_factory=dict)


def discover_corpus(corpus_path: Path) -> list[Path]:
    """Find all JSONL session files in the corpus."""
    sessions = []
    if corpus_path.is_file() and corpus_path.suffix == ".jsonl":
        return [corpus_path]
    for f in sorted(corpus_path.rglob("*.jsonl")):
        if ".bak" not in f.name and ".tmp" not in f.name:
            sessions.append(f)
    return sessions


def prepare_question_prompt(session_path: Path) -> str:
    """Generate the prompt for question generation (Step 1)."""
    from .rubric import build_question_generation_prompt

    text = session_path.read_text(encoding="utf-8")
    return build_question_generation_prompt(text)


def prepare_ground_truth_prompt(session_path: Path, questions: list[dict]) -> str:
    """Generate the prompt for ground truth answers (Step 2)."""
    text = session_path.read_text(encoding="utf-8")
    q_text = "\n".join(f"{i+1}. {q['text']}" for i, q in enumerate(questions))

    return f"""Answer each question using the COMPLETE session transcript below.
Be specific — include file paths, error codes, function names, URLs.

## Questions
{q_text}

## Output (JSON array)
[
  {{"id": "q1", "answer": "...detailed answer..."}},
  ...
]

## Full Session Transcript
{text[:100000]}
"""


def prepare_test_prompt(compressed_path: Path, questions: list[dict]) -> str:
    """Generate the prompt for testing against compressed context (Step 4)."""
    text = compressed_path.read_text(encoding="utf-8")
    q_text = "\n".join(f"{i+1}. {q['text']}" for i, q in enumerate(questions))

    return f"""Answer each question using ONLY the session context below.
If you don't have enough information, say so.

## Questions
{q_text}

## Output (JSON array)
[
  {{"id": "q1", "answer": "...your answer based on available context..."}},
  ...
]

## Session Context
{text[:100000]}
"""


def apply_condition_a(session_path: Path, output_dir: Path) -> Path:
    """Condition A: Raw — copy unchanged."""
    import shutil
    out = output_dir / "condition_A.jsonl"
    shutil.copy2(session_path, out)
    return out


def apply_condition_b(session_path: Path, output_dir: Path) -> Path:
    """Condition B: Cozempic prune (standard)."""
    try:
        from cozempic.session import load_messages, save_messages
        from cozempic.registry import PRESCRIPTIONS
        from cozempic.executor import run_prescription
        import cozempic.strategies  # noqa: F401

        messages = load_messages(session_path)
        new_msgs, _ = run_prescription(messages, PRESCRIPTIONS["standard"], {})
        out = output_dir / "condition_B.jsonl"
        save_messages(out, new_msgs, create_backup=False)
        return out
    except ImportError:
        import shutil
        out = output_dir / "condition_B.jsonl"
        shutil.copy2(session_path, out)
        return out


def format_comparison_table(results: list[SessionResult]) -> str:
    """Format results as a comparison table."""
    from .rubric import COMPACT_RUBRIC as RUBRIC

    # Aggregate scores per condition per dimension
    agg: dict[str, dict[str, list[float]]] = {}
    for sr in results:
        for cid, cr in sr.condition_results.items():
            if cid not in agg:
                agg[cid] = {}
            for dim, score in cr.scores.items():
                agg[cid].setdefault(dim, []).append(score)

    # Build table
    dims = [d["id"] for d in RUBRIC["dimensions"]]
    dim_names = {d["id"]: d["name"] for d in RUBRIC["dimensions"]}
    conditions = sorted(agg.keys())

    header = f"{'Dimension':<22} | " + " | ".join(f"{c:>8}" for c in conditions)
    sep = "-" * len(header)

    lines = ["\n  CE-BENCH RESULTS", "  " + "=" * 60, "", "  " + header, "  " + sep]

    for dim in dims:
        row = f"  {dim_names[dim]:<22} | "
        for c in conditions:
            scores = agg.get(c, {}).get(dim, [])
            mean = sum(scores) / len(scores) if scores else 0
            row += f"{mean:>8.2f} | "
        lines.append(row)

    # Overall (weighted)
    weights = {d["id"]: d["weight"] for d in RUBRIC["dimensions"]}
    total_weight = sum(weights.values())
    row = f"  {'OVERALL (weighted)':<22} | "
    for c in conditions:
        weighted_sum = 0
        for dim in dims:
            scores = agg.get(c, {}).get(dim, [])
            mean = sum(scores) / len(scores) if scores else 0
            weighted_sum += mean * weights[dim]
        overall = weighted_sum / total_weight if total_weight > 0 else 0
        row += f"{overall:>8.2f} | "
    lines.append("  " + sep)
    lines.append(row)
    lines.append("")

    return "\n".join(lines)


def paired_t_test(a: list[float], b: list[float]) -> tuple[float, float]:
    """Paired t-test using stdlib only."""
    n = len(a)
    if n != len(b) or n < 2:
        return 0.0, 1.0

    diffs = [x - y for x, y in zip(a, b)]
    mean_d = sum(diffs) / n
    var_d = sum((d - mean_d) ** 2 for d in diffs) / (n - 1)

    if var_d == 0:
        return float("inf") if mean_d != 0 else 0.0, 0.0

    t = mean_d / math.sqrt(var_d / n)
    # Normal approximation for p-value (valid for n > 30)
    p = 2 * (1 - _normal_cdf(abs(t)))
    return round(t, 4), round(p, 6)


def _normal_cdf(x: float) -> float:
    """Approximate standard normal CDF using Abramowitz & Stegun."""
    a1, a2, a3, a4, a5 = 0.254829592, -0.284496736, 1.421413741, -1.453152027, 1.061405429
    p = 0.3275911
    sign = 1 if x >= 0 else -1
    x = abs(x) / math.sqrt(2)
    t = 1.0 / (1.0 + p * x)
    y = 1.0 - (((((a5 * t + a4) * t) + a3) * t + a2) * t + a1) * t * math.exp(-x * x)
    return 0.5 * (1.0 + sign * y)
