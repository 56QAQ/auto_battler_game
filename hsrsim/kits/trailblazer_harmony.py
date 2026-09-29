"""Trailblazer (Harmony) (开拓者·同谐) — Harmony / Imaginary. Backup Dancer: Super Break for the team."""

from __future__ import annotations

from .. import events as E
from .. import stats as S
from ..entities import Enemy
from ..enums import ActionKind, Side
from ..modifiers import Modifier, Tick
from . import register
from .base import Kit

BOUNCES = 4  # "additionally deals DMG for 4 times" (literal in the skill text, not a parameter)


class _TrailblazerHarmony(Kit):
    def setup(self) -> None:
        self.dancer: Modifier | None = None
        self.first_skill = True
        self.on(E.BREAK, self._on_break)
        self.on(E.ATTACK_END, self._super_break)
        if self.e(4):
            self.passive(
                "Dove in Tophat",
                {},
                scope=self.teammate_scope,
                dyn=lambda m, k, e: self.ep(4, 0) * self.char.stat(S.BREAK_EFFECT),
                dyn_keys={S.BREAK_EFFECT},
            )

    def on_battle_start(self) -> None:
        if self.e(2):
            self.buff_self(
                Modifier("Jailbreaking Rainbowwalk", stats={S.ERR: self.ep(2, 0)}, duration=int(self.ep(2, 1)))
            )

    def technique(self) -> None:
        p = self.sk("technique")["params"][0]
        for c in self.allies():
            self.buff(c, Modifier("Trailblazer Technique", stats={S.BREAK_EFFECT: p[0]}, duration=int(p[1])))

    # -------------------------------------------------------- actions
    def basic(self, target: Enemy | None) -> None:
        assert target is not None
        self.simple_basic(target)

    def skill(self, target: Enemy | None) -> None:
        assert target is not None
        n = BOUNCES + (int(self.ep(6, 0)) if self.e(6) else 0)
        mult = self.p("skill", 0)
        tough = self.toughness("skill")
        with self.action(ActionKind.SKILL, "skill", target) as act:
            first = tough * (1 + self.tp(2, 0)) if self.trace(2) else tough
            act.hit(target, mult, toughness=first)
            act.bounce(None, n, mult, toughness=self.toughness("skill", 2))
        if self.e(1) and self.first_skill:
            self.first_skill = False
            self.battle.gain_sp(1, self.char)

    def ult(self, target: Enemy | None) -> None:
        with self.action(ActionKind.ULT, "ult"):
            self.dancer = self.buff_self(
                Modifier(
                    "Backup Dancer",
                    stats={S.BREAK_EFFECT: self.p("ult", 2)},
                    duration=int(self.p("ult", 0)),
                    tick=Tick.SOURCE_TURN_START,
                    scope=self.ally_scope,
                    key="Backup Dancer",
                )
            )

    # ---------------------------------------------------------- talent
    def _on_break(self, ev: E.Ev) -> None:
        self.battle.gain_energy(self.char, self.p("talent", 0))
        if self.trace(3) and ev.target.alive:
            self.battle.delay(ev.target, self.tp(3, 0))

    def _super_break(self, ev: E.Ev) -> None:
        act = ev.attack
        if self.dancer is None or self.dancer.removed or act.owner is None or act.owner.side != Side.ALLY:
            return
        n = len(self.enemies())
        bonus = 0.0
        if self.trace(1):
            idx = max(0, min(4, 5 - n))  # >=5 / 4 / 3 / 2 / 1 enemies
            bonus = self.tp(1, idx)
        for t in act.attacked:
            tough = self.battle.super_break_toughness(act, t)
            if tough > 0:
                self.battle.super_break(
                    act.actor, t, tough, 1.0 + bonus, credited=act.owner, label="Super Break (Backup Dancer)"
                )


@register
class TrailblazerHarmony(_TrailblazerHarmony):
    char_id = "8005"


@register
class TrailblazerHarmonyF(_TrailblazerHarmony):
    char_id = "8006"
