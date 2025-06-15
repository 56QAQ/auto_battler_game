# data/definitions.py
from typing import Any, Dict, List, Tuple

from data.enums import (
    AbilityEffect,
    Color,
    DamageType,
    StatSource,
    TriggerTarget,
    TriggerTiming,
)

# Stats: HP, AD, AS, AP, Armor, MR, Range (pixels)
UNIT_DEFINITIONS: Dict[str, Dict[str, Any]] = {
    "Clockwork Soldier": {
        "rarity": "COMMON",
        "primary_color": Color.RED,
        "traits": ["Automaton", "Defender"],
        "base_stats": {
            "hp": 600,
            "ad": 50,
            "as": 0.6,
            "ap": 0,
            "armor": 40,
            "mr": 40,
            "range": 50,
        },
        "trigger": {
            "timing_type": TriggerTiming.ON_HIT,
            "target_type": TriggerTarget.ATTACK_TARGET,
            "base_value_source": StatSource.AD,
            "base_value_multiplier": 0.2,
            "base_value_flat": 0,
        },
        "passive": {
            "timing_type": TriggerTiming.START_OF_COMBAT,
            "target_type": TriggerTarget.SELF,
            "base_value_source": StatSource.FLAT,
            "base_value_multiplier": 0.0,
            "base_value_flat": 0,
            "ability": {
                "name": "Celerity",
                "effect_type": AbilityEffect.APPLY_BUFF,
                "effect_data": {
                    "stat": "as",
                    "value": 10,
                    "duration": None,
                    "is_percent": True,
                },
            },
        },
    },
    "Gear Grinder": {
        "rarity": "COMMON",
        "primary_color": Color.GREEN,
        "traits": ["Automaton", "Brawler"],
        "base_stats": {
            "hp": 700,
            "ad": 55,
            "as": 0.5,
            "ap": 0,
            "armor": 30,
            "mr": 30,
            "range": 40,
        },
        "passive": {
            "timing_type": TriggerTiming.START_OF_COMBAT,
            "target_type": TriggerTarget.SELF,
            "base_value_source": StatSource.FLAT,
            "base_value_multiplier": 0.0,
            "base_value_flat": 10,
            "ability": {
                "name": "Reinforced Chassis",
                "effect_type": AbilityEffect.APPLY_BUFF,
                "effect_data": {
                    "stat": "flat_basic_attack_damage_reduction",
                    "value": 10,
                    "duration": None,
                    "is_percent": False,
                },
            },
        },
        "trigger": {
            "timing_type": TriggerTiming.ON_DAMAGE_TAKEN,
            "timing_data": {"threshold": 200},
            "target_type": TriggerTarget.SELF,
            "base_value_source": StatSource.MAX_HP,
            "base_value_multiplier": 0.05,
            "base_value_flat": 0,
        },
    },
    "Boiler Bot": {
        "rarity": "COMMON",
        "primary_color": Color.BLUE,
        "traits": ["Automaton", "Steamcraft"],
        "base_stats": {
            "hp": 650,
            "ad": 50,
            "as": 0.5,
            "ap": 10,
            "armor": 35,
            "mr": 35,
            "range": 45,
        },
        "passive": {
            "timing_type": TriggerTiming.ON_HIT,
            "target_type": TriggerTarget.ATTACK_TARGET,
            "base_value_source": StatSource.AP,
            "base_value_multiplier": 1.0,
            "base_value_flat": 0,
            "ability": {
                "name": "Boil Strike",
                "effect_type": AbilityEffect.DEAL_DAMAGE,
                "effect_data": {
                    "damage_type": DamageType.MAGIC,
                    "scale_factor": 1.0,
                    "flat_value": 0,
                },
            },
        },
        "trigger": {
            "timing_type": TriggerTiming.ON_MAGIC_DAMAGE,
            "target_type": TriggerTarget.SELF,
            "base_value_source": StatSource.FLAT,
            "base_value_multiplier": 0.0,
            "base_value_flat": 30,
        },
    },
    "Scrap Rat": {
        "rarity": "COMMON",
        "traits": ["Scavenger"],
        "base_stats": {
            "hp": 500,
            "ad": 60,
            "as": 0.8,
            "ap": 0,
            "armor": 20,
            "mr": 20,
            "range": 40,
        },
        "trigger": None,
    },
    "Steam Knight": {
        "rarity": "UNCOMMON",
        "traits": ["Steamcraft", "Defender"],
        "base_stats": {
            "hp": 800,
            "ad": 60,
            "as": 0.7,
            "ap": 0,
            "armor": 50,
            "mr": 50,
            "range": 50,
        },
        # FIX-UI: Example: Give Steam Knight a Trigger for demonstration
        "trigger": {
            "timing_type": TriggerTiming.START_OF_COMBAT,
            "target_type": TriggerTarget.SELF,
            "base_value_source": StatSource.ARMOR,
            "base_value_multiplier": 1.0,
            "base_value_flat": 0,
        },
    },
    "Piston Puncher": {
        "rarity": "UNCOMMON",
        "traits": ["Steamcraft", "Brawler"],
        "base_stats": {
            "hp": 900,
            "ad": 70,
            "as": 0.6,
            "ap": 0,
            "armor": 40,
            "mr": 40,
            "range": 40,
        },
        "trigger": {
            "timing_type": TriggerTiming.ON_TAKE_DAMAGE,
            "target_type": TriggerTarget.SELF,
            "base_value_source": StatSource.MAX_HP,
            "base_value_multiplier": 0.02,
            "base_value_flat": 0,
        },
    },
    "Alchemist": {
        "rarity": "UNCOMMON",
        "traits": ["Scavenger", "Mystic"],
        "base_stats": {
            "hp": 600,
            "ad": 45,
            "as": 0.7,
            "ap": 30,
            "armor": 20,
            "mr": 40,
            "range": 120,
        },
        "trigger": {
            "timing_type": TriggerTiming.ON_HIT,
            "target_type": TriggerTarget.ATTACK_TARGET,
            "base_value_source": StatSource.AP,
            "base_value_multiplier": 1.5,
            "base_value_flat": 0,
        },
    },
    "Cogsworth": {
        "rarity": "RARE",
        "traits": ["Automaton", "Arcanist"],
        "base_stats": {
            "hp": 750,
            "ad": 40,
            "as": 0.8,
            "ap": 50,
            "armor": 20,
            "mr": 60,
            "range": 150,
        },
        "trigger": {
            "timing_type": TriggerTiming.TIMED,
            "timing_data": {"interval": 4.0},
            "target_type": TriggerTarget.NEAREST_ENEMY,
            "base_value_source": StatSource.AP,
            "base_value_multiplier": 3.0,
            "base_value_flat": 0,
        },
    },
    "Chronomancer": {
        "rarity": "RARE",
        "traits": ["Arcanist", "Mystic"],
        "base_stats": {
            "hp": 700,
            "ad": 30,
            "as": 0.9,
            "ap": 60,
            "armor": 15,
            "mr": 70,
            "range": 180,
        },
        "trigger": {
            "timing_type": TriggerTiming.TIMED,
            "timing_data": {"interval": 3.0},
            "target_type": TriggerTarget.RANDOM_ENEMY,
            "base_value_source": StatSource.AP,
            "base_value_multiplier": 2.0,
            "base_value_flat": 0,
        },
    },
    "Noble Guard": {
        "rarity": "RARE",
        "traits": ["Noble", "Defender"],
        "base_stats": {
            "hp": 950,
            "ad": 50,
            "as": 0.6,
            "ap": 0,
            "armor": 70,
            "mr": 50,
            "range": 50,
        },
        # FIX-UI: Example: Give Noble Guard a Trigger for demonstration
        "trigger": {
            "timing_type": TriggerTiming.START_OF_COMBAT,
            "target_type": TriggerTarget.SELF,
            "base_value_source": StatSource.FLAT,
            "base_value_multiplier": 0,
            "base_value_flat": 100.0,
        },
    },
    "Brass Baron": {
        "rarity": "EPIC",
        "traits": ["Steamcraft", "Noble"],
        "base_stats": {
            "hp": 1100,
            "ad": 80,
            "as": 0.7,
            "ap": 20,
            "armor": 60,
            "mr": 60,
            "range": 60,
        },
        "trigger": None,
    },
    "Golem": {
        "rarity": "EPIC",
        "traits": ["Automaton", "Defender", "Brawler"],
        "base_stats": {
            "hp": 1500,
            "ad": 90,
            "as": 0.4,
            "ap": 0,
            "armor": 80,
            "mr": 80,
            "range": 40,
        },
        "trigger": {
            "timing_type": TriggerTiming.ON_DEATH,
            "target_type": TriggerTarget.RANDOM_ENEMY,
            "base_value_source": StatSource.MAX_HP,
            "base_value_multiplier": 0.5,
            "base_value_flat": 0,
        },
    },
    "Rift Mage": {
        "rarity": "EPIC",
        "traits": ["Arcanist", "Mystic"],
        "base_stats": {
            "hp": 900,
            "ad": 30,
            "as": 0.7,
            "ap": 100,
            "armor": 20,
            "mr": 80,
            "range": 200,
        },
        "trigger": {
            "timing_type": TriggerTiming.TIMED,
            "timing_data": {"interval": 6.0},
            "target_type": TriggerTarget.LOWEST_HP_ENEMY,
            "base_value_source": StatSource.AP,
            "base_value_multiplier": 4.0,
            "base_value_flat": 0,
        },
    },
    # Enemies
    "Rust Bug": {
        "rarity": "ENEMY",
        "traits": ["Vermin"],
        "base_stats": {
            "hp": 400,
            "ad": 40,
            "as": 0.7,
            "ap": 0,
            "armor": 10,
            "mr": 10,
            "range": 40,
        },
        "trigger": None,
    },
    "Gremlin": {
        "rarity": "ENEMY",
        "traits": ["Vermin"],
        "base_stats": {
            "hp": 300,
            "ad": 60,
            "as": 1.0,
            "ap": 0,
            "armor": 5,
            "mr": 5,
            "range": 100,
        },
        "trigger": None,
    },
    "Big Bad Bot": {
        "rarity": "ENEMY",
        "traits": ["Automaton", "Boss"],
        "base_stats": {
            "hp": 2000,
            "ad": 100,
            "as": 0.8,
            "ap": 50,
            "armor": 70,
            "mr": 70,
            "range": 60,
        },
        "trigger": None,
    },
    "War Bot": {
        "rarity": "ENEMY",
        "traits": ["Automaton", "Boss"],
        "base_stats": {
            "hp": 3500,
            "ad": 150,
            "as": 0.9,
            "ap": 80,
            "armor": 100,
            "mr": 100,
            "range": 80,
        },
        "trigger": None,
    },
}

