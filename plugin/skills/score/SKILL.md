---
name: score
description: Score the current session's context quality — shows information density, noise ratio, and whether restructuring would help.
allowed-tools: Bash(crisper *)
---

Run a context quality assessment:

```bash
crisper score current
```

Present the results to the user. If the assessment is LOW or MODERATE, suggest running `/crisper:engineer` to restructure.
