# data/definitions.py
from typing import List, Dict, Any, Tuple, Optional
from data.enums import TriggerTiming, TriggerTarget, StatSource, AbilityEffect, DamageType

# Stats: HP, AD, AS, AP, Armor, MR, Range (pixels)
UNIT_DEFINITIONS: Dict[str, Dict[str, Any]] = {
    "Clockwork Soldier": {"rarity": "COMMON", "traits": ["Automaton", "Defender"], 
                          "base_stats": {"hp": 600, "ad": 50, "as": 0.6, "ap": 0, "armor": 40, "mr": 40, "range": 50},
                          "trigger": {"timing_type": TriggerTiming.ON_HIT, "target_type": TriggerTarget.ATTACK_TARGET,
                                      "base_value_source": StatSource.AD, "base_value_multiplier": 0.2, "base_value_flat": 0}},
    "Gear Grinder":    {"rarity": "COMMON", "traits": ["Automaton", "Brawler"], 
                        "base_stats": {"hp": 700, "ad": 55, "as": 0.5, "ap": 0, "armor": 30, "mr": 30, "range": 40},
                         "trigger": {"timing_type": TriggerTiming.ON_HIT, "target_type": TriggerTarget.ATTACK_TARGET,
                                     "base_value_source": StatSource.ARMOR, "base_value_multiplier": 1.0, "base_value_flat": 0}},
     "Boiler Bot":     {"rarity": "COMMON", "traits": ["Automaton", "Steamcraft"], 
                        "base_stats": {"hp": 650, "ad": 50, "as": 0.5, "ap": 10, "armor": 35, "mr": 35, "range": 45},
                         "trigger": None},
     "Scrap Rat":       {"rarity": "COMMON", "traits": ["Scavenger"], 
                        "base_stats": {"hp": 500, "ad": 60, "as": 0.8, "ap": 0, "armor": 20, "mr": 20, "range": 40},
                         "trigger": None},
    "Steam Knight":    {"rarity": "UNCOMMON", "traits": ["Steamcraft", "Defender"], 
                        "base_stats": {"hp": 800, "ad": 60, "as": 0.7, "ap": 0, "armor": 50, "mr": 50, "range": 50},
                         # FIX-UI: Example: Give Steam Knight a Trigger for demonstration
                          "trigger": {"timing_type": TriggerTiming.START_OF_COMBAT, "target_type": TriggerTarget.SELF,
                                    "base_value_source": StatSource.ARMOR, "base_value_multiplier": 1.0, "base_value_flat": 0}},
    "Piston Puncher":  {"rarity": "UNCOMMON", "traits": ["Steamcraft", "Brawler"], 
                        "base_stats": {"hp": 900, "ad": 70, "as": 0.6, "ap": 0,"armor": 40, "mr": 40, "range": 40},
                         "trigger": {"timing_type": TriggerTiming.ON_TAKE_DAMAGE, "target_type": TriggerTarget.SELF,
                                     "base_value_source": StatSource.MAX_HP, "base_value_multiplier": 0.02, "base_value_flat": 0}},
    "Alchemist":       {"rarity": "UNCOMMON", "traits": ["Scavenger", "Mystic"],  
                        "base_stats": {"hp": 600, "ad": 45, "as": 0.7, "ap": 30,"armor": 20, "mr": 40, "range": 120},
                         "trigger": {"timing_type": TriggerTiming.ON_HIT, "target_type": TriggerTarget.ATTACK_TARGET,
                                     "base_value_source": StatSource.AP, "base_value_multiplier": 1.5, "base_value_flat": 0}},
    "Cogsworth":       {"rarity": "RARE", "traits": ["Automaton", "Arcanist"], 
                        "base_stats": {"hp": 750, "ad": 40, "as": 0.8, "ap": 50, "armor": 20, "mr": 60, "range": 150},
                         "trigger": {"timing_type": TriggerTiming.TIMED, "timing_data": {"interval": 4.0}, "target_type": TriggerTarget.NEAREST_ENEMY,
                                     "base_value_source": StatSource.AP, "base_value_multiplier": 3.0, "base_value_flat": 0}},
    "Chronomancer":    {"rarity": "RARE", "traits": ["Arcanist", "Mystic"], 
                         "base_stats": {"hp": 700, "ad": 30, "as": 0.9, "ap": 60, "armor": 15, "mr": 70, "range": 180},
                         "trigger": {"timing_type": TriggerTiming.TIMED, "timing_data": {"interval": 3.0}, "target_type": TriggerTarget.RANDOM_ENEMY,
                                     "base_value_source": StatSource.AP, "base_value_multiplier": 2.0, "base_value_flat": 0}},
     "Noble Guard":    {"rarity": "RARE", "traits": ["Noble", "Defender"], 
                         "base_stats": {"hp": 950, "ad": 50, "as": 0.6, "ap": 0, "armor": 70, "mr": 50, "range": 50},
                           # FIX-UI: Example: Give Noble Guard a Trigger for demonstration
                          "trigger": {"timing_type": TriggerTiming.START_OF_COMBAT, "target_type": TriggerTarget.SELF,
                                     "base_value_source": StatSource.FLAT, "base_value_multiplier": 0, "base_value_flat": 100.0}},
     "Brass Baron":     {"rarity": "EPIC", "traits": ["Steamcraft", "Noble"], 
                         "base_stats": {"hp": 1100, "ad": 80, "as": 0.7, "ap": 20, "armor": 60, "mr": 60, "range": 60},
                         "trigger": None},
     "Golem":           {"rarity": "EPIC", "traits": ["Automaton", "Defender", "Brawler"], 
                        "base_stats": {"hp": 1500, "ad": 90, "as": 0.4, "ap": 0,"armor": 80, "mr": 80, "range": 40},
                         "trigger": {"timing_type": TriggerTiming.ON_DEATH, "target_type": TriggerTarget.RANDOM_ENEMY,
                                     "base_value_source": StatSource.MAX_HP, "base_value_multiplier": 0.5, "base_value_flat": 0}},
     "Rift Mage":       {"rarity": "EPIC", "traits": ["Arcanist", "Mystic"], 
                         "base_stats": {"hp": 900, "ad": 30, "as": 0.7, "ap": 100, "armor": 20, "mr": 80, "range": 200},
                         "trigger": {"timing_type": TriggerTiming.TIMED, "timing_data": {"interval": 6.0}, "target_type": TriggerTarget.LOWEST_HP_ENEMY,
                                     "base_value_source": StatSource.AP, "base_value_multiplier": 4.0, "base_value_flat": 0}},
    # Enemies 
     "Rust Bug": {"rarity": "ENEMY", "traits": ["Vermin"], "base_stats": {"hp": 400, "ad": 40, "as": 0.7, "ap": 0, "armor": 10, "mr": 10, "range": 40}, "trigger": None},
     "Gremlin":  {"rarity": "ENEMY", "traits": ["Vermin"], "base_stats": {"hp": 300, "ad": 60, "as": 1.0, "ap": 0, "armor": 5, "mr": 5, "range": 100}, "trigger": None},
     "Big Bad Bot": {"rarity": "ENEMY", "traits": ["Automaton", "Boss"], "base_stats": {"hp": 2000, "ad": 100, "as": 0.8, "ap": 50, "armor": 70, "mr": 70, "range": 60}, "trigger": None},
      "War Bot": {"rarity": "ENEMY", "traits": ["Automaton", "Boss"], "base_stats": {"hp": 3500, "ad": 150, "as": 0.9, "ap": 80, "armor": 100, "mr": 100, "range": 80}, "trigger": None},
}