SYNERGY_DEFINITIONS: Dict[str, Dict[str, Any]] = {
    "Automaton": {
        "description": "Automatons gain Armor and MR.",
        "thresholds": [2, 4],
        "effects": [{"armor": 30, "mr": 30}, {"armor": 70, "mr": 70}],
        "targets": "TRAIT",
        "type": "STAT_BOOST",
    },
    "Steamcraft": {
        "description": "Steamcraft units gain Attack Speed.",
        "thresholds": [2, 3],
        "effects": [{"as_percent": 20}, {"as_percent": 40}],
        "targets": "TRAIT",
        "type": "STAT_BOOST",
    },
    "Defender": {
        "description": "All allies gain Armor.",
        "thresholds": [2, 4],
        "effects": [{"armor": 25}, {"armor": 60}],
        "targets": "ALL_ALLIES",
        "type": "STAT_BOOST",
    },
    "Brawler": {
        "description": "Brawlers gain Health.",
        "thresholds": [2, 4],
        "effects": [{"hp": 250}, {"hp": 600}],
        "targets": "TRAIT",
        "type": "STAT_BOOST",
    },
    "Arcanist": {
        "description": "All allies gain AP.",
        "thresholds": [2, 4],
        "effects": [{"ap": 20}, {"ap": 50}],
        "targets": "ALL_ALLIES",
        "type": "STAT_BOOST",
    },
    "Mystic": {
        "description": "All allies gain MR.",
        "thresholds": [2, 4],
        "effects": [{"mr": 40}, {"mr": 100}],
        "targets": "ALL_ALLIES",
        "type": "STAT_BOOST",
    },
    "Noble": {
        "description": "Gain Armor/MR and heal on hit.",
        "thresholds": [1, 3],
        "effects": [
            {"armor": 25, "mr": 25, "heal_on_hit": 10, "units": 1},
            {"armor": 25, "mr": 25, "heal_on_hit": 10, "units": 99},
        ],
        "targets": "RANDOM_ALLIES",
        "type": "ABILITY",
    },
    "Scavenger": {
        "description": "Scavengers find gold.",
        "thresholds": [2],
        "effects": [{"gold_chance": 0.2, "gold": 1}],
        "targets": "TRAIT",
        "type": "ECONOMY",
    },
    "Vermin": {
        "description": "Enemy units.",
        "thresholds": [1],
        "effects": [{}],
        "targets": "TRAIT",
        "type": "STAT_BOOST",
    },
    "Boss": {
        "description": "Boss unit.",
        "thresholds": [1],
        "effects": [{"hp": 500, "ad": 20}],
        "targets": "TRAIT",
        "type": "STAT_BOOST",
    },
    "Red": {
        "description": "红色提供物理攻击，并在高等级时增幅暴击。",
        "thresholds": [2, 4, 6, 9],
        "effects": [
            {"ad": 20},
            {"ad": 40, "critical_chance": 5, "critical_damage": 10},
            {"ad": 90, "critical_chance": 10, "critical_damage": 20},
            {"ad": 270, "critical_chance": 30, "critical_damage": 60},
        ],
        "targets": "ALL_ALLIES",
        "type": "STAT_BOOST",
    },
    "Blue": {
        "description": "蓝色提升法术强度与魔法穿透。",
        "thresholds": [2, 4, 6, 9],
        "effects": [
            {"ap": 20},
            {
                "ap": 40,
                "percentage_magic_penetration": 10,
                "flat_magic_penetration": 20,
            },
            {
                "ap": 90,
                "percentage_magic_penetration": 20,
                "flat_magic_penetration": 40,
            },
            {
                "ap": 270,
                "percentage_magic_penetration": 60,
                "flat_magic_penetration": 120,
            },
        ],
        "targets": "ALL_ALLIES",
        "type": "STAT_BOOST",
    },
    "Green": {
        "description": "绿色提升生命值与减伤。",
        "thresholds": [2, 4, 6, 9],
        "effects": [
            {"hp": 200},
            {"hp": 400, "percentage_damage_reduction": 90, "armor": 10, "mr": 10},
            {"hp": 900, "percentage_damage_reduction": 80, "armor": 40, "mr": 40},
            {
                "hp": 2700,
                "percentage_damage_reduction": 40,
                "armor": 120,
                "mr": 120,
            },
        ],
        "targets": "ALL_ALLIES",
        "type": "STAT_BOOST",
    },
}

