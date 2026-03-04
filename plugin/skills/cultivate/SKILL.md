---
name: cultivate
description: "GoF — Cultivate the session's context gene. Absorbs recent turns into structured sections grounded in attention research, resolves contradictions, promotes implicit→explicit state, archives raw turns with breadcrumbs. Then reloads."
disable-model-invocation: true
allowed-tools: Bash(crisper *), Task, Read, Write, AskUserQuestion
---

You are running **Crisper GoF — Gain of Function** cultivation.

This is NOT compression. This is context architecture — restructuring what the model sees so every subsequent turn benefits from cleaner, more accessible information.

## Why This Works (grounding your decisions)

Seven research-backed principles drive every cultivation decision:

1. **Interference, not length, is the enemy.** Accumulated contradictions and outdated facts degrade working memory worse than raw token count (Wang et al., p=0.005). Your job: resolve contradictions, remove superseded decisions, keep ONE clean truth per topic.

2. **Attention has a cliff.** There's a sharp phase transition where context stops working — not a gradual decline (Huang et al., 2025). Cultivate BEFORE the cliff, not after.

3. **Only 20% of tokens drive reasoning.** The other 80% (boilerplate, progress ticks, stale reads) actively steals attention from what matters (MI Reasoning Dynamics). Your job: identify and promote the 20%.

4. **Explicit state survives; implicit state dies.** "We discussed using JWT somewhere" will be lost. "Decision: JWT auth (rationale: X, supersedes: sessions)" persists through any context event. Your job: crystallize every implicit decision into explicit structured state.

5. **Multi-turn reliability degrades 112%.** The model doesn't get dumber — it gets unreliable. 50-point fluctuation on identical tasks. Your job: reduce variance by making state unambiguous.

6. **Compression improves performance.** A focused 300-token context outperforms an unfocused 113K-token one by 30% (Chroma). Removing noise actively makes the model smarter.

7. **Different phases need different structures.** During debugging: preserve raw errors (summaries smooth over failure severity, causing 13-15% trajectory elongation — JetBrains). During execution: compress exploration. During planning: expand architecture context.

## Step 1: Prepare

```bash
crisper cultivate-prepare current --format json
```

Save the JSON output — it contains the analysis, raw tail to absorb, and sacred recent turns.

Show the user:
- Turns to absorb, sacred turns preserved
- Whether first cultivation or update
- Current session phase (planning/executing/debugging — infer from recent turns)

## Step 2: Confirm

AskUserQuestion: "Cultivate this session's context?"
- "Yes, cultivate" — proceeds
- "Show analysis first" — show what was extracted before proceeding

## Step 3: Spawn cultivation subagent

Write the preparation data to `/tmp/crisper_cultivation.json`:

```bash
crisper cultivate-prepare current --format json > /tmp/crisper_cultivation.json
```

Then spawn a **Task** subagent (run_in_background=false) with this prompt:

---

You are a context cultivation specialist operating on the Crisper gene model. Your output will become the PRIMARY context that Claude Code reads — it must be precise, complete, and optimally structured.

## Your Task

Read `/tmp/crisper_cultivation.json`. It contains:
- `analysis`: structured extraction (decisions, files, errors, references, topics, etc.)
- `raw_tail`: uncultivated turns to absorb (JSONL lines)
- `recent_turns`: sacred turns to preserve (DO NOT modify)
- `gene_sections_text`: current gene sections (if this is a re-cultivation)

Produce a JSON file at `/tmp/crisper_gene_sections.json` with these 8 keys. Each value is a markdown-formatted string.

## Section Design (why each section exists and where it sits)

### 1. `system_identity` — POSITION: TOP (attention sink + stable prefix)

The first 4 tokens of context receive disproportionate attention regardless of content (StreamingLLM, ICLR 2024). This section serves as the attention anchor. It also stays stable across turns for KV-cache efficiency (Manus AI: cached tokens are 10x cheaper).

WRITE:
- Project name, repo, architecture overview
- Model and context window
- Hard constraints the user specified
- Tool configurations mentioned

RULES:
- This section should RARELY change between cultivations
- Keep it concise — it's a reference header, not a narrative
- Changes only when fundamental project facts change

### 2. `live_state` — POSITION: NEAR TOP (high attention, reference material)

Explicit state declarations that the model can reliably retrieve. Research shows explicit state ("Decision: JWT auth") survives all context events while implicit state ("we talked about JWT in turn 14") is lost (Anthropic, Manus, TME).

WRITE in explicit structured format:
```
## Active Decisions (current truth only)
- Decision: [what] (rationale: [why], supersedes: [what it replaced], turn: [N])
- Decision: ...

## File State Map (what exists NOW, not history)
- [path]: [action] at turn [N], current purpose: [what it does]
- ...

## Dependency Graph
- [Decision X] depends on [Decision Y] — if Y changes, X needs review
- ...

## External Feedback (most recent)
- Last test result: [pass/fail, details]
- Last build: [success/failure]
- Last lint: [clean/warnings]
```

RULES:
- When a decision is superseded, REMOVE the old one. Don't accumulate contradictions.
- If Decision Y is revised and Decision X depends on it, flag X for review.
- File state is CURRENT state, not history. "analyzer.py: created turn 5, modified turn 15" not "analyzer.py was read at turn 3, then written at turn 5, then read again..."
- External feedback: only the MOST RECENT result. Not a log.

### 3. `failure_log` — POSITION: UPPER-MIDDLE (first-class, not buried)

Models "implicitly update internal beliefs" from failed actions (Manus AI). Self-correction WITHOUT seeing failure context does not work (Huang et al., TACL 2024). Failed attempts must be preserved to prevent repetition.

