## Summary
<!-- 1–3 bullets describing what changed and WHY. Link any related issue. -->

-

## Test plan
<!-- Tick what applies; add concrete commands you ran. -->

- [ ] `uv run pytest -ra` (502+ backend tests)
- [ ] `cd web && npm test` (115+ vitest tests)
- [ ] `cd web && npm run type-check && npm run lint`
- [ ] If UI changed: `cd web && npm run test:e2e` and screenshots regenerated where relevant
- [ ] If a new LLM provider / model was added: smoke-ran a 6-hand session against the real API and confirmed `runs/<id>/censored_hands.jsonl` is empty

## Anything reviewers should look at first
<!-- Risky bits, intentional trade-offs, follow-up TODOs. -->
