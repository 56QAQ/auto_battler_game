"""Stat keys and conversion from datamine property names.

Stats are plain string keys summed additively. A key may carry a qualifier after
``:`` which restricts it to hits whose element or damage tags match, e.g.

* ``dmg%``           all-type DMG boost
* ``dmg%:Fire``      Fire DMG boost
* ``dmg%:ult``       Ultimate DMG boost
* ``crit_dmg:fua``   CRIT DMG for follow-up attacks only
* ``vuln:break``     (on the target) Break DMG taken

Attacker-side keys: ``dmg% crit_rate crit_dmg def_ignore res_pen weaken
break_effect break_eff break_dmg% super_break_dmg%``.
Target-side keys: ``vuln def_reduction res_reduction mitigation res``.
``mitigation`` stacks multiplicatively (each contribution is one factor).
"""

from __future__ import annotations

from .enums import Element

# ----------------------------------------------------------------- base stats
BASE_HP = "base_hp"
BASE_ATK = "base_atk"
BASE_DEF = "base_def"
BASE_SPD = "base_spd"
HP_PCT = "hp%"
ATK_PCT = "atk%"
DEF_PCT = "def%"
SPD_PCT = "spd%"
HP_FLAT = "hp_flat"
ATK_FLAT = "atk_flat"
DEF_FLAT = "def_flat"
SPD_FLAT = "spd_flat"

CRIT_RATE = "crit_rate"
CRIT_DMG = "crit_dmg"
BREAK_EFFECT = "break_effect"
ERR = "err"  # energy regeneration rate (bonus part, 0 = 100%)
EHR = "ehr"  # effect hit rate
EFFECT_RES = "effect_res"
HEAL_PCT = "heal%"
HEAL_TAKEN = "heal_taken%"
AGGRO = "aggro"
AGGRO_PCT = "aggro%"

# ------------------------------------------------------------ damage (attacker)
DMG_PCT = "dmg%"
DEF_IGNORE = "def_ignore"
RES_PEN = "res_pen"
WEAKEN = "weaken"
BREAK_EFF = "break_eff"  # Weakness Break Efficiency
BREAK_DMG_PCT = "break_dmg%"  # "Break DMG dealt increases by X%"
SUPER_BREAK_DMG_PCT = "super_break_dmg%"
ELATION_DMG_PCT = "elation%"
MERRYMAKE_PCT = "merrymake%"
FINAL_DMG = "final_dmg"  # multiplicative "final DMG" layer: each source is its own (1 + x) factor
EFFECT_RES_PEN = "effect_res_pen"

# --------------------------------------------------------------- damage (target)
VULN = "vuln"
DEF_REDUCTION = "def_reduction"
RES_REDUCTION = "res_reduction"
MITIGATION = "mitigation"
RES = "res"  # elemental RES of an enemy: "res:Fire"
DEBUFF_RES = "debuff_res"  # e.g. "debuff_res:freeze" (enemy CC RES)

MULTIPLICATIVE_KEYS = frozenset({MITIGATION, FINAL_DMG})

PROPERTY_MAP: dict[str, str] = {
    "HPDelta": HP_FLAT,
    "AttackDelta": ATK_FLAT,
    "DefenceDelta": DEF_FLAT,
    "SpeedDelta": SPD_FLAT,
    "BaseSpeed": BASE_SPD,
    "HPAddedRatio": HP_PCT,
    "AttackAddedRatio": ATK_PCT,
    "DefenceAddedRatio": DEF_PCT,
    "SpeedAddedRatio": SPD_PCT,
    "CriticalChanceBase": CRIT_RATE,
    "CriticalDamageBase": CRIT_DMG,
    "StatusProbabilityBase": EHR,
    "StatusResistanceBase": EFFECT_RES,
    "BreakDamageAddedRatioBase": BREAK_EFFECT,
    "HealRatioBase": HEAL_PCT,
    "HealTakenRatio": HEAL_TAKEN,
    "SPRatioBase": ERR,
    "AllDamageTypeAddedRatio": DMG_PCT,
    "ElationDamageAddedRatioBase": ELATION_DMG_PCT,
    "PhysicalAddedRatio": f"{DMG_PCT}:{Element.PHYSICAL.value}",
    "FireAddedRatio": f"{DMG_PCT}:{Element.FIRE.value}",
    "IceAddedRatio": f"{DMG_PCT}:{Element.ICE.value}",
    "ThunderAddedRatio": f"{DMG_PCT}:{Element.LIGHTNING.value}",
    "WindAddedRatio": f"{DMG_PCT}:{Element.WIND.value}",
    "QuantumAddedRatio": f"{DMG_PCT}:{Element.QUANTUM.value}",
    "ImaginaryAddedRatio": f"{DMG_PCT}:{Element.IMAGINARY.value}",
}

# Friendly aliases accepted in build configs (relic main/sub stats etc.).
ALIASES: dict[str, str] = {
    "hp": HP_FLAT,
    "atk": ATK_FLAT,
    "def": DEF_FLAT,
    "spd": SPD_FLAT,
    "speed": SPD_FLAT,
    "cr": CRIT_RATE,
    "cd": CRIT_DMG,
    "crit rate": CRIT_RATE,
    "crit dmg": CRIT_DMG,
    "be": BREAK_EFFECT,
    "break": BREAK_EFFECT,
    "break effect": BREAK_EFFECT,
    "err": ERR,
    "energy": ERR,
    "ehr": EHR,
    "effect hit": EHR,
    "effect res": EFFECT_RES,
    "res_effect": EFFECT_RES,
    "heal": HEAL_PCT,
    "physical": f"{DMG_PCT}:Physical",
    "fire": f"{DMG_PCT}:Fire",
    "ice": f"{DMG_PCT}:Ice",
    "lightning": f"{DMG_PCT}:Thunder",
    "thunder": f"{DMG_PCT}:Thunder",
    "wind": f"{DMG_PCT}:Wind",
    "quantum": f"{DMG_PCT}:Quantum",
    "imaginary": f"{DMG_PCT}:Imaginary",
    "elemental": "elemental",  # resolved to the wearer's element by the build code
}


def normalize_stat(name: str) -> str:
    """Resolve a user-facing stat name or datamine property name to a stat key."""
    if name in PROPERTY_MAP:
        return PROPERTY_MAP[name]
    low = name.strip().lower().replace("_dmg", "").replace(" dmg", "")
    if name.lower() in ALIASES:
        return ALIASES[name.lower()]
    if low in ALIASES:
        return ALIASES[low]
    return name


def qualified(key: str, qualifiers: frozenset[str] | tuple[str, ...]) -> list[str]:
    """``qualified("dmg%", {"Fire", "ult"})`` -> ``["dmg%", "dmg%:Fire", "dmg%:ult"]``."""
    return [key] + [f"{key}:{q}" for q in qualifiers]
