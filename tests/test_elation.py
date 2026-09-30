"""Elation path: Punchline curve, Aha SPD, Aha Instant flow."""

import pytest

from hsrsim.battle import Battle, BattleConfig
from hsrsim.build import Build, make_character
from hsrsim.elation import ENTER_BATTLE_BANGER, ElationSystem, aha_speed, punchline_multiplier
from hsrsim.entities import Enemy
from hsrsim.scenarios import boss_dps

from .helpers import generic_build


def test_punchline_curve():
    assert punchline_multiplier(0) == 1.0
    assert punchline_multiplier(240) == pytest.approx(1 + 5 * 240 / 480)
    assert punchline_multiplier(20) == pytest.approx(1 + 100 / 260)


def test_aha_speed_weights():
    # 80 + 150/5 + 120/10 + 100/20 + 90/40 + 80/40
    assert aha_speed([100, 150, 120, 90, 80]) == pytest.approx(80 + 30 + 12 + 5 + 2.25 + 2)


def test_aha_instant_consumes_punchline_and_grants_banger():
    team = [Build("Sparxie"), Build("Yao Guang"), Build("Robin"), Build("Huohuo")]
    rep = boss_dps(cycles=4).run(team)
    b = rep.battle
    assert b.elation.instants >= 1
    assert b.turn_counts.get("Aha", 0) >= 1
    assert any(r.tags and "elation" in r.tags for r in b.records)


# ------------------------------------------------------------------ path rules (StageAbility_Elation)


def _battle(builds, enemies=None, **cfg):
    chars = [make_character(b) for b in builds]
    b = Battle(chars, [enemies or [Enemy("Dummy", hp=1e12)]], BattleConfig(**cfg))
    b.start()
    return b, chars


def _tv(name):
    # W3_TV_03 "Smile Magic" (SkillP01 = [3]): first time attacked -> the team gains 3 Punchline
    return Enemy(name, hp=1e12, template="W3_TV_03", passives={"SkillP01": [3.0]})


def test_battle_start_punchline_and_banger_per_elation_character():
    b, (sparxie, yao, bronya) = _battle([generic_build("Sparxie"), generic_build("Yao Guang"), generic_build("Bronya")])
    assert b.elation.punchline == 2  # 1 per Elation character
    assert b.elation.aha.on_timeline
    for c in (sparxie, yao):
        assert ElationSystem.certified_banger(c) == ENTER_BATTLE_BANGER
    assert ElationSystem.certified_banger(bronya) == 0


def test_no_elation_character_no_punchline():
    b, _ = _battle([generic_build("Seele"), generic_build("Bronya")])
    assert b.elation.punchline == 0 and not b.elation.aha.on_timeline


def test_aha_instant_consumes_then_regains_per_elation_character():
    b, _ = _battle([generic_build("Sparxie"), generic_build("Yao Guang"), generic_build("Bronya")])
    b.elation.gain(10)
    b.elation.instant(b.elation.punchline, consume=True)
    assert b.elation.punchline == 2  # all consumed, then +1 per Elation character
    b.elation.instant(20, consume=False)  # fixed extra turn: nothing consumed, still +2 afterwards
    assert b.elation.punchline == 4
    assert b.elation.aha.on_timeline


def test_smile_magic_first_hit_grants_punchline_once():
    tv = _tv("TV")
    b, (sparxie, _) = _battle([generic_build("Sparxie"), generic_build("Bronya")], [tv, Enemy("Dummy", hp=1e12)])
    assert b.elation.punchline == 1
    sparxie.kit.basic(tv)
    assert b.elation.punchline == 4
    sparxie.kit.basic(tv)
    assert b.elation.punchline == 4  # only the first time it is attacked


def test_smile_magic_needs_an_elation_team():
    tv = _tv("TV")
    b, (seele, _) = _battle([generic_build("Seele"), generic_build("Bronya")], [tv])
    seele.kit.basic(tv)
    assert b.elation.punchline == 0 and not b.elation.aha.on_timeline