ENEMY_TEAM_DEFINITIONS: Dict[str, List[Dict[str, Any]]] = {
    "EASY_1": [{"name": "Rust Bug", "level": 1}, {"name": "Rust Bug", "level": 1}],
    "EASY_2": [
        {"name": "Rust Bug", "level": 1},
        {"name": "Gremlin", "level": 1},
        {"name": "Rust Bug", "level": 1},
    ],
    "MEDIUM_1": [
        {"name": "Rust Bug", "level": 2},
        {"name": "Gremlin", "level": 1},
        {"name": "Clockwork Soldier", "level": 1},
    ],
    "MEDIUM_2": [
        {"name": "Clockwork Soldier", "level": 1},
        {"name": "Boiler Bot", "level": 1},
        {"name": "Steam Knight", "level": 1},
        {"name": "Gremlin", "level": 2},
    ],
    "HARD_1": [
        {"name": "Clockwork Soldier", "level": 2},
        {"name": "Steam Knight", "level": 2},
        {"name": "Piston Puncher", "level": 1},
        {"name": "Cogsworth", "level": 1},
    ],
    "BOSS_1": [
        {"name": "Big Bad Bot", "level": 1},
        {"name": "Rust Bug", "level": 2},
        {"name": "Gremlin", "level": 2},
        {"name": "Clockwork Soldier", "level": 2},
    ],
    "BOSS_2": [
        {"name": "War Bot", "level": 1},
        {"name": "Golem", "level": 1},
        {"name": "Gremlin", "level": 2},
    ],
}

