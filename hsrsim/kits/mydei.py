"""Mydei (万敌) — Destruction / Imaginary. HP-scaling; Charge from HP loss drives the "Vendetta" state
(auto "Kingslayer Be King" every turn, "Godslayer Be God" extra turns at 150 Charge).

Options (``default_opts``):
  * ``rotation``: ``"skill"`` (Skill every turn outside Vendetta, default; the Skill costs HP, not SP) or ``"basic"``.

# not modelled: Taunt (Ultimate / Technique), Crowd Control immunity (A4).
# approximation: with ``allies_immortal`` a "killing blow" is an enemy hit that leaves Mydei at 1 HP.
"""

from __future__ import annotations

from typing import Any

from .. import events as E
from .. import stats as S
from ..entities import Enemy, Entity
from ..enums import ActionKind
from ..modifiers import Modifier, hidden
from . import register
from .base import Kit

MAX_CHARGE = 200.0  # "accumulates 1 point of Charge (up to 200 points)" (literal)
VENDETTA_CHARGE = 100.0  # "When Charge reaches 100, consumes 100 points of Charge" (literal)
A6_STEP = 100.0  # A6 "for every 100 excess HP" (literal)
# "Godslayer Be God" hits twice (split 0.5 / 0.5 in Avatar_Mydeimos_00_Skill22_Ability; not in the skill record)
GODSLAYER_SPLITS = [0.5, 0.5]