WRITE:
```
## Failed Approaches
- Approach: [what was tried]
  Why failed: [specific reason]
  Turn: [N]
  Lesson: [what to do instead]

- Approach: ...
```

RULES:
- Each failure gets WHY it failed and WHAT TO DO INSTEAD
- Once a failure's lesson is absorbed into a successful decision in live_state, you can compress the failure to one line
- Never delete failures entirely — they prevent the model from repeating them

### 4. `subgoal_tree` — POSITION: MIDDLE (hierarchical structure)

Subgoal-based memory organization doubles success rate and reduces context by 35% (HiAgent, ACL 2025). Compress when subgoals COMPLETE — cognitive boundaries are natural compression points.

WRITE:
```
## Goal: [top-level objective]
  - [x] Subgoal 1: [completed] → outcome: [one-liner]
  - [x] Subgoal 2: [completed] → outcome: [one-liner]
  - [/] Subgoal 3: [in progress]
    - Context: [what's being worked on, blockers, approach]
    - [x] Sub-sub 3.1: done
    - [ ] Sub-sub 3.2: pending
  - [ ] Subgoal 4: [not started]
```

RULES:
- Completed subgoals compress to ONE LINE (outcome only)
- Active subgoal gets FULL context (it's what the model is working on)
- Pending subgoals get brief description only
- This is a living document — update status, don't just append

### 5. `compressed_history` — POSITION: MIDDLE (lowest attention zone)

This goes in the middle deliberately. Liu et al. (TACL 2024) showed 24.6pp accuracy drop for middle-positioned information. History is the LEAST critical for ongoing work — decisions and state (above) matter more.

Chroma Research (2025) found shuffled text outperforms coherent narrative because coherent text creates stronger recency bias. Group by TOPIC, not chronology.

WRITE:
```
## Topic: [name]
[Compressed summary of what happened]
[archive:LINE-LINE for full detail]

## Topic: [name]
...
```

RULES:
- Topic-based, NOT chronological
- Include archive references (breadcrumbs) for anything compressed
- Preserve error messages VERBATIM (don't summarize error text)
- Keep URLs/links inline, drop fetched content
- If a topic is fully resolved and captured in live_state, compress to one line + breadcrumb

### 6. `breadcrumbs` — POSITION: AFTER HISTORY

Explicit index of what's in the archive and how to retrieve it. This makes compression REVERSIBLE — the model can call `crisper retrieve` to get full detail.

WRITE:
```
## Archive Index
- Turns 1-50: Initial exploration and setup [archive:1-50]
- Turns 51-80: Authentication implementation [archive:51-80]
- Turn 92: Full error trace for ENOENT bug [archive:92]
- Turns 100-120: Refactoring discussion [archive:100-120]

## How to Retrieve
Run: crisper retrieve current --line N
Or:  crisper retrieve current --query "keyword"
```

### 7. `objectives` — POSITION: VERY END (highest attention)

This goes LAST because of the recency attention effect — the model attends most strongly to the end of context. Manus AI's todo.md pattern pushes objectives into this high-attention zone deliberately.

WRITE:
```
## Current Task
[What we're working on right now + acceptance criteria]

## Next Steps
1. [Immediate next action]
2. [After that]
3. [Then]

## Blockers
- [Anything blocking progress]

## Agent Team State (if active)
- [Teammate roles and status]
```

## Phase Detection

Detect the current session phase from the raw tail content and ADAPT:

- **Planning phase** (user asking "how should we...", architecture discussion):
  → Expand system_identity with architecture detail
  → Expand subgoal_tree with full goal breakdown

- **Execution phase** (active coding, file writes, tool calls):
  → Maximize live_state (file map, decisions)
  → Compress history aggressively

- **Debugging phase** (errors, "that didn't work", retries):
  → Preserve raw error messages VERBATIM in failure_log
  → Promote error traces to live_state external feedback
  → DO NOT summarize errors — summaries smooth over failure severity (JetBrains: 13-15% trajectory elongation)

## Contradiction Resolution

When the raw tail contains information that contradicts the existing gene:
- A new decision supersedes an old one → REMOVE the old, add the new with "supersedes: X"
- A file was deleted → Remove from file state map
- A previously failed approach now works → Move from failure_log to live_state
- Test status changed → Update external feedback (keep only latest)

## Output

Write to `/tmp/crisper_gene_sections.json`:
```json
{
  "system_identity": "...",
  "live_state": "...",
  "failure_log": "...",
  "subgoal_tree": "...",
  "compressed_history": "...",
  "breadcrumbs": "...",
  "objectives": "..."
}
```

After writing, verify:
```bash
python3 -c "import json; d=json.load(open('/tmp/crisper_gene_sections.json')); print(f'{len(d)} sections'); [print(f'  {k}: {len(v)} chars') for k,v in d.items()]"
```

---

## Step 4: Write the gene

Save recent turns:
```bash
crisper cultivate-prepare current --format json | python3 -c "
import sys, json
d = json.load(sys.stdin)
with open('/tmp/crisper_recent.jsonl', 'w') as f:
    f.write('\n'.join(d.get('recent_turns', [])))
"
```

Write the cultivated gene:
```bash
crisper cultivate-write current /tmp/crisper_gene_sections.json --recent /tmp/crisper_recent.jsonl
```

## Step 5: Tell the user

> **Context cultivated.**
> [X] turns absorbed into gene, [Y] archived with breadcrumbs.
> Before: [A]KB → After: [B]KB
> Phase detected: [planning/executing/debugging]
>
> Type `/exit` — next `claude --resume` loads the cultivated context.

## Step 6: Cleanup

```bash
rm -f /tmp/crisper_cultivation.json /tmp/crisper_gene_sections.json /tmp/crisper_recent.jsonl
```