ITEM_DEFINITIONS: Dict[str, Dict[str, Any]] = {
    # Components
    "Gear": {
        "item_type": "ARMAMENT",
        "type": "ARMAMENT",
        "stats": {"ad": 10},
        "ability": None,
        "description": "+10 AD",
    },
    "Plate": {
        "item_type": "ARMAMENT",
        "type": "ARMAMENT",
        "stats": {"armor": 15},
        "ability": None,
        "description": "+15 Armor",
    },
    "Lubricant": {
        "item_type": "ARMAMENT",
        "type": "ARMAMENT",
        "stats": {"hp": 150},
        "ability": None,
        "description": "+150 Health",
    },
    "Amp Coil": {
        "item_type": "ARMAMENT",
        "type": "ARMAMENT",
        "stats": {"ap": 15},
        # FIX-UI: Added effect to allow unit Trigger to fire, for Tooltip demo
        "ability": {
            "name": "Spark",
            "effect_type": AbilityEffect.DEAL_DAMAGE,
            "effect_data": {
                "damage_type": DamageType.MAGIC,
                "scale_factor": 1.0,
                "flat_value": 0,
            },
        },
        "description": "+15 AP. Ability: Spark (Deal 100% Base Value as Magic DMG)",
    },
    "Essence": {
        "item_type": "ARMAMENT",
        "type": "ARMAMENT",
        "stats": {"mr": 15},
        # FIX-UI: Added effect to allow unit Trigger to fire, for Tooltip demo
        "ability": {
            "name": "Restoration",
            "effect_type": AbilityEffect.HEAL,
            "effect_data": {"scale_factor": 1.0, "flat_value": 0},
        },
        "description": "+15 MR. Ability: Restoration (Heal 100% Base Value)",
    },
    # Combined
    "Zap Blade": {
        "item_type": "ARMAMENT",
        "type": "ARMAMENT",
        "stats": {"ad": 15, "ap": 20},  # Gear + Amp Coil
        "ability": {
            "name": "Overcharge",
            "effect_type": AbilityEffect.DEAL_DAMAGE,
            "effect_data": {
                "damage_type": DamageType.MAGIC,
                "scale_factor": 5.0,
                "flat_value": 0,
            },
        },
        "description": "+15AD,+20AP. Ability: Overcharge (Deal 500% Base Value as Magic DMG)",
    },
    "Fireball": {
        "item_type": "ARMAMENT",
        "type": "ARMAMENT",
        "stats": {"ap": 40},  # Amp Coil + Amp Coil
        "ability": {
            "name": "Fireball",
            "effect_type": AbilityEffect.DEAL_DAMAGE,
            "effect_data": {
                "damage_type": DamageType.MAGIC,
                "scale_factor": 0,
                "flat_value": 180,
            },
        },
        "description": "+40AP. Ability: Fireball (Deal 180 flat Magic DMG)",
    },
    "SwordPlate": {
        "item_type": "ARMAMENT",
        "type": "ARMAMENT",
        "stats": {"ad": 10, "armor": 20},  # Gear + Plate
        "ability": {
            "name": "Rend",
            "effect_type": AbilityEffect.APPLY_BUFF,
            "effect_data": {
                "stat": "armor",
                "value": -15,
                "duration": 4.0,
                "is_percent": False,
            },
        },
        "description": "+10AD,+20Armor. Ability: Rend (-15 Armor for 4s)",
    },
    "Bulwark": {
        "item_type": "ARMAMENT",
        "type": "ARMAMENT",
        "stats": {"armor": 20, "hp": 200},  # Plate + Lubricant
        # FIX-UI: Added effect to allow unit Trigger to fire, for Tooltip demo
        "ability": {
            "name": "Fortify",
            "effect_type": AbilityEffect.APPLY_BUFF,
            "effect_data": {
                "stat": "armor",
                "value": 40,
                "duration": 5.0,
                "is_percent": False,
            },
        },
        "description": "+20Ar,+200HP. Ability: Fortify (+40 Armor for 5s)",
    },
    "Oil Can": {
        "item_type": "ARMAMENT",
        "type": "ARMAMENT",
        "stats": {"hp": 200, "ap": 20},  # Lubricant + Amp Coil
        "ability": {
            "name": "Mend",
            "effect_type": AbilityEffect.HEAL,
            "effect_data": {"scale_factor": 1.5, "flat_value": 20},
        },
        "description": "+200HP,+20AP. Ability: Mend (Heal 150% Base Value + 20)",
    },
    "Time Orb": {
        "item_type": "ARMAMENT",
        "type": "ARMAMENT",
        "stats": {"ap": 20, "mr": 20},  # Amp Coil + Essence
        "ability": {
            "name": "Slow",
            "effect_type": AbilityEffect.APPLY_BUFF,
            "effect_data": {
                "stat": "as",
                "value": -30,
                "duration": 3.0,
                "is_percent": True,
            },
        },
        "description": "+20AP,+20MR. Ability: Slow (-30% AS for 3s)",
    },
    "Aegis Shield": {
        "item_type": "ARMAMENT",
        "type": "ARMAMENT",
        "stats": {"armor": 20, "mr": 20},  # Plate + Essence
        "ability": {
            "name": "Barrier",
            "effect_type": AbilityEffect.APPLY_BUFF,
            "effect_data": {
                "stat": "mr",
                "value": 40,
                "duration": 5.0,
                "is_percent": False,
            },
        },
        "description": "+20Ar,+20MR. Ability: Barrier (+40 MR for 5s)",
    },
    "Life Gem": {
        "item_type": "ARMAMENT",
        "type": "ARMAMENT",
        "stats": {"hp": 200, "mr": 20},  # Lubricant + Essence
        "ability": {
            "name": "Greater Mend",
            "effect_type": AbilityEffect.HEAL,
            "effect_data": {"scale_factor": 2.0, "flat_value": 50},
        },
        "description": "+200HP,+20MR. Ability: Greater Mend (Heal 200% Base Value + 50)",
    },
}
for _clr, _theme in [
    ("RED", "Physical DMG"),
    ("GREEN", "Healing"),
    ("BLUE", "Magic DMG"),
    ("YELLOW", "Damage Reduction"),
    ("PURPLE", "Mixed DMG"),
    ("CYAN", "Buff / Debuff"),
    ("BLACK", "Versatile"),
    ("WHITE", "Resource Gen"),
]:
    ITEM_DEFINITIONS[f"Disk_{_clr}"] = {
        "item_type": "DISK",
        "type": "DISK",
        "color": _clr,
        "rarity": "COMMON",
        "stats": {},
        "ability": None,
        "description": f"{_theme} Disk (placeholder)",
    }
