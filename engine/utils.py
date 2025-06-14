# engine/utils.py
import math
from typing import Tuple, Dict, Any, Optional, List
# FIX-UI: Import enums for formatting
from data.enums import TriggerTiming, TriggerTarget, StatSource, AbilityEffect, DamageType
#from engine.classes import Item # FIX-UI

def lerp(a: float, b: float, t: float) -> float:
    return a + (b - a) * t

def lerp_color(color1: Tuple, color2: Tuple, t: float) -> Tuple[int, int, int]:
     # Needs clamp because lerp itself doesn't guarantee 0-255 range if t is outside 0-1
     return (int(clamp(lerp(color1[0], color2[0], t), 0, 255)),
             int(clamp(lerp(color1[1], color2[1], t), 0, 255)),
             int(clamp(lerp(color1[2], color2[2], t), 0, 255)))
             
def clamp(value, min_val, max_val):
     return max(min_val, min(value, max_val))

def normalize_vector(dx: float, dy: float, dist: float) -> Tuple[float, float, float]:
    if dist == 0: return 0.0, 0.0, 0.1 # avoid div zero
    return dx / dist, dy / dist, dist

# FIX-UI: New function for tooltips
def format_trigger_description(trigger: Optional[Dict], items) -> str:
    if not trigger: return "Passive"
    
    timing_map = {
        TriggerTiming.ON_HIT: "On Hit:",
        TriggerTiming.TIMED: f"Every {trigger.get('timing_data', {}).get('interval', '?')}s:",
        TriggerTiming.START_OF_COMBAT: "Start of Combat:",
        TriggerTiming.ON_TAKE_DAMAGE: "On Take Damage:",
        TriggerTiming.ON_DEATH: "On Death:",
    }
    target_map = {
       TriggerTarget.ATTACK_TARGET: "Target ->",
       TriggerTarget.NEAREST_ENEMY: "Nearest Enemy ->",
       TriggerTarget.SELF: "Self ->",
       TriggerTarget.LOWEST_HP_ENEMY: "Lowest HP Enemy ->",
       TriggerTarget.RANDOM_ENEMY: "Random Enemy ->",
    }
    source_map = {
        StatSource.AD: "AD", StatSource.AP: "AP", StatSource.MAX_HP: "MaxHP",
        StatSource.CURRENT_HP: "CurHP", StatSource.ARMOR: "Armor", StatSource.MR: "MR",
         StatSource.AS: "AS", StatSource.FLAT: "Flat"
    }

    timing_str = timing_map.get(trigger.get('timing_type'), "?:")
    target_str = target_map.get(trigger.get('target_type'), "? ->")
    source = trigger.get('base_value_source', StatSource.FLAT)
    source_str = source_map.get(source, "?")
    multiplier = trigger.get('base_value_multiplier', 0)
    flat_base = trigger.get('base_value_flat', 0)
    
    base_value_desc = ""
    if source == StatSource.FLAT:
         base_value_desc = f"{flat_base:.0f}"
    elif multiplier > 0 and flat_base > 0:
         base_value_desc = f"({multiplier*100:.0f}% {source_str} + {flat_base:.0f})"
    elif multiplier > 0:
        base_value_desc = f"{multiplier*100:.0f}% {source_str}"
    elif flat_base > 0:
         base_value_desc = f"{flat_base:.0f}"
    else:
        base_value_desc = "0"

    # Find an item with an ability to describe the effect
    effect_desc = "No Item Ability"
    items_with_abilities = [item for item in items if item and item.ability]
    if items_with_abilities:
        ability = items_with_abilities[0].ability # Just describe the first one
        data = ability.get('effect_data', {})
        scale = data.get('scale_factor', 0)
        flat_effect = data.get('flat_value', 0)
        
        effect_val_desc = ""
        if scale > 0 and flat_effect > 0:
            effect_val_desc = f"{scale*100:.0f}% Base + {flat_effect:.0f}"
        elif scale > 0 :
             effect_val_desc = f"{scale*100:.0f}% Base"
        elif flat_effect > 0:
            effect_val_desc = f"{flat_effect:.0f}"
        else: # e.g. for buffs
             effect_val_desc = ""

        if ability.get('effect_type') == AbilityEffect.DEAL_DAMAGE:
             dtype = data.get('damage_type', DamageType.TRUE)
             effect_desc = f"Deal {effect_val_desc} {dtype.value.capitalize()} Dmg"
        elif ability.get('effect_type') == AbilityEffect.HEAL:
             effect_desc = f"Heal {effect_val_desc}"
        elif ability.get('effect_type') == AbilityEffect.APPLY_BUFF:
             stat = data.get('stat', '?')
             val = data.get('value', 0)
             dur = data.get('duration','?')
             is_pct = data.get('is_percent', False)
             val_str = f"{val:+}%" if is_pct else f"{val:+}"
             effect_desc = f"Apply {val_str} {stat.upper()} for {dur}s"
             
    full_desc = f"{timing_str} {target_str}\n  Base: {base_value_desc}\n  Effect: {effect_desc}"
    # Basic fallback
    if not items_with_abilities:
         full_desc = f"{timing_str} {target_str} {base_value_desc} (Base)"

    return full_desc