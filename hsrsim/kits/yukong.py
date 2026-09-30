"""Yukong (驭空) — Harmony / Imaginary. "Roaring Bowstrings": team ATK% that loses a stack at the end of
every ally turn; Ultimate adds team CRIT Rate / CRIT DMG while Roaring Bowstrings is active.

Options (``default_opts``):

* ``rotation``: ``"skill"`` (default: Skill when Roaring Bowstrings is not active, else Basic ATK) or ``"basic"``.
* ``ult_needs_bowstrings``: only cast the Ultimate while Roaring Bowstrings is active (default True;
  ignored at E6, which grants a stack on cast).
"""

from __future__ import annotations

from .. import events as E
from .. import stats as S
from ..entities import Character, Enemy
from ..enums import ActionKind, Element
from ..modifiers import Modifier, ModKind, Stacking, Tick
from . import register
from .base import Kit

RB = "Roaring Bowstrings"
RB_MAX = 2  # "to a maximum of 2 stacks" (literal)
KESTREL = "Diving Kestrel"
TALENT_CD = "Seven Layers, One Arrow (cooldown)"


@register
class Yukong(Kit):
    char_id = "1207"
    default_opts = {"rotation": "skill", "ult_needs_bowstrings": True}

    def setup(self) -> None:
        self.keep_rb_this_turn = False
        self.e2_done: set[int] = set()
        # not modelled: A2 Archerion (resist 1 debuff every 2 turns) - enemies do not inflict debuffs
        if self.trace(2):
            self.passive("Bowmaster", {f"{S.DMG_PCT}:{Element.IMAGINARY.value}": self.tp(2, 0)}, scope=self.ally_scope)
        self.on(E.TURN_END, self._on_turn_end)
        if self.e(2):
            self.on(E.ENERGY_GAINED, self._e2)
        if self.e(4):
            self.on(E.BEFORE_HIT, self._e4)

    def on_battle_start(self) -> None:
        if self.e(1):
            for c in self.allies():
                self.buff(c, Modifier("Aerial Marshal", stats={S.SPD_PCT: self.ep(1, 0)}, duration=int(self.ep(1, 1))))

    def technique(self) -> None:
        self._gain_rb(int(self.sk("technique")["params"][0][2]))

    # --------------------------------------------------- Roaring Bowstrings
    def _rb(self) -> Modifier | None:
        return self.char.get_mod(RB)

    def _gain_rb(self, n: int) -> None:
        self.buff_self(
            Modifier(
                RB,
                stats={S.ATK_PCT: self.p("skill", 1)},
                stacks=n,
                max_stacks=RB_MAX,
                per_stack=False,
                stacking=Stacking.STACK,
                tick=Tick.NONE,
                scope=self.ally_scope,
            )
        )

    def _lose_rb_stack(self) -> None:
        rb = self._rb()
        if rb is None:
            return
        rb.stacks -= 1
        if rb.stacks <= 0:
            self.battle.remove_modifier(rb)
            # approximation: the Ultimate's CRIT buffs last exactly as long as Roaring Bowstrings
            self.battle.remove_named(self.char, KESTREL)

    def _on_turn_end(self, ev: E.Ev) -> None:
        ent = ev.entity
        if not isinstance(ent, Character):  # approximation: summon/memosprite turns do not consume stacks
            return
        if self.trace(3) and self._rb() is not None:
            # approximation: "every time an ally takes action" counted once per ally turn
            self.battle.gain_energy(self.char, self.tp(3, 0))
        if ent is self.char and self.keep_rb_this_turn:
            self.keep_rb_this_turn = False
            return
        self._lose_rb_stack()

    # ------------------------------------------------------------- policy
    def take_turn(self) -> None:
        target = self.pick_target()
        if target is None:
            return
        if self.opts.get("rotation", "skill") == "skill" and self.can_skill() and self._rb() is None:
            self.skill(target)
        else:
            self.basic(target)

    def want_ult(self) -> bool:
        if not super().want_ult():
            return False
        return self.e(6) or not self.opts.get("ult_needs_bowstrings", True) or self._rb() is not None

    # ------------------------------------------------------------ actions
    def basic(self, target: Enemy | None) -> None:
        assert target is not None
        mult = self.p("basic", 0)
        tough = self.toughness("basic")
        # approximation: the Talent's cooldown is a 1-turn marker applied in her own turn, so the enhanced Basic
        # ATK is available every other turn
        talent = not self.char.has_mod(TALENT_CD)
        if talent:
            mult += self.p("talent", 0)
            tough *= 1.0 + self.p("talent", 1)
        with self.action(ActionKind.BASIC, "basic", target) as act:
            act.hit(target, mult, toughness=tough, splits="data")
        if talent:
            self.buff_self(
                Modifier(TALENT_CD, kind=ModKind.OTHER, duration=int(self.p("talent", 2)), dispellable=False)
            )

    def skill(self, target: Enemy | None) -> None:
        with self.action(ActionKind.SKILL, "skill"):
            self._gain_rb(int(self.p("skill", 0)))
            self.keep_rb_this_turn = self.battle.current_turn is self.char

    def ult(self, target: Enemy | None) -> None:
        assert target is not None
        with self.action(ActionKind.ULT, "ult", target) as act:
            if self.e(6):
                self._gain_rb(int(self.ep(6, 0)))
            if self._rb() is not None:
                self.buff_self(
                    Modifier(
                        KESTREL,
                        stats={S.CRIT_RATE: self.p("ult", 1), S.CRIT_DMG: self.p("ult", 2)},
                        tick=Tick.NONE,
                        scope=self.ally_scope,
                    )
                )
            act.hit(target, self.p("ult", 0), toughness=self.toughness("ult"), splits="data")
        if self.e(2):
            self.e2_done.clear()

    # ------------------------------------------------------------ eidolons
    def _e2(self, ev: E.Ev) -> None:
        c = ev.entity
        if c.max_energy > 0 and c.energy >= c.max_energy - 1e-9 and c.uid not in self.e2_done:
            self.e2_done.add(c.uid)
            self.battle.gain_energy(self.char, self.ep(2, 0))

    def _e4(self, ev: E.Ev) -> None:
        hit = ev.hit
        if hit.attacker is self.char and self._rb() is not None:
            hit.add(S.DMG_PCT, self.ep(4, 0))