ITEM_RECIPES: Dict[Tuple[str, str], str] = {}
THEMES: list[str] = ["MECHANICAL", "FROST", "ARCANE", "DESERT"]
# FIX-UI: Add used_in_run flag to definition
ARTIFACT_DEFINITIONS: Dict[str, Dict[str, Any]] = {
    "Reinforced Plating": {
        "type": "GLOBAL_STAT_BUFF",
        "stats": {"armor": 10},
        "description": "All allies gain +10 Armor.",
        "one_shot": False,
    },
    "Victory Spoils": {
        "type": "GOLD_ON_WIN",
        "value": 2,
        "description": "+2 Gold on combat victory.",
        "one_shot": False,
    },
    "Hasty Clock": {
        "type": "GLOBAL_STAT_BUFF",
        "stats": {"as_percent": 10},
        "description": "All allies gain +10% AS.",
        "one_shot": False,
    },
    "Knowledge Tome": {
        "type": "XP_GRANT",
        "value": 8,
        "description": "Gain 8 XP immediately.",
        "one_shot": True,
    },
    "Lucky Coin": {
        "type": "GOLD_GRANT",
        "value": 10,
        "description": "Gain 10 Gold immediately.",
        "one_shot": True,
    },
    "Spare Gear": {
        "type": "ITEM_GRANT",
        "item": "Gear",
        "description": "Gain 1 Gear component.",
        "one_shot": True,
    },
    "Spare Coil": {
        "type": "ITEM_GRANT",
        "item": "Amp Coil",
        "description": "Gain 1 Amp Coil component.",
        "one_shot": True,
    },
    "Spare Essence": {
        "type": "ITEM_GRANT",
        "item": "Essence",
        "description": "Gain 1 Essence component.",
        "one_shot": True,
    },
}

