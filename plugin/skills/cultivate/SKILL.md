---
name: cultivate
description: "GoF — Cultivate the session's context gene. Absorbs recent turns into structured sections grounded in attention research, resolves contradictions, promotes implicit→explicit state, archives raw turns with breadcrumbs. Then reloads."
disable-model-invocation: true
allowed-tools: Bash(crisper *), Task, Read, Write, AskUserQuestion
---

You are running **Crisper GoF — Gain of Function** cultivation.

This is NOT compression. The goal is NOT to make context smaller. The goal is to make context BETTER — so the next turn's output is higher quality than it would have been with the raw conversation.

The cultivated gene should be **richer, more explicit, better linked, and more useful** than the messy transcript it replaces. If that means the gene is LARGER than the raw tail it absorbed — that's correct. Quality per token matters, not token count.

What cultivation does:
- **Enriches**: "yeah let's go with JWT" → full decision record with rationale, alternatives, dependencies, references
- **Links**: connects related decisions, shows dependency chains, cross-references files
- **Researches**: if a decision lacks rationale, infer and document why it was made
- **Anticipates**: if we're about to implement X, include the architecture context that makes X easier
- **Resolves**: contradictions, outdated state, superseded decisions — one clean truth per topic

## Why This Works (grounding your decisions)

Seven research-backed principles drive every cultivation decision:

1. **Interference, not length, is the enemy.** Accumulated contradictions and outdated facts degrade working memory worse than raw token count (Wang et al., p=0.005). Your job: resolve contradictions, remove superseded decisions, keep ONE clean truth per topic.

2. **Attention has a cliff.** There's a sharp phase transition where context stops working — not a gradual decline (Huang et al., 2025). Cultivate BEFORE the cliff, not after.

3. **Only 20% of tokens drive reasoning.** The other 80% (boilerplate, progress ticks, stale reads) actively steals attention from what matters (MI Reasoning Dynamics). Your job: identify the 20% and ENRICH it — add rationale, dependencies, cross-references. Remove the 80% noise. The result may be similar in size but dramatically higher in quality.

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

## Step 3: Detect changes and snipe

Write the preparation data to `/tmp/crisper_cultivation.json`:

```bash
crisper cultivate-prepare current --format json > /tmp/crisper_cultivation.json
```

**THREE-STEP CULTIVATION: Analyze → Reflect → Snipe**

Do NOT rewrite the entire gene. The pipeline is:

### Step 3a: ANALYZE (detect what changed)
Read the preparation data. Identify changes in the raw tail:
- New decisions → affects: live_state, dependencies, objectives
- New files created/modified → affects: live_state.file_map
- Errors occurred → affects: failure_log, live_state.feedback
- Subgoal completed → affects: subgoal_tree
- Decision superseded → affects: live_state (remove old + add new), failure_log (add abandoned)
- Phase shifted → affects: section emphasis
- Nothing structural → just archive the tail, no section changes

### Step 3b: REFLECT (evaluate + enrich + augment)
Spawn a **Task** subagent (the Reflector) with this prompt:

```
You are the Reflector in a context cultivation pipeline. You evaluate what happened, enrich it with insights, and augment it with relevant knowledge the conversation never contained.

CHANGES DETECTED:
[paste the change list from step 3a]

CURRENT GENE STATE:
[paste the affected sections from the gene]

RAW TAIL (new turns):
[paste the raw tail]

Produce THREE categories of insights:

## EVALUATE (what happened and why)
- For each decision: WHY was it made? What was the implicit rationale?
- Patterns: what preferences is the user showing? (simplicity vs scalability, speed vs correctness, etc.)
- Lessons: what worked, what failed, what should be done differently?

## ENRICH (connect the dots)
- Cross-references: which decisions relate to which files and topics?
- Dependency chains: if X changes, what else is affected?
- Risks: contradictions, technical debt, scaling concerns, security gaps
- Pattern violations: is a new decision inconsistent with established patterns?

## AUGMENT (bring in knowledge the conversation lacks)
For each technology/decision in the changes, surface RELEVANT parametric knowledge:
- Best practices specific to THIS use case (not generic advice)
- Common pitfalls that apply given the current architecture and stack
- Code patterns the model should follow for consistency
- What should be tested given these changes
- Relevant official documentation links
- Security considerations if applicable
- Performance implications if applicable

RULES:
- Only augment with knowledge DIRECTLY relevant to the current state
- Mark augmented content as [reflector-augmented]
- Don't hallucinate links — only reference well-known documentation URLs
- Be specific to the stack, not generic ("for FastAPI + SQLAlchemy" not "for web apps")

Output as JSON:
{
  "evaluate": {"decisions": [...], "patterns": [...], "lessons": [...]},
  "enrich": {"cross_refs": [...], "dependencies": [...], "risks": [...]},
  "augment": {"best_practices": [...], "pitfalls": [...], "patterns": [...], "testing": [...], "docs": [...]}
}
```

### Step 3c: SNIPE (surgical section updates with reflector insights)
For **first cultivation** (no existing gene): spawn a subagent to produce ALL sections. For **subsequent cultivations**: only snipe affected sections, enriched with reflector output.

