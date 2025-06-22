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
    mend = ITEM_DEFINITIONS["Verdant Mend Disk"]
    renewal = ITEM_DEFINITIONS["Verdant Renewal Disk"]
    precision = ITEM_DEFINITIONS["Verdant Precision Disk"]

    assert mend["color"] == "GREEN"
    assert mend["ability"]["quality_chances"]["fail"] == 0.1
    assert mend["ability"]["effect_data"]["great_multiplier"] == 2.0

    assert renewal["ability"]["effect_data"]["status_name"] == "HOT"
    assert precision["ability"]["effect_data"]["status_name"] == "CRIT_HEAL"


def test_verdant_new_disks():
    drain = ITEM_DEFINITIONS["Verdant Drain Disk"]
    aegis = ITEM_DEFINITIONS["Verdant Aegis Disk"]
    purity = ITEM_DEFINITIONS["Verdant Purity Disk"]
    ward = ITEM_DEFINITIONS["Verdant Ward Disk"]
    vitality = ITEM_DEFINITIONS["Verdant Vitality Disk"]

    assert drain["rarity"] == "RARE"
    assert drain["ability"]["effect_data"]["status_name"] == "LEECH_DOT"
    assert aegis["ability"]["effect_data"]["status_name"] == "SPEED_SHIELD"
    assert purity["ability"]["effect_data"]["status_name"] == "PURIFY"
    assert ward["rarity"] == "EPIC"
    assert ward["ability"]["effect_data"]["status_name"] == "MAGIC_WARD"
    assert vitality["ability"]["quality_chances"]["per_100_shift"] == 0.01


def test_determine_quality_fail():
    from engine.logic import determine_quality

    ability = {"quality_chances": {"fail": 1.0, "great": 0.0}}
    random_value = determine_quality(ability)
    assert random_value == "fail"

