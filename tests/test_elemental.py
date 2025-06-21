import os

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
import pygame

pygame.display.init()

from data.definitions import ITEM_DEFINITIONS  # noqa: E402
from data.definitions import UNIT_DEFINITIONS  # noqa: E402
from data.enums import DamageType, Element  # noqa: E402
from engine.classes import Unit  # noqa: E402
from engine.game_state import get_game_state, reset_game_state  # noqa: E402


def test_elemental_aura_reaction():
    reset_game_state()
    state = get_game_state()
    definition = UNIT_DEFINITIONS["Clockwork Soldier"]
    attacker = Unit("Attacker", definition)
    target = Unit("Target", definition)
    state.player_combat_team = [attacker]
    state.enemy_combat_team = [target]

    target.take_damage(10, DamageType.MAGIC, state, attacker, element=Element.ICE)
    assert "ELEMENTAL_AURA" in target.statuses
    assert target.statuses["ELEMENTAL_AURA"][0].params["element"] == Element.ICE

    target.take_damage(10, DamageType.MAGIC, state, attacker, element=Element.ICE)
    assert "ELEMENTAL_AURA" not in target.statuses
    assert "CHILL" in target.statuses


def test_azure_disk_definitions():
    flame = ITEM_DEFINITIONS["Azure Flame Disk"]
    frost = ITEM_DEFINITIONS["Azure Frost Disk"]
    storm = ITEM_DEFINITIONS["Azure Storm Disk"]
    scorch = ITEM_DEFINITIONS["Azure Scorch Disk"]
    bastion = ITEM_DEFINITIONS["Azure Bastion Disk"]
    surge = ITEM_DEFINITIONS["Azure Surge Disk"]
    blizzard = ITEM_DEFINITIONS["Azure Blizzard Disk"]
    detonation = ITEM_DEFINITIONS["Azure Detonation Disk"]

    assert flame["color"] == "BLUE"
    assert flame["rarity"] == "UNCOMMON"
    assert flame["ability"]["effect_data"]["element"] == Element.FIRE

    assert frost["ability"]["effect_data"]["element"] == Element.ICE
    assert frost["ability"]["effect_data"]["flat_magic_penetration"] == 20

    assert storm["ability"]["effect_data"]["element"] == Element.LIGHTNING
    assert storm["ability"]["effect_data"]["bounces"] == 2

    assert scorch["rarity"] == "RARE"
    assert scorch["ability"]["effect_data"]["element"] == Element.FIRE

    assert bastion["ability"]["effect_data"]["status_name"] == "DECAY_SHIELD"
    assert surge["ability"]["effect_data"]["auto_crit_if_status"] == [
        "SHOCK",
        "SUPERCONDUCT",
    ]

    assert blizzard["rarity"] == "EPIC"
    assert blizzard["ability"]["effect_data"]["status_name"] == "ICY_PULSE"

    assert detonation["ability"]["effect_data"]["hp_percent_of_max"] == 0.5


def test_verdant_disk_definitions():
    renew = ITEM_DEFINITIONS["Verdant Renewal Disk"]
    vigor = ITEM_DEFINITIONS["Verdant Vigor Disk"]
    focus = ITEM_DEFINITIONS["Verdant Focus Disk"]

    assert renew["color"] == "GREEN"
    assert vigor["rarity"] == "UNCOMMON"
    assert focus["ability"]["effect_data"]["stat"] == "critical_chance"
