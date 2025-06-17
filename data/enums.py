from enum import Enum, auto


class TriggerTiming(Enum):
    ON_HIT = auto()
    TIMED = auto()
    START_OF_COMBAT = auto()
    ON_TAKE_DAMAGE = auto()
    ON_DEATH = auto()
    ON_MAGIC_DAMAGE = auto()
    ON_PHYSICAL_DAMAGE = auto()
    ON_DAMAGE = auto()
    ON_DAMAGE_TAKEN = auto()
    ON_HEAL = auto()
    ON_HEALED = auto()
    ON_SHIELD_BROKEN = auto()
    ON_ANY_DEATH = auto()
    ON_AOE_DAMAGE = auto()
    ON_DOT_DAMAGE = auto()
    ON_ALLY_HIT = auto()
    ON_BONDED_DEATH = auto()
class TriggerTarget(Enum):
    ATTACK_TARGET = auto()  # Requires event_target
    NEAREST_ENEMY = auto()
    NEAREST_ALLY = auto()
    SELF = auto()
    LOWEST_HP_ENEMY = auto()
    LOWEST_HP_ALLY = auto()
    LOWEST_HP_ALLY_ADJACENT = auto()
    RANDOM_NEGATIVE_ALLY = auto()
    RANDOM_ENEMY = auto()
    EVENT_TARGETS = auto()
    ALL_NEGATIVE_ENEMIES = auto()

class StatSource(Enum):
    AD = "ad"
    AP = "ap"
    MAX_HP = "hp"
    CURRENT_HP = "current_hp"
    ARMOR = "armor"
    MR = "mr"
    AS = "as"
    FLAT = "flat"
    EVENT = "event"

class AbilityEffect(Enum):
    DEAL_DAMAGE = auto()
    APPLY_BUFF = auto()  # or debuff
    HEAL = auto()
    APPLY_DOT = auto()

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