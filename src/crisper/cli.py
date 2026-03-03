"""CLI interface for Crisper Context."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def cmd_analyze(args):
    """Extract structured analysis from a session."""
    from .analyzer import analyze_session
    from .engineer import build_full_analysis_json, split_messages, build_analysis_text
    from .session import resolve_session

    path = resolve_session(args.session)
    analysis = analyze_session(path, recent_window=args.window)

    if args.format == "json":
        output = json.loads(build_full_analysis_json(analysis))
        if args.include_messages:
            older, sacred = split_messages(path, analysis.recent_turn_start)
            output["restructurable_messages"] = older
            output["sacred_messages"] = sacred
        json.dump(output, sys.stdout, indent=2)
        print()
    else:
        print(f"\n  CRISPER ANALYSIS")
        print(f"  {'=' * 60}")
        print(f"  Session:    {path.name}")
        print(f"  Model:      {analysis.model or 'unknown'}")
        print(f"  Tokens:     {analysis.token_count:,}")
        print(f"  Turns:      {analysis.total_turns}")
        print(f"  Sacred:     last {args.window} turns (from index {analysis.recent_turn_start})")
        print()
        print(f"  Extracted:")
        print(f"    Intent:         {analysis.session_intent[:60]}...")
        print(f"    Decisions:      {len(analysis.decisions)}")
        print(f"    File changes:   {len(analysis.file_changes)}")
        print(f"    Error chains:   {len(analysis.error_chains)}")
        print(f"    References:     {len(analysis.references)}")
        print(f"    Failed attempts:{len(analysis.failed_attempts)}")
        print(f"    Topics:         {len(analysis.topics)}")
        print(f"    Next steps:     {len(analysis.next_steps)}")
        if analysis.agent_team_state:
            print(f"    Agent team:     detected")
        print()

        if args.verbose:
            print(build_analysis_text(analysis, analysis.topics))


def cmd_score(args):
    """Score message importance."""
    from .analyzer import analyze_session
    from .scorer import score_messages, format_scores_report
    from .session import resolve_session

    path = resolve_session(args.session)
    analysis = analyze_session(path, recent_window=args.window)
    scores = score_messages(path, analysis, recent_window=args.window)

    if args.format == "json":
        json.dump([
            {"line_index": s.line_index, "score": s.score, "category": s.category,
             "reason": s.reason, "is_sacred": s.is_sacred}
            for s in scores
        ], sys.stdout, indent=2)
        print()
    else:
        print(format_scores_report(scores))


def cmd_validate(args):
    """Validate restructured output against original."""
    from .validator import validate
    from .session import resolve_session

    original = resolve_session(args.original)
    restructured = Path(args.restructured)

    result = validate(original, restructured)

    if args.format == "json":
        json.dump({
            "is_valid": result.is_valid,
            "checks": [
                {"name": c.name, "passed": c.passed, "detail": c.detail}
                for c in result.checks
            ],
            "missing_decisions": result.missing_decisions,
            "missing_files": result.missing_files,
            "missing_references": result.missing_references,
        }, sys.stdout, indent=2)
        print()
    else:
        print(f"\n  VALIDATION {'PASSED' if result.is_valid else 'FAILED'}")
        print(f"  {'=' * 60}")
        for check in result.checks:
            icon = "+" if check.passed else "x"
            print(f"  [{icon}] {check.name}: {check.detail}")
        if result.missing_decisions:
            print(f"\n  Missing decisions:")
            for d in result.missing_decisions:
                print(f"    - {d}")
        if result.missing_files:
            print(f"\n  Missing files:")
            for f in result.missing_files:
                print(f"    - {f}")
        if result.missing_references:
            print(f"\n  Missing references:")
            for r in result.missing_references:
                print(f"    - {r}")
        print()

    sys.exit(0 if result.is_valid else 1)


def cmd_write(args):
    """Replace session with restructured version."""
    from .writer import write_restructured
    from .session import resolve_session

    original = resolve_session(args.original)
    restructured = Path(args.restructured)

    result = write_restructured(original, restructured, not args.no_backup)

    if args.format == "json":
        json.dump({
            "success": result.success,
            "original_path": result.original_path,
            "backup_path": result.backup_path,
            "bytes_before": result.bytes_before,
            "bytes_after": result.bytes_after,
            "error": result.error,
        }, sys.stdout, indent=2)
        print()
    else:
        if result.success:
            saved = result.bytes_before - result.bytes_after
            pct = saved / result.bytes_before * 100 if result.bytes_before > 0 else 0
            print(f"\n  Written: {result.original_path}")
            print(f"  Before: {result.bytes_before / 1024:.1f}KB")
            print(f"  After:  {result.bytes_after / 1024:.1f}KB")
            print(f"  Saved:  {saved / 1024:.1f}KB ({pct:.1f}%)")
            if result.backup_path:
                print(f"  Backup: {result.backup_path}")
            print()
        else:
            print(f"  ERROR: {result.error}", file=sys.stderr)

    sys.exit(0 if result.success else 1)


def cmd_engineer(args):
    """Show instructions for using the skill."""
    print("\n  Crisper Context — Engineer Mode")
    print("  " + "=" * 60)
    print()
    print("  To restructure your context, use the Claude Code skill:")
    print("    /crisper:engineer")
    print()
    print("  Or run the analysis locally:")
    print("    crisper analyze current")
    print("    crisper analyze current --format json --include-messages")
    print()
    print("  The skill spawns a subagent that uses Claude's own intelligence")
    print("  to restructure your context. No API key needed.")
    print()


def cmd_eval_prepare(args):
    """Prepare CE-Bench workspace for a session."""
    from .eval.runner import prepare_full_benchmark
    from .session import resolve_session

    path = resolve_session(args.session)
    workspace = Path(args.workspace) if args.workspace else None
    ws = prepare_full_benchmark(path, workspace)
    print(f"  Workspace: {ws}")


def cmd_eval_ground_truth(args):
    """Generate ground truth prompt (after questions.json exists)."""
    from .eval.runner import step3_generate_ground_truth_prompt

    ws = Path(args.workspace)
    prompt_path = step3_generate_ground_truth_prompt(ws)
    if prompt_path:
        print(f"  Ground truth prompt: {prompt_path.name}")
    else:
        print("  ERROR: questions.json not found. Run question generation first.", file=sys.stderr)
        sys.exit(1)


def cmd_eval_test(args):
    """Generate test prompts for all conditions."""
    from .eval.runner import step4_generate_test_prompts

    ws = Path(args.workspace)
    prompts = step4_generate_test_prompts(ws)
    for cid, path in prompts.items():
        print(f"  Condition {cid}: {path.name}")
    if not prompts:
        print("  ERROR: questions.json or condition files not found.", file=sys.stderr)
        sys.exit(1)


def cmd_eval_judge(args):
    """Generate judge prompts for all conditions."""
    from .eval.runner import step5_generate_judge_prompts

    ws = Path(args.workspace)
    prompts = step5_generate_judge_prompts(ws)
    for cid, path in prompts.items():
        print(f"  Condition {cid}: {path.name}")
    if not prompts:
        print("  ERROR: ground_truth.json or answers files not found.", file=sys.stderr)
        sys.exit(1)


def cmd_eval_aggregate(args):
    """Aggregate judge scores into final results."""
    from .eval.runner import step6_aggregate

    ws = Path(args.workspace)
    results = step6_aggregate(ws)
    print(f"  Aggregated {len(results.get('conditions', {}))} conditions")
    print(f"  Results: {ws / 'results.json'}")


def cmd_eval_results(args):
    """Show benchmark results."""
    from .eval.runner import format_results

    ws = Path(args.workspace)
    print(format_results(ws))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="crisper",
        description="Crisper Context — context engineering for Claude Code",
    )
    parser.add_argument("--version", action="version", version="%(prog)s 0.2.0")
    sub = parser.add_subparsers(dest="command")

    # analyze
    p = sub.add_parser("analyze", help="Extract structured analysis from a session")
    p.add_argument("session", help="Session ID, path, or 'current'")
    p.add_argument("--window", type=int, default=10, help="Recent turns to preserve (default: 10)")
    p.add_argument("--format", choices=["json", "text"], default="text")
    p.add_argument("--include-messages", action="store_true", help="Include split JSONL in output")
    p.add_argument("--verbose", "-v", action="store_true")

    # score
    p = sub.add_parser("score", help="Score message importance")
    p.add_argument("session", help="Session ID, path, or 'current'")
    p.add_argument("--window", type=int, default=10)
    p.add_argument("--format", choices=["json", "text"], default="text")

    # validate
    p = sub.add_parser("validate", help="Verify restructured output")
    p.add_argument("original", help="Original session")
    p.add_argument("restructured", help="Path to restructured JSONL")
    p.add_argument("--format", choices=["json", "text"], default="text")

    # write
    p = sub.add_parser("write", help="Replace session with restructured version")
    p.add_argument("original", help="Original session")
    p.add_argument("restructured", help="Path to restructured JSONL")
    p.add_argument("--no-backup", action="store_true")
    p.add_argument("--format", choices=["json", "text"], default="text")

    # engineer (points to skill)
    sub.add_parser("engineer", help="Use /crisper:engineer skill instead")

    # eval commands
    p = sub.add_parser("eval-prepare", help="Prepare CE-Bench workspace")
    p.add_argument("session", help="Session ID, path, or 'current'")
    p.add_argument("--workspace", help="Custom workspace path")

    p = sub.add_parser("eval-ground-truth", help="Generate ground truth prompt")
    p.add_argument("workspace", help="CE-Bench workspace path")

    p = sub.add_parser("eval-test", help="Generate test prompts for all conditions")
    p.add_argument("workspace", help="CE-Bench workspace path")

    p = sub.add_parser("eval-judge", help="Generate judge prompts")
    p.add_argument("workspace", help="CE-Bench workspace path")

    p = sub.add_parser("eval-aggregate", help="Aggregate judge scores")
    p.add_argument("workspace", help="CE-Bench workspace path")

    p = sub.add_parser("eval-results", help="Show benchmark results")
    p.add_argument("workspace", help="CE-Bench workspace path")

    return parser


def main():
    parser = build_parser()
    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(0)

    commands = {
        "analyze": cmd_analyze,
        "score": cmd_score,
        "validate": cmd_validate,
        "write": cmd_write,
        "engineer": cmd_engineer,
        "eval-prepare": cmd_eval_prepare,
        "eval-ground-truth": cmd_eval_ground_truth,
        "eval-test": cmd_eval_test,
        "eval-judge": cmd_eval_judge,
        "eval-aggregate": cmd_eval_aggregate,
        "eval-results": cmd_eval_results,
    }

    commands[args.command](args)


if __name__ == "__main__":
    main()
