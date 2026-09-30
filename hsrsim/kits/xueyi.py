"""Xueyi (雪衣) — Destruction / Quantum. Karma stacks from Toughness reduction trigger a 3-hit follow-up;
Ultimate ignores Weakness Types and deals more DMG the more Toughness it reduces.

Options (``default_opts``):
* ``rotation``: ``"skill"`` (default: Skill whenever SP allows) or ``"basic"``.
"""

from __future__ import annotations

import math

from .. import events as E
from .. import stats as S
from ..entities import Enemy, Entity
from ..enums import ActionKind, DmgTag, Side
from ..modifiers import Modifier
from . import register
from .base import Kit

# Ability config (MAvatar_Xueyi_00_Passive_AddCount / Skill03_AddAttackRatio): internal Toughness units are
# 3x the data units; Karma = floor(reduced / 30) (at least 1) and the Ultimate DMG bonus = P2 x reduced / 30
# (at least 1 unit), i.e. one unit per 10 Toughness in data units.
TOUGHNESS_UNIT = 10.0
FUA_HITS = 3  # Talent text "dealing DMG for 3 times"


@register
class Xueyi(Kit):
    char_id = "1214"
    default_opts = {"rotation": "skill"}

    def setup(self) -> None:
        self.karma = 0
        self.tally = 0  # A6: Karma above the cap
        self.fua_pending = False
        self._reduced: dict[int, float] = {}
        self.on(E.AFTER_HIT, self._after_hit)
        self.on(E.ATTACK_END, self._after_attack)
        self.on(E.WAVE_START, self._on_wave)
        if self.trace(1):
            self.passive("Clairvoyant Loom", {}, dyn=self._a2, dyn_keys={S.DMG_PCT})

    def technique(self) -> None:
        p = self.sk("technique")["params"][0]
        with self.action(ActionKind.EXTRA, None, label="Summary Execution", energy=0, sp=0) as act:
            act.aoe(p[0], toughness=self.toughness("technique"))

    def _a2(self, mod: Modifier, key: str, ent: Entity) -> float:
        return min(self.tp(1, 1), self.tp(1, 0) * self.char.stat(S.BREAK_EFFECT))

    # -------------------------------------------------------------- Karma
    def karma_max(self) -> int:
        return int(self.ep(6, 0)) if self.e(6) else int(self.p("talent", 0))

    def gain_karma(self, n: int) -> None:
        cap = self.karma_max()
        total = self.karma + n
        if total > cap and self.trace(3):
            self.tally = min(int(self.tp(3, 0)), self.tally + total - cap)
        self.karma = min(cap, total)
        if self.karma >= cap and not self.fua_pending:
            self.fua_pending = True
            self.battle.queue_action(self._fua, self.char, "Xueyi Talent")

    def _after_hit(self, ev: E.Ev) -> None:
        hit = ev.hit
        if hit.action is not None and hit.toughness_reduced > 0:
            key = id(hit.action)
            self._reduced[key] = self._reduced.get(key, 0.0) + hit.toughness_reduced

    def _after_attack(self, ev: E.Ev) -> None:
        act = ev.attack
        reduced = self._reduced.pop(id(act), 0.0)
        if reduced <= 0 or act.owner is None or act.owner.side != Side.ALLY:
            return
        if act.owner is self.char:
            # the follow-up adds no Karma; the Technique (EXTRA) does: StageAbility_Maze_Xueyi_Modifier adds
            # MAvatar_Xueyi_00_Passive_AddCount after its DMG
            if act.kind in (ActionKind.BASIC, ActionKind.SKILL, ActionKind.ULT, ActionKind.EXTRA):
                self.gain_karma(max(1, math.floor(reduced / TOUGHNESS_UNIT + 1e-9)))
        else:
            self.gain_karma(int(self.p("talent", 2)))

    def _on_wave(self, ev: E.Ev) -> None:
        if self.fua_pending:  # a queued follow-up is dropped when the wave ends: re-launch it
            self.battle.queue_action(self._fua, self.char, "Xueyi Talent")

    def _fua(self) -> None:
        if not self.enemies():
            return
        self.fua_pending = False
        self.karma = 0
        extra = {S.DMG_PCT: self.ep(1, 0)} if self.e(1) else None
        with self.action(ActionKind.FUA, "talent", self.battle.default_target()) as act:
            act.bounce(
                None,
                FUA_HITS,
                self.p("talent", 1),
                toughness=self.toughness("talent"),
                ignore_weakness=self.e(2),
                extra=extra,
            )
            if self.e(2):
                self.battle.heal(self.char, self.ep(2, 0) * self.char.max_hp, self.char)
        if self.tally:
            n, self.tally = self.tally, 0
            self.gain_karma(n)

    # ------------------------------------------------------------ actions
    def basic(self, target: Enemy | None) -> None:
        assert target is not None
        self.simple_basic(target)

    def skill(self, target: Enemy | None) -> None:
        assert target is not None
        with self.action(ActionKind.SKILL, "skill", target) as act:
            act.blast(
                target,
                self.p("skill", 0),
                self.p("skill", 1),
                toughness=(self.toughness("skill", 0), self.toughness("skill", 2)),
            )

    def ult_bonus(self, target: Enemy) -> float:
        """DMG% of the Ultimate from the Toughness it is about to reduce (0 on a Weakness Broken target)."""
        if target.broken or target.max_toughness <= 0:
            return 0.0
        tough = self.toughness("ult")
        pot = tough * (1.0 + self.char.stat_q(S.BREAK_EFF, (self.char.element.value, DmgTag.ULT)))
        reduced = min(pot, target.toughness)
        if reduced <= 0:
            return 0.0
        units = max(1.0, reduced / TOUGHNESS_UNIT)
        return min(self.p("ult", 2), self.p("ult", 1) * units)

    def ult(self, target: Enemy | None) -> None:
        if target is None:
            return
        with self.action(ActionKind.ULT, "ult", target) as act:
            if self.e(4):
                self.buff_self(
                    Modifier("Karma, Severed", stats={S.BREAK_EFFECT: self.ep(4, 0)}, duration=int(self.ep(4, 1)))
                )
            bonus = self.ult_bonus(target)
            if self.trace(2) and target.max_toughness > 0 and target.toughness >= self.tp(2, 0) * target.max_toughness:
                bonus += self.tp(2, 1)
            act.hit(
                target,
                self.p("ult", 0),
                toughness=self.toughness("ult"),
                ignore_weakness=True,
                extra={S.DMG_PCT: bonus},
            )