SYNERGY_DEFINITIONS: Dict[str, Dict[str, Any]] = {
    "Automaton": { "description": "Automatons gain Armor and MR.", "thresholds": [2, 4], "effects": [ {"armor": 30, "mr": 30}, {"armor": 70, "mr": 70} ], "targets": "TRAIT", "type": "STAT_BOOST"},
     "Steamcraft": { "description": "Steamcraft units gain Attack Speed.", "thresholds": [2, 3], "effects": [ {"as_percent": 20}, {"as_percent": 40} ], "targets": "TRAIT", "type": "STAT_BOOST"},
     "Defender": { "description": "All allies gain Armor.", "thresholds": [2, 4], "effects": [ {"armor": 25}, {"armor": 60} ], "targets": "ALL_ALLIES", "type": "STAT_BOOST"},
      "Brawler": { "description": "Brawlers gain Health.", "thresholds": [2, 4], "effects": [ {"hp": 250}, {"hp": 600} ], "targets": "TRAIT", "type": "STAT_BOOST"},
       "Arcanist": { "description": "All allies gain AP.", "thresholds": [2, 4], "effects": [{"ap": 20}, {"ap": 50}], "targets": "ALL_ALLIES", "type": "STAT_BOOST" },
        "Mystic": { "description": "All allies gain MR.", "thresholds": [2, 4], "effects": [{"mr": 40}, {"mr": 100}], "targets": "ALL_ALLIES", "type": "STAT_BOOST" }, 
      "Noble": { "description": "Gain Armor/MR and heal on hit.", "thresholds": [1, 3], 
                "effects": [{"armor": 25, "mr": 25, "heal_on_hit": 10, "units": 1}, 
                            {"armor": 25, "mr": 25, "heal_on_hit": 10, "units": 99}], 
                "targets": "RANDOM_ALLIES", "type": "ABILITY" }, 
      "Scavenger": { "description": "Scavengers find gold.", "thresholds": [2], "effects": [{"gold_chance": 0.2, "gold": 1}], "targets": "TRAIT", "type": "ECONOMY" },
      "Vermin": { "description": "Enemy units.", "thresholds": [1], "effects": [{}], "targets": "TRAIT", "type": "STAT_BOOST" },
      "Boss": { "description": "Boss unit.", "thresholds": [1], "effects": [{"hp": 500, "ad": 20}], "targets": "TRAIT", "type": "STAT_BOOST" },
}

