"""CE-Bench Runner — orchestrates the full benchmark pipeline.

Designed to run as a CLI command. LLM-dependent steps (question generation,
ground truth, testing, judging) produce prompt files that Claude Code
subagents execute when run via the /crisper:eval skill.

For fully automated runs, use: crisper eval <session> --prepare
Then run the eval skill: /crisper:eval

Non-LLM steps (condition application, aggregation) run locally.
"""

from __future__ import annotations

import json
import os
import shutil
from datetime import datetime
from pathlib import Path

from .bench import (
    apply_condition_a,
    apply_condition_b,
    discover_corpus,
    format_comparison_table,
    paired_t_test,
    prepare_question_prompt,
    prepare_ground_truth_prompt,
    prepare_test_prompt,
)
from .rubric import RUBRIC, build_judge_prompt


def setup_workspace(session_path: Path, workspace: Path | None = None) -> Path:
    """Create workspace directory for a benchmark run."""
    if workspace is None:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        workspace = Path("/tmp") / "ce-bench" / f"{session_path.stem}_{ts}"

    workspace.mkdir(parents=True, exist_ok=True)

    # Copy original (read-only reference)
    original = workspace / "original.jsonl"
    if not original.exists():
        shutil.copy2(session_path, original)

    return workspace


def step1_apply_conditions(workspace: Path) -> dict:
    """Step 1: Apply all non-LLM conditions (A and B).

    Conditions C, D, E require LLM work and are handled by subagents.
    Returns paths to condition files.
    """
    original = workspace / "original.jsonl"
    results = {}

    # Condition A: Raw
    path_a = apply_condition_a(original, workspace)
    results["A"] = {"path": str(path_a), "bytes": path_a.stat().st_size}

    # Condition B: Cozempic prune
    path_b = apply_condition_b(original, workspace)
    results["B"] = {"path": str(path_b), "bytes": path_b.stat().st_size}

    # Save condition metadata
    (workspace / "conditions.json").write_text(
        json.dumps(results, indent=2), encoding="utf-8",
    )

    return results


def step2_generate_question_prompt(workspace: Path) -> Path:
    """Step 2: Generate the prompt for question creation (needs LLM).

    Writes the prompt to a file. A subagent reads it and writes questions.json.
    """
    original = workspace / "original.jsonl"
    prompt = prepare_question_prompt(original)

    prompt_path = workspace / "prompt_questions.txt"
    prompt_path.write_text(prompt, encoding="utf-8")

    return prompt_path


def step3_generate_ground_truth_prompt(workspace: Path) -> Path | None:
    """Step 3: Generate prompt for ground truth answers (needs LLM).

    Requires questions.json to exist (from Step 2 subagent output).
    """
    questions_path = workspace / "questions.json"
    if not questions_path.exists():
        return None

    questions = json.loads(questions_path.read_text(encoding="utf-8"))
    original = workspace / "original.jsonl"
    prompt = prepare_ground_truth_prompt(original, questions)

    prompt_path = workspace / "prompt_ground_truth.txt"
    prompt_path.write_text(prompt, encoding="utf-8")

    return prompt_path


def step4_generate_test_prompts(workspace: Path) -> dict[str, Path]:
    """Step 4: Generate test prompts for each condition (needs LLM per condition).

    Requires questions.json and all condition files to exist.
    """
    questions_path = workspace / "questions.json"
    if not questions_path.exists():
        return {}

    questions = json.loads(questions_path.read_text(encoding="utf-8"))
    prompts = {}

    for cond_file in sorted(workspace.glob("condition_*.jsonl")):
        cond_id = cond_file.stem.split("_")[1]  # "condition_A" -> "A"
        prompt = prepare_test_prompt(cond_file, questions)
        prompt_path = workspace / f"prompt_test_{cond_id}.txt"
        prompt_path.write_text(prompt, encoding="utf-8")
        prompts[cond_id] = prompt_path

    return prompts


def step5_generate_judge_prompts(workspace: Path) -> dict[str, Path]:
    """Step 5: Generate judge prompts for each condition (needs LLM per condition).

    Requires ground_truth.json and answers_*.json files.
    """
    gt_path = workspace / "ground_truth.json"
    questions_path = workspace / "questions.json"
    if not gt_path.exists() or not questions_path.exists():
        return {}

    ground_truth = json.loads(gt_path.read_text(encoding="utf-8"))
    questions = json.loads(questions_path.read_text(encoding="utf-8"))
    prompts = {}

    for answers_file in sorted(workspace.glob("answers_*.json")):
        cond_id = answers_file.stem.split("_")[1]  # "answers_A" -> "A"
        answers = json.loads(answers_file.read_text(encoding="utf-8"))

        # Build one judge prompt per question
        all_judge_prompts = []
        for i, (q, gt, ans) in enumerate(zip(questions, ground_truth, answers)):
            q_text = q.get("text", q.get("question", f"Question {i+1}"))
            gt_text = gt.get("answer", str(gt))
            ans_text = ans.get("answer", str(ans))
            judge_prompt = build_judge_prompt(q_text, gt_text, ans_text)
            all_judge_prompts.append({
                "question_id": q.get("id", f"q{i+1}"),
                "prompt": judge_prompt,
            })

        prompt_path = workspace / f"prompt_judge_{cond_id}.json"
        prompt_path.write_text(
            json.dumps(all_judge_prompts, indent=2), encoding="utf-8",
        )
        prompts[cond_id] = prompt_path

    return prompts


