from enum import Enum, auto


class TriggerTiming(Enum):
    ON_HIT = auto()
    TIMED = auto()
    START_OF_COMBAT = auto()
    ON_TAKE_DAMAGE = auto()
    ON_DEATH = auto()
    ON_MAGIC_DAMAGE = auto()


class TriggerTarget(Enum):
    ATTACK_TARGET = auto()  # Requires event_target
    NEAREST_ENEMY = auto()
    SELF = auto()
    LOWEST_HP_ENEMY = auto()
    RANDOM_ENEMY = auto()


class StatSource(Enum):
    AD = "ad"
    AP = "ap"
    MAX_HP = "hp"
    CURRENT_HP = "current_hp"
    ARMOR = "armor"
    MR = "mr"
    AS = "as"
    FLAT = "flat"


class AbilityEffect(Enum):
    DEAL_DAMAGE = auto()
    APPLY_BUFF = auto()  # or debuff
    HEAL = auto()


class DamageType(Enum):
    PHYSICAL = "physical"
    MAGIC = "magic"
    TRUE = "true"


class DamageSource(Enum):
    BASIC_ATTACK = auto()
    ITEM_ABILITY = auto()
    SYNERGY = auto()
    ARTIFACT = auto()
    MAP_EFFECT = auto()


class Color(Enum):
    RED = "RED"
    GREEN = "GREEN"
    BLUE = "BLUE"
    YELLOW = "YELLOW"  # RED+GREEN
    PURPLE = "PURPLE"  # RED+BLUE
    CYAN = "CYAN"  # BLUE+GREEN
    BLACK = "BLACK"  # RED+GREEN+BLUE
    WHITE = "WHITE"  # wildcard / neutral


class ItemType(Enum):
    ARMAMENT = "ARMAMENT"
    DISK = "DISK"
    MODULE = "MODULE"


class ResourceType(Enum):
    MATERIAL_RED = "MATERIAL_RED"
    MATERIAL_GREEN = "MATERIAL_GREEN"
    MATERIAL_BLUE = "MATERIAL_BLUE"
    CRYSTAL = "CRYSTAL"