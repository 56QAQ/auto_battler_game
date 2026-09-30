"""Enumerations shared across the simulator.

Enum values use the identifiers found in the datamined client tables so data
records can be converted with ``Element(record["element"])`` directly.
"""

from __future__ import annotations

from enum import Enum


class Element(str, Enum):
    PHYSICAL = "Physical"
    FIRE = "Fire"
    ICE = "Ice"
    LIGHTNING = "Thunder"
    WIND = "Wind"
    QUANTUM = "Quantum"
    IMAGINARY = "Imaginary"

    @property
    def cn(self) -> str:
        return _ELEMENT_CN[self]


_ELEMENT_CN = {
    Element.PHYSICAL: "物理",
    Element.FIRE: "火",
    Element.ICE: "冰",
    Element.LIGHTNING: "雷",
    Element.WIND: "风",
    Element.QUANTUM: "量子",
    Element.IMAGINARY: "虚数",
}


class Path(str, Enum):
    DESTRUCTION = "Warrior"
    HUNT = "Rogue"
    ERUDITION = "Mage"
    HARMONY = "Shaman"
    NIHILITY = "Warlock"
    PRESERVATION = "Knight"
    ABUNDANCE = "Priest"
    REMEMBRANCE = "Memory"
    ELATION = "Elation"


class Side(str, Enum):
    ALLY = "ally"
    ENEMY = "enemy"


class ActionKind(str, Enum):
    """What kind of action an entity is taking (drives SP/energy bookkeeping)."""

    BASIC = "basic"
    SKILL = "skill"
    ULT = "ult"
    FUA = "fua"  # follow-up attack / counter
    MEMOSPRITE = "memosprite"  # memosprite / summon turn or skill
    ELATION = "elation"  # Elation Skill (during an Aha Instant)
    EXTRA = "extra"  # anything else inserted (e.g. talent triggered actions)
    ENEMY = "enemy"


class DmgTag:
    """Damage type tags. A hit may carry several (e.g. a follow-up that counts as ultimate DMG).

    Tags double as stat qualifiers: ``dmg%:ult`` boosts every hit tagged ``ult``.
    """

    BASIC = "basic"
    SKILL = "skill"
    ULT = "ult"
    FUA = "fua"
    DOT = "dot"
    BREAK = "break"
    SUPER_BREAK = "super_break"
    ADDITIONAL = "additional"
    MEMOSPRITE = "memosprite"
    ELATION = "elation"
    TRUE = "true"
    ENEMY = "enemy"


class EnemyRank(str, Enum):
    NORMAL = "normal"
    ELITE = "elite"
    BOSS = "boss"
