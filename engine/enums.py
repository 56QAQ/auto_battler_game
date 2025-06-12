# engine/enums.py
from enum import Enum, auto
# Enums specific to engine logic (animation, effects)

class AnimationState(Enum):
    IDLE = auto()
    ATTACKING = auto()
    HIT = auto()
    HEALED = auto()
    CASTING = auto()
    DYING = auto()

class EffectType(Enum):
    PROJECTILE_BASIC = auto()
    PROJECTILE_MAGIC = auto()
    SLASH = auto()
    HIT_SPARK = auto()
    HEAL_AURA = auto()
    BUFF_AURA = auto()
    CAST_AURA = auto()
    DEATH_EFFECT = auto()