When sniping, pass the reflector's insights to each section's update prompt so the sniper can embed them.

### First cultivation (bootstrap): spawn subagent for all sections

Use **Task** (run_in_background=false) with this prompt:

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

WRITE in explicit structured format — and ENRICH every entry:
```
## Active Decisions (current truth only — enriched)
- Decision: [what]
  Rationale: [why — if the conversation didn't state why, INFER from context]
  Alternatives rejected: [what was considered and dismissed]
  Supersedes: [what it replaced, if anything]
  Dependencies: [what other decisions/files depend on this]
  Impact: [what parts of the codebase this affects]
  Turn: [N]

## File State Map (what exists NOW — enriched with purpose)
- [path]: [created/modified] at turn [N]
  Purpose: [what this file does in the architecture]
  Key contents: [main functions/classes/exports]
  Dependencies: [what it imports, what imports it]
  Last change: [what was changed and why]

## Dependency Graph
- [Decision X] depends on [Decision Y] — if Y changes, X needs review
- [File A] imports from [File B] — changes to B affect A
- [Feature X] requires [Feature Y] to be complete first

## External Feedback (most recent)
- Last test result: [pass/fail, count, details]
- Last build: [success/failure, errors if any]
- Last lint: [clean/warnings]

## Anticipated Needs (proactive)
- If the next task is [X], the model will need: [relevant architecture context, file paths, decisions]
- Known risks: [things that could go wrong based on current state]
```

RULES:
- ENRICH every decision with rationale, alternatives, and dependencies — even if the conversation was casual about it
- When a decision is superseded, REMOVE the old one. Don't accumulate contradictions.
- If Decision Y is revised and Decision X depends on it, flag X for review.
- File state includes PURPOSE and KEY CONTENTS — not just "it exists"
- Add an "Anticipated Needs" section that proactively surfaces context for likely next steps
- The live state should be so good that the model never needs to re-read a file or re-ask a question

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

WRITE — distill and enrich, don't just summarize:
```
## Topic: [name]
What happened: [distilled narrative — not "we discussed X" but "X was implemented because Y"]
Key outcome: [the concrete result]
Lessons learned: [what this taught us that applies going forward]
Causal chain: [if errors were involved: error → investigation → root cause → fix]
References: [URLs, docs consulted]
[archive:LINE-LINE for full raw discussion]

## Topic: [name]
...
```

RULES:
- Topic-based, NOT chronological (Chroma: shuffled > coherent)
- DISTILL, don't summarize — extract the insight, not the process
- Include "Lessons learned" — what applies going forward, not just what happened
- Causal chains must be COMPLETE: error → what was investigated → root cause → fix applied
- Preserve error messages VERBATIM (summaries smooth over severity)
- Keep URLs/links inline, drop fetched content
- If a topic is fully resolved AND its lessons are captured in live_state, compress to one line + breadcrumb
- Add cross-references: "Related: see [other topic] for the authentication decision that affected this"

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

WRITE — forward-looking, actionable, enriched with what the model needs to execute:
```
## Current Task
What: [precise description]
Acceptance criteria: [when is this done?]
Approach: [how we're doing it — the plan]
Context needed: [files, decisions, and architecture the model needs to have in mind]
Risks: [what could go wrong, based on past failures and current state]

## Next Steps (prioritized)
1. [Immediate] — what to do, which files to touch, expected outcome
2. [After that] — depends on step 1 completing
3. [Then] — ...

## Blockers
- [What's blocking progress and what would unblock it]

## Agent Team State (if active)
- [Teammate roles, current task, status]
- [Coordination: who needs what from whom]

## Proactive Context
[Information the model will likely need in the next few turns:
 - Architecture decisions relevant to the current task
 - File dependencies that will be affected
 - Past failures in similar work that should be avoided
 - Related decisions that constrain the approach]
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

### Subsequent cultivations (snipe mode): targeted section updates

For each affected section, spawn a focused **Task** subagent (or handle inline if the change is simple):

**Snipe prompt template:**
```
You are surgically updating ONE section of a cultivated context gene.

CURRENT SECTION CONTENT:
[paste the current content of this specific section]

WHAT CHANGED (from new turns):
[describe the specific change: new decision, new error, file modified, etc.]

SECTION RULES:
[paste the section-specific rules from above]

INSTRUCTIONS:
- Update this section to reflect the change
- ENRICH: add rationale, dependencies, cross-references
- Do NOT remove existing content unless it's explicitly superseded
- Output ONLY the updated section content (nothing else)
```

For simple changes (test result updated, file modified), you can update inline without spawning a subagent — just edit the section content directly.

After all snipes complete, write the updated sections to `/tmp/crisper_gene_sections.json`. Include ALL sections — unchanged ones with their original content, changed ones with updated content.

**Anti-collapse verification:**
- Count facts (decisions, files, errors) before and after each snipe
- If a count DECREASED without an explicit deletion, something was lost — redo the snipe
- Sections not in the change map should be byte-identical to before

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
