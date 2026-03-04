---
name: engineer
description: "Crisper Compact — one-shot restructuring of session context into the research-proven 5-section layout. Use before compaction or when context is too large."
disable-model-invocation: true
allowed-tools: Bash(crisper *), Task, Read, Write, AskUserQuestion
---

You are running **Crisper Compact** — one-shot context restructuring.

This is the static version. For continuous cultivation, use `/crisper:cultivate`.

## Research Grounding (inform your restructuring decisions)

- **Position matters:** Information at the beginning and end of context gets 24.6pp higher accuracy than the middle (Liu et al., TACL 2024). Place critical state at edges.
- **Structured > unstructured:** Format alone causes up to 40pp accuracy swing. Explicit labels ("Decision:", "File:") outperform prose (Formatting Study 2024).
- **Topic-based > chronological:** Shuffled text outperforms coherent narrative because coherent text amplifies recency bias (Chroma 2025). Group by topic.
- **Preserve failures:** Models cannot self-correct without seeing failure context (Huang et al., TACL 2024). Keep wrong turns.
- **10-turn sacred window:** JetBrains (NeurIPS 2025) found 10 recent turns is the optimal observation window. Don't touch them.
- **Compression improves output:** Focused 300-token context beats unfocused 113K by 30% (Chroma). Less noise = better reasoning.

## Step 1: Analyze

```bash
crisper analyze current --format json --include-messages --window 10
```

## Step 2: Confirm

Show analysis summary. AskUserQuestion to confirm.

## Step 3: Spawn restructuring subagent

Write analysis to `/tmp/crisper_compact_analysis.json`, then spawn **Task** (run_in_background=false):

---

You are restructuring a Claude Code session into the optimal 5-section layout. The output replaces the raw session — it must be valid JSONL with correct uuid/parentUuid chains.

Read `/tmp/crisper_compact_analysis.json`.

Produce `/tmp/crisper_restructured.jsonl` with these 5 sections as JSONL message pairs:

**Section 1: SYSTEM STATE** (TOP — stable, KV-cacheable)
Project overview, constraints, tool configs. Stable across turns.

**Section 2: STRUCTURED STATE** (NEAR TOP — reference)
- Session intent
- File modifications: EVERY path + action (this is critical — Factory.ai scored only 2.45/5 on artifact trail; we solve this with explicit extraction)
- Decisions: EVERY decision + rationale + what it superseded
- Current state: deployed, pending, blocked

**Section 3: COMPRESSED HISTORY** (MIDDLE — lowest attention, acceptable)
Group by topic, NOT chronological. Preserve failed attempts with "why." Preserve causal chains (error→cause→fix). Keep URLs, drop fetched content. Error messages verbatim.

**Section 4: RECENT TURNS** (NEAR END — sacred)
Last 10 turns from `sacred_messages`. Copy BYTE-IDENTICAL. Connect parentUuid to last Section 3 message.

**Section 5: OBJECTIVES + NEXT STEPS** (VERY END — highest attention)
Current task, acceptance criteria, agent team state, pending items, blockers.

Each section is a user/assistant JSONL pair. Generate UUIDs via `python3 -c "import uuid; print(uuid.uuid4())"`. Chain parentUuid correctly.

RULES:
1. Every decision from analysis → Section 2
2. Every file path → Section 2
3. Every URL → Section 2 or 3
4. Failed attempts → Section 3
5. Section 4 = byte-identical sacred turns
6. Valid JSONL, valid uuid chain
7. NEVER invent information
8. Output smaller than input

---

## Step 4: Validate

```bash
crisper validate current /tmp/crisper_restructured.jsonl
```

## Step 5: Write

```bash
crisper write current /tmp/crisper_restructured.jsonl
```

## Step 6: Tell user

> Restructured. [X] tokens → [Y] tokens.
> Type `/exit` then `claude --resume`.

```bash
rm -f /tmp/crisper_compact_analysis.json /tmp/crisper_restructured.jsonl
```
