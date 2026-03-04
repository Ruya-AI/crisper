---
name: cultivate
description: GoF — Cultivate the session context. Absorbs recent turns into structured gene sections, archives raw turns, then reloads with optimized context.
disable-model-invocation: true
allowed-tools: Bash(crisper *), Task, Read, Write, AskUserQuestion
---

You are running **Crisper GoF — Gain of Function** cultivation.

This absorbs recent uncultivated turns into the 9-section gene structure, archives raw turns for breadcrumb retrieval, and reloads with optimized context.

## Step 1: Prepare

```bash
crisper cultivate-prepare current --format json
```

This outputs the analysis + raw tail + recent turns. Save the JSON output.

## Step 2: Confirm

Show the user:
- How many turns will be absorbed
- How many are sacred (preserved verbatim)
- Whether this is the first cultivation or an update

Ask confirmation via AskUserQuestion.

## Step 3: Spawn cultivation subagent

Use **Task** tool (run_in_background=false):

**Subagent prompt:**

```
You are cultivating a Claude Code session's context gene. You will read the current session analysis and raw turns, then produce the 9 gene sections.

Read the cultivation data from: [paste the JSON from step 1, or write to /tmp/crisper_cultivation.json and have subagent read it]

Produce a JSON file at /tmp/crisper_gene_sections.json with these keys:

{
  "system_identity": "Project: ...\nArchitecture: ...\nConstraints: ...",
  "live_state": "## Active Decisions\n- Decision: ...\n\n## File State Map\n- path: action, turn\n\n## External Feedback\n- Last test: ...",
  "failure_log": "## Failed Approaches\n- What: ...\n  Why failed: ...",
  "subgoal_tree": "## Goals\n- [x] Goal 1 (completed)\n  - [x] Sub 1.1\n- [ ] Goal 2 (active)\n  - [/] Sub 2.1 (in progress)",
  "compressed_history": "## Topic: Authentication\nDiscussed JWT vs sessions...\n[archive:45-67 for full discussion]\n\n## Topic: Database\n...",
  "breadcrumbs": "## Archive References\n- Full auth discussion: archive:45-67\n- Error trace: archive:128-135\n- Original requirements: archive:1-5",
  "objectives": "## Current Task\n...\n\n## Next Steps\n1. ...\n2. ...\n\n## Blockers\n- ..."
}

RULES:
1. Every decision from the analysis MUST appear in live_state
2. Every file path MUST appear in live_state
3. Every URL/reference MUST be preserved (in compressed_history or breadcrumbs)
4. Failed attempts MUST be in failure_log
5. Superseded decisions should be REMOVED (only keep current truth)
6. Add breadcrumb references: "archive:LINE-LINE" for archived content
7. Compress completed subgoals to one-liners
8. Expand active subgoals with full context

Analysis data:
[PASTE ANALYSIS JSON HERE]

Raw turns to absorb:
[PASTE RAW TAIL HERE]
```

## Step 4: Write the gene

After subagent produces /tmp/crisper_gene_sections.json:

Also save the recent turns to a file:
```bash
crisper cultivate-prepare current --format json | python3 -c "import sys,json; d=json.load(sys.stdin); open('/tmp/crisper_recent.jsonl','w').write('\n'.join(d.get('recent_turns',[])))"
```

Then write:
```bash
crisper cultivate-write current /tmp/crisper_gene_sections.json --recent /tmp/crisper_recent.jsonl
```

## Step 5: Reload

Tell the user:

> Gene cultivated. [X] turns absorbed, [Y] archived.
> Before: [A]KB → After: [B]KB
>
> Type /exit — a new terminal will open with the cultivated context.

The next `claude --resume` will load the cultivated gene as the primary context.

## Step 6: Cleanup

```bash
rm -f /tmp/crisper_cultivation.json /tmp/crisper_gene_sections.json /tmp/crisper_recent.jsonl
```
