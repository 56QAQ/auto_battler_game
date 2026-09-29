"""Clara (克拉拉) — Destruction / Physical. Svarog counters enemies that attack her; enhanced counters
(Blast) after the Ultimate; the Skill hits all enemies with bonus DMG on Marks of Counter.

Options (``default_opts``):

* ``rotation``: ``"skill"`` (default, Skill whenever SP allows) or ``"basic"``.
"""

from __future__ import annotations

from .. import events as E
from .. import stats as S
from ..entities import Enemy
from ..enums import ActionKind
from ..modifiers import Modifier, ModKind, Tick
from . import register
from .base import Kit

# "Enemies adjacent to it take 50% of the DMG dealt to the primary target enemy" (literal in the Ultimate text)
ENHANCED_COUNTER_ADJ_RATIO = 0.5
MARK = "Mark of Counter"


@register
class Clara(Kit):
    char_id = "1107"
    default_opts = {"rotation": "skill"}

    def setup(self) -> None:
        self.enhanced_left = 0
        self.passive("Because We're Family", {S.MITIGATION: self.p("talent", 2)})
        if self.trace(2):
            self.passive("Under Protection", {f"{S.DEBUFF_RES}:cc": self.tp(2, 0)})
        self.on(E.ALLY_ATTACKED, self._on_ally_attacked)

    def technique(self) -> None:
        p = self.sk("technique")["params"][0]  # [turns, aggro]
        # approximation: "chance to be attacked increases" = Aggro +param x 100%
        self.buff_self(Modifier("A Small Price for Victory", stats={S.AGGRO_PCT: p[1]}, duration=int(p[0])))

    # ------------------------------------------------------------ actions
    def basic(self, target: Enemy | None) -> None:
        assert target is not None
        self.simple_basic(target)

    def skill(self, target: Enemy | None) -> None:
        assert target is not None
        with self.action(ActionKind.SKILL, "skill", target) as act:
            act.aoe(self.p("skill", 0), toughness=self.toughness("skill", 1), main_target=target)
            for e in self.enemies():
                if e.has_mod(MARK):
                    act.hit(e, self.p("skill", 1), label="Svarog Watches Over You (Mark)", primary=e is target)
        if not self.e(1):
            for e in self.battle.enemies:
                self.battle.remove_named(e, MARK)

    def ult(self, target: Enemy | None) -> None:
        with self.action(ActionKind.ULT, "ult"):
            # approximation: "greatly increased chances of being attacked" = Aggro +param x 100%
            self.buff_self(
                Modifier(
                    "Promise, Not Command",
                    stats={S.MITIGATION: self.p("ult", 3), S.AGGRO_PCT: self.p("ult", 0)},
                    duration=int(self.p("ult", 2)),
                )
            )
            # approximation: Enhanced Counters stay available until used (they do not expire with the buff)
            self.enhanced_left = int(self.p("ult", 4)) + (int(self.ep(6, 1)) if self.e(6) else 0)
            if self.e(2):
                self.buff_self(
                    Modifier("A Tight Embrace", stats={S.ATK_PCT: self.ep(2, 0)}, duration=int(self.ep(2, 1)))
                )

    # ------------------------------------------------------------ talent
    def _mark(self, enemy: Enemy) -> None:
        if enemy.alive:
            self.battle.apply(Modifier(MARK, kind=ModKind.OTHER, tick=Tick.NONE, key=MARK), enemy, self.char)

    def _on_ally_attacked(self, ev: E.Ev) -> None:
        enemy = ev.attacker
        if not isinstance(enemy, Enemy):
            return
        c = self.char
        clara_hit = c in ev.targets
        if clara_hit:
            if self.trace(1) and c.debuffs and self.battle.rng.random() < self.tp(1, 0):
                m = next((m for m in c.debuffs if m.dispellable), None)
                if m is not None:
                    self.battle.remove_modifier(m)
            if self.e(4):
                self.buff_self(
                    Modifier(
                        "Family's Warmth",
                        stats={S.MITIGATION: self.ep(4, 0)},
                        duration=1,
                        tick=Tick.HOLDER_TURN_START,
                    )
                )
        if self.enhanced_left > 0:
            self.enhanced_left -= 1
            self._queue_counter(enemy, enhanced=True)
        elif clara_hit or (self.e(6) and self.battle.rng.random() < self.ep(6, 0)):
            self._queue_counter(enemy, enhanced=False)

    def _queue_counter(self, enemy: Enemy, enhanced: bool) -> None:
        # approximation: every Counter (also Enhanced ones triggered by other allies) marks its target
        self._mark(enemy)

        def counter() -> None:
            t = enemy if enemy.alive else self.battle.default_target()
            if t is None:
                return
            self._mark(t)
            mult = self.p("talent", 1) + (self.p("ult", 1) if enhanced else 0.0)
            extra = {S.DMG_PCT: self.tp(3, 0)} if self.trace(3) else None
            label = "Svarog Enhanced Counter" if enhanced else "Svarog Counter"
            with self.action(ActionKind.FUA, "talent", t, label=label) as act:
                if enhanced:
                    # approximation: adjacent enemies take 50% of the multiplier (not of the final DMG dealt)
                    act.blast(
                        t,
                        mult,
                        mult * ENHANCED_COUNTER_ADJ_RATIO,
                        toughness=(self.toughness("talent", 0), self.toughness("talent", 2)),
                        extra=extra,
                    )
                else:
                    act.hit(t, mult, toughness=self.toughness("talent"), extra=extra)

        self.battle.queue_action(counter, self.char, "Svarog Counter")
