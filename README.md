# llm-poker-arena

6-max No-Limit Texas Hold'em simulation platform for observing multi-agent LLM gameplay.

## Status

Phase 1 (engine + test suite, no LLM). See
[docs/superpowers/plans/2026-04-23-llm-poker-arena-phase-1.md](docs/superpowers/plans/2026-04-23-llm-poker-arena-phase-1.md).

## Design

Authoritative spec: [docs/superpowers/specs/2026-04-23-llm-poker-arena-design-v2.md](docs/superpowers/specs/2026-04-23-llm-poker-arena-design-v2.md)
(v2.1.1). The older v1 spec is superseded.

## Quickstart

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e '.[dev]'
pytest
ruff check .
mypy
```

## Testing notes

- Always activate the project venv before running pytest:
  `source .venv/bin/activate && pytest`.
- `uv run pytest` has been observed to segfault on some macOS setups during
  pytest's capture init (`import readline` crash). Until that is root-caused,
  prefer the direct `.venv/bin/pytest` path over `uv run`.
- `UV_CACHE_DIR=/tmp/uv-cache ruff check .` / `mypy` have worked cleanly on
  the same machines that segfault under `uv run pytest`.
