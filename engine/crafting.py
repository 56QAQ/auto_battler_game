#engine/crafting.py

from __future__ import annotations

import random
from typing import Dict

from data.enums import AbilityEffect, Color, DamageType, ItemType
from data.constants import CRAFT_RARITY_BREAKPOINTS, DISMANTLE_REFUND_RATIO
from engine.classes import Item, Unit

# ------------------------------------------------------------ #
#                   Disk ability templates                     #
# ------------------------------------------------------------ #

DiskAbilityRegistry: dict[Color, dict] = {
    Color.RED: {
        "name": "Power Strike",
        "effect_type": AbilityEffect.DEAL_DAMAGE,
        "effect_data": {
            "damage_type": DamageType.PHYSICAL,
            "scale_factor": 1.5,
            "flat_value": 0,
        },
    },
    Color.GREEN: {
        "name": "Rejuvenation",
        "effect_type": AbilityEffect.HEAL,
        "effect_data": {
            "scale_factor": 1.0,
            "flat_value": 0,
        },
    },
    Color.BLUE: {
        "name": "Arcane Bolt",
        "effect_type": AbilityEffect.DEAL_DAMAGE,
        "effect_data": {
            "damage_type": DamageType.MAGIC,
            "scale_factor": 1.5,
            "flat_value": 0,
        },
    },
    Color.YELLOW: {
        "name": "Fortify",
        "effect_type": AbilityEffect.APPLY_BUFF,
        "effect_data": {
            "stat": "percentage_damage_reduction",
            "value": 20,
            "duration": 3.0,
            "is_percent": False,
        },
    },
    Color.PURPLE: {
        "name": "Void Pulse",
        "effect_type": AbilityEffect.DEAL_DAMAGE,
        "effect_data": {
            "damage_type": DamageType.TRUE,
            "scale_factor": 1.2,
            "flat_value": 0,
        },
    },
    Color.CYAN: {
        "name": "Weakening Beam",
        "effect_type": AbilityEffect.APPLY_BUFF,
        "effect_data": {
            "stat": "ad",
            "value": -10,
            "duration": 4.0,
            "is_percent": False,
        },
    },
    Color.BLACK: {
        "name": "Annihilation",
        "effect_type": AbilityEffect.DEAL_DAMAGE,
        "effect_data": {
            "damage_type": DamageType.TRUE,
            "scale_factor": 2.0,
            "flat_value": 0,
        },
    },
    Color.WHITE: {
        "name": "Inspiration",
        "effect_type": AbilityEffect.APPLY_BUFF,
        "effect_data": {
            "stat": "ap",
            "value": 10,
            "duration": 5.0,
            "is_percent": False,
        },
    },
}

__all__ = ["craft", "dismantle", "can_craft", "DiskAbilityRegistry"]

# ------------------------------------------------------------ #
#                 internal helper  (color math)                #
# ------------------------------------------------------------ #

def _infer_color(r: int, g: int, b: int) -> Color:
    comps = [c for c, n in zip([Color.RED, Color.GREEN, Color.BLUE], [r, g, b]) if n]
    if len(comps) == 1:
        return comps[0]
    if len(comps) == 2:
        if Color.RED in comps and Color.GREEN in comps:
            return Color.YELLOW
        if Color.RED in comps and Color.BLUE in comps:
            return Color.PURPLE
        return Color.CYAN        # BLUE+GREEN
    if len(comps) == 3:
        return Color.BLACK
    return Color.WHITE


def _roll_rarity(total: int) -> str:
    rarity = "COMMON"
    for threshold, name in sorted(CRAFT_RARITY_BREAKPOINTS.items()):
        if total >= threshold:
            rarity = name
    return rarity

# ------------------------------------------------------------ #
#                   public craft / dismantle                   #
# ------------------------------------------------------------ #

def can_craft(materials: Dict[str, int]) -> bool:
    """True iff ≥ 2 材料且至少两格投入 (可同色)。"""
    return sum(materials.values()) >= 2


def craft(item_type: ItemType, materials: Dict[str, int]) -> Item:
    """
    生成一件新 Item，名称采用占位规则：
        <Type>_<Rarity>_<Color>
    真实数值由前端 / 后期数据表驱动。
    """
    if not can_craft(materials):
        raise ValueError("Need at least 1 + 1 materials to craft.")

    total = sum(materials.values())
    rarity = _roll_rarity(total)

    r = materials.get("RED", 0)
    g = materials.get("GREEN", 0)
    b = materials.get("BLUE", 0)
    color = _infer_color(r, g, b) if item_type != ItemType.ARMAMENT else Color.WHITE

    name = f"{item_type.value}_{rarity}_{color.value}"

    # ---- very light placeholder stats ---- #
    stats = {}
    ability = None
    if item_type == ItemType.ARMAMENT:
        stats = {
            "armor": 20
            + 10
            * ("UNCOMMON RARE EPIC".split().index(rarity) if rarity != "COMMON" else 0)
        }
    elif item_type == ItemType.DISK:
        stats = {
            "ap": 10
            + 10
            * ("UNCOMMON RARE EPIC".split().index(rarity) if rarity != "COMMON" else 0)
        }
        ability = DiskAbilityRegistry.get(color)
    elif item_type == ItemType.MODULE:
        stats = {}

    new_item = Item(
        name,
        item_type=item_type,
        color=color,
        rarity=rarity,
        material_cost=total,
        stats_override=stats,
    )
    if ability:
        new_item.ability = ability.copy()
    return new_item

def dismantle(item: Item) -> Dict[str, int]:
    """
    拆解返还 ⌊cost × ratio⌋ 材料，颜色按 Item 颜色返还。
    """
    refund = int(getattr(item, "material_cost", 0) * DISMANTLE_REFUND_RATIO)
    if refund <= 0:
        return {}
    col = getattr(item, "color", Color.WHITE)
    if col == Color.WHITE:
        return {"RED": refund // 3, "GREEN": refund // 3, "BLUE": refund // 3}
    if col == Color.YELLOW:       # R+G
        return {"RED": refund // 2, "GREEN": refund // 2}
    if col == Color.PURPLE:       # R+B
        return {"RED": refund // 2, "BLUE": refund // 2}
    if col == Color.CYAN:         # B+G
        return {"GREEN": refund // 2, "BLUE": refund // 2}
    if col == Color.BLACK:        # RGB
        share = refund // 3
        return {"RED": share, "GREEN": share, "BLUE": share}
    # primary
    return {col.value: refund}

# ------------------------------------------------------------ #
#           helper used by UI (preview probability)            #
# ------------------------------------------------------------ #

def preview_rarity_distribution(total_materials: int) -> Dict[str, float]:
    """
    给 UI 用：投入 N 材料时，各稀有度理论权重（累计区间制）。
    这里只给出简化的阶梯分布 – 真实项目可改为 sigmoid/曲线。
    """
    out = {}
    for th, rar in sorted(CRAFT_RARITY_BREAKPOINTS.items()):
        out[rar] = 1.0 if total_materials >= th else 0.0
    return out
