# AGENTS.md

This repository contains a small prototype of a rogue-lite auto‑battler built with **Python 3.12** and **Pygame**. The goal is to provide a PvE rogue‑lite game inspired by *Slay the Spire*, *The Binding of Isaac*, and *Hades*, but featuring *Teamfight Tactics–style auto‑battler combat*. The following notes describe the current layout and development practices.

## Module Overview

| Path        | Role |
|-------------|------|
| `ai/`       | Combat behaviours including navigation and target selection. |
| `assets/`   | CC0 or procedurally generated sprites, fonts and UI elements. |
| `data/`     | Game constants, enumerations and dictionary based definitions. |
| `engine/`   | Core gameplay classes (units, items, map) and combat logic. |
| `states/`   | Finite state machine controlling game phases and input routing. |
| `ui/`       | Rendering helpers and UI windows. Uses `ui/constants.py` for layout. |
| `tests/`    | PyTest cases exercising engine and utility functions. |
| `main.py`   | Application entry point wiring the modules together. |

## Development Guidelines

- Keep the code portable; avoid OS specific APIs.
- Format using **Black**, **isort** and **ruff**.
- Provide type hints and run `mypy` on the main packages.
- Ensure tests pass before submitting a PR.

### Local Run

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
PYTHONPATH=. python main.py
```

### Checks
```bash
PYTHONPATH=. pytest -q
```

## Pull Requests
Follow [Conventional Commits](https://www.conventionalcommits.org/en/v1.0.0/) for PR titles and keep one logical change per PR. Summarise why the change was made and mention test results. Assign the PR to `@project-owner` and request review from `@game-lead`.

## Asset Policy
Graphics are placeholders located in `assets/`. They are either simple shapes or CC0 material so the project can be built without manual asset creation.

## License

All source code is released under the MIT license. Document any third‑party resources in `docs/THIRD_PARTY.md`.