---
name: engineer
description: Restructure the current session context into the scientifically optimal 5-section layout. Spawns a subagent to analyze, restructure, validate, and write.
disable-model-invocation: true
allowed-tools: Bash(crisper *), Task, Read, Write, AskUserQuestion
---

You are activating **Crisper Context** — scientifically optimal context restructuring.

This restructures your session from raw chronological conversation into a 5-section layout proven by research to maximize model performance (Factory.ai 3.70/5, JetBrains NeurIPS 2025, Liu et al. TACL 2024).

## Step 1: Check for PreCompact signal

```bash
cat /tmp/crisper_precompact_signal.json 2>/dev/null
```

If the signal file exists, read it — analysis is already done. Skip to Step 3.
If not, proceed to Step 2.

## Step 2: Run analysis

```bash
crisper analyze current --format json --include-messages --window 10
```

Save this JSON output — you will pass it to the subagent.

Present a summary to the user:
- Session: [name], Model: [model], Tokens: [count]
- Decisions: N, File changes: N, Errors: N, References: N
- Topics: N, Failed attempts: N

## Step 3: Confirm with user

Use AskUserQuestion:
- Question: "Restructure this session into optimal 5-section layout?"
- Options:
  1. "Yes, restructure" — "Creates backup, restructures, preserves recent 10 turns verbatim"
  2. "Dry run" — "Show what would change without modifying anything"

If dry run: show the analysis text and stop.

## Step 4: Spawn restructuring subagent

Use the **Task** tool with these parameters:
- `subagent_type`: "general-purpose"
- `run_in_background`: false (must complete before we continue)

**Subagent prompt** (paste the analysis JSON where indicated):

---

You are a context engineering specialist. Restructure this Claude Code session into the optimal 5-section format.

## The 5-Section Layout

### Section 1: SYSTEM STATE (position: TOP — stable, KV-cacheable)
Create 1-2 synthetic user/assistant message pairs capturing:
- Project architecture (inferred from file changes and session intent)
- Key constraints and user preferences
- Any tool configurations mentioned

### Section 2: STRUCTURED STATE (position: NEAR TOP — reference material)
Create 1-2 synthetic message pairs with explicit sections:
- **Session Intent**: [from analysis]
- **File Modifications**: Every file path + what action (created/modified/deleted)
- **Decisions Made**: Every decision + rationale + what was rejected
- **Current State**: What is deployed, pending, blocked

### Section 3: COMPRESSED HISTORY (position: MIDDLE — grouped by topic)
For each topic from the analysis, create a concise message pair:
- Summarize exchanges by topic, NOT chronologically
- Preserve failed attempts: what was tried, why it failed
- Preserve causal chains: error → cause → fix
- Keep ALL URLs/references, drop fetched content
- Error messages verbatim, compress surrounding discussion

### Section 4: RECENT TURNS (position: NEAR END — sacred, verbatim)
Copy the sacred messages EXACTLY. Do not modify a single character.
Read them from the `sacred_messages` field in the analysis.

### Section 5: OBJECTIVES + NEXT STEPS (position: VERY END — highest attention)
Create 1-2 message pairs with:
- Current task + acceptance criteria
- Agent team state (if any)
- Pending items, blockers, next actions

## Output Format

Write the restructured session to `/tmp/crisper_restructured.jsonl`.

Each line must be valid JSON:
```json
{"type":"user","uuid":"<new-uuid>","parentUuid":"<prev-uuid>","sessionId":"<session-id>","timestamp":"<iso>","isSidechain":false,"message":{"role":"user","content":"<text>"}}
```

For synthetic messages, generate new UUIDs (use Python uuid4 via Bash if needed).
Chain parentUuid: each message's parentUuid = previous message's uuid.
For Section 4 (sacred turns), keep original uuids but connect the first sacred turn's parentUuid to the last Section 3 message's uuid.

## Critical Rules

1. Every decision from the analysis MUST appear in Section 2
2. Every file path MUST appear in Section 2
3. Every URL/reference MUST be preserved
4. Failed attempts MUST be in Section 3
5. Section 4 (recent turns) MUST be byte-identical to the sacred_messages
6. Valid JSONL output
7. NEVER invent information not in the analysis
8. Output must be smaller than input

## After Writing

Validate:
```bash
crisper validate current /tmp/crisper_restructured.jsonl --format json
```

If validation fails, fix the issues and re-validate.

Report back: original tokens, restructured tokens, validation result.

## Analysis Data

[PASTE THE ANALYSIS JSON HERE]

---

## Step 5: Check result

After the subagent completes, verify:

```bash
crisper validate current /tmp/crisper_restructured.jsonl
```

Show the validation summary to the user.

## Step 6: Apply

If validation passed:

```bash
crisper write current /tmp/crisper_restructured.jsonl
```

## Step 7: Tell the user

> Context restructured. Backup created automatically.
> Before: [X] tokens → After: [Y] tokens ([Z]% reduction)
> To resume with optimized context: exit and run `claude --resume`

Clean up:
```bash
rm -f /tmp/crisper_precompact_signal.json /tmp/crisper_restructured.jsonl
```