ENEMY_TEAM_DEFINITIONS: Dict[str, List[Dict[str, Any]]] = {
     "EASY_1": [{"name": "Rust Bug", "level": 1}, {"name": "Rust Bug", "level": 1}],
     "EASY_2": [{"name": "Rust Bug", "level": 1}, {"name": "Gremlin", "level": 1}, {"name": "Rust Bug", "level": 1}],
      "MEDIUM_1": [{"name": "Rust Bug", "level": 2}, {"name": "Gremlin", "level": 1}, {"name": "Clockwork Soldier", "level": 1}],
       "MEDIUM_2": [{"name": "Clockwork Soldier", "level": 1}, {"name": "Boiler Bot", "level": 1},{"name": "Steam Knight", "level": 1}, {"name": "Gremlin", "level": 2} ],
        "HARD_1": [{"name": "Clockwork Soldier", "level": 2}, {"name": "Steam Knight", "level": 2},{"name": "Piston Puncher", "level": 1}, {"name": "Cogsworth", "level": 1}],
       "BOSS_1": [{"name": "Big Bad Bot", "level": 1}, {"name": "Rust Bug", "level": 2}, {"name": "Gremlin", "level": 2}, {"name": "Clockwork Soldier", "level": 2}], 
        "BOSS_2": [{"name": "War Bot", "level": 1}, {"name": "Golem", "level": 1}, {"name": "Gremlin", "level": 2}],
}

