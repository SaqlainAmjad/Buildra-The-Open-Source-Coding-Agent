# Contributing to Buildra

Thanks for helping. Buildra is a learning-oriented project, so clarity beats
cleverness: small functions, full type hints, and a docstring on every public
function.

## Setup

You need Python 3.11+ and [uv](https://docs.astral.sh/uv/) (or plain `pip`).

```bash
git clone https://github.com/SaqlainAmjad/Buildra-The-Open-Source-Coding-Agent.git
cd Buildra-The-Open-Source-Coding-Agent
uv sync                      # creates .venv with runtime + dev dependencies
uv run pre-commit install    # lint and type-check on every commit
cp .env.example .env         # add your DEEPSEEK_API_KEY (only needed for live runs)
```

With pip instead: `python -m venv .venv`, activate it, then
`pip install -e . --group dev` (pip 25.1+).

## Checks (the same ones CI runs)

```bash
uv run ruff check            # lint
uv run ruff format --check   # formatting
uv run mypy                  # strict type check
uv run pytest                # offline tests; the LLM is faked
uv run pytest -m live        # optional: real API calls, needs a key
```

## Project rules

- **One responsibility per module.** No `utils.py` or `helpers.py`. If a
  function has no obvious home, the design needs a new, well-named module.
- **Layering:** `cli/` -> `agent/` -> `tools/`, `llm/`, `permissions/`,
  `memory/`, `config/`. Lower layers never import upper ones. `agent/` never
  prints. `permissions/` is pure logic.
- **Tests run offline.** Use the fake chat model fixtures. Tests that need a
  real API are marked `@pytest.mark.live`.
- **No secrets** in code, tests or fixtures.
- **Explain design choices** in the PR description, and update
  `docs/architecture.md` when you change one.

## Commits

Conventional commits, one logical change each:
`feat(tools): add grep tool`, `fix(agent): ...`, `docs: ...`, `test: ...`,
`chore: ...`, `ci: ...`.
