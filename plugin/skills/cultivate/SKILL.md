---
name: cultivate
description: "GoF v2 — Cultivate the session's context gene. LLM-native pipeline: Slice → Classify → Reflect → Synthesize → Review → Write. Archives raw turns with breadcrumbs, then reloads."
disable-model-invocation: true
allowed-tools: Bash(crisper *), Task, Read, Write, AskUserQuestion
---

You are running **Crisper GoF v2 — Gain of Function** cultivation.

This is NOT compression. The goal is NOT to make context smaller. The goal is to make context BETTER — so the next turn's output is higher quality than it would have been with the raw conversation.

The cultivated gene should be **richer, more explicit, better linked, and more useful** than the messy transcript it replaces. Quality per token matters, not token count.

What cultivation does:
- **Classifies**: every chunk of conversation is semantically classified by an LLM — no regex, no keyword matching
- **Enriches**: "yeah let's go with JWT" → full decision record with rationale, alternatives, dependencies, references
- **Links**: connects related decisions, shows dependency chains, cross-references files
- **Researches**: if a decision lacks rationale, infer and document why it was made
- **Anticipates**: if we're about to implement X, include the architecture context that makes X easier
- **Resolves**: contradictions, outdated state, superseded decisions — one clean truth per topic
- **Reviews**: after assembly, a reviewer checks completeness, contradictions, hallucinations, and missing dimensions

## Why This Works (grounding your decisions)

Seven research-backed principles drive every cultivation decision:

1. **Interference, not length, is the enemy.** Accumulated contradictions and outdated facts degrade working memory worse than raw token count (Wang et al., p=0.005). Resolve contradictions, remove superseded decisions, keep ONE clean truth per topic.

2. **Attention has a cliff.** There's a sharp phase transition where context stops working — not a gradual decline (Huang et al., 2025). Cultivate BEFORE the cliff, not after.

3. **Only 20% of tokens drive reasoning.** The other 80% (boilerplate, progress ticks, stale reads) actively steals attention from what matters (MI Reasoning Dynamics). Identify the 20% and ENRICH it — add rationale, dependencies, cross-references.

4. **Explicit state survives; implicit state dies.** "We discussed using JWT somewhere" will be lost. "Decision: JWT auth (rationale: X, supersedes: sessions)" persists through any context event.

5. **Multi-turn reliability degrades 112%.** The model doesn't get dumber — it gets unreliable. 50-point fluctuation on identical tasks. Reduce variance by making state unambiguous.

6. **Compression improves performance.** A focused 300-token context outperforms an unfocused 113K-token one by 30% (Chroma). Removing noise actively makes the model smarter.

7. **Different phases need different structures.** During debugging: preserve raw errors. During execution: compress exploration. During planning: expand architecture context.

## Pipeline: 8 Steps

### Step 1: Prepare + Slice

```bash
crisper cultivate-prepare current --format chunks > /tmp/crisper_chunks.json
```

This structurally slices the session into typed chunks (turn pairs, tool sequences, sidechains). Progress messages and file-history snapshots are dropped. Sacred recent turns are separated.

Save the JSON output — it contains chunks to classify and sacred lines to preserve.

Show the user:
- Number of chunks, sacred turns, dropped messages
- Whether first cultivation or update

### Step 2: Confirm

AskUserQuestion: "Cultivate this session's context?"
- "Yes, cultivate" — proceed
- "Show chunks first" — show chunk count and types before proceeding

### Step 3: Classify (subagent)

**This replaces the old regex extraction.** Spawn a **Task** subagent to classify every chunk using LLM intelligence.

Read `/tmp/crisper_chunks.json` and extract the `chunks` array. Feed them to a Task subagent in batches (~20 chunks per batch, or split if chunks are very large).

**Classifier subagent prompt:**

