"""Trailblazer (Destruction) (开拓者·毁灭) — Destruction / Physical. Blast Skill, two Ultimate modes, ATK on break.

Options:
  ult_mode: "auto" (default: "Blowout: RIP Home Run" when the target has adjacent enemies, else
            "Blowout: Farewell Hit"), "single" or "blast"
"""

from __future__ import annotations

from .. import events as E
from .. import stats as S
from ..entities import Enemy
from ..enums import ActionKind, Element
from ..modifiers import Modifier, Stacking, Tick
from . import register
from .base import Kit

FAREWELL_HIT, RIP_HOME_RUN = "08", "09"  # skill ID suffixes of the two Ultimate modes


class _TrailblazerDestruction(Kit):
    default_opts = {"ult_mode": "auto"}

    def setup(self) -> None:
        self.on(E.BREAK, lambda ev: ev.credited is self.char and self.perfect_pickoff())
        if self.trace(3):
            self.on(E.BEFORE_HIT, self._fighting_will)
        if self.e(1):
            self.on(E.ACTION_END, self._e1)
        if self.e(2):
            self.on(E.ATTACK_END, self._e2)
        if self.e(4):
            self.on(E.BEFORE_HIT, self._e4)
        if self.e(6):
            self.on(E.KILL, lambda ev: ev.killer is self.char and self.perfect_pickoff())

    def on_battle_start(self) -> None:
        if self.trace(1):
            self.battle.gain_energy(self.char, self.tp(1, 0))

    def technique(self) -> None:
        pct = self.sk("technique")["params"][0][0]
        for c in self.allies():
            self.battle.heal(c, pct * c.max_hp, self.char)

    # ------------------------------------------------------------ talent
    def perfect_pickoff(self) -> None:
        stats = {S.ATK_PCT: self.p("talent", 0)}
        if self.trace(2):
            stats[S.DEF_PCT] = self.tp(2, 0)
        self.buff_self(
            Modifier(
                "Perfect Pickoff",
                stats=stats,
                max_stacks=int(self.p("talent", 1)),
                stacking=Stacking.STACK,
                tick=Tick.NONE,
                key="Perfect Pickoff",
            )
        )

    def _fighting_will(self, ev: E.Ev) -> None:
        h = ev.hit
        if h.attacker is self.char and h.primary and h.action is not None and h.action.data.get("fighting_will"):
            h.add(S.DMG_PCT, self.tp(3, 0))

    def _e1(self, ev: E.Ev) -> None:
        act = ev.action
        if act.owner is self.char and act.kind == ActionKind.ULT and any(t.hp <= 0 for t in act.attacked):
            self.battle.gain_energy(self.char, self.ep(1, 0))  # once per attack

    def _e2(self, ev: E.Ev) -> None:
        act = ev.attack
        if act.owner is self.char and any(t.is_weak_to(Element.PHYSICAL) for t in act.attacked):
            self.battle.heal(self.char, self.ep(2, 0) * self.char.atk, self.char)

    def _e4(self, ev: E.Ev) -> None:
        h = ev.hit
        if h.attacker is self.char and h.target.broken:
            h.add(S.CRIT_RATE, self.ep(4, 0))

    # ------------------------------------------------------------ actions
    def basic(self, target: Enemy | None) -> None:
        assert target is not None
        self.simple_basic(target)

    def skill(self, target: Enemy | None) -> None:
        assert target is not None
        with self.action(ActionKind.SKILL, "skill", target) as act:
            act.data["fighting_will"] = True
            act.blast(
                target,
                self.p("skill", 0),
                self.p("skill", 0),
                toughness=(self.toughness("skill", 0), self.toughness("skill", 2)),
            )

    def ult(self, target: Enemy | None) -> None:
        assert target is not None
        mode = self.opts.get("ult_mode", "auto")
        blast = mode == "blast" or (mode == "auto" and bool(self.battle.adjacent(target)))
        rec = self.sk(self.char.char_id + (RIP_HOME_RUN if blast else FAREWELL_HIT))
        lv = rec["params"][self.level_of(rec) - 1]
        tough = rec["toughness"]
        with self.action(ActionKind.ULT, rec, target) as act:
            if blast:
                act.data["fighting_will"] = True
                act.blast(target, lv[0], lv[1], toughness=(float(tough[0]), float(tough[2])))
            else:
                act.hit(target, lv[0], toughness=float(tough[0]))


@register
class TrailblazerDestruction(_TrailblazerDestruction):
    char_id = "8001"


@register
class TrailblazerDestructionF(_TrailblazerDestruction):
    char_id = "8002"
