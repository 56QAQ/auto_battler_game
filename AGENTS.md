# AGENTS.md

This repository contains **hsrsim**, a Honkai: Star Rail combat simulator (pure logic, no art)
used to measure character damage output in configurable scenarios. Python 3.11+, no runtime
dependencies (PyYAML optional for YAML configs).

## Module overview

| Path | Role |
|---|---|
| `hsrsim/battle.py` | Engine: AV timeline, turns, actions/hits, damage, toughness/break, modifiers, SP/energy, waves |
| `hsrsim/formulas.py` | Pure damage formulas (unit-tested) |
| `hsrsim/modifiers.py` | Buffs/debuffs/fields/DoTs and duration semantics |
| `hsrsim/kits/` | Character kits, one module per character (`@register`) |
| `hsrsim/gear/` | Light cone and relic set conditional effects |
| `hsrsim/data/` | Loader + generated data snapshot (`gamedata/*.json`, do not edit by hand) |
| `tools/` | `build_gamedata.py` (regenerate snapshot), `kitinfo.py`, `lcinfo.py` |
| `docs/` | `RESEARCH.md` (feasibility + formulas), `mechanics_memo.md`, `DEVELOPING.md` (content API) |
| `tests/` | PyTest suite |

## Development guidelines

- Content code encodes logic only; every number must come from the data (`self.p(...)`, `self.tp(...)`, `self.ep(...)`).
- Read `docs/DEVELOPING.md` before adding kits/gear; follow the duration semantics described there.
- Format with **Black** (line length 120), **isort**, **ruff**; type hints everywhere.
- Mark anything approximated with a `# not modelled:` / `# approximation:` comment.

## Checks

```bash
PYTHONPATH=. pytest -q
ruff check hsrsim tools tests
```

## Pull requests

Conventional Commits for titles, one logical change per PR, mention test results.
