"""Targeted checks for a few Harmony / Nihility / Preservation light cones."""

import pytest

from hsrsim import stats as S
from hsrsim.battle import Battle
from hsrsim.build import Build, make_character
from hsrsim.entities import Enemy

from .helpers import generic_build


def _battle(builds):
    chars = [make_character(b) for b in builds]
    battle = Battle(chars, [[Enemy("Dummy", effect_res=0.0, hp=1e12)]])
    battle.start()
    return battle, chars


def test_a_grounded_ascent_hymn_energy_and_sp():
    # real Bronya kit: her Skill targets one ally (the first teammate)
    b, (bronya, seele) = _battle([Build("Bronya", light_cone="23034"), generic_build("Seele")])
    lc = bronya.light_cone
    sp0, e0 = b.sp, bronya.energy
    bronya.kit.skill(b.default_target())
    hymn = seele.get_mod("Hymn")
    assert hymn is not None and hymn.stacks == 1
    assert hymn.value(S.DMG_PCT) == pytest.approx(lc.p(1))
    skill_energy = float(bronya.kit.sk("skill")["energy"])
    assert bronya.energy - e0 == pytest.approx((skill_energy + lc.p(0)) * (1 + bronya.stat(S.ERR)))
    bronya.kit.skill(b.default_target())
    assert seele.get_mod("Hymn").stacks == 2
    assert b.sp == sp0 - 2 + 1  # two Skills cost 2 SP, the 2nd use on an ally recovers 1


def test_past_self_in_mirror_team_buff_sp_and_wave_energy():
    b, (bronya, seele) = _battle(
        [generic_build("Bronya", light_cone="23019", extra_stats={"break_effect": 1.0}), generic_build("Seele")]
    )
    lc = bronya.light_cone
    assert seele.energy == pytest.approx(seele.max_energy * b.cfg.start_energy + lc.p(4) * (1 + seele.stat(S.ERR)))
    sp0 = b.sp
    bronya.energy = bronya.max_energy
    bronya.kit.use_ult()
    for c in (bronya, seele):
        assert c.get_mod("Past Self in Mirror").value(S.DMG_PCT) == pytest.approx(lc.p(1))
    assert b.sp == sp0 + 1  # Break Effect >= 150%


def test_lies_dance_on_the_breeze_def_shred():
    # Kafka base SPD 100 * 1.18 + 60 >= 170 -> Theft on top of Bamboozle
    b, (kafka, _) = _battle(
        [generic_build("Kafka", light_cone="23043", extra_stats={"spd": 60}), generic_build("Bronya")]
    )
    lc = kafka.light_cone
    assert kafka.spd >= lc.p(6)
    enemy = b.default_target()
    kafka.kit.basic(enemy)
    assert enemy.has_mod("Bamboozle") and enemy.has_mod("Theft")
    assert enemy.stat(S.DEF_REDUCTION) == pytest.approx(lc.p(2) + lc.p(5))
    kafka.kit.basic(enemy)  # re-inflicting refreshes instead of stacking
    assert enemy.stat(S.DEF_REDUCTION) == pytest.approx(lc.p(2) + lc.p(5))


def test_destinys_threads_forewoven_dmg_from_def():
    b, (gepard, _) = _battle([generic_build("Gepard", light_cone="21039"), generic_build("Bronya")])
    lc = gepard.light_cone
    expected = min(lc.p(3), (gepard.defense // lc.p(1)) * lc.p(2))
    assert gepard.stat(S.DMG_PCT) == pytest.approx(expected)
    b2, (tank, _) = _battle(
        [generic_build("Gepard", light_cone="21039", extra_stats={"def": 9000}), generic_build("Bronya")]
    )
    assert tank.stat(S.DMG_PCT) == pytest.approx(lc.p(3))  # capped


def test_earthly_escapade_mask_and_radiant_flame_counts_overflow_sp():
    b, (bronya, seele) = _battle([generic_build("Bronya", light_cone="23021"), generic_build("Seele")])
    lc = bronya.light_cone
    mask = bronya.get_mod("Mask")
    assert mask is not None and mask.duration == int(lc.p(5))
    cr_seele, cr_bronya = seele.stat(S.CRIT_RATE), bronya.stat(S.CRIT_RATE)
    b.remove_modifier(mask)
    assert cr_seele - seele.stat(S.CRIT_RATE) == pytest.approx(lc.p(4))  # teammates only
    assert bronya.stat(S.CRIT_RATE) == pytest.approx(cr_bronya)
    b.sp = b.max_sp
    for _ in range(int(lc.p(3))):  # Basic ATK recovers 1 SP each, all of it overflow at max SP
        bronya.kit.basic(b.default_target())
    assert bronya.get_mod("Radiant Flame") is None
    assert bronya.get_mod("Mask").duration == int(lc.p(2))


def test_patience_is_all_you_need_erode_counts_as_shock():
    b, (kafka, _) = _battle([generic_build("Kafka", light_cone="23006"), generic_build("Bronya")])
    enemy = b.default_target()
    spd0 = kafka.spd
    kafka.kit.basic(enemy)
    erode = enemy.get_mod("Erode")
    assert erode is not None and enemy.has_tag("shock") and erode.is_debuff
    assert kafka.spd > spd0
