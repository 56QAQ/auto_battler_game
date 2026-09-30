"""Targeted checks for Abundance / Remembrance / Elation light cones (hsrsim/gear/lightcones_misc.py)."""

import pytest

from hsrsim import stats as S
from hsrsim.battle import Battle, BattleConfig
from hsrsim.build import make_character
from hsrsim.entities import Enemy, Summon
from hsrsim.enums import ActionKind, Element
from hsrsim.modifiers import hidden

from .helpers import generic_build


def start(*builds):
    chars = [make_character(b) for b in builds]
    battle = Battle(chars, [[Enemy("Boss", hp=1e12, weaknesses=list(Element))]], BattleConfig())
    battle.start()
    return battle, chars


def add_memosprite(battle, owner):
    memo = Summon("Memo", owner, spd=150, stat_mode="sync", targetable=True)
    memo.base[S.BASE_HP] = 3000
    return battle.add_unit(memo)


def test_echoes_of_the_coffin_energy_per_target_and_team_spd():
    battle, (luocha, bronya) = start(generic_build("Luocha", light_cone="23008"), generic_build("Bronya"))
    spd = bronya.spd
    luocha.energy = luocha.max_energy
    luocha.kit.use_ult()
    assert bronya.spd == pytest.approx(spd + 12)  # S1: +12 SPD for all allies
    # 1 enemy hit -> 3 Energy, plus the Ultimate's own 5 Energy refund (both ERR-scaled)
    assert luocha.energy == pytest.approx((3 + 5) * (1 + luocha.stat(S.ERR)))


def test_scent_alone_stays_true_woefree_scales_with_break_effect():
    battle, (wearer, _) = start(generic_build("Luocha", light_cone="23032"), generic_build("Bronya"))
    boss = battle.enemies[0]
    assert wearer.stat(S.BREAK_EFFECT) < 1.5
    wearer.energy = wearer.max_energy
    wearer.kit.use_ult()
    assert boss.has_mod("Woefree")
    assert boss.stat(S.VULN) == pytest.approx(0.10)
    battle.apply(hidden("BE", {S.BREAK_EFFECT: 1.0}), wearer, wearer)  # BE >= 150%: +8% more
    assert boss.stat(S.VULN) == pytest.approx(0.18)


def test_sweat_now_cry_less_needs_memosprite_and_is_not_double_counted():
    battle, (aglaea, _) = start(generic_build("Aglaea", light_cone="21052"), generic_build("Bronya"))
    base = aglaea.stat(S.DMG_PCT)
    memo = add_memosprite(battle, aglaea)
    assert aglaea.stat(S.DMG_PCT) == pytest.approx(base + 0.24)
    assert memo.stat(S.DMG_PCT) == pytest.approx(aglaea.stat(S.DMG_PCT))  # synced once, not twice
    battle.remove_unit(memo)
    assert aglaea.stat(S.DMG_PCT) == pytest.approx(base)


def test_long_may_rainbows_consumes_hp_and_memosprite_deals_additional_dmg():
    battle, (wearer, bronya) = start(generic_build("Aglaea", light_cone="23042"), generic_build("Bronya"))
    memo = add_memosprite(battle, wearer)
    hp = {e: e.hp for e in (wearer, bronya, memo)}
    wearer.kit.basic(battle.enemies[0])
    consumed = sum(v - e.hp for e, v in hp.items())
    assert consumed == pytest.approx(0.01 * sum(hp.values()))
    boss = battle.enemies[0]
    with battle.action(memo, ActionKind.MEMOSPRITE, target=boss) as act:
        act.hit(boss, 1.0)
    extra = [r for r in battle.records if r.label == "Long May Rainbows Adorn the Sky"]
    assert len(extra) == 1 and extra[0].amount > 0
    assert boss.stat(S.VULN) == pytest.approx(0.18)  # Memosprite Skill: all enemies take +18% DMG


def test_dazzled_sp_limit_def_ignore_stacks_and_stream_promo():
    battle, (sparxie, bronya) = start(generic_build("Sparxie", light_cone="23053"), generic_build("Bronya"))
    assert battle.max_sp == 5 + 1  # one Elation character in the team
    battle.sp = battle.max_sp
    battle.use_sp(2, sparxie)
    assert sparxie.stat(f"{S.DEF_IGNORE}:elation") == pytest.approx(2 * 0.05)
    assert bronya.stat(S.ELATION_DMG_PCT) == pytest.approx(0.0)
    battle.use_sp(2, sparxie)  # 4 SP in the same turn -> "Stream Promo" for all allies
    assert sparxie.stat(f"{S.DEF_IGNORE}:elation") == pytest.approx(4 * 0.05)
    assert bronya.stat(S.ELATION_DMG_PCT) == pytest.approx(0.2)