POSSIBLE_EVENT_ITEMS: List[str] = ["Gear", "Plate", "Lubricant", "Amp Coil", "Essence"]
POSSIBLE_EVENT_ARTIFACTS: List[str] = list(ARTIFACT_DEFINITIONS.keys())

NODE_REWARDS: Dict[str, Dict[str, Any]] = {
    "COMBAT_EASY": {"xp": 0, "items": [], "artifacts": []},
    "COMBAT_MEDIUM": {"xp": 0, "items": ["Gear"], "artifacts": []},
    "COMBAT_HARD": {
        "xp": 1,
        "items": ["Plate", "Gear"],
        "artifacts": ["Reinforced Plating"],
    },
    "BOSS": {
        "items": ["Amp Coil", "Plate", "Essence"],
        "artifacts": ["Reinforced Plating", "Hasty Clock"],
    },
    "SHOP": {"xp": 0, "items": [], "artifacts": []},
    "EVENT": {"xp": 0, "items": [], "artifacts": []},
}


def _split(base: list[str]) -> dict[str, list[str]]:
    pools = {"ACT1": [], "ACT4": []}
    for t in THEMES:
        pools[t] = []
    for i, n in enumerate(base):
        bucket = list(pools.keys())[i % len(pools)]
        pools[bucket].append(n)
    # 占位补足
    for k, v in pools.items():
        while len(v) < 3:
            v.append(f"{v[0]}_{len(v)+1}" if v else f"Placeholder_{k}_{len(v)+1}")
    return pools


EVENT_POOLS = _split(list(NODE_REWARDS.keys()))
ITEM_POOLS = _split(list(ITEM_DEFINITIONS.keys()))
ARTIFACT_POOLS = _split(list(ARTIFACT_DEFINITIONS.keys()))
ENEMY_TEAM_POOLS = _split(list(ENEMY_TEAM_DEFINITIONS.keys()))
BOSS_POOLS = _split([k for k in ENEMY_TEAM_DEFINITIONS if "BOSS" in k])