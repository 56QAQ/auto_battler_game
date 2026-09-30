"""Archer — Hunt / Quantum. "Circuit Connection": chained 2-SP Skills within one turn (stacking Skill DMG),
Charge-based follow-ups (+1 Skill Point) after teammates attack, bigger Skill Point cap.

Options:
  ``sp_reserve``: Skill Points to keep for teammates when chaining Skills (default 0).

Policy: enter Circuit Connection whenever 2 Skill Points (+ reserve) are available and keep using the Skill
while possible (up to 5 times); otherwise Basic ATK. Rin Tohsaka's Joint Follow-Up ATK and Archer's own
follow-ups triggered during the chain are resolved between the Skills.
"""

from __future__ import annotations

from typing import Any

from .. import events as E
from .. import stats as S
from ..entities import Character, Enemy
from ..enums import ActionKind, DmgTag, Element
from ..modifiers import Modifier, ModKind
from . import register
from .base import Kit

FUA_SP = 1  # "recovering 1 Skill Point" (literal in the Talent text)


@register
class Archer(Kit):
    char_id = "1015"
    default_opts: dict[str, Any] = {"sp_reserve": 0}

    def setup(self) -> None:
        self.charge = 0
        self.cc = False
        self.cc_count = 0
        self.cc_stacks = 0
        self.in_chain = False
        self._pending: list[Enemy | None] = []
        if self.trace(1):
            self.battle.max_sp += int(self.tp(1, 0))
        if self.trace(3):
            self.on(E.SP_CHANGED, self._a6)
        if self.e(4):
            self.passive("The Unsung Life", {f"{S.DMG_PCT}:{DmgTag.ULT}": self.ep(4, 0)})
        if self.e(6):
            self.passive("The Endless Pilgrimage", {f"{S.DEF_IGNORE}:{DmgTag.SKILL}": self.ep(6, 1)})
            self.on(E.TURN_START, lambda ev: ev.entity is self.char and self.battle.gain_sp(int(self.ep(6, 0)), self.char))
        self.on(E.ATTACK_END, self._talent)

    def on_battle_start(self) -> None:
        if self.trace(2):
            self.add_charge(int(self.tp(2, 0)))

    def technique(self) -> None:
        p = self.sk("technique")["params"][0]
        with self.action(ActionKind.EXTRA, None, label="Archer Technique", energy=0, sp=0) as act:
            act.aoe(p[0], toughness=20)
        self.add_charge(int(p[1]))

    def add_charge(self, n: int) -> None:
        self.charge = min(int(self.p("ult", 2)), self.charge + n)

    def _a6(self, ev: E.Ev) -> None:
        if ev.delta > 0 and self.battle.sp >= self.tp(3, 2):
            self.buff_self(Modifier("Guardian", stats={S.CRIT_DMG: self.tp(3, 0)}, duration=int(self.tp(3, 1))))

    # ---------------------------------------------------------------- talent
    def _talent(self, ev: E.Ev) -> None:
        act = ev.attack
        owner = act.owner
        if not isinstance(owner, Character) or owner is self.char or not act.attacked or self.charge <= 0:
            return
        self.charge -= 1
        primary = act.target if isinstance(act.target, Enemy) else act.attacked[0]
        if self.in_chain:
            self._pending.append(primary)  # resolved before the next Skill of the chain
        else:
            self.battle.queue_action(lambda: self.follow_up(primary), self.char, "Mind's Eye (True)")

    def follow_up(self, target: Enemy | None) -> None:
        t = target if target is not None and target.alive and target.hp > 0 else None
        if t is None:
            pool = [e for e in self.enemies() if e.hp > 0] or self.enemies()
            if not pool:
                return
            t = self.battle.rng.choice(pool)
        with self.action(ActionKind.FUA, "talent", t) as act:
            act.hit(t, self.p("talent", 0), toughness=self.toughness("talent"))
        self.battle.gain_sp(FUA_SP, self.char)

    # ---------------------------------------------------------------- policy
    def _skill_cost(self) -> int:
        return int(self.sk("skill")["sp_need"])

    def _can_chain(self) -> bool:
        return self.battle.sp >= self._skill_cost() and self.battle.sp - self._skill_cost() >= int(
            self.opts.get("sp_reserve", 0)
        )

    def take_turn(self) -> None:
        target = self.pick_target()
        if target is None:
            return
        if self.opts.get("rotation", "skill") == "skill" and self._can_chain():
            self.chain()
        else:
            self.basic(target)

    def chain(self) -> None:
        self.cc, self.cc_count, self.cc_stacks = True, 0, 0
        self.in_chain = True
        try:
            while True:
                t = self.pick_target()
                if t is None:
                    break
                self.skill(t)
                self._after_skill()
                if self.cc_count >= int(self.p("skill", 4)) or not self.enemies() or not self._can_chain():
                    break
        finally:
            self.in_chain = False
            self.cc = False
            for t in self._pending:
                self.battle.queue_action(lambda t=t: self.follow_up(t), self.char, "Mind's Eye (True)")
            self._pending = []

    def _after_skill(self) -> None:
        for c in self.battle.team:
            hook = getattr(c.kit, "archer_skill_used", None)
            if c.alive and hook is not None:
                hook(self)
        while self._pending and self.enemies():
            self.follow_up(self._pending.pop(0))

    # --------------------------------------------------------------- actions
    def basic(self, target: Enemy | None) -> None:
        assert target is not None
        self.simple_basic(target)

    def skill(self, target: Enemy | None) -> None:
        assert target is not None
        extra = {S.DMG_PCT: self.cc_stacks * self.p("skill", 1)} if self.cc_stacks else None
        with self.action(ActionKind.SKILL, "skill", target) as act:
            act.hit(target, self.p("skill", 0), toughness=self.toughness("skill"), extra=extra)
        self.cc_count += 1
        max_stacks = int(self.p("skill", 2)) + (1 if self.e(6) else 0)  # E6: "increases by 1" (literal)
        self.cc_stacks = min(max_stacks, self.cc_stacks + 1)
        if self.e(1) and self.cc_count == int(self.ep(1, 0)):
            self.battle.gain_sp(int(self.ep(1, 1)), self.char)

    def ult(self, target: Enemy | None) -> None:
        assert target is not None
        with self.action(ActionKind.ULT, "ult", target) as act:
            if self.e(2):
                self.battle.apply(
                    Modifier(
                        "The Unfulfilled Happiness",
                        stats={f"{S.RES}:Quantum": -self.ep(2, 0)},
                        duration=int(self.ep(2, 1)),
                        kind=ModKind.DEBUFF,
                        tags={f"weak:{Element.QUANTUM.value}"},
                    ),
                    target,
                    self.char,
                )
            act.hit(target, self.p("ult", 0), toughness=self.toughness("ult"))
        self.add_charge(int(self.p("ult", 1)))
