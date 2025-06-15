import os

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
import pygame

pygame.display.init()

from data.definitions import UNIT_DEFINITIONS
from data.enums import TriggerTiming
from engine.classes import Unit
from engine.game_state import GameState
from engine.logic import resolve_passive


def test_passive_start_of_combat_heal():
    state = GameState()
    definition = UNIT_DEFINITIONS["Clockwork Soldier"]
    unit = Unit("Clockwork Soldier", definition)
    unit.current_hp -= 30
    resolve_passive(unit, TriggerTiming.START_OF_COMBAT, state, None)
    assert unit.current_hp == unit.current_stats["hp"] - 10