# CE-Bench: Evaluating Context Engineering for LLM Coding Agents

**Junaid Qureshi, Ruya AI**

## Abstract

Long-running LLM coding sessions accumulate context bloat — progress ticks, stale file reads, duplicate system-reminders, and metadata noise that wastes tokens and triggers lossy auto-compaction. While several approaches exist for managing context (Anthropic's built-in compaction, Factory.ai's anchored summarization, JetBrains' observation masking), no standardized benchmark measures context preservation fidelity: how much task-relevant information survives after compression?

We introduce **CE-Bench** (Context Engineering Benchmark), an evaluation framework that measures context preservation across 8 dimensions using an LLM-judge protocol. We evaluate 5 conditions: raw (unmodified), noise-pruned (Cozempic), Anthropic-style compaction, Factory-style 4-anchor summarization, and our approach — **Crisper Context**, which restructures session context into a 5-section layout grounded in attention research (Liu et al., 2024), cache optimization (Manus AI), and information density findings (Chroma, 2025).

In our initial evaluation on a real 2,940-turn Claude Code session (517K tokens), Crisper Context scored **4.21/5** overall, compared to Factory-style (3.52), Anthropic-style compaction (3.41), and raw uncompressed (2.46). The raw session scored lowest despite containing all information — confirming the Lost in the Middle effect (Liu et al., 2024) where long-context models cannot effectively access information buried in the middle of large sessions.

Our key contributions:
1. **CE-Bench** — the first open benchmark for context preservation fidelity in LLM coding agents
2. **Crisper Context** — a context engineering tool that restructures (not just prunes) session context into scientifically optimal form
3. **Artifact trail solution** — existing approaches score 2.19-3.50/5 on file/artifact tracking (Factory.ai); Crisper achieves 4.00/5 through explicit extraction
4. **Empirical confirmation** — raw uncompressed sessions score worse than compressed ones because information accessibility matters more than information presence

CE-Bench and Crisper Context are open-source at github.com/Ruya-AI.

## 1. Introduction

LLM coding agents (Claude Code, Cursor, Aider, Codex) conduct extended sessions where the conversation history serves as working memory. As sessions grow — often to 100K-500K tokens — they accumulate substantial noise: hundreds of progress tick messages, repeated thinking blocks, stale file reads superseded by later edits, duplicate document injections, and metadata fields (token counts, stop reasons, cost fields). A typical session carries 20-50% noise by token count.

When context nears the model's window limit, auto-compaction triggers — a lossy summarization that frequently destroys critical state. For Agent Teams, this is catastrophic: the lead agent's context is compacted, team coordination messages are discarded, and subagents are orphaned.

The standard response has been compression — reducing context to fit within limits. Factory.ai evaluated three approaches and found their structured method (3.70/5) outperformed Anthropic (3.44/5) and OpenAI (3.35/5) on a 6-dimension rubric across 36,611 production messages. However, all three approaches scored poorly on artifact trail preservation (2.19-2.45/5), and no standardized benchmark exists for comparing approaches.

We argue that the field needs:
1. A **standardized benchmark** for context preservation fidelity
2. A shift from **compression** (make it smaller) to **engineering** (make it optimal)
3. Research-grounded context structure that respects attention patterns, cache mechanics, and information density

### 1.1 Tokens per task, not per request

Factory.ai's key insight: "The right optimization target is not tokens per request. It is tokens per task." OpenAI's 99.3% compression achieved the smallest per-request context but caused agents to re-fetch files, re-read docs, and re-explore rejected approaches — increasing total task cost.

## 2. Related Work

### 2.1 Context compression

**Anthropic compaction**: Default summarization preserving "state, next steps, learnings." Scored 3.44/5 on Factory.ai's evaluation.

**Factory.ai's anchored iterative summarization**: Four persistent sections (session intent, file modifications, decisions made, next steps). Scored 3.70/5. All providers scored poorly on artifact trail (2.19-2.45/5).

### 2.2 Observation masking

**JetBrains Research (NeurIPS 2025)**: Simple observation masking matches or beats LLM summarization at 52% lower cost. Optimal window: 10 recent turns in full detail. LLM summarization caused 13-15% trajectory elongation.

### 2.3 Attention patterns

**Liu et al. (TACL 2024)**: U-shaped attention — performance highest at beginning and end, degraded in the middle.

**Chroma (July 2025)**: All 18 models tested degrade with context length. Models performed better on shuffled text than coherent text — coherent narratives create stronger recency bias.

**NoLiMa (ICML 2025)**: At 32K tokens, 11 models dropped below 50% of baseline on inference-requiring questions.

### 2.4 Hierarchical memory

**HiAgent (ACL 2025)**: Subgoal-based memory — 2x success rate, 35% context reduction.

**ACON (KAIST, 2025)**: Gradient-free compression optimization — 26-54% token reduction, 95%+ accuracy.

### 2.5 Production context engineering

**Manus AI**: KV-cache hit rate as #1 metric (10x cost difference). Append-only context, todo.md pattern for attention manipulation, file-system as extended memory.

## 3. CE-Bench: Benchmark Design

### 3.1 Conditions

| Condition | Description | Compression | LLM calls |
|-----------|-------------|-------------|-----------|
| A: Raw | Unmodified session | 0% | 0 |
| B: Cozempic | 13 pruning strategies | 36% | 0 |
| C: Anthropic-style | Narrative summary compaction | 99.9% | 1 |
| D: Factory-style | 4-anchor structured summary | 99.8% | 1 |
| E: Crisper | 5-section optimal layout | 98.8% | 1 |

### 3.2 Evaluation protocol

For each session: (1) generate 10 test questions targeting 8 dimensions, (2) generate ground truth answers from complete session, (3) apply each condition, (4) answer questions from each condition's context using the same model, (5) judge answers against ground truth on 8 dimensions, (6) aggregate with statistical tests.

All LLM steps use the same model (Claude Opus 4.6) for fair comparison.

### 3.3 Scoring dimensions

We adopt Factory.ai's 6 dimensions and add 2:

| Dimension | Source | Weight |
|-----------|--------|--------|
| Accuracy | Factory.ai | 1.0 |
| Context Awareness | Factory.ai | 1.0 |
| Artifact Trail | Factory.ai | 1.5 |
| Completeness | Factory.ai | 1.0 |
| Continuity | Factory.ai | 1.0 |
| Instruction Following | Factory.ai | 1.0 |
| Token Efficiency | CE-Bench | 0.5 |
| Cache Friendliness | CE-Bench | 0.5 |

Artifact trail receives 1.5x weight as it was identified as the key weakness across all existing approaches.

## 4. Crisper Context: Our Approach

### 4.1 Architecture

The system has two modes:
- **Skill mode**: Claude Code subagent does the restructuring (production use, no API key needed)
- **API mode**: Direct Anthropic API calls (benchmarking, reproducible evaluation)

Both modes use the same pipeline: Analyze (local extraction) → Engineer (LLM restructuring) → Validate (local verification) → Write (atomic swap with backup).

### 4.2 The 5-section layout

| Section | Position | Research basis |
|---------|----------|---------------|
| System State | Top | Manus: stable prefix for KV-cache (10x cost reduction) |
| Structured State | Near top | Factory: 4-anchor preservation (3.70/5) |
| Compressed History | Middle | Chroma: topic-based > chronological; Liu: middle = lowest attention |
| Recent Turns | Near end | JetBrains: 10-turn optimal window |
| Objectives | Very end | Manus: todo.md in recency window; Liu: end = highest attention |

### 4.3 Artifact trail solution

Factory.ai identified artifact trail as "unsolved" (2.45/5). Crisper's Phase 1 analyzer explicitly extracts every file path from every Read/Write/Edit tool call, building a complete artifact map. This structured extraction is passed to the LLM as input, which must include every file path in Section 2.

## 5. Results

### 5.1 Initial evaluation

Evaluated on a real 2,940-turn Claude Code session (517K tokens) spanning codebase exploration, feature development, community engagement, research, and tool building.

| Dimension | Raw (A) | Cozempic (B) | /compact (C) | Factory (D) | Crisper (E) |
|-----------|--------:|-----------:|-----------:|----------:|----------:|
| Accuracy | 2.50 | 2.50 | 3.80 | 3.70 | **4.40** |
| Context Awareness | 2.60 | 2.40 | 3.60 | 3.50 | **4.40** |
| Artifact Trail | 2.30 | 2.60 | 3.20 | 3.50 | **4.00** |
| Completeness | 2.10 | 2.00 | 3.30 | 3.10 | **3.50** |
| Continuity | 2.40 | 2.20 | 3.50 | 3.40 | **4.00** |
| Instruction Following | 3.40 | 2.60 | 3.60 | 3.60 | **4.40** |
| Token Efficiency | 3.00 | 2.60 | 3.90 | 3.70 | **4.80** |
| Cache Friendliness | 1.00 | 1.00 | 2.00 | 4.00 | **5.00** |
| **OVERALL** | **2.46** | **2.32** | **3.41** | **3.52** | **4.21** |

### 5.2 Key findings

**Finding 1: Raw sessions score worst.** Despite containing all information, the raw 8.5MB session scored 2.46/5 — lower than every compressed approach. The model could not effectively access information in the middle of the session, confirming the Lost in the Middle effect in a practical setting.

**Finding 2: Crisper beats Factory by +0.69.** The 5-section structured layout (4.21) outperformed the 4-anchor approach (3.52) across every dimension. The key difference: position-aware placement (critical info at edges, compressed history in middle) and explicit artifact extraction.

**Finding 3: Artifact trail is solvable.** Crisper scored 4.00 vs Factory 3.50 on artifact trail — the dimension Factory identified as "unsolved." Explicit file path extraction in Phase 1, combined with LLM-structured Section 2, closes this gap.

**Finding 4: Noise pruning alone doesn't help.** Cozempic (2.32) scored marginally lower than raw (2.46). Removing noise without restructuring doesn't address the fundamental problem — the session is still too large for effective information access.

**Finding 5: Compression + structure > compression alone.** Anthropic-style narrative compaction (3.41) performed well but was outperformed by structured approaches (Factory 3.52, Crisper 4.21), confirming Factory's finding that "structure forces preservation."

### 5.3 Comparison with published baselines

| Source | Their score | Our replication |
|--------|------------|----------------|
| Factory.ai (their approach) | 3.70 | 3.52 |
| Factory.ai (Anthropic) | 3.44 | 3.41 |
| Factory.ai (OpenAI) | 3.35 | Not tested |

Our Anthropic-style replication (3.41) closely matches Factory's published score (3.44), validating our benchmark methodology. Our Factory-style replication (3.52) is slightly below their published 3.70, likely due to implementation differences.

## 6. Discussion

### 6.1 Why raw sessions lose

This is the most counterintuitive finding. A session containing 100% of the information scored lower than sessions with 98.8-99.9% compression. The explanation is the Lost in the Middle effect: transformer attention patterns favor the beginning and end of context, systematically under-weighting information in the middle. For a 2,940-turn session, decisions made at turn 500 are effectively invisible.

This has practical implications: **more context is not better context.** The model's effective context is determined by attention patterns, not window size. Structured compression that places critical information in attention-favorable positions outperforms raw access to all information.

### 6.2 Limitations

- **Single session**: Initial evaluation on one session. Need 50+ sessions across diverse task types for statistical significance.
- **Condition C simulation**: We simulated Anthropic's /compact rather than using the actual API endpoint. Our replication closely matches Factory's published score (3.41 vs 3.44).
- **Condition D replication**: We implemented Factory's 4-anchor approach but don't have access to their exact code. Our replication scores slightly below their published 3.70.
- **Same-model judge bias**: The judge (Opus 4.6) is the same model that generated answers. Cross-model judging would strengthen results.
- **No human validation**: All scoring is LLM-based. A human evaluation sample would validate the rubric.

### 6.3 Future work

- **Lossless compression**: Compress context without losing information — semantic deduplication, reference compression, tokenizer-aware rewriting.
- **Subagent progress deduplication**: Individual progress entries carrying 3MB of duplicate normalizedMessages — potential 60-95% savings.
- **Cross-session persistence**: Bridge context engineering across sessions using external memory.

## 7. Conclusion

We introduce CE-Bench, a benchmark for evaluating context preservation fidelity in LLM coding agents, and Crisper Context, a tool that restructures session context into a position-aware 5-section layout. Our initial evaluation shows Crisper (4.21/5) outperforms Factory-style compression (3.52), Anthropic-style compaction (3.41), and raw sessions (2.46) across all 8 dimensions. The most significant finding is that raw uncompressed sessions score worst — confirming that information accessibility matters more than information presence.

CE-Bench and Crisper Context are open-source at github.com/Ruya-AI.

## References

[1] Liu et al., "Lost in the Middle: How Language Models Use Long Contexts," TACL 2024.
[2] Chroma Research, "Context Rot," July 2025.
[3] JetBrains Research, "The Complexity Trap," NeurIPS 2025 DL4Code Workshop.
[4] Factory.ai, "Evaluating Context Compression," 2025.
[5] Factory.ai, "Compressing Context," 2025.
[6] Manus AI, "Context Engineering for AI Agents," July 2025.
[7] Anthropic, "Effective Context Engineering for AI Agents," September 2025.
[8] ACON, "Optimizing Context Compression," KAIST, October 2025.
[9] HiAgent, "Hierarchical Working Memory," ACL 2025.
[10] ReSum, "Context Summarization for Web Agents," 2025.
[11] NoLiMa, "Long-Context Evaluation," ICML 2025.
[12] "A Survey of Context Engineering for LLMs," July 2025.
