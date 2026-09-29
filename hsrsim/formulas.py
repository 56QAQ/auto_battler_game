"""Pure damage formulas.

Every function here is side-effect free so it can be unit-tested against
hand-computed values. The battle engine gathers the inputs (stats of attacker
and target, including hit-local modifiers) and calls into this module.

Outgoing DMG = Base DMG x DMG% x DEF x RES x Vulnerability x Mitigation
               x Broken x Weaken x CRIT
"""

from __future__ import annotations

from dataclasses import dataclass

from .enums import Element

# ---------------------------------------------------------------- constants
AV_BASE = 10000.0  # action gauge length; AV = gauge / SPD
RES_MIN_MULT = 0.1  # effective RES is capped at 90% (community; data only shows the floor)
RES_MAX_MULT = 2.0  # ... and at -100% (GameCoreConstValue.OverallResistanceMin = -1)
VULN_MAX = 2.5  # GameCoreConstValue.DamageTakenRatioMax = 3.5 -> 1 + min(vuln, 2.5)
MITIGATION_MAX = 0.99  # AllDamageReduceMax
WEAKEN_MAX = 0.8  # MinimumFatigueRatio = 0.2
NOT_BROKEN_MULT = 0.9  # "Toughness multiplier" while the target still has Toughness
BROKEN_MULT = 1.0

# Base Break DMG multiplier per element.
BREAK_ELEMENT_MULT: dict[Element, float] = {
    Element.PHYSICAL: 2.0,
    Element.FIRE: 2.0,
    Element.WIND: 1.5,
    Element.ICE: 1.0,
    Element.LIGHTNING: 1.0,
    Element.QUANTUM: 0.5,
    Element.IMAGINARY: 0.5,
}

# Break status parameters (per element).
BLEED_MULT = 2.0
BLEED_HP_CAP = {"normal": 0.16, "elite": 0.07, "boss": 0.07}
BURN_MULT = 1.0
SHOCK_MULT = 2.0
WIND_SHEAR_MULT = 1.0
WIND_SHEAR_STACKS = {"normal": 1, "elite": 3, "boss": 3}
WIND_SHEAR_MAX = 5
FREEZE_MULT = 1.0
ENTANGLE_MULT = 0.6
ENTANGLE_MAX = 5
BREAK_DELAY = 0.25
QUANTUM_BREAK_DELAY = 0.20  # x (1 + Break Effect)
IMAGINARY_BREAK_DELAY = 0.30  # x (1 + Break Effect)
IMPRISON_SLOW = 0.10
FREEZE_THAW_ADVANCE = 0.50
TOUGHNESS_DIVISOR = 40.0  # Max-Toughness multiplier = 0.5 + MaxToughness / 40
SUPER_BREAK_DIVISOR = 10.0  # Super Break base = level mult x toughness reduced / 10


def enemy_base_def(level: int) -> float:
    return 200.0 + 10.0 * level


def def_multiplier(
    attacker_level: int,
    target_def: float,
    def_bonus: float = 0.0,
    def_reduction: float = 0.0,
    def_ignore: float = 0.0,
    def_flat: float = 0.0,
) -> float:
    """1 - DEF / (DEF + 200 + 10 x attacker level), DEF after reductions (floored at 0)."""
    effective = max(0.0, target_def * (1.0 + def_bonus - def_reduction - def_ignore) + def_flat)
    k = 200.0 + 10.0 * attacker_level
    return k / (effective + k)


def res_multiplier(res: float, res_pen: float = 0.0, res_reduction: float = 0.0) -> float:
    return min(RES_MAX_MULT, max(RES_MIN_MULT, 1.0 - (res - res_pen - res_reduction)))


def vuln_multiplier(vuln: float) -> float:
    return max(0.0, 1.0 + min(vuln, VULN_MAX))


def mitigation_multiplier(mitigations: list[float]) -> float:
    """Each DMG reduction source is its own factor (1 - r); total reduction capped at 99%."""
    m = 1.0
    for x in mitigations:
        m *= 1.0 - x
    return max(1.0 - MITIGATION_MAX, m)


def final_dmg_multiplier(boosts: list[float]) -> float:
    """ "Final DMG" boosts (e.g. Acheron trace, Castorice E1) multiply with each other."""
    m = 1.0
    for x in boosts:
        m *= 1.0 + x
    return m


def crit_multiplier_expected(crit_rate: float, crit_dmg: float) -> float:
    return 1.0 + min(1.0, max(0.0, crit_rate)) * crit_dmg


def toughness_multiplier(max_toughness: float) -> float:
    return 0.5 + max_toughness / TOUGHNESS_DIVISOR


@dataclass(frozen=True)
class DamageParts:
    """All multiplier layers of one damage instance (useful for debugging/reporting)."""

    base: float
    dmg_boost: float
    def_mult: float
    res_mult: float
    vuln_mult: float
    mitig_mult: float
    broken_mult: float
    weaken_mult: float
    crit_mult: float
    extra_mult: float = 1.0

    @property
    def total(self) -> float:
        return (
            self.base
            * self.dmg_boost
            * self.def_mult
            * self.res_mult
            * self.vuln_mult
            * self.mitig_mult
            * self.broken_mult
            * self.weaken_mult
            * self.crit_mult
            * self.extra_mult
        )

    @property
    def non_crit(self) -> float:
        return self.total / self.crit_mult if self.crit_mult else 0.0


def break_base_damage(element: Element, level_mult: float, max_toughness: float) -> float:
    """Base of the Break DMG dealt at the moment of Weakness Break (before BE and target layers)."""
    return BREAK_ELEMENT_MULT[element] * level_mult * toughness_multiplier(max_toughness)


def super_break_base(level_mult: float, toughness_reduced: float) -> float:
    return level_mult * toughness_reduced / SUPER_BREAK_DIVISOR


def cycle_index(av: float, first: float = 150.0, per: float = 100.0) -> int:
    """0-based cycle containing time ``av`` (MoC: first cycle 150 AV, then 100)."""
    if av < first:
        return 0
    return 1 + int((av - first) // per)


def effect_hit_chance(
    base: float, ehr: float, effect_res: float, debuff_res: float = 0.0, effect_res_pen: float = 0.0
) -> float:
    return base * (1.0 + ehr) * (1.0 - effect_res + effect_res_pen) * (1.0 - debuff_res)