@pytest.mark.parametrize("p, bonus_steps", [(19, 0), (20, 1), (40, 2)])
def test_silver_wolf_lv999_true_ending_unlocked(p, bonus_steps):
    b, (sw, _) = _battle([Build("Silver Wolf LV.999"), generic_build("Bronya")])
    kit = sw.kit
    rec = kit.sk(kit.elation_skill_id)
    base = rec["params"][kit.level_of(rec) - 1][0]  # "Pro-Gamer Move": gains #1 Hidden MMR
    bonus = [0.0, kit.tp(2, 2), kit.tp(2, 2) + kit.tp(2, 3)][bonus_steps]
    assert kit.tp(2, 0) == 20 and kit.tp(2, 1) == 40
    mmr0 = kit.mmr
    b.elation.instant(p, consume=True)
    # + the Punchline regained after the Aha Instant (1 Elation character), which Silver Wolf also gains as MMR
    assert kit.mmr - mmr0 == pytest.approx(base + bonus + 1)


def test_users_pure_fiction_opening_reaches_16_punchline():
    """Silver Wolf LV.999 / Pearl / Yao Guang / Trailblazer (Elation), all Techniques, two W3_TV_03 on the field:
    4 (battle start) + 3 (Yao Guang's Technique Skill) + 3 + 3 (Smile Magic x2, hit by the Funky Munch Bean box)
    + 3 (the box's own Punchline) = 16 Punchline and 16 Hidden MMR, as in game."""
    team = [Build("Silver Wolf LV.999", eidolon=2), Build("Pearl", eidolon=2), Build("Yao Guang"), Build("8009")]
    b, (sw, pearl, *_rest) = _battle(team, [_tv("TV A"), Enemy("Dummy", hp=1e12), _tv("TV B")], techniques=True)
    assert b.elation.punchline == 16
    assert sw.kit.mmr == 16
    assert ElationSystem.certified_banger(pearl) == 40  # 20 (battle start) + 20 (Technique)


def test_custom_wave_spec_keeps_monster_traits():
    """Endgame stages copied to custom waves in the UI keep the monster template and passives."""
    from hsrsim.scenarios import EnemySpec

    e = EnemySpec(**{"name": "TV", "template": "W3_TV_03", "passives": {"SkillP01": [3.0]}}).make()[0]
    assert e.template == "W3_TV_03" and e.passives == {"SkillP01": [3.0]}


def test_elation_hit_parts_match_the_reference_formula():
    """ElationBase(L) x scaling x (1+Elation) x (1+Merrymake) x (1 + 5P/(P+240)) x DEF x RES x Toughness x CRIT."""
    from hsrsim import stats as S
    from hsrsim.data import get_data
    from hsrsim.formulas import def_multiplier

    b, (sw, _) = _battle([Build("Silver Wolf LV.999"), generic_build("Bronya")], [Enemy("Dummy", hp=1e12, level=95)])
    enemy = b.enemies[0]
    hit = b.elation.damage(sw, enemy, 0.45, punchline=99, label="probe", can_crit=False)
    p = hit.parts
    assert p.base == pytest.approx(get_data().elation_base(sw.level) * 0.45)
    assert p.elation_mult == pytest.approx(1 + sw.stat(S.ELATION_DMG_PCT))
    assert p.merry_mult == pytest.approx(1 + sw.stat(S.MERRYMAKE_PCT))
    assert p.punch_mult == pytest.approx(1 + 5 * 99 / (99 + 240)) and p.punchline == 99
    assert p.dmg_boost == 1.0  # DMG% boosts do not apply
    dm = def_multiplier(sw.level, enemy.raw(S.BASE_DEF), def_ignore=sw.stat_q(S.DEF_IGNORE, ("elation",)))
    expected = p.base * p.elation_mult * p.merry_mult * p.punch_mult * dm * p.res_mult * 0.9
    assert hit.damage == pytest.approx(expected)


def test_magical_girl_4pc_def_ignore_grows_with_punchline_gained():
    from hsrsim import stats as S
    from hsrsim.data import get_data

    params = get_data().relic_set("129")["pieces"]["4"]["params"]  # [0.1, 5, 0.01, 10]
    b, (sw, _) = _battle([Build("Silver Wolf LV.999", relics={"129": 4}), generic_build("Bronya")])
    key = f"{S.DEF_IGNORE}:elation"
    gained = b.elation.total_gained
    assert sw.stat(key) == pytest.approx(params[0] + (gained // params[1]) * params[2])
    b.elation.gain(200)
    assert sw.stat(key) == pytest.approx(params[0] + params[3] * params[2])  # capped at 10 stacks
