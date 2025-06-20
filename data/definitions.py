# data/definitions.py
from typing import Any, Dict, List, Tuple
from data.constants import RARITY_ORDER
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
            "hp": 60000,
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
    "Scrap Rat": {
        "rarity": "COMMON",
        "primary_color": Color.WHITE,
        "traits": [],
        "base_stats": {
            "hp": 500,
            "ad": 60,
            "as": 0.8,
            "ap": 0,
            "armor": 20,
            "mr": 20,
            "range": 40,
        },
        "trigger": {
            "timing_type": TriggerTiming.START_OF_COMBAT,
            "target_type": TriggerTarget.SELF,
            "base_value_source": StatSource.MAX_HP,
            "base_value_multiplier": 0,
            "base_value_flat": 10,
        },
    },
    "Azure Ranger": {
        "rarity": "COMMON",
        "primary_color": Color.BLUE,
        "traits": ["Arcanist"],
        "base_stats": {
            "hp": 550,
            "ad": 35,
            "as": 0.9,
            "ap": 20,
            "armor": 20,
            "mr": 20,
            "range": 130,
        },
        "passive": {"end_of_battle_ap_gain": 1},
        "trigger": {
            "timing_type": TriggerTiming.TIMED,
            "timing_data": {"interval": 5.0},
            "target_type": TriggerTarget.NEAREST_ENEMY,
            "base_value_source": StatSource.AP,
            "base_value_multiplier": 1.0,
            "base_value_flat": 0,
        },
    },
    "Sapphire Medic": {
        "rarity": "UNCOMMON",
        "primary_color": Color.BLUE,
        "traits": ["Mystic"],
        "base_stats": {
            "hp": 650,
            "ad": 30,
            "as": 0.8,
            "ap": 25,
            "armor": 25,
            "mr": 30,
            "range": 130,
        },
        "passive": {"regen_on_trigger": {"duration": 5.0, "heal": 20}},
        "trigger": {
            "timing_type": TriggerTiming.TIMED,
            "timing_data": {"interval": 2.0},
            "target_type": TriggerTarget.LOWEST_HP_ALLY_ADJACENT,
            "base_value_source": StatSource.AP,
            "base_value_multiplier": 0.2,
            "base_value_flat": 0,
        },
    },
    "Azure Skirmisher": {
        "rarity": "UNCOMMON",
        "primary_color": Color.BLUE,
        "traits": ["Brawler"],
        "base_stats": {
            "hp": 750,
            "ad": 55,
            "as": 0.8,
            "ap": 20,
            "armor": 40,
            "mr": 40,
            "range": 50,
        },
        "passive": {"accuracy_counter_debuff": {"value": -25, "duration": 3.0}},
        "trigger": {
            "timing_type": TriggerTiming.TIMED,
            "timing_data": {"interval": 8.0, "accelerate_on_hit": 1.0},
            "target_type": TriggerTarget.RANDOM_NEGATIVE_ALLY,
            "base_value_source": StatSource.AP,
            "base_value_multiplier": 1.0,
            "base_value_flat": 0,
        },
    },
    "Steam Knight": {
        "rarity": "UNCOMMON",
        "primary_color": Color.YELLOW,
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
        "passive": {
            "timing_type": TriggerTiming.TIMED,
            "timing_data": {"interval": 9999.0},
            "target_type": TriggerTarget.SELF,
            "base_value_source": StatSource.FLAT,
            "base_value_multiplier": 0.0,
            "base_value_flat": 0,
            "overheal_to_shield": True,
            "ability": {
            },
        },
        # FIX-UI: Example: Give Steam Knight a Trigger for demonstration
        "trigger": {
            "timing_type": TriggerTiming.ON_SHIELD_BROKEN,
            "target_type": TriggerTarget.SELF,
            "base_value_source": StatSource.EVENT,
            "event_key": "shield",
            "base_value_multiplier": 1.0,
            "base_value_flat": 0,
        },
    },
    "Piston Puncher": {
        "rarity": "UNCOMMON",
        "primary_color": Color.PURPLE,
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
        "passive": {
            "timing_type": TriggerTiming.TIMED,
            "timing_data": {"interval": 9999.0},
            "target_type": TriggerTarget.SELF,
            "base_value_source": StatSource.FLAT,
            "base_value_multiplier": 0.0,
            "base_value_flat": 10,
            "chain_bounces": 3,
            "ability": {
            },
        },
        "trigger": {
            "timing_type": TriggerTiming.ON_HIT,
            "target_type": TriggerTarget.EVENT_TARGETS,
            "base_value_source": StatSource.AP,
            "base_value_multiplier": 1.0,
            "base_value_flat": 0,
        },
    },
    "Alchemist": {
        "rarity": "UNCOMMON",
        "primary_color": Color.CYAN,
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
            "timing_type": TriggerTiming.ON_ANY_DEATH,
            "target_type": TriggerTarget.EVENT_TARGETS,
            "base_value_source": StatSource.EVENT,
            "event_key": "value",
            "base_value_multiplier": 1.0,
            "base_value_flat": 0,
        },
        "passive": {
            "timing_type": TriggerTiming.ON_ANY_DEATH,
            "target_type": TriggerTarget.EVENT_TARGETS,
            "base_value_source": StatSource.FLAT,
            "base_value_multiplier": 0.0,
            "base_value_flat": 0,
            "ability": {
                "name": "Toxic Gift",
                "effect_type": AbilityEffect.APPLY_BUFF,
                "effect_data": {
                    "stat": "percentage_damage_bonus",
                    "value": 20,
                    "duration": None,
                    "is_percent": True,
                    "dot": 50,
                },
            },
        },
    },
    "Water Spitter": {
        "rarity": "UNCOMMON",
        "primary_color": Color.RED,
        "traits": ["Steamcraft"],
        "base_stats": {
            "hp": 700,
            "ad": 60,
            "as": 0.7,
            "ap": 0,
            "armor": 30,
            "mr": 30,
            "range": 80,
        },
        "passive": {
            "timing_type": TriggerTiming.TIMED,
            "timing_data": {"interval": 9999.0},
            "target_type": TriggerTarget.SELF,
            "base_value_source": StatSource.FLAT,
            "base_value_multiplier": 0.0,
            "base_value_flat": 0,
            "cone_attack": True,
            "cone_arc_deg": 60,
            "cone_length": 500,
        },
        "trigger": {
            "timing_type": TriggerTiming.ON_HIT,
            "target_type": TriggerTarget.EVENT_TARGETS,
            "base_value_source": StatSource.EVENT,
            "event_key": "value",
            "base_value_multiplier": 1.0,
            "base_value_flat": 0,
        },
    },
    "Blood Reaver": {
        "rarity": "UNCOMMON",
        "primary_color": Color.RED,
        "traits": ["Brawler"],
        "base_stats": {
            "hp": 850,
            "ad": 65,
            "as": 0.65,
            "ap": 0,
            "armor": 45,
            "mr": 45,
            "range": 50,
        },
        "passive": {
            "timing_type": TriggerTiming.ON_ANY_DEATH,
            "target_type": TriggerTarget.SELF,
            "base_value_source": StatSource.EVENT,
            "event_key": "dead_unit_ad",
            "base_value_multiplier": 0.5,
            "base_value_flat": 0,
            "ability": {
                "name": "Blood Tribute",
                "effect_type": AbilityEffect.APPLY_BUFF,
                "effect_data": {
                    "stat": "ad",
                    "duration": None,
                    "is_percent": False,
                    "scale_factor": 1.0,
                    "flat_value": 0,
                },
            },
        },
        "trigger": {
            "timing_type": TriggerTiming.ON_ANY_DEATH,
            "target_type": TriggerTarget.EVENT_TARGETS,
            "base_value_source": StatSource.AD,
            "base_value_multiplier": 1.0,
            "base_value_flat": 0,
        },
    },
    "Verdant Acolyte": {
        "rarity": "UNCOMMON",
        "primary_color": Color.GREEN,
        "traits": ["Mystic"],
        "base_stats": {
            "hp": 700,
            "ad": 40,
            "as": 0.6,
            "ap": 30,
            "armor": 30,
            "mr": 40,
            "range": 50,
        },
        "trigger": {
            "timing_type": TriggerTiming.TIMED,
            "timing_data": {"interval": 5.0},
            "target_type": TriggerTarget.NEAREST_ALLY,
            "hp_threshold": 0.5,
            "base_value_source": StatSource.MAX_HP,
            "base_value_multiplier": 0.2,
            "base_value_flat": 0,
        },
        "passive": {
            "timing_type": TriggerTiming.START_OF_COMBAT,
            "target_type": TriggerTarget.SELF,
            "base_value_source": StatSource.FLAT,
            "base_value_multiplier": 0.0,
            "base_value_flat": 0,
            "double_heal_first": 3,
            "max_double_heal_stacks": 10,
        },
    },
    "Railgunner": {
        "rarity": "RARE",
        "primary_color": Color.RED,
        "traits": ["Automaton", "Steamcraft"],
        "base_stats": {
            "hp": 800,
            "ad": 65,
            "as": 2,
            "ap": 0,
            "armor": 40,
            "mr": 30,
            "range": 1000,
        },
        "passive": {
            "timing_type": TriggerTiming.TIMED,
            "timing_data": {"interval": 9999.0},
            "target_type": TriggerTarget.SELF,
            "base_value_source": StatSource.FLAT,
            "base_value_multiplier": 0.0,
            "base_value_flat": 10,
            "ability": {
            },
            "line_attack": True,
            "scatter_deg": 30,
            "line_width": 20,
            "line_length": 4000,
        },
        "trigger": {
            "timing_type": TriggerTiming.ON_HIT,
            "target_type": TriggerTarget.EVENT_TARGETS,
            "base_value_source": StatSource.AD,
            "base_value_multiplier": 1.0,
            "base_value_flat": 0,
        },
    },
    "Crimson Spinner": {
        "rarity": "RARE",
        "primary_color": Color.RED,
        "traits": ["Brawler"],
        "base_stats": {
            "hp": 850,
            "ad": 70,
            "as": 0.7,
            "ap": 0,
            "armor": 50,
            "mr": 40,
            "range": 50,
        },
        "passive": {
            "timing_type": TriggerTiming.TIMED,
            "timing_data": {"interval": 9999.0},
            "target_type": TriggerTarget.SELF,
            "base_value_source": StatSource.FLAT,
            "base_value_multiplier": 0.0,
            "base_value_flat": 0,
            "circle_attack": True,
            "circle_radius": 80,
        },
        "trigger": {
            "timing_type": TriggerTiming.ON_AOE_DAMAGE,
            "target_type": TriggerTarget.EVENT_TARGETS,
            "base_value_source": StatSource.EVENT,
            "event_key": "damage",
            "base_value_multiplier": 1.0,
            "base_value_flat": 0,
            "radius": 120,
        },
    },
    "Forge Adept": {
        "rarity": "EPIC",
        "primary_color": Color.RED,
        "traits": ["Steamcraft"],
        "base_stats": {
            "hp": 1000,
            "ad": 75,
            "as": 0.6,
            "ap": 0,
            "armor": 50,
            "mr": 50,
            "range": 80,
        },
        "passive": {
            "timing_type": TriggerTiming.ON_HIT,
            "target_type": TriggerTarget.ATTACK_TARGET,
            "base_value_source": StatSource.AD,
            "base_value_multiplier": 0.0,
            "base_value_flat": 0,
            "burning_attack": True,
        },
        "trigger": {
            "timing_type": TriggerTiming.ON_DOT_DAMAGE,
            "target_type": TriggerTarget.ATTACK_TARGET,
            "base_value_source": StatSource.AD,
            "base_value_multiplier": 0.02,
            "base_value_flat": 0,
        },
    },
    "Lifebond Sentinel": {
        "rarity": "RARE",
        "primary_color": Color.GREEN,
        "traits": ["Mystic", "Defender"],
        "base_stats": {
            "hp": 850,
            "ad": 45,
            "as": 0.6,
            "ap": 30,
            "armor": 50,
            "mr": 60,
            "range": 120,
        },
        "trigger": {
            "timing_type": TriggerTiming.TIMED,
            "target_type": TriggerTarget.EVENT_TARGETS,
            "all_allies_below_hp": 0.5,
            "base_value_source": StatSource.CURRENT_HP,
            "base_value_multiplier": 0.5,
            "base_value_flat": 0,
        },
        "passive": {
            "timing_type": TriggerTiming.ON_HIT,
            "target_type": TriggerTarget.ATTACK_TARGET,
            "base_value_source": StatSource.AD,
            "base_value_multiplier": 0.0,
            "base_value_flat": 0,
          "hp_loss_on_trigger_percent": 0.5,
        },
    },
    "Emerald Warden": {
        "rarity": "RARE",
        "primary_color": Color.GREEN,
        "traits": ["Brawler"],
        "base_stats": {
            "hp": 900,
            "ad": 55,
            "as": 0.7,
            "ap": 0,
            "armor": 50,
            "mr": 50,
            "range": 50,
        },
        "passive": {
            "timing_type": TriggerTiming.START_OF_COMBAT,
            "target_type": TriggerTarget.SELF,
            "base_value_source": StatSource.FLAT,
            "base_value_multiplier": 0.0,
            "base_value_flat": 0,
            "ranged_evasion_aura": 20,
        },
        "trigger": {
            "timing_type": TriggerTiming.ON_ALLY_HIT,
            "target_type": TriggerTarget.ATTACK_TARGET,
            "base_value_source": StatSource.MAX_HP,
            "base_value_multiplier": 0.2,
            "base_value_flat": 0,
        },
    },
    "Cobalt Hexer": {
        "rarity": "RARE",
        "primary_color": Color.BLUE,
        "secondary_synergies": [],
        "traits": ["Arcanist"],
        "base_stats": {
            "hp": 700,
            "ad": 40,
            "as": 0.8,
            "ap": 50,
            "armor": 20,
            "mr": 60,
            "range": 150,
        },
        "passive": {"extra_negative_stack_on_trigger": True},
        "trigger": {
            "timing_type": TriggerTiming.TIMED,
            "timing_data": {
                "interval": 20.0,
                "accelerate_per_negative": 0.05,
            },
            "target_type": TriggerTarget.ALL_NEGATIVE_ENEMIES,
            "base_value_source": StatSource.AP,
            "base_value_multiplier": 0.1,
            "base_value_flat": 0,
            "num_negative_multiplier": True,
        },
    },
    "Azure Channeler": {
        "rarity": "RARE",
        "primary_color": Color.BLUE,
        "secondary_synergies": [],
        "traits": ["Arcanist"],
        "base_stats": {
            "hp": 800,
            "ad": 40,
            "as": 0.7,
            "ap": 60,
            "armor": 30,
            "mr": 40,
            "range": 100,
        },
        "passive": {
            "empower_per_status_on_trigger": True,
            "empower_damage": 10,
            "empower_duration": 10.0,
        },
        "trigger": {
            "timing_type": TriggerTiming.ON_TEAM_DAMAGE_DOUBLED,
            "target_type": TriggerTarget.EVENT_TARGETS,
            "base_value_source": StatSource.AP,
            "base_value_multiplier": 0.2,
            "base_value_flat": 0,
            "count_multiplier": True,
        },
    },
    "Twilight Vanguard": {
        "rarity": "EPIC",
        "primary_color": Color.PURPLE,
        "secondary_synergies": [],
        "traits": [],
        "base_stats": {
            "hp": 1100,
            "ad": 80,
            "as": 0.7,
            "ap": 0,
            "armor": 60,
            "mr": 60,
            "range": 50,
            "omnivamp": 25,
        },
        "trigger": {
            "timing_type": TriggerTiming.ON_DAMAGE,
            "timing_data": {"threshold": 500},
            "target_type": TriggerTarget.SELF_AND_EVENT_TARGETS,
            "base_value_source": StatSource.FLAT,
            "base_value_multiplier": 0.0,
            "base_value_flat": 10,
        },
    },
    "Gilded Caretaker": {
        "rarity": "UNCOMMON",
        "primary_color": Color.YELLOW,
        "secondary_synergies": [],
        "traits": ["Mystic"],
        "base_stats": {
            "hp": 700,
            "ad": 0,
            "as": 0.7,
            "ap": 0,
            "armor": 30,
            "mr": 30,
            "range": 80,
        },
        "passive": {"target_lowest_hp_ally": True},
        "trigger": {
            "timing_type": TriggerTiming.ON_HIT,
            "target_type": TriggerTarget.ATTACK_TARGET,
            "base_value_source": StatSource.EVENT,
            "event_key": "missing_hp",
            "base_value_multiplier": 0.1,
            "base_value_flat": 0,
        },
    },
    "Gilded Marshal": {
        "rarity": "RARE",
        "primary_color": Color.YELLOW,
        "secondary_synergies": [],
        "traits": ["Mystic"],
        "base_stats": {
            "hp": 850,
            "ad": 55,
            "as": 0.7,
            "ap": 0,
            "armor": 50,
            "mr": 50,
            "range": 120,
        },
        "passive": {"extend_positive_duration": 10.0},
        "trigger": {
            "timing_type": TriggerTiming.START_OF_COMBAT,
            "target_type": TriggerTarget.ALL_ALLIES,
            "base_value_source": StatSource.RESIST_SUM,
            "base_value_multiplier": 1.0,
            "base_value_flat": 0,
        },
    },
    "Gilded Purifier": {
        "rarity": "EPIC",
        "primary_color": Color.YELLOW,
        "secondary_synergies": [],
        "traits": ["Mystic"],
        "base_stats": {
            "hp": 1000,
            "ad": 55,
            "as": 0.7,
            "ap": 40,
            "armor": 60,
            "mr": 60,
            "range": 120,
        },
        "passive": {"purge_after_trigger": 3},
        "trigger": {
            "timing_type": TriggerTiming.STATUS_OVERLOAD,
            "target_type": TriggerTarget.EVENT_TARGETS,
            "base_value_source": StatSource.EVENT,
            "event_key": "attack_sum",
            "base_value_multiplier": 1.0,
            "base_value_flat": 0,
        },
    },
    "Azure Bulwark": {
        "rarity": "RARE",
        "primary_color": Color.CYAN,
        "secondary_synergies": [],
        "traits": ["Defender"],
        "base_stats": {
            "hp": 900,
            "ad": 60,
            "as": 0.7,
            "ap": 0,
            "armor": 55,
            "mr": 55,
            "range": 50,
        },
        "passive": {"bleed_storage_percent": 50},
        "trigger": {
            "timing_type": TriggerTiming.BLEED_THRESHOLD,
            "timing_data": {"threshold": 0.25},
            "target_type": TriggerTarget.SELF,
            "base_value_source": StatSource.MAX_HP,
            "base_value_multiplier": 0.05,
            "base_value_flat": 0,
        },
    },
    "Azure Phoenix": {
        "rarity": "EPIC",
        "primary_color": Color.CYAN,
        "secondary_synergies": [],
        "traits": ["Mystic"],
        "base_stats": {
            "hp": 1000,
            "ad": 60,
            "as": 0.7,
            "ap": 0,
            "armor": 55,
            "mr": 55,
            "range": 80,
        },
        "passive": {"revive_percent": 20},
        "trigger": {
            "timing_type": TriggerTiming.ON_ANY_DEATH,
            "target_type": TriggerTarget.ALL_ENEMIES,
            "base_value_source": StatSource.EVENT,
            "event_key": "dead_unit_hp",
            "base_value_multiplier": 0.05,
            "base_value_flat": 0,
        },
    },
    "Lifebond Guardian": {
        "rarity": "EPIC",
        "primary_color": Color.GREEN,
        "traits": ["Defender"],
        "base_stats": {
            "hp": 1200,
            "ad": 70,
            "as": 0.6,
            "ap": 0,
            "armor": 70,
            "mr": 70,
            "range": 50,
        },
        "passive": {
            "timing_type": TriggerTiming.START_OF_COMBAT,
            "target_type": TriggerTarget.SELF,
            "base_value_source": StatSource.FLAT,
            "base_value_multiplier": 0.0,
            "base_value_flat": 0,
            "bond_damage_redirect": 40,
        },
        "trigger": {
            "timing_type": TriggerTiming.ON_BONDED_DEATH,
            "target_type": TriggerTarget.SELF,
            "base_value_source": StatSource.EVENT,
            "event_key": "redirect_total",
            "base_value_multiplier": 5.0,
            "base_value_flat": 0,
        },
    },
    "Azure Timekeeper": {
        "rarity": "EPIC",
        "primary_color": Color.BLUE,
        "secondary_synergies": [],
        "traits": ["Arcanist"],
        "base_stats": {
            "hp": 950,
            "ad": 50,
            "as": 0.7,
            "ap": 70,
            "armor": 40,
            "mr": 60,
            "range": 130,
        },
        "passive": {
            "ally_timer_haste": 25,
            "tally_timer_activations": True,
        },
        "trigger": {
            "timing_type": TriggerTiming.TIMED,
            "timing_data": {"interval": 5.0, "accelerate_per_tally": 0.1},
            "target_type": TriggerTarget.RANDOM_ENEMY,
            "base_value_source": StatSource.AP,
            "base_value_multiplier": 1.0,
            "base_value_flat": 0,
            "repeat_from_tally": True,
            "tally_multiplier": True,
        },
    },
    "Amethyst Watcher": {
        "rarity": "UNCOMMON",
        "primary_color": Color.PURPLE,
        "secondary_synergies": [],
        "traits": [],
        "base_stats": {
            "hp": 700,
            "ad": 0,
            "as": 0.0,
            "ap": 0,
            "armor": 40,
            "mr": 40,
            "range": 0,
            "move_speed": 0,
        },
        "passive": {},
        "trigger": {
            "timing_type": TriggerTiming.TIMED,
            "timing_data": {"interval": 15.0},
            "target_type": TriggerTarget.FARTHEST_ENEMY_ADJACENT,
            "base_value_source": StatSource.FLAT,
            "base_value_multiplier": 0.0,
            "base_value_flat": 1500,
        },
    },
    # Enemies
    "Rust Bug": {
        "rarity": "ENEMY",
        "traits": ["Vermin"],
        "base_stats": {
            "hp": 40000,
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
    "Yellow": {
        "description": "Yellow units amplify healing and gain omnivamp.",
        "thresholds": [2, 3, 4],
        "effects": [
            {"incoming_healing_bonus": 20, "omnivamp": 3},
            {"incoming_healing_bonus": 50, "omnivamp": 5},
            {"incoming_healing_bonus": 100, "omnivamp": 10},
        ],
        "targets": "ALL_ALLIES",
        "type": "STAT_BOOST",
    },
    "Purple": {
        "description": "Purple units empower all allies' damage output.",
        "thresholds": [2, 3, 4],
        "effects": [
            {"percentage_damage_bonus": 20, "flat_damage_bonus": 30},
            {"percentage_damage_bonus": 50, "flat_damage_bonus": 60},
            {"percentage_damage_bonus": 100, "flat_damage_bonus": 120},
        ],
        "targets": "ALL_ALLIES",
        "type": "STAT_BOOST",
    },
    "Cyan": {
        "description": "Cyan units grant regeneration and evasion.",
        "thresholds": [2, 3, 4],
        "effects": [
            {"regen": 20, "dodge_chance": 20},
            {"regen": 80, "dodge_chance": 30},
            {"regen": 200, "dodge_chance": 40},
        ],
        "targets": "ALL_ALLIES",
        "type": "ABILITY",
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
    "Viper MK2": {
        "item_type": "ARMAMENT",
        "type": "ARMAMENT",
        "stats": {"ap": 20},
        "special": "poison_on_magic",
        "ability": None,
        "description": "+20AP. Passive: poison target for 20 dmg over 5s when dealing magic damage.",
    },
    "Riposte MK3": {
        "item_type": "ARMAMENT",
        "type": "ARMAMENT",
        "stats": {"dodge_chance": 20},
        "special": "counter_on_dodge",
        "ability": None,
        "description": "+20% Dodge. Passive: counter attack when dodging a basic attack.",
    },
}
# Generate stat booster armaments for each rarity level
_stat_prefix = {
    "ad": "AD",
    "ap": "AP",
    "as_percent": "AS",
    "hp": "HP",
    "armor": "Armor",
    "mr": "MR",
}
_stat_values = {
    "ad": [10, 20, 30, 45, 60],
    "ap": [15, 30, 45, 60, 80],
    "as_percent": [10, 20, 30, 40, 50],
    "hp": [150, 300, 450, 600, 800],
    "armor": [15, 30, 45, 60, 80],
    "mr": [15, 30, 45, 60, 80],
}
for stat, prefix in _stat_prefix.items():
    values = _stat_values[stat]
    for rar, val in zip(RARITY_ORDER, values):
        ITEM_DEFINITIONS[f"{prefix} MK{RARITY_ORDER.index(rar)+1}"] = {
            "item_type": "ARMAMENT",
            "type": "ARMAMENT",
            "stats": {stat: val},
            "ability": None,
            "description": f"+{val} {prefix if stat != 'as_percent' else 'AS%'}",
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
DiskAbilityRegistry: dict[Color, dict[str, List[dict]]] = {
    Color.RED: {
        "COMMON": [
            {
                "ability": {
                    "name": "Power Strike",
                    "effect_type": AbilityEffect.DEAL_DAMAGE,
                    "effect_data": {
                        "damage_type": DamageType.PHYSICAL,
                        "scale_factor": 0.0,
                        "flat_value": 50,
                    },
                },
                "stats": {},
            }
        ],
        "UNCOMMON": [
            {
                "ability": {
                    "name": "Crushing Blow",
                    "effect_type": AbilityEffect.DEAL_DAMAGE,
                    "effect_data": {
                        "damage_type": DamageType.PHYSICAL,
                        "scale_factor": 0.0,
                        "flat_value": 100,
                        "flat_physical_penetration": 20,
                    },
                },
                "stats": {},
            },
            {
                "ability": {
                    "name": "Frenzied Strike",
                    "effect_type": AbilityEffect.DEAL_DAMAGE,
                    "effect_data": {
                        "damage_type": DamageType.PHYSICAL,
                        "scale_factor": 0.0,
                        "flat_value": 100,
                        "extra_attack_every": 3,
                    },
                },
                "stats": {},
            },
        ],
        "RARE": [
            {
                "ability": {
                    "name": "Power Strike",
                    "effect_type": AbilityEffect.DEAL_DAMAGE,
                    "effect_data": {
                        "damage_type": DamageType.PHYSICAL,
                        "scale_factor": 1.5,
                        "flat_value": 0,
                    },
                },
                "stats": {},
            }
        ],
        "EPIC": [
            {
                "ability": {
                    "name": "Power Strike",
                    "effect_type": AbilityEffect.DEAL_DAMAGE,
                    "effect_data": {
                        "damage_type": DamageType.PHYSICAL,
                        "scale_factor": 1.5,
                        "flat_value": 0,
                    },
                },
                "stats": {},
            }
        ],
    },
    Color.GREEN: {
        k: [
            {
                "ability": {
                    "name": "Rejuvenation",
                    "effect_type": AbilityEffect.HEAL,
                    "effect_data": {"scale_factor": 1.0, "flat_value": 0},
                },
                "stats": {},
            }
        ]
        for k in ["COMMON", "UNCOMMON", "RARE", "EPIC"]
    },
    Color.BLUE: {
        k: [
            {
                "ability": {
                    "name": "Arcane Bolt",
                    "effect_type": AbilityEffect.DEAL_DAMAGE,
                    "effect_data": {
                        "damage_type": DamageType.MAGIC,
                        "scale_factor": 1.5,
                        "flat_value": 0,
                    },
                },
                "stats": {},
            }
        ]
        for k in ["COMMON", "UNCOMMON", "RARE", "EPIC"]
    },
    Color.YELLOW: {
        k: [
            {
                "ability": {
                    "name": "Fortify",
                    "effect_type": AbilityEffect.APPLY_BUFF,
                    "effect_data": {
                        "stat": "percentage_damage_reduction",
                        "value": 20,
                        "duration": 3.0,
                        "is_percent": False,
                    },
                },
                "stats": {},
            }
        ]
        for k in ["COMMON", "UNCOMMON", "RARE", "EPIC"]
    },
    Color.PURPLE: {
        k: [
            {
                "ability": {
                    "name": "Void Pulse",
                    "effect_type": AbilityEffect.DEAL_DAMAGE,
                    "effect_data": {
                        "damage_type": DamageType.TRUE,
                        "scale_factor": 1.2,
                        "flat_value": 0,
                    },
                },
                "stats": {},
            }
        ]
        for k in ["COMMON", "UNCOMMON", "RARE", "EPIC"]
    },
    Color.CYAN: {
        k: [
            {
                "ability": {
                    "name": "Weakening Beam",
                    "effect_type": AbilityEffect.APPLY_BUFF,
                    "effect_data": {
                        "stat": "ad",
                        "value": -10,
                        "duration": 4.0,
                        "is_percent": False,
                    },
                },
                "stats": {},
            }
        ]
        for k in ["COMMON", "UNCOMMON", "RARE", "EPIC"]
    },
    Color.BLACK: {
        k: [
            {
                "ability": {
                    "name": "Annihilation",
                    "effect_type": AbilityEffect.DEAL_DAMAGE,
                    "effect_data": {
                        "damage_type": DamageType.TRUE,
                        "scale_factor": 2.0,
                        "flat_value": 0,
                    },
                },
                "stats": {},
            }
        ]
        for k in ["COMMON", "UNCOMMON", "RARE", "EPIC"]
    },
    Color.WHITE: {
        k: [
            {
                "ability": {
                    "name": "Inspiration",
                    "effect_type": AbilityEffect.APPLY_BUFF,
                    "effect_data": {
                        "stat": "ap",
                        "value": 10,
                        "duration": 5.0,
                        "is_percent": False,
                    },
                },
                "stats": {},
            }
        ]
        for k in ["COMMON", "UNCOMMON", "RARE", "EPIC"]
    },
}
# ------------------------------------------------------------
#               bespoke disk item definitions
# ------------------------------------------------------------

ITEM_DEFINITIONS["Crimson Burn Disk"] = {
    "item_type": "DISK",
    "type": "DISK",
    "color": "RED",
    "rarity": "UNCOMMON",
    "stats": {},
    "ability": {
        "name": "Sear",
        "effect_type": AbilityEffect.DEAL_DAMAGE,
        "effect_data": {
            "damage_type": DamageType.PHYSICAL,
            "scale_factor": 0.0,
            "flat_value": 70,
            "dot_damage": 12,
            "dot_duration": 3.0,
            "dot_max_stacks": 5,
        },
    },
    "description": "Deal 70 physical damage and apply a stacking burn.",
}

ITEM_DEFINITIONS["Crimson Fury Disk"] = {
    "item_type": "DISK",
    "type": "DISK",
    "color": "RED",
    "rarity": "UNCOMMON",
    "stats": {},
    "ability": {
        "name": "Overload",
        "effect_type": AbilityEffect.DEAL_DAMAGE,
        "effect_data": {
            "damage_type": DamageType.PHYSICAL,
            "scale_factor": 0.0,
            "flat_value": 200,
            "max_damage_uses": 6,
        },
    },
    "description": "Deals 200 physical damage, then fizzles after 6 uses.",
}

ITEM_DEFINITIONS["Crimson Precision Disk"] = {
    "item_type": "DISK",
    "type": "DISK",
    "color": "RED",
    "rarity": "UNCOMMON",
    "stats": {},
    "ability": {
        "name": "Piercing Strike",
        "effect_type": AbilityEffect.DEAL_DAMAGE,
        "effect_data": {
            "damage_type": DamageType.PHYSICAL,
            "scale_factor": 0.0,
            "flat_value": 70,
            "can_crit": True,
            "extra_crit_chance": 50,
        },
    },
    "description": "70 physical damage that gains +50% crit chance.",
}

ITEM_DEFINITIONS["Crimson Impact Disk"] = {
    "item_type": "DISK",
    "type": "DISK",
    "color": "RED",
    "rarity": "UNCOMMON",
    "stats": {},
    "ability": {
        "name": "Impact Burst",
        "effect_type": AbilityEffect.DEAL_DAMAGE,
        "effect_data": {
            "damage_type": DamageType.PHYSICAL,
            "scale_factor": 2.0,
            "flat_value": 300,
            "cooldown": 5.0,
        },
    },
    "description": "300 + 2×value physical damage, 5s cooldown.",
}

ITEM_DEFINITIONS["Crimson Execution Disk"] = {
    "item_type": "DISK",
    "type": "DISK",
    "color": "RED",
    "rarity": "RARE",
    "stats": {},
    "ability": {
        "name": "Execute",
        "effect_type": AbilityEffect.DEAL_DAMAGE,
        "effect_data": {
            "damage_type": DamageType.PHYSICAL,
            "flat_value": 120,
            "hp_compare_factor": 5.0,
            "hp_compare_multiplier": 2.0,
        },
    },
    "description": "120 damage doubled vs targets with >5× your HP.",
}

ITEM_DEFINITIONS["Crimson Knockback Disk"] = {
    "item_type": "DISK",
    "type": "DISK",
    "color": "RED",
    "rarity": "RARE",
    "stats": {},
    "ability": {
        "name": "Force Thrust",
        "effect_type": AbilityEffect.DEAL_DAMAGE,
        "effect_data": {
            "damage_type": DamageType.PHYSICAL,
            "flat_value": 120,
            "knockback_per_value": 20.0,
        },
    },
    "description": "120 damage and knockback 20×value.",
}

ITEM_DEFINITIONS["Crimson Splash Disk"] = {
    "item_type": "DISK",
    "type": "DISK",
    "color": "RED",
    "rarity": "RARE",
    "stats": {},
    "ability": {
        "name": "Splash Hit",
        "effect_type": AbilityEffect.DEAL_DAMAGE,
        "effect_data": {
            "damage_type": DamageType.PHYSICAL,
            "flat_value": 100,
            "splash_ratio": 0.5,
            "splash_radius": 60,
        },
    },
    "description": "100 damage and splash half in a radius.",
}

ITEM_DEFINITIONS["Crimson Doom Disk"] = {
    "item_type": "DISK",
    "type": "DISK",
    "color": "RED",
    "rarity": "EPIC",
    "stats": {},
    "ability": {
        "name": "Doom Brand",
        "effect_type": AbilityEffect.APPLY_BUFF,
        "effect_data": {
            "status_name": "DOOM_BRAND",
            "threshold": 7,
            "damage_pct": 0.35,
        },
    },
    "description": "Stacking mark; at 7 stacks deal 35% current HP true damage.",
}

ITEM_DEFINITIONS["Crimson Frenzy Disk"] = {
    "item_type": "DISK",
    "type": "DISK",
    "color": "RED",
    "rarity": "EPIC",
    "stats": {},
    "ability": {
        "name": "Frenzy",
        "effect_type": AbilityEffect.APPLY_BUFF,
        "effect_data": {
            "stack_buff_stat": "as_percent",
            "value": 8,
            "is_percent": True,
            "duration": None,
            "apply_to_source": True,
        },
    },
    "description": "Grants +8% attack speed per trigger indefinitely.",
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