"""Targeted checks for a few Hunt / Destruction / Erudition light cones (hsrsim/gear/lightcones_dps.py)."""

import pytest

from hsrsim import events as E
from hsrsim import stats as S
from hsrsim.battle import Battle
from hsrsim.build import make_character
from hsrsim.data import get_data
from hsrsim.entities import Enemy
from hsrsim.enums import ActionKind, Element

from .helpers import generic_build


def _params(lc_id: str, s: int = 1) -> list[float]:
    return [float(x) for x in get_data().light_cone(lc_id)["params"][s - 1]]


def _battle(char: str, lc_id: str, **kw):
    c = make_character(generic_build(char, light_cone=lc_id, **kw))
    e = Enemy("Dummy", hp=1e9, toughness=1e6, weaknesses=list(Element))
    b = Battle([c], [[e]])
    b.start()
    return b, c, e


def test_in_the_night_scales_with_spd_and_caps():
    p = _params("23001")
    b, c, e = _battle("Seele", "23001", extra_stats={"spd": 45.0})  # Seele 115 SPD -> 160 SPD: 6 stacks
    stacks = int((c.spd - 100) // p[1])
    assert stacks == 6
    assert c.stat(f"{S.DMG_PCT}:basic") == pytest.approx(stacks * p[2])
    assert c.stat(f"{S.CRIT_DMG}:ult") == pytest.approx(stacks * p[3])
    b, c, e = _battle("Seele", "23001", extra_stats={"spd": 200.0})  # capped at #5 stacks
    assert c.stat(f"{S.DMG_PCT}:skill") == pytest.approx(p[4] * p[2])


def test_before_dawn_somnus_corpus_boosts_next_follow_up():
    p = _params("23010")
    b, c, e = _battle("Himeko", "23010")
    hits = []
    b.events.on(E.AFTER_HIT, lambda ev: hits.append(ev.hit))
    c.kit.skill(e)
    assert hits[-1].extra[S.DMG_PCT] == pytest.approx(p[1])  # Skill/Ultimate DMG bonus (hit-local)
    assert c.has_mod("Somnus Corpus")
    with b.action(c, ActionKind.FUA, target=e) as act:
        assert c.stat(f"{S.DMG_PCT}:fua") == pytest.approx(p[2])
        act.hit(e, 1.0)
    assert not c.has_mod("Somnus Corpus")
    assert c.stat(f"{S.DMG_PCT}:fua") == 0.0


def test_thus_burns_the_dawn_blazing_sun_until_next_turn_start():
    p = _params("23044")
    b, c, e = _battle("Clara", "23044")
    assert c.stat(S.DEF_IGNORE) == pytest.approx(p[1])
    c.kit.ult(e)
    assert c.stat(S.DMG_PCT) == pytest.approx(p[2])
    b.take_turn(c)
    assert not c.has_mod("Blazing Sun")


def test_finale_of_a_lie_umbra_devourer_at_battle_start():
    p = _params("23056", 5)
    b, c, e = _battle("Seele", "23056", superimposition=5)
    umbra = c.get_mod("Umbra Devourer")
    assert umbra is not None and umbra.stats[S.ATK_PCT] == pytest.approx(p[3])
    assert e.stat(S.VULN) == pytest.approx(p[4])  # team-wide field on every enemy
    assert umbra.duration == int(p[2])


def test_something_irreplaceable_triggers_once_per_turn():
    p = _params("23002")
    b, c, e = _battle("Clara", "23002")
    heals = []
    b.events.on(E.HP_CHANGED, lambda ev: ev.delta > 0 and ev.source is c and heals.append(ev.delta))
    b.enemy_basic_attack(e)
    b.enemy_basic_attack(e)  # same turn: no second trigger
    mod = c.get_mod("Something Irreplaceable")
    assert mod is not None and mod.stats[S.DMG_PCT] == pytest.approx(p[2])
    assert len(heals) == 1 and heals[0] == pytest.approx(p[1] * c.atk)