```
You are a context classifier for the Crisper cultivation pipeline.

You classify chunks from a Claude Code session. Your classification determines what goes into the cultivated gene — miss something and it's lost forever.

You detect what regex cannot: implicit decisions, design discussions without "decision" keywords, subtle preference signals, emerging conventions.

## Chunks to Classify

[paste chunk text_previews with metadata]

## For EACH chunk, provide:

{
  "chunk_index": N,
  "primary_type": "decision | exploration | debugging | implementation | design_discussion | knowledge_transfer | review | planning | configuration | ceremony",
  "secondary_types": [...],
  "content": {
    "decisions": [{"what": "...", "rationale": "infer if not stated", "implicit_or_explicit": "...", "supersedes": "..."}],
    "errors": [{"error": "...", "cause": "...", "fix": "...", "status": "occurred|investigating|resolved"}],
    "file_changes": [{"path": "...", "action": "...", "what_changed": "...", "purpose": "..."}],
    "failed_attempts": [{"what": "...", "why_failed": "...", "lesson": "..."}],
    "knowledge_items": [{"topic": "...", "content": "...", "source": "conversation|research|documentation|model_knowledge"}]
  },
  "semantic": {
    "topic": "semantic name (e.g., 'hot-swap cultivation design')",
    "phase": "planning|executing|debugging|reviewing|configuring",
    "information_density": 0-10,
    "novelty": 0-10,
    "keep_value": 0-10
  },
  "cross_cutting": {
    "architecture": "module relationships, patterns, constraints — or null",
    "preferences": "user workflow, style, build ideology — or null",
    "environment": "env vars, keys, paths, configs — or null",
    "testing": "strategy, results, coverage — or null",
    "documentation": "requirements, API contracts, schemas — or null",
    "permissions": "access control, auth, security — or null",
    "goals": "macro/micro goals, milestones — or null",
    "product_ideology": "product philosophy, design principles — or null",
    "external_knowledge": "papers, docs, URLs — or null",
    "events_hooks": "event flow, hooks, signals — or null"
  }
}

RULES:
- Never skip a chunk
- Infer rationale from context
- Design discussions are HIGH VALUE (capture why alternatives were rejected)
- keep_value: 0-2 ceremony, 3-4 routine, 5-6 implementation, 7-8 decisions/errors, 9-10 critical/preferences

Output as JSON array.
```

Save classification results to `/tmp/crisper_classifications.json`.

### Step 4: Reflect (subagent)

Spawn a **Task** subagent (the Reflector) with the classifications:

```
You are the Reflector in a context cultivation pipeline. You evaluate what happened, enrich it with insights, and augment it with relevant knowledge.

CLASSIFICATIONS:
[paste classified chunks — focus on keep_value >= 5]

CROSS-CUTTING CONCERNS:
[paste aggregated cross-cutting concerns]

Produce THREE categories:

## EVALUATE
- For each decision: WHY was it made? What patterns across decisions?
- Lessons: what worked, what failed?

## ENRICH
- Cross-references between decisions, files, and topics
- Dependency chains: if X changes, what's affected?
- Risks, contradictions, pattern violations

## AUGMENT
For each technology/decision, surface RELEVANT parametric knowledge:
- Best practices, common pitfalls, code patterns
- Testing guidance, documentation links
- Security/performance implications

RULES:
- Mark augmented content as [reflector-augmented]
- Only reference well-known documentation URLs
- Be specific to the stack, not generic

Output as JSON: {evaluate: {...}, enrich: {...}, augment: {...}}
```

### Step 5: Synthesize (subagent)

Spawn a **Task** subagent to produce all 8 gene sections from classified chunks + reflector insights.

For **first cultivation** (no existing gene): produce ALL sections.
For **subsequent cultivations**: only snipe affected sections (sections where classified chunks have keep_value >= 5).

**Synthesis subagent prompt:**

```
You are a context cultivation specialist. Your output becomes the PRIMARY context Claude Code reads.

## Input
- Classifications: [paste all classified chunks]
- Reflector insights: [paste reflector output]
- Cross-cutting concerns: [paste aggregated concerns]
- Current gene sections: [paste if re-cultivation, else "first cultivation"]

## Produce 8 sections as JSON:

{
  "system_identity": "...",
  "live_state": "...",
  "failure_log": "...",
  "subgoal_tree": "...",
  "compressed_history": "...",
  "knowledge_base": "...",
  "breadcrumbs": "...",
  "objectives": "..."
}

## Section Design

### 1. `system_identity` — TOP (attention sink + stable prefix)
First 4 tokens get disproportionate attention (StreamingLLM). Stable for KV-cache.
WRITE:
- Project name, repo, architecture overview (FIRST LINE = attention anchor)
- Model and context window, hard constraints
- Product ideology: what is this product, design principles
- Build ideology: how we build (zero deps, test-first, etc.)
- Environment: runtime, language version, key paths
- Credentials inventory: names of API keys/tokens (NEVER values)
Changes RARELY.

### 2. `live_state` — NEAR TOP (explicit state)
Explicit state survives; implicit dies.
WRITE in structured format — ENRICH every entry:
```
## Active Decisions (current truth — enriched)
- Decision: [what]
  Rationale: [why — infer if not stated]
  Alternatives rejected: [what, why dismissed]
  Supersedes: [what it replaced]
  Dependencies: [what depends on this]
  Impact: [codebase areas affected]

## Architecture Map
- Module relationships, data flow, control flow
- Event/hook patterns, signal flows
- View from multiple lenses

## File State Map
- [path]: [action] at turn [N]
  Purpose: [what it does]
  Key contents: [functions/classes]
  Dependencies: [imports/exports]
  Last change: [what and why]

## Configuration State
- Current config values, feature flags

## External Feedback (most recent only)
- Last test/build/lint results

