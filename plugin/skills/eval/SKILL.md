---
name: eval
description: Run CE-Bench — evaluate context engineering quality across 5 conditions with LLM-judged scoring.
argument-hint: "[session-path] [--workspace /tmp/ce-bench/...]"
disable-model-invocation: true
allowed-tools: Bash(crisper *), Task, Read, Write
---

You are running **CE-Bench** — the Context Engineering Benchmark.

This evaluates how well different context management approaches preserve information, scored on 8 dimensions by an LLM judge.

## Step 0: Prepare workspace

If the user provided a workspace path, use it. Otherwise, prepare a new one:

```bash
crisper eval-prepare current
```

This creates the workspace with condition_A.jsonl, condition_B.jsonl, and the question prompt.

Note the workspace path from the output.

## Step 1: Generate questions (subagent)

Read the question prompt:
```bash
cat <workspace>/prompt_questions.txt
```

Spawn a **Task** subagent with this prompt. The subagent should:
1. Read the prompt
2. Generate 10 test questions as JSON
3. Write the output to `<workspace>/questions.json`

The JSON format:
```json
[
  {"id": "q1", "dimension": "artifact_trail", "text": "What files were created or modified?"},
  {"id": "q2", "dimension": "decision_rationale", "text": "Why was X chosen over Y?"},
  ...
]
```

After the subagent completes, verify:
```bash
cat <workspace>/questions.json | python3 -c "import sys,json; d=json.load(sys.stdin); print(f'{len(d)} questions generated')"
```

## Step 2: Generate ground truth (subagent)

Generate the ground truth prompt:
```bash
crisper eval-ground-truth <workspace>
```

Read the prompt and spawn a **Task** subagent to answer all 10 questions using the FULL original session. Write output to `<workspace>/ground_truth.json`:

```json
[
  {"id": "q1", "answer": "Files modified: src/foo.py (created), src/bar.py (edited)..."},
  ...
]
```

## Step 3: Apply LLM conditions (C, D, E)

For conditions that need LLM restructuring, spawn subagents:

### Condition C: Anthropic /compact simulation

Spawn a **Task** subagent:
> "Read <workspace>/original.jsonl. Summarize this session as Anthropic's /compact would — preserve state, next steps, and learnings in a condensed summary. Write the summary as a JSONL session to <workspace>/condition_C.jsonl. Each line must be valid JSON with type, uuid, parentUuid, message fields."

### Condition D: Factory-style 4-anchor summary

Spawn a **Task** subagent:
> "Read <workspace>/original.jsonl. Create a structured summary using Factory.ai's 4-anchor format:
> 1. Session Intent — what the user wants to accomplish
> 2. File Modifications — every file path and what changed
> 3. Decisions Made — every decision with rationale
> 4. Next Steps — what remains to be done
> Write as JSONL to <workspace>/condition_D.jsonl."

### Condition E: Crisper 5-section engineering

Run the analysis:
```bash
crisper analyze <workspace>/original.jsonl --format json --include-messages > /tmp/crisper_eval_analysis.json
```

Then spawn a **Task** subagent with the full engineer prompt from /crisper:engineer, but writing to `<workspace>/condition_E.jsonl` instead of the signal file path.

## Step 4: Test each condition (subagents)

For each condition file (A through E), spawn a **Task** subagent:

> "Read <workspace>/condition_X.jsonl. This is a Claude Code session. Answer these questions using ONLY the information in this session:
> [paste questions from questions.json]
> Write answers as JSON to <workspace>/answers_X.json"

Run all 5 in parallel (run_in_background=true), then collect results.

## Step 5: Judge each condition (subagents)

Generate judge prompts:
```bash
crisper eval-judge <workspace>
```

For each condition, read `<workspace>/prompt_judge_X.json` and spawn a **Task** subagent:

> "You are an expert judge. For each question, score the candidate answer against the ground truth on 8 dimensions (1-5 scale). Read the prompts from the file and output scores.
> Write to <workspace>/scores_X.json as:
> [{"question_id": "q1", "scores": {"accuracy": {"score": 4, "reason": "..."}, ...}}, ...]"

## Step 6: Aggregate

```bash
crisper eval-aggregate <workspace>
```

Then show the results:
```bash
crisper eval-results <workspace>
```

Present the comparison table to the user, including the Factory.ai reference numbers (3.70/3.44/3.35).
