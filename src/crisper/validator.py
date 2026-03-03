"""Validator — verify restructured output preserves all critical information.

Runs locally (no LLM) after the subagent produces restructured output.
"""

from __future__ import annotations

import json
from pathlib import Path

from .analyzer import analyze_session, _load_messages
from .types import AnalysisResult, ValidationCheck, ValidationResult


def validate_jsonl_structure(path: Path) -> list[ValidationCheck]:
    """Check that every line is valid JSON with required fields."""
    checks = []
    try:
        lines = path.read_text(encoding="utf-8").strip().split("\n")
    except OSError as e:
        return [ValidationCheck("file_readable", False, str(e))]

    invalid = 0
    missing_type = 0
    for i, line in enumerate(lines):
        if not line.strip():
            continue
        try:
            msg = json.loads(line)
            if "type" not in msg:
                missing_type += 1
        except json.JSONDecodeError:
            invalid += 1

    checks.append(ValidationCheck(
        "valid_json", invalid == 0,
        f"{invalid} invalid JSON lines" if invalid else f"All {len(lines)} lines valid",
    ))
    checks.append(ValidationCheck(
        "has_type_field", missing_type == 0,
        f"{missing_type} messages missing 'type'" if missing_type else "All messages have 'type'",
    ))
    return checks


def validate_uuid_chain(path: Path) -> list[ValidationCheck]:
    """Verify uuid/parentUuid chain is valid."""
    messages = _load_messages(path)
    uuids = set()
    orphaned_parents = 0
    duplicates = 0

    for _, msg in messages:
        uid = msg.get("uuid", "")
        if uid:
            if uid in uuids:
                duplicates += 1
            uuids.add(uid)

    for i, (_, msg) in enumerate(messages):
        parent = msg.get("parentUuid", "")
        if parent and i > 0 and parent not in uuids:
            # Allow the first message or root to have unknown parent
            orphaned_parents += 1

    checks = []
    checks.append(ValidationCheck(
        "no_duplicate_uuids", duplicates == 0,
        f"{duplicates} duplicate uuids" if duplicates else "No duplicates",
    ))
    checks.append(ValidationCheck(
        "valid_parent_refs", orphaned_parents == 0,
        f"{orphaned_parents} orphaned parentUuid refs" if orphaned_parents else "All parentUuids valid",
    ))
    return checks


def validate_tool_pairs(path: Path) -> list[ValidationCheck]:
    """Verify all tool_use blocks have matching tool_result blocks."""
    messages = _load_messages(path)

    tool_use_ids = set()
    tool_result_ids = set()

    for _, msg in messages:
        inner = msg.get("message", {})
        content = inner.get("content", [])
        if not isinstance(content, list):
            continue
        for block in content:
            if not isinstance(block, dict):
                continue
            if block.get("type") == "tool_use":
                uid = block.get("id", "")
                if uid:
                    tool_use_ids.add(uid)
            elif block.get("type") == "tool_result":
                uid = block.get("tool_use_id", "")
                if uid:
                    tool_result_ids.add(uid)

    orphaned_results = tool_result_ids - tool_use_ids
    orphaned_uses = tool_use_ids - tool_result_ids

    checks = []
    checks.append(ValidationCheck(
        "no_orphaned_tool_results", len(orphaned_results) == 0,
        f"{len(orphaned_results)} tool_results without matching tool_use" if orphaned_results else "All paired",
    ))
    # Orphaned tool_use is less critical (tool may not have returned yet)
    if orphaned_uses:
        checks.append(ValidationCheck(
            "tool_use_coverage", True,
            f"{len(orphaned_uses)} tool_use without result (may be in progress)",
        ))
    return checks


def validate_content_preservation(
    original_path: Path,
    restructured_path: Path,
    analysis: AnalysisResult,
) -> list[ValidationCheck]:
    """Verify critical information from analysis is present in output."""
    restructured_text = restructured_path.read_text(encoding="utf-8").lower()
    checks = []

    # Decisions
    missing_decisions = []
    for d in analysis.decisions:
        # Fuzzy match: check if key words from decision appear
        key_words = [w for w in d.summary.lower().split() if len(w) > 4][:5]
        if key_words:
            found = sum(1 for w in key_words if w in restructured_text)
            if found < len(key_words) * 0.6:
                missing_decisions.append(d.summary[:80])

    checks.append(ValidationCheck(
        "decisions_preserved",
        len(missing_decisions) == 0,
        f"{len(missing_decisions)} decisions may be missing" if missing_decisions else f"All {len(analysis.decisions)} decisions found",
    ))

    # File paths
    missing_files = []
    for fc in analysis.file_changes:
        if fc.path.lower() not in restructured_text:
            missing_files.append(fc.path)

    checks.append(ValidationCheck(
        "files_preserved",
        len(missing_files) == 0,
        f"{len(missing_files)} file paths missing" if missing_files else f"All {len(analysis.file_changes)} file paths found",
    ))

    # References
    missing_refs = []
    for ref in analysis.references:
        if ref.url.lower() not in restructured_text:
            missing_refs.append(ref.url)

    checks.append(ValidationCheck(
        "references_preserved",
        len(missing_refs) == 0,
        f"{len(missing_refs)} URLs missing" if missing_refs else f"All {len(analysis.references)} URLs found",
    ))

    return checks, missing_decisions, missing_files, missing_refs


def validate_token_reduction(
    original_path: Path,
    restructured_path: Path,
) -> list[ValidationCheck]:
    """Verify restructured output is smaller than original."""
    orig_size = original_path.stat().st_size
    rest_size = restructured_path.stat().st_size

    reduced = rest_size < orig_size
    pct = (1 - rest_size / orig_size) * 100 if orig_size > 0 else 0

    return [ValidationCheck(
        "token_reduction",
        reduced,
        f"{'Reduced' if reduced else 'NOT reduced'}: {orig_size} → {rest_size} bytes ({pct:.1f}%)",
    )]


def validate(
    original_path: Path,
    restructured_path: Path,
    analysis: AnalysisResult | None = None,
) -> ValidationResult:
    """Run all validation checks."""
    if analysis is None:
        analysis = analyze_session(original_path)

    all_checks = []
    missing_decisions = []
    missing_files = []
    missing_refs = []

    # Structure
    all_checks.extend(validate_jsonl_structure(restructured_path))

    # UUID chain
    all_checks.extend(validate_uuid_chain(restructured_path))

    # Tool pairs
    tool_checks = validate_tool_pairs(restructured_path)
    all_checks.extend(tool_checks)
    orphaned = [c.detail for c in tool_checks if not c.passed]

    # Content preservation
    content_result = validate_content_preservation(original_path, restructured_path, analysis)
    content_checks, missing_decisions, missing_files, missing_refs = content_result
    all_checks.extend(content_checks)

    # Token reduction
    all_checks.extend(validate_token_reduction(original_path, restructured_path))

    is_valid = all(c.passed for c in all_checks)

    return ValidationResult(
        is_valid=is_valid,
        checks=all_checks,
        missing_decisions=missing_decisions,
        missing_files=missing_files,
        missing_references=missing_refs,
        orphaned_tool_results=orphaned,
        original_tokens=analysis.token_count,
    )
