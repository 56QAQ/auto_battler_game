# data/constants.py
import math
from typing import Dict, List

# Game Logic Constants
_DEPRECATED_STARTING_GOLD = 0
STARTING_MATERIALS = {"RED": 10, "GREEN": 10, "BLUE": 10}
STARTING_CRYSTAL = 200
REFRESH_CRYSTAL_COST = 1
XP_BUY_CRYSTAL_COST = 2
DISMANTLE_REFUND_RATIO = 0.5
CRAFT_RARITY_BREAKPOINTS = {1: "COMMON", 3: "UNCOMMON", 5: "RARE", 8: "EPIC"}
COST_BY_RARITY_MATERIALS = {"COMMON": 1, "UNCOMMON": 2, "RARE": 4, "EPIC": 6}
STARTING_HEALTH = 100
MAX_LEVEL = 9
XP_PER_LEVEL = [0, 2, 2, 6, 10, 20, 36, 56, 80]  # Adjusted XP
XP_BUY_COST = 4
XP_BUY_AMOUNT = 4
PASSIVE_XP = 2
REFRESH_COST = 2


def MAX_UNITS_ON_BOARD(level: int) -> int:
    """Return max units allowed on board for the given level."""
    return level


DEFAULT_MOVE_SPEED = 100
UNIT_POOL_SIZE_MULTIPLIER: Dict[str, int] = {
    "COMMON": 29,
    "UNCOMMON": 22,
    "RARE": 16,
    "EPIC": 10,
    "LEGENDARY": 5,
}
LEVEL_PROBABILITIES: Dict[int, List[float]] = {
    1: [1.00, 0.00, 0.00, 0.00, 0.00],
    2: [1.00, 0.00, 0.00, 0.00, 0.00],
    3: [0.75, 0.25, 0.00, 0.00, 0.00],
    4: [0.55, 0.30, 0.15, 0.00, 0.00],
    5: [0.45, 0.33, 0.20, 0.02, 0.00],
    6: [0.25, 0.40, 0.30, 0.05, 0.00],
    7: [0.19, 0.30, 0.35, 0.15, 0.01],
    8: [0.16, 0.20, 0.35, 0.25, 0.04],
    9: [0.09, 0.15, 0.30, 0.30, 0.16],
}
RARITY_COST: Dict[str, int] = {
    "COMMON": 1,
    "UNCOMMON": 2,
    "RARE": 3,
    "EPIC": 4,
    "LEGENDARY": 5,
}
RARITY_ORDER: List[str] = ["COMMON", "UNCOMMON", "RARE", "EPIC", "LEGENDARY"]

MAX_ITEMS_EQUIPPED = 3
MAX_COMBINED_ITEMS = 1

# Default probabilities for disk ability resolution outcomes
# These control the chance of a disk ability failing, succeeding or
# achieving a great success when the ability specifies outcome based
# resolution mechanics.
DISK_OUTCOME_DEFAULT_PROBS = {"fail": 0.1, "success": 0.8, "great": 0.1}

# Combat timing / balance
MAX_COMBAT_DURATION = 30  # seconds
OVERTIME_START = MAX_COMBAT_DURATION
OVERTIME_DAMAGE_INTERVAL = 1.0
OVERTIME_DAMAGE_PERCENT = 0.05
MELEE_RANGE_THRESHOLD = 70
PROJECTILE_SPEED = 400.0

# Animation Timing (Belongs to engine/UI but defined here for balance)
ATTACK_ANIM_DURATION = 0.25
HIT_ANIM_DURATION = 0.2
HEAL_ANIM_DURATION = 0.3
CAST_ANIM_DURATION = 0.3
DEATH_ANIM_DURATION = 0.5
IDLE_WOBBLE_SPEED = 3.0
IDLE_WOBBLE_ANGLE = math.radians(5)
ATTACK_LUNGE_ANGLE = math.radians(25)
HIT_RECOIL_ANGLE = math.radians(-10)
FLOATER_LIFESPAN = 0.8
FLOATER_SPEED = 30.0  # pixels/sec

# Map Generation
MAP_DEPTH = 7
NODES_PER_LAYER: List[int] = [1, 3, 4, 4, 3, 2, 1]
MAP_NODE_TYPES: List[str] = [
    "COMBAT_EASY",
    "COMBAT_MEDIUM",
    "COMBAT_HARD",
    "SHOP",
    "EVENT",
    "BOSS",
]
NODE_TYPE_DISTRIBUTION: Dict[str, float] = {
    "COMBAT_EASY": 0.3,
    "COMBAT_MEDIUM": 0.25,
    "COMBAT_HARD": 0.1,
    "SHOP": 0.15,
    "EVENT": 0.2,
    "BOSS": 0.0,
}
NODE_REWARDS: List[str] = ["BOSS_1", "BOSS_2"]
BOSS_NODES: List[str] = ["BOSS_1", "BOSS_2"]
MEDIUM_NODES: List[str] = ["MEDIUM_1", "MEDIUM_2"]
HARD_NODES: List[str] = ["HARD_1"]


try:
    import importlib
    import sys

    ui_consts = importlib.import_module("ui.constants")
    # 把 ui.constants 中非私有（非以下划线开头）的名字写进当前模块命名空间
    for _k, _v in vars(ui_consts).items():
        if not _k.startswith("_"):
            globals()[_k] = _v

    # 可选：让任何直接 `import ui.constants` 的模块也能看到 data 的常量
    # 把自己注册到 sys.modules，使得后续 import ui.constants
    # 返回的其实是已合并后的对象
    sys.modules.setdefault("ui.constants", sys.modules[__name__])

except ModuleNotFoundError:
    # 如果项目里根本没有 ui.constants，就什么也不做
    pass
