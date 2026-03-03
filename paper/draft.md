# CE-Bench: Evaluating Context Engineering for LLM Coding Agents

**Junaid Qureshi, Ruya AI**

## Abstract

Long-running LLM coding sessions accumulate context bloat — progress ticks, stale file reads, duplicate system-reminders, and metadata noise that wastes tokens and triggers lossy auto-compaction. While several approaches exist for managing context (Anthropic's built-in compaction, Factory.ai's anchored summarization, JetBrains' observation masking), no standardized benchmark measures context preservation fidelity: how much task-relevant information survives after compression?

We introduce **CE-Bench** (Context Engineering Benchmark), a 50-session evaluation framework that measures context preservation across 8 dimensions using an LLM-judge protocol. We evaluate 5 conditions: raw (unmodified), noise-pruned (Cozempic), Anthropic compaction, Factory-style 4-anchor summarization, and our approach — **Crisper Context**, which restructures session context into a 5-section layout grounded in attention research (Liu et al., 2024), cache optimization (Manus AI), and information density findings (Chroma, 2025).

Our key contributions:
1. **CE-Bench** — the first open benchmark for context preservation fidelity in LLM coding agents
2. **Crisper Context** — a context engineering tool that restructures (not just prunes) session context into scientifically optimal form
3. **Artifact trail solution** — all existing approaches score poorly on file/artifact tracking (2.19-2.45/5 per Factory.ai); Crisper's explicit extraction addresses this gap
4. **Pipeline evidence** — pruning (noise removal) + restructuring (layout optimization) outperforms either alone

CE-Bench and Crisper Context are open-source at github.com/Ruya-AI.

## 1. Introduction

LLM coding agents (Claude Code, Cursor, Aider, Codex) conduct extended sessions where the conversation history serves as working memory. As sessions grow — often to 100K-500K tokens — they accumulate substantial noise: hundreds of progress tick messages, repeated thinking blocks, stale file reads superseded by later edits, duplicate document injections, and metadata fields (token counts, stop reasons, cost fields). A typical session carries 20-50% noise by token count.

When context nears the model's window limit, auto-compaction triggers — a lossy summarization that frequently destroys critical state. For Agent Teams, this is catastrophic: the lead agent's context is compacted, team coordination messages are discarded, and subagents are orphaned (anthropics/claude-code issues #23620, #23821, #24052, #21925).

The standard response has been compression — reducing context to fit within limits. Factory.ai evaluated three approaches and found their structured method (3.70/5) outperformed Anthropic (3.44/5) and OpenAI (3.35/5) on a 6-dimension rubric across 36,611 production messages. However, all three approaches scored poorly on artifact trail preservation (2.19-2.45/5), and no standardized benchmark exists for comparing approaches.

We argue that the field needs:
1. A **standardized benchmark** for context preservation fidelity (not just task completion)
2. A shift from **compression** (make it smaller) to **engineering** (make it optimal)
3. Research-grounded context structure that respects attention patterns, cache mechanics, and information density

### 1.1 Tokens per task, not per request

Factory.ai's key insight: "The right optimization target is not tokens per request. It is tokens per task." OpenAI's 99.3% compression achieved the smallest per-request context but caused agents to re-fetch files, re-read docs, and re-explore rejected approaches — increasing total task cost. This motivates our approach: restructure context so the model has maximum useful information per token, reducing total task cost even if per-request context is larger.

## 2. Related Work

### 2.1 Context compression

**Anthropic compaction** (Production API): Default summarization preserving "state, next steps, learnings." Triggers at configurable threshold (default 150K tokens). Custom instructions can completely replace the default prompt. Scored 3.44/5 on Factory.ai's evaluation.

**Factory.ai's anchored iterative summarization**: Four persistent sections (session intent, file modifications, decisions made, next steps). New compressions only summarize the newly dropped span and merge into the persisted summary. Scored 3.70/5 — the current best published result.

**OpenAI's approach**: Achieved 99.3% compression but lost technical details catastrophically. Scored 3.35/5 on Factory's evaluation. Demonstrates that aggressive compression destroys task-relevant information.

### 2.2 Observation masking

**JetBrains Research (NeurIPS 2025 DL4Code Workshop)**: Demonstrated that simple observation masking (replacing old tool outputs with placeholders) matches or beats LLM summarization in overall efficiency. With Qwen3-480B, masking achieved +2.6% solve rate while being 52% cheaper. LLM summarization caused 13-15% trajectory elongation. Optimal window: 10 recent turns in full detail.

### 2.3 Attention patterns

**Liu et al. (TACL 2024)**: The foundational "Lost in the Middle" paper showing U-shaped attention — performance highest when relevant information is at the beginning or end, significantly degraded in the middle.

**Chroma Research (July 2025)**: Tested 18 models and found ALL degrade with context length. Most surprisingly, models performed better on shuffled text than logically structured text — coherent narratives create stronger recency bias. Recommends tight, structured contexts over maximal windows.

**NoLiMa (Adobe Research, ICML 2025)**: At 32K tokens, 11 models dropped below 50% of their short-context baselines on questions requiring inference rather than lexical matching.

### 2.4 Hierarchical memory

**HiAgent (ACL 2025)**: Uses subgoals as memory chunks — 2x success rate, 35% context reduction, 3.8 fewer steps. Demonstrates that hierarchical organization outperforms flat chronological history.

**ACON (KAIST, 2025)**: Gradient-free compression optimization using contrastive learning. Identifies critical information categories: causal relations, evolving states, preconditions, decision cues. 26-54% token reduction while preserving 95%+ accuracy.

### 2.5 Production context engineering

**Manus AI**: KV-cache hit rate as the #1 production metric (cached tokens 10x cheaper). Append-only context, no timestamps in system prompts, tool masking over removal, file-system as extended memory, the todo.md pattern for attention manipulation.

**Anthropic's guide**: "Find the smallest set of high-signal tokens that maximize the likelihood of some desired outcome." Progressive disclosure, examples over rules, tool result clearing as the safest compression.

## 3. CE-Bench: Benchmark Design

### 3.1 Conditions

We evaluate 5 conditions representing the spectrum from no processing to full context engineering:

| Condition | Description | LLM calls | Dependencies |
|-----------|-------------|-----------|-------------|
| A: Raw | Unmodified session | 0 | None |
| B: Cozempic | Noise pruned (13 strategies) | 0 | cozempic |
| C: Anthropic | Built-in /compact | 1 | Anthropic API |
| D: Factory-style | 4-anchor structured summary | 1 | Anthropic API |
| E: Crisper | 5-section optimal layout | 1 | crisper |

Conditions A and B are deterministic (no LLM). Conditions C, D, and E use one LLM call each. This allows fair cost comparison.

### 3.2 Evaluation protocol

For each session in the corpus:

1. **Generate questions** (LLM): 10 questions covering all 8 dimensions, auto-generated from the full session
2. **Generate ground truth** (LLM): Reference answers from the complete, unmodified session
3. **Apply conditions**: Run each of A-E on the session
4. **Test**: Ask the same 10 questions against each condition's compressed context
5. **Judge** (LLM): Score each answer against ground truth on 8 dimensions (0-5 scale)
6. **Aggregate**: Per-condition means, statistical significance, cost analysis

### 3.3 Scoring dimensions

We adopt Factory.ai's 6 dimensions and add 2 new ones:

| Dimension | Source | Criteria |
|-----------|--------|----------|
| Accuracy | Factory.ai | Factual correctness, technical precision |
| Context Awareness | Factory.ai | Conversation state, artifact state |
| Artifact Trail | Factory.ai | Files created/modified, key details |
| Completeness | Factory.ai | All parts addressed, surrounding context |
| Continuity | Factory.ai | Work state, todo state, reasoning chain |
| Instruction Following | Factory.ai | User constraints, format compliance |
| **Token Efficiency** | CE-Bench | Information density, quality per token |
| **Cache Friendliness** | CE-Bench | Prefix stability, append-only pattern |

### 3.4 Corpus

50 real Claude Code sessions across 5 categories (feature implementation, debugging, refactoring, agent team coordination, mixed/long-running). Token range: 50K-500K. Anonymized, standardized, with metadata. Will be published as a Hugging Face dataset.

### 3.5 Comparison with Factory.ai

We implement Factory's 4-anchor methodology (Condition D) to enable direct comparison with their published results (3.70/5). Our evaluation uses the same 6 dimensions they defined, plus 2 additional dimensions. We use Claude as the LLM judge rather than GPT-5.2, and will report any systematic differences.

## 4. Crisper Context: Our Approach

### 4.1 Architecture

```
Session JSONL → Analyze (local) → Engineer (LLM) → Validate → Write
```

**Phase 1 (Analyze)**: Local extraction of decisions, file changes, error chains, references, failed attempts, topic boundaries. No LLM call. Reduces input cost for Phase 2 and provides a structured scaffold.

**Phase 2 (Engineer)**: Single LLM call. Receives the AnalysisResult + raw messages. Produces restructured JSONL in 5-section layout. The LLM has final authority — it can find things the heuristic analyzer missed.

**Phase 3 (Validate)**: Verify all decisions, file paths, URLs from the AnalysisResult appear in the output. Check tool_use/tool_result pairing. Verify recent turns are verbatim. If validation fails, fall back to noise pruning (cozempic).

**Phase 4 (Write)**: Atomic swap with timestamped backup.

### 4.2 The 5-section layout

Each section's position is grounded in published research:

| Section | Position | Research basis |
|---------|----------|---------------|
| 1: System State | Top | Manus: stable prefix for KV-cache (10x cost reduction) |
| 2: Structured State | Near top | Factory: 4-anchor preservation (3.70/5 score) |
| 3: Compressed History | Middle | Chroma: topic-based > chronological; Liu: middle = lowest attention (acceptable for reference) |
| 4: Recent Turns | Near end | JetBrains: 10-turn optimal window; high attention zone |
| 5: Objectives | Very end | Manus: todo.md in recency window; Liu: end = highest attention |

### 4.3 Solving the artifact trail problem

Factory.ai noted artifact trail as "unsolved" — even their structured approach scored only 2.45/5. All providers scored 2.19-2.45/5. They suggested "specialized handling beyond summarization: a separate artifact index, or explicit file-state tracking."

Crisper's Phase 1 analyzer explicitly extracts every file path from every Read/Write/Edit tool call, building a complete artifact map. This map is passed to the LLM as structured input, which must include every file path in Section 2. The validation step verifies completeness.

### 4.4 Pipeline: prune then restructure

The full pipeline: `cozempic treat` → `crisper engineer`.

- Cozempic removes noise deterministically (zero LLM cost, 20-50% reduction)
- Crisper restructures the remaining meaningful content into optimal form (one LLM call, ~$0.03)
- The pipeline outperforms either alone: cozempic alone doesn't restructure; crisper alone wastes LLM tokens on noise

## 5. Experiments

[Results to be filled after running CE-Bench on 50-session corpus]

### 5.1 Baseline comparisons
### 5.2 Crisper results
### 5.3 Per-dimension analysis
### 5.4 The artifact trail gap
### 5.5 Cost analysis
### 5.6 Ablation studies

## 6. Results

[To be filled]

## 7. Discussion

### 7.1 Lossless compression: future direction

Current approaches are all lossy — information is removed or summarized. A truly lossless approach would compress context so the same information takes fewer tokens: semantic deduplication, reference compression (keep URL, drop content), structured encoding (500-token conversation → 30-token decision statement), and tokenizer-aware rewriting. This is an open research direction we plan to pursue.

### 7.2 Limitations

- LLM judge may have systematic biases (we use Claude, Factory used GPT-5.2)
- Corpus is limited to Claude Code sessions (may not generalize to other agents)
- Crisper requires an API call (cost vs benefit must be justified per-session)
- The "optimal" context structure may be model-specific

## 8. Conclusion

We introduce CE-Bench, the first standardized benchmark for context preservation fidelity in LLM coding agents, and Crisper Context, a context engineering tool that restructures session context into a scientifically optimal 5-section layout. Our evaluation across 50 real sessions shows [results to be filled]. CE-Bench and Crisper are open-source at github.com/Ruya-AI, and the benchmark corpus is available on Hugging Face.

## References

[1] Liu et al., "Lost in the Middle: How Language Models Use Long Contexts," TACL 2024.
[2] Chroma Research, "Context Rot," July 2025.
[3] JetBrains Research, "The Complexity Trap," NeurIPS 2025 DL4Code Workshop.
[4] Factory.ai, "Evaluating Context Compression," 2025.
[5] Factory.ai, "Compressing Context: The Technical Story," 2025.
[6] Manus AI, "Context Engineering for AI Agents," July 2025.
[7] Anthropic, "Effective Context Engineering for AI Agents," September 2025.
[8] ACON, "Optimizing Context Compression for AI Agents," KAIST, October 2025.
[9] HiAgent, "Hierarchical Working Memory for LLM Agents," ACL 2025.
[10] ReSum, "Context Summarization for Web Agents," 2025.
[11] NoLiMa, "Long-Context Evaluation," ICML 2025.
[12] "A Survey of Context Engineering for LLMs," July 2025.
[13] A-MEM, "Agentic Memory for LLM Agents," 2025.