def step6_aggregate(workspace: Path) -> dict:
    """Step 6: Aggregate scores across all conditions.

    Requires scores_*.json files from judge subagents.
    """
    results = {}

    for scores_file in sorted(workspace.glob("scores_*.json")):
        cond_id = scores_file.stem.split("_")[1]
        scores_data = json.loads(scores_file.read_text(encoding="utf-8"))

        # Average across all questions for each dimension
        dim_scores: dict[str, list[float]] = {}
        for q_scores in scores_data:
            if isinstance(q_scores, dict) and "scores" in q_scores:
                for dim, data in q_scores["scores"].items():
                    score = data.get("score", data) if isinstance(data, dict) else data
                    if isinstance(score, (int, float)):
                        dim_scores.setdefault(dim, []).append(float(score))

        dim_means = {
            dim: round(sum(vals) / len(vals), 2) if vals else 0
            for dim, vals in dim_scores.items()
        }

        # Weighted overall
        weights = {d["id"]: d["weight"] for d in RUBRIC["dimensions"]}
        total_weight = sum(weights.values())
        weighted_sum = sum(dim_means.get(d, 0) * weights.get(d, 1) for d in dim_means)
        overall = round(weighted_sum / total_weight, 2) if total_weight > 0 else 0

        # Condition file size
        cond_file = workspace / f"condition_{cond_id}.jsonl"
        cond_bytes = cond_file.stat().st_size if cond_file.exists() else 0
        orig_bytes = (workspace / "original.jsonl").stat().st_size

        results[cond_id] = {
            "dimension_scores": dim_means,
            "overall": overall,
            "bytes": cond_bytes,
            "compression_pct": round((1 - cond_bytes / orig_bytes) * 100, 1) if orig_bytes > 0 else 0,
        }

    # Save aggregated results
    output = {
        "timestamp": datetime.now().isoformat(),
        "conditions": results,
    }
    (workspace / "results.json").write_text(
        json.dumps(output, indent=2), encoding="utf-8",
    )

    return output


def format_results(workspace: Path) -> str:
    """Format benchmark results as a readable report."""
    results_path = workspace / "results.json"
    if not results_path.exists():
        return "No results found. Run the benchmark first."

    data = json.loads(results_path.read_text(encoding="utf-8"))
    conditions = data.get("conditions", {})

    if not conditions:
        return "No condition results found."

    dim_names = {d["id"]: d["name"] for d in RUBRIC["dimensions"]}
    cond_labels = {
        "A": "Raw",
        "B": "Cozempic",
        "C": "/compact",
        "D": "Factory",
        "E": "Crisper",
    }

    cids = sorted(conditions.keys())
    lines = []
    lines.append("\n  CE-BENCH RESULTS")
    lines.append("  " + "=" * 72)
    lines.append("")

    # Header
    header = f"  {'Dimension':<22}"
    for c in cids:
        label = cond_labels.get(c, c)
        header += f" | {label:>10}"
    lines.append(header)
    lines.append("  " + "-" * len(header))

    # Dimension rows
    all_dims = [d["id"] for d in RUBRIC["dimensions"]]
    for dim in all_dims:
        row = f"  {dim_names.get(dim, dim):<22}"
        for c in cids:
            score = conditions[c].get("dimension_scores", {}).get(dim, 0)
            row += f" | {score:>10.2f}"
        lines.append(row)

    # Overall
    lines.append("  " + "-" * len(header))
    row = f"  {'OVERALL (weighted)':<22}"
    for c in cids:
        row += f" | {conditions[c].get('overall', 0):>10.2f}"
    lines.append(row)

    # Compression
    lines.append("")
    row = f"  {'Compression':<22}"
    for c in cids:
        pct = conditions[c].get("compression_pct", 0)
        row += f" | {pct:>9.1f}%"
    lines.append(row)

    # Comparison with Factory published numbers
    lines.append("")
    lines.append("  Reference (Factory.ai published):")
    lines.append("    Factory: 3.70  |  Anthropic: 3.44  |  OpenAI: 3.35")
    lines.append("")

    return "\n".join(lines)


def prepare_full_benchmark(session_path: Path, workspace: Path | None = None) -> Path:
    """Prepare everything for a full benchmark run.

    Creates workspace, applies local conditions, generates all prompt files.
    Returns the workspace path. The prompts are ready for subagent execution.
    """
    ws = setup_workspace(session_path, workspace)

    print(f"  CE-Bench workspace: {ws}")
    print(f"  Original: {session_path.name} ({session_path.stat().st_size / 1024:.1f}KB)")
    print()

    # Step 1: Apply local conditions (A, B)
    print("  Step 1: Applying conditions A (raw) and B (cozempic)...")
    conds = step1_apply_conditions(ws)
    for cid, info in conds.items():
        print(f"    Condition {cid}: {info['bytes'] / 1024:.1f}KB")

    # Step 2: Generate question prompt
    print("  Step 2: Generating question prompt...")
    q_prompt = step2_generate_question_prompt(ws)
    print(f"    Prompt: {q_prompt.name} ({q_prompt.stat().st_size / 1024:.1f}KB)")

    print()
    print(f"  Workspace ready at: {ws}")
    print()
    print("  Next steps (require LLM via subagents):")
    print("    1. Run /crisper:eval to execute LLM steps")
    print("    2. Or manually run each step's prompt with a subagent")
    print()
    print("  Prompt files generated:")
    print(f"    {q_prompt.name} — generate 10 test questions")
    print(f"    (more prompts generated after each step completes)")
    print()

    return ws
