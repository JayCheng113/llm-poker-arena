---
name: Bug report
about: Something is broken or behaves unexpectedly
title: "[bug] "
labels: bug
---

## What happened
<!-- Concrete description. Include the command you ran, the actual output, and the expected output. -->

## Repro
<!-- Minimal steps. If session-level: `runs/<id>/config.json` + the seed used is enough. -->

```bash
# command(s) that reproduce it
```

## Environment

- OS:
- Python version: <!-- `python --version` -->
- Project commit: <!-- `git rev-parse HEAD` -->
- Provider(s) involved (if LLM-side): <!-- e.g. anthropic + kimi -->

## Logs / artifacts
<!-- Paste the relevant `runs/<id>/meta.json` slice, the failing pytest output, or the censored_hands.jsonl entry. Redact API keys. -->