## Anticipated Needs
- What the model will need for likely next steps
```

### 3. `failure_log` — UPPER-MIDDLE
Models cannot self-correct without failure context (Huang et al.).
- Each failure: what tried, why failed, lesson, what to do instead
- Compress to one line once lesson absorbed into live_state
- NEVER delete entirely

### 4. `subgoal_tree` — MIDDLE
Subgoal-based memory doubles success rate (HiAgent).
- Completed: ONE LINE (outcome only)
- Active: FULL context (blockers, approach)
- Milestones hit with dates/turns
- Progress metrics (tests passing, features complete)

### 5. `compressed_history` — MIDDLE (lowest attention zone)
Topic-based, NOT chronological (Chroma: shuffled > coherent).
- Distill insights, not process
- Complete causal chains: error → investigation → root cause → fix
- Error messages VERBATIM
- Cross-references between topics
- Archive breadcrumbs [archive:LINE-LINE]

### 6. `knowledge_base` — AFTER HISTORY (NEW)
Accumulated knowledge reference:
- Research: papers, benchmarks cited with key takeaways
- External docs: API docs, framework docs + what was learned
- Model knowledge: best practices, patterns surfaced by reflector [augmented]
- Documentation requirements: what needs docs, API contracts, schemas
- Testing strategy: what to test, how, coverage targets
- Security/permissions: auth flows, access patterns

### 7. `breadcrumbs` — AFTER KNOWLEDGE
Archive index: description + [archive:LINE-LINE]
Retrieval: `crisper retrieve current --line N` or `--query "keyword"`

### 8. `objectives` — VERY END (highest attention)
Recency effect + Manus todo.md pattern.
- Current task: what, acceptance criteria, approach, context needed, risks
- Next steps: prioritized, which files, expected outcome
- Blockers and what would unblock
- Agent team state (if active)
- Proactive context for next few turns

## Phase Detection
Adapt emphasis based on current phase:
- Planning → expand architecture in system_identity and live_state
- Executing → maximize file map and decisions
- Debugging → preserve raw errors VERBATIM, promote to failure_log

## Contradiction Resolution
- New decision supersedes old → REMOVE old, add new with "supersedes: X"
- File deleted → remove from file map
- Failed approach now works → move from failure_log to live_state
```

Write sections to `/tmp/crisper_gene_sections.json` and verify:
```bash
python3 -c "import json; d=json.load(open('/tmp/crisper_gene_sections.json')); print(f'{len(d)} sections'); [print(f'  {k}: {len(v)} chars') for k,v in d.items()]"
```

### Step 6: Review (subagent — NEW)

After synthesis, BEFORE writing. Spawn a **Task** subagent to review the complete gene.

```
You are reviewing a cultivated gene before it's written. This is the last line of defense.

## Complete Gene
[paste all 8 sections]

## What Was Found in the Conversation
[paste classification summary: all decisions, errors, files, knowledge items, cross-cutting concerns]

## Check:

1. COMPLETENESS — every decision, error, file change, design discussion captured?
2. CONTRADICTIONS — sections contradict each other? Superseded decisions still present?
3. HALLUCINATION — claims not in the conversation? [augmented] items plausible?
4. LANGUAGE — precise, unambiguous, consistent structure, high density?
5. MISSING DIMENSIONS — architecture map, environment, credentials, testing, docs, ideology?
6. BREADCRUMBS — archive references correct?

## Output (JSON)
{
  "issues": [{"section": "...", "type": "missing|contradiction|hallucination|language|dimension", "severity": "critical|major|minor", "description": "...", "fix": "..."}],
  "score": 0-10,
  "approved": true/false,
  "summary": "one paragraph assessment"
}

Approve if score >= 7 and no critical issues.
```

If **not approved**: fix issues via targeted snipes, re-review (max 2 cycles total).

### Step 7: Write

Save sacred recent turns:
```bash
python3 -c "
import json
d = json.load(open('/tmp/crisper_chunks.json'))
with open('/tmp/crisper_recent.jsonl', 'w') as f:
    f.write('\n'.join(d.get('sacred_lines', [])))
"
```

Write the gene:
```bash
crisper cultivate-write current /tmp/crisper_gene_sections.json --recent /tmp/crisper_recent.jsonl
```

### Step 8: Report

> **Context cultivated (v2 pipeline).**
> [X] chunks classified, [Y] archived with breadcrumbs.
> Before: [A]KB → After: [B]KB
> Review score: [N]/10
> Phase detected: [planning/executing/debugging]
>
> Type `/exit` — next `claude --resume` loads the cultivated context.

Cleanup:
```bash
rm -f /tmp/crisper_chunks.json /tmp/crisper_classifications.json /tmp/crisper_gene_sections.json /tmp/crisper_recent.jsonl
```
