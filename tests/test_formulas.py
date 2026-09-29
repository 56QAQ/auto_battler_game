"""Damage formula layers against hand-computed values."""

import pytest

from hsrsim import formulas as F
from hsrsim.enums import Element


def test_enemy_def_and_def_multiplier():
    assert F.enemy_base_def(95) == 1150
    # level 80 attacker vs level 95 enemy, no reduction: 1000 / (1150 + 1000)
    assert F.def_multiplier(80, 1150) == pytest.approx(1000 / 2150)
    # 40% DEF reduction + 20% DEF ignore -> DEF 1150 * 0.4 = 460
    assert F.def_multiplier(80, 1150, def_reduction=0.4, def_ignore=0.2) == pytest.approx(1000 / 1460)
    # DEF can not go below zero
    assert F.def_multiplier(80, 1150, def_reduction=1.5) == pytest.approx(1.0)


def test_res_multiplier_clamps():
    assert F.res_multiplier(0.2) == pytest.approx(0.8)
    assert F.res_multiplier(0.0, res_pen=0.25) == pytest.approx(1.25)
    assert F.res_multiplier(-0.5, res_pen=0.8) == pytest.approx(2.0)  # floor at -100% RES
    assert F.res_multiplier(1.0) == pytest.approx(0.1)  # cap at 90% RES


def test_vulnerability_cap():
    assert F.vuln_multiplier(0.3) == pytest.approx(1.3)
    assert F.vuln_multiplier(4.0) == pytest.approx(3.5)


def test_mitigation_and_final_dmg_multiply():
    assert F.mitigation_multiplier([0.1, 0.2]) == pytest.approx(0.72)
    assert F.final_dmg_multiplier([0.1, 0.2]) == pytest.approx(1.32)


def test_crit_expected():
    assert F.crit_multiplier_expected(0.5, 1.0) == pytest.approx(1.5)
    assert F.crit_multiplier_expected(1.4, 1.0) == pytest.approx(2.0)  # CRIT Rate capped at 100%


def test_break_base_and_toughness_multiplier():
    # display toughness 240 (data 720) -> 0.5 + 240/40 = 6.5
    assert F.toughness_multiplier(240) == pytest.approx(6.5)
    lvl80 = 3767.5535
    assert F.break_base_damage(Element.PHYSICAL, lvl80, 240) == pytest.approx(2 * lvl80 * 6.5)
    assert F.break_base_damage(Element.QUANTUM, lvl80, 240) == pytest.approx(0.5 * lvl80 * 6.5)
    # 20 display toughness reduced -> 2 x level multiplier
    assert F.super_break_base(lvl80, 20) == pytest.approx(2 * lvl80)


def test_cycles():
    assert F.cycle_index(0) == 0
    assert F.cycle_index(149.9) == 0
    assert F.cycle_index(150) == 1
    assert F.cycle_index(249.9) == 1
    assert F.cycle_index(250) == 2


def test_effect_hit_chance():
    assert F.effect_hit_chance(1.0, 0.0, 0.3) == pytest.approx(0.7)
    assert F.effect_hit_chance(1.0, 0.43, 0.3) == pytest.approx(1.001)
    assert F.effect_hit_chance(1.5, 0.0, 0.4, debuff_res=0.75) == pytest.approx(1.5 * 0.6 * 0.25)
