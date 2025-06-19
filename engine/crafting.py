#engine/crafting.py

from __future__ import annotations

import random
from typing import Dict

from data.constants import CRAFT_RARITY_BREAKPOINTS, DISMANTLE_REFUND_RATIO

from data.definitions import DiskAbilityRegistry
from data.enums import Color, ItemType
from engine.classes import Item
# ------------------------------------------------------------ #
#                   Disk ability templates                     #
# ------------------------------------------------------------ #
# ------------------------------------------------------------ #
#                Armament stat tables and mappings             #
# ------------------------------------------------------------ #

STAT_BY_COLOR = {
    Color.RED: "ad",
    Color.GREEN: "as_percent",
    Color.BLUE: "ap",
    Color.YELLOW: "hp",
    Color.PURPLE: "armor",
    Color.CYAN: "mr",
    Color.BLACK: "hp",
}

STAT_PREFIX = {
    "ad": "AD",
    "as_percent": "AS",
    "ap": "AP",
    "hp": "HP",
    "armor": "Armor",
    "mr": "MR",
}

RARITY_TO_MK = {
    "COMMON": 1,
    "UNCOMMON": 2,
    "RARE": 3,
    "EPIC": 4,
    "LEGENDARY": 5,
}

STAT_VALUES = {
    "ad": {
        "COMMON": 10,
        "UNCOMMON": 20,
        "RARE": 30,
        "EPIC": 45,
        "LEGENDARY": 60,
    },
    "ap": {
        "COMMON": 15,
        "UNCOMMON": 30,
        "RARE": 45,
        "EPIC": 60,
        "LEGENDARY": 80,
    },
    "as_percent": {
        "COMMON": 10,
        "UNCOMMON": 20,
        "RARE": 30,
        "EPIC": 40,
        "LEGENDARY": 50,
    },
    "hp": {
        "COMMON": 150,
        "UNCOMMON": 300,
        "RARE": 450,
        "EPIC": 600,
        "LEGENDARY": 800,
    },
    "armor": {
        "COMMON": 15,
        "UNCOMMON": 30,
        "RARE": 45,
        "EPIC": 60,
        "LEGENDARY": 80,
    },
    "mr": {
        "COMMON": 15,
        "UNCOMMON": 30,
        "RARE": 45,
        "EPIC": 60,
        "LEGENDARY": 80,
    },
}

__all__ = ["craft", "dismantle", "can_craft", "DiskAbilityRegistry"]

# ------------------------------------------------------------ #
#                 internal helper  (color math)                #
# ------------------------------------------------------------ #

def _infer_color(r: int, g: int, b: int) -> Color:
    comps = [c for c, n in zip([Color.RED, Color.GREEN, Color.BLUE], [r, g, b]) if n]
    print(r)
    print(g)
    print(b)
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
    color = _infer_color(r, g, b)

    name = f"{item_type.value}_{rarity}_{color.value}"

    # ---- very light placeholder stats ---- #
    stats = {}
    ability = None
    if item_type == ItemType.ARMAMENT:
        stat_key = STAT_BY_COLOR.get(color, "ad")
        mk = RARITY_TO_MK[rarity]
        name = f"{STAT_PREFIX[stat_key]} MK{mk}"
        stats = {stat_key: STAT_VALUES[stat_key][rarity]}
    elif item_type == ItemType.DISK:
        stats = {
            "ap": 10
            + 10
            * ("UNCOMMON RARE EPIC".split().index(rarity) if rarity != "COMMON" else 0)
        }
        variants = DiskAbilityRegistry.get(color, {}).get(rarity, [])
        if variants:
            chosen = random.choice(variants)
            ability = chosen.get("ability")
            stats.update(chosen.get("stats", {}))
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
