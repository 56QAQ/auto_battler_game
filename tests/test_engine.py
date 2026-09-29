"""Engine mechanics: timeline, damage pipeline, toughness/break, durations."""

import pytest

from hsrsim import formulas as F
from hsrsim import stats as S
from hsrsim.battle import Battle, BattleConfig
from hsrsim.build import Build, make_character
from hsrsim.entities import Enemy
from hsrsim.enums import ActionKind, Element, EnemyRank
from hsrsim.kits.base import Kit
from hsrsim.modifiers import Modifier


class Scripted(Kit):
    """Basic ATK every turn (100% ATK, 10 toughness); optional self-buff; never ults."""

    def setup(self):
        self.state["turns"] = []

    def take_turn(self):
        self.state["turns"].append(self.battle.time)
        if self.opts.get("self_buff"):
            self.buff_self(Modifier("Test Buff", stats={S.DMG_PCT: 0.5}, duration=1))
        self.basic(self.pick_target())

    def basic(self, target):
        with self.action(ActionKind.BASIC, "basic", target) as act:
            act.hit(target, 1.0, toughness=10)

    def ult_ready(self):
        return False


def make_battle(toughness=100.0, spd=100.0, weak=(Element.QUANTUM,), opts=None, **cfg):
    char = make_character(Build("Seele", kit=Scripted, options=opts or {}))
    enemy = Enemy("Dummy", level=95, hp=1e9, spd=spd, toughness=toughness, weaknesses=weak, rank=EnemyRank.ELITE)
    return Battle([char], [[enemy]], BattleConfig(**cfg)), char, enemy


def test_turn_order_av():
    b, c, e = make_battle()
    b.run(max_av=200)
    turns = c.kit.state["turns"]
    assert turns[0] == pytest.approx(10000 / 115)
    assert turns[1] == pytest.approx(2 * 10000 / 115)


def test_action_advance_and_speed_change():
    b, c, e = make_battle()
    b.start()
    b._advance_time(50)
    assert c.av == pytest.approx(10000 / 115 - 50)
    b.advance(c, 0.25)
    assert c.gauge == pytest.approx(10000 - 115 * 50 - 2500)
    remaining = c.gauge
    b.apply(Modifier("SPD", stats={S.SPD_PCT: 0.5}), c, c)
    assert c.av == pytest.approx(remaining / (115 * 1.5))  # gauge distance kept, AV rescaled


def test_single_hit_damage_matches_formula():
    b, c, e = make_battle(toughness=1000)
    b.run(max_av=90)
    rec = b.records[0]
    expected = (
        c.atk
        * 1.0
        * F.def_multiplier(80, 1150)
        * F.res_multiplier(0.0)
        * 0.9
        * F.crit_multiplier_expected(c.stat(S.CRIT_RATE), c.stat(S.CRIT_DMG))
    )
    assert rec.amount == pytest.approx(expected)


def test_weakness_break_damage_and_delay():
    b, c, e = make_battle(toughness=10, spd=90)
    b.run(max_av=90)  # Seele acts once at 86.96 and breaks the enemy
    brk = [r for r in b.records if r.label == "Break"]
    assert len(brk) == 1
    lvl = 3767.5535
    expected = 0.5 * lvl * F.toughness_multiplier(10) * F.def_multiplier(80, 1150) * 1.0
    assert brk[0].amount == pytest.approx(expected)
    assert e.broken
    # enemy (SPD 90) had 10000 - 90*86.96 left; delayed by 25% + Entanglement 20%
    t = 10000 / 115
    assert e.gauge == pytest.approx(10000 - 90 * t + 2500 + 2000 - 90 * (90 - t))


def test_break_dot_first_tick_while_broken():
    b, c, e = make_battle(toughness=10, weak=(Element.QUANTUM,))
    b.run(max_av=300)
    ent = [r for r in b.records if r.label == "Entanglement"]
    assert ent, "Entanglement should trigger at the enemy's next turn start"
    # 0.6 x stacks x level x toughness mult; Seele attacked once more before the enemy's turn -> 2 stacks
    assert ent[0].amount > 0


def test_own_turn_buff_lasts_through_next_turn():
    b, c, e = make_battle(toughness=1000, opts={"self_buff": True})
    b.start()
    b.run(max_av=10000 / 115 + 1)
    assert c.has_mod("Test Buff")  # applied during own turn: that turn's end does not count
    b.cfg.skip_tick_if_applied_in_own_turn = False
    b.run(max_av=2 * 10000 / 115 + 1)
    assert not c.has_mod("Test Buff")  # re-applied without the skip rule: gone at turn end


def test_vulnerability_and_final_dmg_layers():
    b, c, e = make_battle(toughness=1000)
    b.start()
    b.apply(Modifier("Vuln", stats={S.VULN: 0.2}), e, c)
    b.apply(Modifier("Final", stats={S.FINAL_DMG: 0.1}), c, c)
    b.run(max_av=90)
    base = (
        c.atk * F.def_multiplier(80, 1150) * 0.9 * F.crit_multiplier_expected(c.stat(S.CRIT_RATE), c.stat(S.CRIT_DMG))
    )
    assert b.records[0].amount == pytest.approx(base * 1.2 * 1.1)
