# Your Raw Claude Code Session Scores Worse Than a 17KB Summary

We ran a benchmark comparing 5 approaches to managing Claude Code context. The result surprised us: a raw 8.5MB session scored **2.46/5** on information preservation — lower than every compressed version, including a 17KB structured summary that scored **3.52/5**.

More context isn't better context. Here's what we found.

## The problem

A typical Claude Code session accumulates 200K-500K tokens. Nearly half is noise: progress ticks, stale file reads, duplicate system-reminders, metadata. When the context window fills, auto-compaction triggers and summarizes away your decisions, file changes, and error chains.

We kept losing agent team state, decisions, and context after compaction. So we built two tools: **Cozempic** (prunes the noise) and **Crisper Context** (restructures what remains into the optimal layout for the model).

Then we asked: how do we know it actually works better?

## CE-Bench

We built an evaluation framework — CE-Bench — to measure how much information survives different compression approaches. Factory.ai published the best prior numbers: their structured approach scored 3.70/5 vs Anthropic's 3.44 vs OpenAI's 3.35.

We adopted their 6 scoring dimensions, added 2 (token efficiency, cache friendliness), and tested 5 conditions on a real 2,940-turn Claude Code session:

| Condition | What it does | Overall Score |
|-----------|-------------|:------------:|
| **Raw** | Full unmodified session (8.5MB) | 2.46 |
| **Cozempic** | Noise pruned (5.4MB) | 2.32 |
| **/compact** | Anthropic-style narrative summary (8KB) | 3.41 |
| **Factory** | 4-anchor structured summary (17KB) | 3.52 |
| **Crisper** | 5-section optimal layout (102KB) | **4.21** |

All conditions evaluated by Claude Opus 4.6 via API — same model, same questions, fair comparison.

## Why raw sessions lose

This is the counterintuitive finding. The raw session has 100% of the information. Every decision, every file path, every error chain is there. But it scored worst.

The reason is the **Lost in the Middle** effect (Liu et al., TACL 2024). Transformer attention follows a U-curve — the model attends strongly to the beginning and end of context, but information in the middle is effectively invisible. In a 2,940-turn session, a decision made at turn 500 is buried in a dead zone.

A 17KB structured summary (Factory) scored 3.52 because it placed all decisions explicitly where the model could read them. A 102KB restructured session (Crisper) scored 4.21 because it placed them in the research-proven optimal positions.

**More tokens ≠ more useful context.** The model's effective context is determined by attention patterns, not window size.

## How Crisper works

Instead of just compressing, Crisper restructures context into 5 sections, each placed where research says the model attends best:

```
Section 1: SYSTEM STATE      → Top (stable prefix, KV-cacheable)
Section 2: STRUCTURED STATE   → Near top (decisions, files, intent)
Section 3: COMPRESSED HISTORY → Middle (topic-grouped, not chronological)
Section 4: RECENT TURNS       → Near end (last 10 turns, verbatim)
Section 5: OBJECTIVES         → Very end (highest attention position)
```

Grounded in:
- **Liu et al.**: Critical info at beginning + end, compressed in middle
- **Manus AI**: Stable prefix for KV-cache (10x cost reduction), objectives in recency window
- **JetBrains**: 10-turn observation window is optimal
- **Chroma**: Topic-based grouping outperforms chronological (shuffled > coherent)
- **Factory.ai**: Structure forces preservation

## The artifact trail problem (solved)

Factory.ai called artifact trail preservation "unsolved" — even their best approach scored only 2.45/5 on tracking which files were modified. All providers scored 2.19-2.45/5.

Crisper scored **4.00/5** by extracting every file path from every Read/Write/Edit tool call during the analysis phase, then requiring the restructuring to include every path explicitly in Section 2. The extraction is deterministic (no LLM needed), and the validation step verifies completeness.

## Per-dimension results

| Dimension | Raw | /compact | Factory | Crisper |
|-----------|----:|---------:|--------:|--------:|
| Accuracy | 2.50 | 3.80 | 3.70 | **4.40** |
| Context Awareness | 2.60 | 3.60 | 3.50 | **4.40** |
| Artifact Trail | 2.30 | 3.20 | 3.50 | **4.00** |
| Completeness | 2.10 | 3.30 | 3.10 | **3.50** |
| Continuity | 2.40 | 3.50 | 3.40 | **4.00** |
| Instruction Following | 3.40 | 3.60 | 3.60 | **4.40** |
| Token Efficiency | 3.00 | 3.90 | 3.70 | **4.80** |
| Cache Friendliness | 1.00 | 2.00 | 4.00 | **5.00** |

Crisper wins every dimension.

## What this means for you

If you're running long Claude Code sessions:

1. **Your raw session is hurting you.** The model literally can't see decisions you made 500 turns ago.
2. **Noise pruning alone doesn't fix it.** Cozempic removes progress ticks and stale reads, but if the session is still too large, the Lost in the Middle problem persists.
3. **Structure matters more than size.** A 102KB restructured session outperforms an 8.5MB raw one.
4. **Artifact trail needs explicit tracking.** Generic summarization drops file paths. You need to extract them deterministically.

## Try it

```bash
pip install cozempic    # prune noise
pip install crisper     # restructure context (coming soon)
```

Cozempic is live (6,800+ downloads, 120 stars). Crisper is in development — the CE-Bench results are from our first evaluation run.

## Limitations (honest)

- This is one session. We need 50+ for statistical significance.
- Our /compact condition is a simulation, not the actual Anthropic API.
- Our Factory condition is our implementation, not their exact code.
- The judge model is the same as the answer model.
- No human validation yet.

We're planning to run on 50 diverse sessions and submit to NeurIPS 2026 Datasets & Benchmarks.

## Links

- [CE-Bench results](https://github.com/Ruya-AI/crisper/blob/main/benchmarks/opus_api_run.json)
- [Crisper Context](https://github.com/Ruya-AI/crisper)
- [Cozempic](https://github.com/Ruya-AI/cozempic)
- [CE-Bench specification](https://github.com/Ruya-AI/crisper/blob/main/CE-BENCH.md)
- [Full paper draft](https://github.com/Ruya-AI/crisper/blob/main/paper/draft.md)

Built by [Ruya AI](https://ruya.ai). Feedback welcome — open an issue or comment on the repo.
