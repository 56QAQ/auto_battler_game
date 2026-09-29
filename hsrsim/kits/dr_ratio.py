"""Dr. Ratio (真理医生) — Hunt / Imaginary. Debuff-scaling follow-ups, Wiseman's Folly."""

from __future__ import annotations

from .. import events as E
from .. import stats as S
from ..entities import Character, Enemy
from ..enums import ActionKind, DmgTag, Element
from ..modifiers import Modifier, ModKind, Stacking, Tick
from . import register
from .base import Kit


@register
class DrRatio(Kit):
    char_id = "1305"

    def setup(self) -> None:
        self.folly_target: Enemy | None = None
        self.folly_left = 0
        self.summation_max = int(self.tp(1, 2)) + (int(self.ep(1, 0)) if self.e(1) else 0) if self.trace(1) else 0
        self.on(E.ATTACK_END, self._wiseman)
        if self.trace(3):
            self.on(E.BEFORE_HIT, self._deduction)
        if self.e(6):
            self.passive("Vincit Omnia Veritas", {f"{S.DMG_PCT}:{DmgTag.FUA}": self.ep(6, 1)})

    def on_battle_start(self) -> None:
        if self.e(1):
            self.summation(int(self.ep(1, 1)))

    def technique(self) -> None:
        p = self.sk("technique")["params"][0]
        for e in self.enemies():
            self.battle.try_debuff(
                Modifier("Mold of Idolatry", stats={S.SPD_PCT: -p[2]}, duration=int(p[3]), kind=ModKind.DEBUFF),
                e,
                self.char,
                p[1],
            )

    # ------------------------------------------------------------ traces
    def summation(self, n: int) -> None:
        """A2: stacks accumulate per Skill (one per debuff on the target) and are kept.
        approximation: no expiry (the trace text gives no duration)."""
        n = min(n, self.summation_max)
        if n <= 0:
            return
        self.buff_self(
            Modifier(
                "Summation",
                stats={S.CRIT_RATE: self.tp(1, 0), S.CRIT_DMG: self.tp(1, 1)},
                stacks=n,
                max_stacks=self.summation_max,
                stacking=Stacking.STACK,
                tick=Tick.NONE,
                key="Summation",
            )
        )

    def _deduction(self, ev: E.Ev) -> None:
        h = ev.hit
        n = len(h.target.debuffs)
        if h.attacker is self.char and n >= self.tp(3, 0):
            h.add(S.DMG_PCT, min(self.tp(3, 2), self.tp(3, 1) * n))

    # ------------------------------------------------------------ talent
    def _fua(self, target: Enemy) -> None:
        t: Enemy | None = target
        if t is None or not t.alive or t.hp <= 0:
            alive = [e for e in self.enemies() if e.hp > 0]
            t = self.battle.rng.choice(alive) if alive else None
        if t is None:
            return
        with self.action(ActionKind.FUA, "talent", t) as act:
            act.hit(t, self.p("talent", 0), toughness=self.toughness("talent"))
            if self.e(2):
                for _ in range(min(int(self.ep(2, 1)), len(t.debuffs))):
                    self.battle.additional_damage(
                        self.char, t, self.ep(2, 0), element=Element.IMAGINARY, label="The Divine Is in the Details"
                    )
        if self.e(4):
            self.battle.gain_energy(self.char, self.ep(4, 0))

    def queue_fua(self, target: Enemy) -> None:
        self.battle.queue_action(lambda: self._fua(target), self.char, "Dr. Ratio follow-up")

    def _wiseman(self, ev: E.Ev) -> None:
        act = ev.attack
        t = self.folly_target
        owner = act.owner
        if t is None or self.folly_left <= 0 or not isinstance(owner, Character) or owner is self.char:
            return
        if t in act.attacked and t.alive and t.hp > 0:
            self.folly_left -= 1
            self.queue_fua(t)

    # ----------------------------------------------------------- actions
    def basic(self, target: Enemy | None) -> None:
        assert target is not None
        self.simple_basic(target)

    def skill(self, target: Enemy | None) -> None:
        assert target is not None
        with self.action(ActionKind.SKILL, "skill", target) as act:
            if self.trace(1):
                self.summation(len(target.debuffs))
            act.hit(target, self.p("skill", 0), toughness=self.toughness("skill"))
            if self.trace(2) and target.alive:
                self.battle.try_debuff(
                    Modifier(
                        "Inference",
                        stats={S.EFFECT_RES: -self.tp(2, 1)},
                        duration=int(self.tp(2, 2)),
                        kind=ModKind.DEBUFF,
                    ),
                    target,
                    self.char,
                    self.tp(2, 0),
                )
        chance = self.p("talent", 1) + self.p("talent", 2) * len(target.debuffs)  # fixed chance
        if chance >= 1.0 or self.battle.rng.random() < chance:
            self.queue_fua(target)

    def ult(self, target: Enemy | None) -> None:
        assert target is not None
        with self.action(ActionKind.ULT, "ult", target) as act:
            act.hit(target, self.p("ult", 0), toughness=self.toughness("ult"))
        # approximation: Wiseman's Folly is tracked on the kit and is not counted as a debuff
        self.folly_target = target
        self.folly_left = int(self.p("ult", 1)) + (int(self.ep(6, 0)) if self.e(6) else 0)