ITEM_DEFINITIONS: Dict[str, Dict[str, Any]] = {
    # Components
    "Gear": {"type": "COMPONENT", "stats": {"ad": 10}, "ability": None, "description": "+10 AD"},
    "Plate": {"type": "COMPONENT", "stats": {"armor": 15}, "ability": None, "description": "+15 Armor"},
    "Lubricant": {"type": "COMPONENT", "stats": {"hp": 150}, "ability": None, "description": "+150 Health"},
     "Amp Coil": {"type": "COMPONENT", "stats": {"ap": 15}, 
                   # FIX-UI: Added effect to allow unit Trigger to fire, for Tooltip demo
                   "ability": {"name": "Spark", "effect_type": AbilityEffect.DEAL_DAMAGE, 
                               "effect_data": {"damage_type": DamageType.MAGIC, "scale_factor": 1.0, "flat_value": 0}},
                  "description": "+15 AP. Ability: Spark (Deal 100% Base Value as Magic DMG)"},
     "Essence":  {"type": "COMPONENT", "stats": {"mr": 15}, 
                   # FIX-UI: Added effect to allow unit Trigger to fire, for Tooltip demo
                   "ability": {"name": "Restoration", "effect_type": AbilityEffect.HEAL, 
                               "effect_data": {"scale_factor": 1.0, "flat_value": 0}},
                  "description": "+15 MR. Ability: Restoration (Heal 100% Base Value)"},
    # Combined
     "Zap Blade": {"type": "COMBINED", "stats": {"ad": 15, "ap": 20}, # Gear + Amp Coil 
                    "ability": {"name": "Overcharge", "effect_type": AbilityEffect.DEAL_DAMAGE, 
                                "effect_data": {"damage_type": DamageType.MAGIC, "scale_factor": 5.0, "flat_value": 0}}, 
                   "description": "+15AD,+20AP. Ability: Overcharge (Deal 500% Base Value as Magic DMG)"},
     "Fireball": {"type": "COMBINED", "stats": {"ap": 40}, # Amp Coil + Amp Coil
                   "ability": {"name": "Fireball", "effect_type": AbilityEffect.DEAL_DAMAGE, 
                               "effect_data": {"damage_type": DamageType.MAGIC, "scale_factor": 0, "flat_value": 180}},
                  "description": "+40AP. Ability: Fireball (Deal 180 flat Magic DMG)"},
     "SwordPlate": {"type": "COMBINED", "stats": {"ad": 10, "armor": 20}, # Gear + Plate
                   "ability": {"name": "Rend", "effect_type": AbilityEffect.APPLY_BUFF, 
                               "effect_data": {"stat": "armor", "value": -15, "duration": 4.0, "is_percent": False}},
                  "description": "+10AD,+20Armor. Ability: Rend (-15 Armor for 4s)"},
      "Bulwark": {"type": "COMBINED", "stats": {"armor": 20, "hp": 200}, # Plate + Lubricant
                    # FIX-UI: Added effect to allow unit Trigger to fire, for Tooltip demo
                   "ability": {"name": "Fortify", "effect_type": AbilityEffect.APPLY_BUFF, 
                               "effect_data": {"stat": "armor", "value": 40, "duration": 5.0, "is_percent": False}},
                  "description": "+20Ar,+200HP. Ability: Fortify (+40 Armor for 5s)"},
        "Oil Can": {"type": "COMBINED", "stats": {"hp": 200, "ap": 20}, # Lubricant + Amp Coil
                   "ability": {"name": "Mend", "effect_type": AbilityEffect.HEAL, 
                               "effect_data": {"scale_factor": 1.5, "flat_value": 20}},
                  "description": "+200HP,+20AP. Ability: Mend (Heal 150% Base Value + 20)"},
       "Time Orb": {"type": "COMBINED", "stats": {"ap": 20, "mr": 20}, # Amp Coil + Essence
                   "ability": {"name": "Slow", "effect_type": AbilityEffect.APPLY_BUFF, 
                               "effect_data": {"stat": "as", "value": -30, "duration": 3.0, "is_percent": True}},
                  "description": "+20AP,+20MR. Ability: Slow (-30% AS for 3s)"},
       "Aegis Shield":{"type": "COMBINED", "stats": {"armor": 20, "mr": 20}, # Plate + Essence
                   "ability": {"name": "Barrier", "effect_type": AbilityEffect.APPLY_BUFF, 
                               "effect_data": {"stat": "mr", "value": 40, "duration": 5.0, "is_percent": False}},
                  "description": "+20Ar,+20MR. Ability: Barrier (+40 MR for 5s)"},
        "Life Gem": {"type": "COMBINED", "stats": {"hp": 200, "mr": 20}, # Lubricant + Essence
                   "ability": {"name": "Greater Mend", "effect_type": AbilityEffect.HEAL, 
                               "effect_data": {"scale_factor": 2.0, "flat_value": 50}},
                  "description": "+200HP,+20MR. Ability: Greater Mend (Heal 200% Base Value + 50)"},
}
ITEM_RECIPES: Dict[Tuple[str, str], str] = { 
     ("Gear", "Amp Coil"): "Zap Blade", ("Amp Coil", "Gear"): "Zap Blade",
      ("Amp Coil", "Amp Coil"): "Fireball",
     ("Gear", "Plate"): "SwordPlate", ("Plate", "Gear"): "SwordPlate",
      ("Plate", "Lubricant"): "Bulwark", ("Lubricant", "Plate"): "Bulwark",
       ("Lubricant", "Amp Coil"): "Oil Can", ("Amp Coil", "Lubricant"): "Oil Can",
     ("Amp Coil", "Essence"): "Time Orb", ("Essence", "Amp Coil"): "Time Orb",
     ("Plate", "Essence"): "Aegis Shield", ("Essence", "Plate"): "Aegis Shield",
      ("Lubricant", "Essence"): "Life Gem", ("Essence", "Lubricant"): "Life Gem",
}

