"""hsrsim — a Honkai: Star Rail combat simulator for measuring character output.

Quick start::

    from hsrsim import Build, scenarios
    team = [Build("Seele", light_cone="In the Night"), Build("Sparkle"), ...]
    report = scenarios.boss_dps(cycles=5).run(team)
    print(report)
"""

from . import scenarios
from .battle import Battle, BattleConfig
from .build import Build, make_character, stat_sheet
from .data import get_data

__all__ = ["Battle", "BattleConfig", "Build", "make_character", "stat_sheet", "get_data", "scenarios"]
__version__ = "0.1.0"
