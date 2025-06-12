from enum import Enum, auto

class TriggerTiming(Enum):
    ON_HIT = auto()
    TIMED = auto()
    START_OF_COMBAT = auto()
    ON_TAKE_DAMAGE = auto() 
    ON_DEATH = auto() 
    
class TriggerTarget(Enum):
    ATTACK_TARGET = auto() # Requires event_target
    NEAREST_ENEMY = auto()
    SELF = auto()
    LOWEST_HP_ENEMY = auto() 
    RANDOM_ENEMY = auto() 

class StatSource(Enum):
     AD = 'ad'
     AP = 'ap'
     MAX_HP = 'hp'
     CURRENT_HP = 'current_hp'
     ARMOR = 'armor'
     MR = 'mr'
     AS = 'as'
     FLAT = 'flat'

class AbilityEffect(Enum):
     DEAL_DAMAGE = auto()
     APPLY_BUFF = auto() # or debuff
     HEAL = auto()

class DamageType(Enum):
    PHYSICAL = 'physical'
    MAGIC = 'magic'
    TRUE = 'true'