# FIX-UI: Add used_in_run flag to definition
ARTIFACT_DEFINITIONS: Dict[str, Dict[str, Any]] = {
     "Reinforced Plating": {"type": "GLOBAL_STAT_BUFF", "stats": {"armor": 10}, "description": "All allies gain +10 Armor.", "one_shot": False},
     "Victory Spoils": {"type": "GOLD_ON_WIN", "value": 2, "description": "+2 Gold on combat victory.", "one_shot": False},
      "Hasty Clock": {"type": "GLOBAL_STAT_BUFF", "stats": {"as_percent": 10}, "description": "All allies gain +10% AS.", "one_shot": False},
       "Knowledge Tome": {"type": "XP_GRANT", "value": 8, "description": "Gain 8 XP immediately.", "one_shot": True},
        "Lucky Coin": {"type": "GOLD_GRANT", "value": 10, "description": "Gain 10 Gold immediately.", "one_shot": True},
     "Spare Gear": {"type": "ITEM_GRANT", "item": "Gear", "description": "Gain 1 Gear component.", "one_shot": True},
      "Spare Coil": {"type": "ITEM_GRANT", "item": "Amp Coil", "description": "Gain 1 Amp Coil component.", "one_shot": True},
       "Spare Essence": {"type": "ITEM_GRANT", "item": "Essence", "description": "Gain 1 Essence component.", "one_shot": True},
}

POSSIBLE_EVENT_ITEMS: List[str] = ["Gear", "Plate", "Lubricant", "Amp Coil", "Essence"]
POSSIBLE_EVENT_ARTIFACTS: List[str] = list(ARTIFACT_DEFINITIONS.keys())

NODE_REWARDS: Dict[str, Dict[str, Any]] = { 
     'COMBAT_EASY': {'gold': 3, 'xp': 0, 'items': [], 'artifacts': []},
     'COMBAT_MEDIUM': {'gold': 5, 'xp': 0, 'items': ["Gear"], 'artifacts': []},
      'COMBAT_HARD': {'gold': 7, 'xp': 1, 'items': ["Plate", "Gear"], 'artifacts': ["Reinforced Plating"]},
      'BOSS': {'gold': 10, 'xp': 2, 'items': ["Amp Coil", "Plate", "Essence"], 'artifacts': ["Reinforced Plating", "Hasty Clock"]}, 
     'SHOP': {'gold': 5, 'xp': 0, 'items': [], 'artifacts': []}, 
     'EVENT': {'gold': 0, 'xp': 0, 'items': [], 'artifacts': []}, 
}
