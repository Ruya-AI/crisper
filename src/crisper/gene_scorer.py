"""Gene Quality Scorer — measures the quality of a cultivated gene.

8 dimensions based on published research:
1. Information Density (MI Reasoning: top 20% drives output)
2. Interference Level (Wang et al.: interference degrades working memory)
3. Explicit/Implicit Ratio (Anthropic, Manus: explicit survives)
4. Attention Alignment (Liu et al.: U-shaped attention)
5. Completeness (every fact represented or breadcrumbed)
6. Freshness (Chroma: context rot across all models)
7. Enrichment Level (our unique contribution)
8. Cross-Reference Density (TME, ACON: dependency tracking)
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path

from .cultivator import is_cultivated, find_gene_boundary, GENE_MARKER, SECTION_MARKERS
from .analyzer import _load_messages, _get_type, _all_text, _get_content_blocks


@dataclass
class GeneScore:
    overall: float
    density: float
    interference: float
    explicit_ratio: float
    attention_alignment: float
    completeness: float
    freshness: float
    enrichment: float
    cross_references: float
    details: dict


def score_gene(session_path: Path, turns_since_cultivation: int = 0) -> GeneScore:
    """Score the quality of a cultivated gene."""
    if not is_cultivated(session_path):
        return GeneScore(
            overall=0, density=0, interference=0, explicit_ratio=0,
            attention_alignment=0, completeness=0, freshness=0,
            enrichment=0, cross_references=0,
            details={"error": "not cultivated"},
        )

    messages = _load_messages(session_path)
    gene_boundary = find_gene_boundary(session_path)
    gene_messages = messages[:gene_boundary]
    tail_messages = messages[gene_boundary:]

    # Collect gene text
    gene_text = ""
    for idx, msg in gene_messages:
        gene_text += _all_text(msg) + "\n"

    details = {}

    # 1. Information Density (0-10)
    # High-entropy: decisions, errors, file paths, URLs, code
    # Low-entropy: boilerplate, markers, empty content
    high_entropy_patterns = [
        r"Decision:", r"Error:", r"File:", r"Rationale:", r"Risk:",
        r"Lesson:", r"Dependency:", r"https?://", r"\.py\b", r"\.js\b",
        r"def \w+", r"class \w+", r"import \w+",
        r"Research:", r"Testing:", r"Environment:", r"Credential:",
        r"Architecture:", r"Ideology:", r"Documentation:",
    ]
    total_lines = gene_text.count("\n") + 1
    high_entropy_lines = 0
    for line in gene_text.split("\n"):
        if any(re.search(p, line) for p in high_entropy_patterns):
            high_entropy_lines += 1
    density_ratio = high_entropy_lines / max(total_lines, 1)
    density = min(10, density_ratio * 15)  # Scale: 66%+ = 10
    details["density_ratio"] = round(density_ratio, 3)

    # 2. Interference Level (0-10, inverted — lower interference = higher score)
    # Check for contradictions: same topic with conflicting info
    decisions = re.findall(r"Decision:\s*(.+)", gene_text)
    superseded_still_present = len(re.findall(r"supersede|replaced by|old:", gene_text, re.I))
    contradictions = 0  # Would need LLM to truly detect, use proxy
    interference = max(0, 10 - superseded_still_present * 2 - contradictions * 3)
    details["superseded_refs"] = superseded_still_present
    details["decisions_count"] = len(decisions)

    # 3. Explicit/Implicit Ratio (0-10)
    explicit_markers = len(re.findall(
        r"(Decision:|File:|Error:|Status:|Rationale:|Dependencies:|Approach:|Lesson:|Risk:|Constraint:)",
        gene_text,
    ))
    total_sentences = len(re.findall(r'[.!?\n]', gene_text))
    explicit_ratio_val = explicit_markers / max(total_sentences, 1)
    explicit_ratio = min(10, explicit_ratio_val * 25)  # Scale: 40%+ markers = 10
    details["explicit_markers"] = explicit_markers
    details["total_sentences"] = total_sentences

    # 4. Attention Alignment (0-10)
    # Critical info should be in first 20% and last 20% of gene
    gene_lines = gene_text.split("\n")
    total = len(gene_lines)
    if total > 10:
        first_20 = "\n".join(gene_lines[:total // 5])
        last_20 = "\n".join(gene_lines[-(total // 5):])
        middle = "\n".join(gene_lines[total // 5:-(total // 5)])

        edge_decisions = len(re.findall(r"Decision:", first_20 + last_20))
        middle_decisions = len(re.findall(r"Decision:", middle))
        edge_objectives = len(re.findall(r"(Current Task|Next Step|Blocker|Objective)", last_20))

        attention = min(10, (edge_decisions * 2 + edge_objectives * 3) / max(edge_decisions + middle_decisions + 1, 1) * 10)
    else:
        attention = 5  # Too short to assess
    details["attention_alignment"] = round(attention, 1)

    # 5. Completeness (0-10)
    # Does the gene have all section types?
    sections_found = 0
    for marker in SECTION_MARKERS:
        if marker.lower() in gene_text.lower():
            sections_found += 1
    completeness = (sections_found / len(SECTION_MARKERS)) * 10
    details["sections_found"] = sections_found
    details["sections_expected"] = len(SECTION_MARKERS)

    # 6. Freshness (0-10)
    # Based on turns since last cultivation
    if turns_since_cultivation == 0:
        freshness = 10
    elif turns_since_cultivation <= 5:
        freshness = 9
    elif turns_since_cultivation <= 10:
        freshness = 7
    elif turns_since_cultivation <= 20:
        freshness = 5
    elif turns_since_cultivation <= 50:
        freshness = 3
    else:
        freshness = 1
    freshness = max(0, freshness - len(tail_messages) * 0.1)  # Decay with tail size
    details["turns_since_cultivation"] = turns_since_cultivation
    details["tail_size"] = len(tail_messages)

    # 7. Enrichment Level (0-10)
    # Decisions with rationale, alternatives, dependencies
    decisions_with_rationale = len(re.findall(r"Rationale:", gene_text))
    decisions_with_alternatives = len(re.findall(r"Alternative|rejected|supersede", gene_text, re.I))
    augmented_items = len(re.findall(r"\[augmented\]|\[reflector-augmented\]", gene_text, re.I))
    files_with_purpose = len(re.findall(r"Purpose:", gene_text))

    enrichment_count = decisions_with_rationale + decisions_with_alternatives + augmented_items + files_with_purpose
    enrichment = min(10, enrichment_count / max(len(decisions), 1) * 5)
    details["enrichment_items"] = enrichment_count
    details["augmented_items"] = augmented_items

    # 8. Cross-Reference Density (0-10)
    cross_refs = len(re.findall(r"(depends on|related to|see also|linked to|affects|imports from|archive:)", gene_text, re.I))
    cross_ref_density = cross_refs / max(total_lines / 10, 1)
    cross_references = min(10, cross_ref_density * 5)
    details["cross_references_count"] = cross_refs

    # Weighted overall
    weights = {
        "density": 1.0,
        "interference": 1.5,
        "explicit_ratio": 1.0,
        "attention_alignment": 1.0,
        "completeness": 1.0,
        "freshness": 0.5,
        "enrichment": 1.5,
        "cross_references": 1.0,
    }
    scores = {
        "density": density,
        "interference": interference,
        "explicit_ratio": explicit_ratio,
        "attention_alignment": attention,
        "completeness": completeness,
        "freshness": freshness,
        "enrichment": enrichment,
        "cross_references": cross_references,
    }
    total_weight = sum(weights.values())
    weighted_sum = sum(scores[k] * weights[k] for k in weights)
    overall = round(weighted_sum / total_weight, 2)

    return GeneScore(
        overall=overall,
        density=round(density, 2),
        interference=round(interference, 2),
        explicit_ratio=round(explicit_ratio, 2),
        attention_alignment=round(attention, 2),
        completeness=round(completeness, 2),
        freshness=round(freshness, 2),
        enrichment=round(enrichment, 2),
        cross_references=round(cross_references, 2),
        details=details,
    )


def format_gene_score(score: GeneScore) -> str:
    """Format gene score for display."""
    lines = []
    lines.append("\n  GENE QUALITY SCORE")
    lines.append("  " + "=" * 50)
    lines.append(f"  Overall:              {score.overall}/10")
    lines.append("")
    lines.append(f"  Density:              {score.density}/10  (high-entropy tokens)")
    lines.append(f"  Interference:         {score.interference}/10  (fewer contradictions = higher)")
    lines.append(f"  Explicit Ratio:       {score.explicit_ratio}/10  (structured declarations)")
    lines.append(f"  Attention Alignment:  {score.attention_alignment}/10  (critical info at edges)")
    lines.append(f"  Completeness:         {score.completeness}/10  (all sections present)")
    lines.append(f"  Freshness:            {score.freshness}/10  (recently cultivated)")
    lines.append(f"  Enrichment:           {score.enrichment}/10  (rationale, augmentation)")
    lines.append(f"  Cross-References:     {score.cross_references}/10  (linked decisions/files)")
    lines.append("")
    return "\n".join(lines)