@register
class Mydei(Kit):
    char_id = "1404"
    default_opts = {"rotation": "skill"}

    def setup(self) -> None:
        self.charge = 0.0
        self.vendetta: Modifier | None = None
        self.pending_godslayer = False
        self.in_godslayer = False
        self.ult_target: Enemy | None = None
        self.a2_left = int(self.tp(1, 0)) if self.trace(1) else 0
        self.a6_charge = 0.0
        self.e2_tally = 0.0
        self.on(E.HP_CHANGED, self._on_hp)
        if self.e(2):
            self.on(E.HEALED, self._e2_heal)
            self.on(E.ACTION_END, lambda ev: setattr(self, "e2_tally", 0.0))
        if self.e(4):
            self.on(E.ALLY_ATTACKED, self._e4)

    def on_battle_start(self) -> None:
        if self.trace(3):
            excess = min(self.tp(3, 1), max(0.0, self.char.max_hp - self.tp(3, 0)))
            steps = int(excess / A6_STEP)
            self.passive("Bloodied Chiton", {S.CRIT_RATE: steps * self.tp(3, 2)})
            self.a6_charge = steps * self.tp(3, 3)
            # not modelled: the healing received bonus (steps * #5) - heals are not scaled by the engine
        if self.e(6):
            self._enter_vendetta(consume=False)

    def technique(self) -> None:
        p = self.sk("technique")["params"][0]
        with self.action(ActionKind.EXTRA, None, label="Cage of Broken Lance (Technique)", energy=0, sp=0) as act:
            act.aoe(p[1], stat="hp", toughness=self.toughness("technique"))
        self.add_charge(p[4])

    # -------------------------------------------------------------- Charge
    def godslayer_cost(self) -> float:
        if self.e(6):
            return self.ep(6, 0)
        rec = self.sk("140411")
        return float(rec["params"][self.level_of(rec) - 1][2])

    def add_charge(self, n: float) -> None:
        if self.in_godslayer or n <= 0:
            return
        self.charge = min(MAX_CHARGE, self.charge + n)
        self._check_charge()

    def _check_charge(self) -> None:
        if self.vendetta is None and self.charge >= VENDETTA_CHARGE:
            self._enter_vendetta(consume=True)
        if self.vendetta is not None and not self.pending_godslayer and self.charge >= self.godslayer_cost():
            self.pending_godslayer = True
            self.battle.queue_extra_turn(self.char)

    def _on_hp(self, ev: E.Ev) -> None:
        if ev.entity is not self.char or ev.delta >= 0:
            return
        from_enemy = isinstance(ev.source, Enemy)
        ratio = 1.0 + (self.a6_charge if from_enemy else 0.0)
        self.add_charge(-ev.delta / self.char.max_hp * 100.0 * ratio)
        if from_enemy and self.char.hp <= 1.0 and self.vendetta is not None:
            self._killing_blow()

    def _killing_blow(self) -> None:
        if self.a2_left > 0:
            self.a2_left -= 1
            return
        self.charge = 0.0
        self._exit_vendetta()
        self.battle.heal(self.char, self.p("talent", 3) * self.char.max_hp, self.char)

    def _e2_heal(self, ev: E.Ev) -> None:
        if ev.entity is not self.char or ev.effective <= 0:
            return
        gain = min(self.ep(2, 2) - self.e2_tally, ev.effective / self.char.max_hp * 100.0 * self.ep(2, 1))
        if gain > 0:
            self.e2_tally += gain
            self.add_charge(gain)

    def _e4(self, ev: E.Ev) -> None:
        if self.vendetta is not None and self.char in ev.targets:
            self.battle.heal(self.char, self.ep(4, 0) * self.char.max_hp, self.char)

    # ------------------------------------------------------------ Vendetta
    def _enter_vendetta(self, consume: bool) -> None:
        if self.vendetta is not None:
            return
        if consume:
            self.charge -= VENDETTA_CHARGE
        stats: dict[str, float] = {}
        if self.e(2):
            stats[S.DEF_IGNORE] = self.ep(2, 0)
        if self.e(4):
            stats[S.CRIT_DMG] = self.ep(4, 1)
        mod = hidden("Vendetta", stats, dyn=self._dyn, dyn_keys={S.HP_FLAT, S.DEF_FLAT, S.DEF_PCT})
        ratio = self.char.hp_ratio
        self.vendetta = self.buff_self(mod)
        self.char.hp = ratio * self.char.max_hp  # the Max HP increase keeps the HP percentage
        self.battle.heal(self.char, self.p("talent", 0) * self.char.max_hp, self.char)
        self.battle.advance(self.char, 1.0)
        self._check_charge()

    def _dyn(self, mod: Modifier, key: str, ent: Entity) -> float:
        """Max HP +50% of the current Max HP; "DEF remains at 0" (cancels every other DEF source).
        Inside these queries the engine's recursion guard excludes this modifier's own dynamic part."""
        if key == S.HP_FLAT:
            return self.p("talent", 4) * self.char.max_hp
        if key == S.DEF_PCT:
            return -1.0 - self.char.raw(S.DEF_PCT)
        if key == S.DEF_FLAT:
            return -self.char.raw(S.DEF_FLAT)
        return 0.0

    def _exit_vendetta(self) -> None:
        if self.vendetta is not None:
            self.battle.remove_modifier(self.vendetta)
        self.vendetta = None
        self.pending_godslayer = False
        self.char.hp = min(self.char.hp, self.char.max_hp)

    # -------------------------------------------------------------- policy
    def take_turn(self) -> None:
        target = self.pick_target()
        if target is None:
            return
        if self.pending_godslayer and self.vendetta is not None:
            self.godslayer()
        elif self.vendetta is not None:
            self.kingslayer(target)
        elif self.opts.get("rotation", "skill") == "skill" and self.can_skill():
            self.skill(target)
        else:
            self.basic(target)

    # ------------------------------------------------------------- actions
    def basic(self, target: Enemy | None) -> None:
        assert target is not None
        with self.action(ActionKind.BASIC, "basic", target) as act:
            act.hit(target, self.p("basic", 0), stat="hp", toughness=self.toughness("basic"), splits="data")

    def _blast(self, rec: dict[str, Any], target: Enemy, main: float, adj: float) -> None:
        t = rec["toughness"]
        with self.action(ActionKind.SKILL, rec, target) as act:
            act.blast(target, main, adj, stat="hp", toughness=(float(t[0]), float(t[2])))

    def skill(self, target: Enemy | None) -> None:
        assert target is not None
        if self.vendetta is not None:
            self.kingslayer(target)
            return
        self.battle.lose_hp(self.char, self.p("skill", 2) * self.char.hp, self.char)
        self._blast(self.sk("skill"), target, self.p("skill", 0), self.p("skill", 1))

    def kingslayer(self, target: Enemy) -> None:
        rec = self.sk("140409")
        lv = rec["params"][self.level_of(rec) - 1]
        self.battle.lose_hp(self.char, lv[2] * self.char.hp, self.char)
        self._blast(rec, target, lv[0], lv[1])

    def godslayer(self) -> None:
        self.pending_godslayer = False
        t = self.ult_target if self.ult_target is not None and self.ult_target.alive else self.pick_target()
        if t is None:
            return
        rec = self.sk("140411")
        lv = rec["params"][self.level_of(rec) - 1]
        tough = rec["toughness"]
        self.charge = max(0.0, self.charge - self.godslayer_cost())
        self.in_godslayer = True
        try:
            with self.action(ActionKind.SKILL, rec, t) as act:
                if self.e(1):  # every enemy takes the primary target's multiplier
                    main = lv[0] + self.ep(1, 0)
                    for e in self.enemies():
                        act.hit(
                            e,
                            main,
                            stat="hp",
                            toughness=float(tough[0] if e is t else tough[2]),
                            primary=e is t,
                            splits=GODSLAYER_SPLITS,
                        )
                else:
                    act.blast(
                        t,
                        lv[0],
                        lv[1],
                        stat="hp",
                        toughness=(float(tough[0]), float(tough[2])),
                        splits=GODSLAYER_SPLITS,
                    )
        finally:
            self.in_godslayer = False
        self._check_charge()

    def ult(self, target: Enemy | None) -> None:
        if target is None:
            return
        self.ult_target = target
        self.battle.heal(self.char, self.p("ult", 2) * self.char.max_hp, self.char)
        with self.action(ActionKind.ULT, "ult", target) as act:
            act.blast(
                target,
                self.p("ult", 0),
                self.p("ult", 1),
                stat="hp",
                toughness=(self.toughness("ult", 0), self.toughness("ult", 2)),
            )
        self.add_charge(self.p("ult", 4))
