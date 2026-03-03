"""CLI interface for Crisper Context."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


def cmd_engineer(args):
    """Restructure session context into optimal form."""
    from .analyzer import analyze_session
    from .engineer import engineer_context
    from .session import resolve_session

    path = resolve_session(args.session)

    print(f"\n  CRISPER CONTEXT")
    print(f"  ═══════════════════════════════════════════════════════════════════")
    print(f"  Session: {path.name}")
    print()

    # Phase 1: Analyze
    print(f"  Phase 1: Analyzing session...")
    analysis = analyze_session(path, recent_window=args.window)

    print(f"    Intent:     {analysis.session_intent[:80]}...")
    print(f"    Model:      {analysis.model or 'unknown'}")
    print(f"    Tokens:     {analysis.token_count:,}")
    print(f"    Turns:      {analysis.total_turns}")
    print(f"    Decisions:  {len(analysis.decisions)}")
    print(f"    File mods:  {len(analysis.file_changes)}")
    print(f"    Errors:     {len(analysis.error_chains)}")
    print(f"    References: {len(analysis.references)}")
    print(f"    Recent:     last {args.window} turns (verbatim)")
    print()

    if args.dry_run:
        print(f"  Phase 2: Dry run — generating prompt without calling LLM...")
        prompt = engineer_context(analysis, path, dry_run=True)
        print(f"    Prompt length: {len(prompt):,} chars")
        if args.verbose:
            print(f"\n--- PROMPT ---\n{prompt[:2000]}\n--- END ---")
        print(f"\n  DRY RUN — no API call made. Remove --dry-run to restructure.")
        return

    # Phase 2: Engineer
    model = args.model or "claude-sonnet-4-6"
    print(f"  Phase 2: Engineering context (model: {model})...")
    result = engineer_context(analysis, path, model=model)

    if isinstance(result, str):
        print(f"  ERROR: {result}", file=sys.stderr)
        sys.exit(1)

    print(f"    Cost:       ${result.llm_cost_usd:.4f}")
    print(f"    Sections:   {result.sections_generated}")
    print()

    if not args.execute:
        print(f"  DRY RUN — use --execute to apply the restructured context.")
    else:
        print(f"  Context engineered and written.")
        if result.backup_path:
            print(f"  Backup: {result.backup_path}")
    print()


def cmd_score(args):
    """Score current context quality."""
    from .analyzer import analyze_session
    from .session import resolve_session

    path = resolve_session(args.session)
    analysis = analyze_session(path)

    # Simple quality indicators
    total = analysis.total_turns
    decisions = len(analysis.decisions)
    files = len(analysis.file_changes)
    refs = len(analysis.references)

    print(f"\n  CONTEXT QUALITY SCORE")
    print(f"  ═══════════════════════════════════════════════════════════════════")
    print(f"  Session: {path.name}")
    print(f"  Tokens:  {analysis.token_count:,}")
    print(f"  Model:   {analysis.model or 'unknown'}")
    print()
    print(f"  Extracted:")
    print(f"    Decisions:     {decisions}")
    print(f"    File changes:  {files}")
    print(f"    Error chains:  {len(analysis.error_chains)}")
    print(f"    References:    {refs}")
    print(f"    Failed attempts: {len(analysis.failed_attempts)}")
    print()

    # Density score: information pieces per 1K tokens
    info_pieces = decisions + files + refs + len(analysis.error_chains)
    density = info_pieces / max(analysis.token_count / 1000, 1)
    print(f"  Info density: {density:.1f} pieces per 1K tokens")

    if density < 0.5:
        print(f"  Assessment: LOW — most context is conversation noise, not structured information")
        print(f"  Recommendation: Run 'crisper engineer' to restructure")
    elif density < 2.0:
        print(f"  Assessment: MODERATE — some structure, room for improvement")
    else:
        print(f"  Assessment: HIGH — context is information-dense")
    print()


def cmd_init(args):
    """Wire crisper hooks into the current project."""
    print(f"\n  CRISPER INIT")
    print(f"  ═══════════════════════════════════════════════════════════════════")
    print(f"  Coming soon — will wire PreCompact and PostToolUse hooks.")
    print()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="crisper",
        description="Crisper Context — scientifically optimal context engineering for Claude Code",
    )
    parser.add_argument("--version", action="version", version="%(prog)s 0.1.0")
    sub = parser.add_subparsers(dest="command")

    # engineer
    p_eng = sub.add_parser("engineer", help="Restructure session context into optimal form")
    p_eng.add_argument("session", help="Session ID, path, or 'current'")
    p_eng.add_argument("--model", help="LLM model for restructuring (default: claude-sonnet-4-6)")
    p_eng.add_argument("--window", type=int, default=10, help="Recent turns to preserve verbatim (default: 10)")
    p_eng.add_argument("--dry-run", action="store_true", help="Generate prompt without calling LLM")
    p_eng.add_argument("--execute", action="store_true", help="Apply the restructured context")
    p_eng.add_argument("--verbose", "-v", action="store_true", help="Show prompt in dry-run mode")

    # score
    p_score = sub.add_parser("score", help="Score current context quality")
    p_score.add_argument("session", help="Session ID, path, or 'current'")

    # init
    sub.add_parser("init", help="Wire crisper hooks into the current project")

    return parser


def main():
    parser = build_parser()
    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(0)

    commands = {
        "engineer": cmd_engineer,
        "score": cmd_score,
        "init": cmd_init,
    }

    commands[args.command](args)


if __name__ == "__main__":
    main()
