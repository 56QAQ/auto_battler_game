"""Seele (希儿) — Hunt / Quantum. Extra turns on kill (Resurgence)."""

from __future__ import annotations

from .. import events as E
from .. import stats as S
from ..entities import Enemy
from ..enums import ActionKind
from ..modifiers import Modifier, ModKind, Stacking
from . import register, register_enhanced
from .base import Kit


@register
class Seele(Kit):
    char_id = "1102"

    def setup(self) -> None:
        self.in_resurgence = False
        self.on(E.ACTION_END, self._on_action_end)
        self.on(E.TURN_START, self._on_turn_start)
        self.on(E.TURN_END, self._on_turn_end)
        if self.e(1):
            self.on(E.BEFORE_HIT, self._e1)
        if self.e(4):
            self.on(E.KILL, lambda ev: ev.killer is self.char and self.battle.gain_energy(self.char, self.ep(4, 0)))
        if self.e(6):
            self.on(E.ATTACK_END, self._e6_trigger)

    def technique(self) -> None:
        self.amplify()

    # ------------------------------------------------------------ states
    def amplify(self) -> None:
        stats = {S.DMG_PCT: self.p("talent", 0)}
        if self.trace(2):
            stats[f"{S.RES_PEN}:Quantum"] = self.tp(2, 0)
        self.buff_self(Modifier("Amplification", stats=stats, duration=int(self.p("talent", 1))))

    # ----------------------------------------------------------- actions
    def basic(self, target: Enemy | None) -> None:
        assert target is not None
        self.simple_basic(target)
        if self.trace(3):
            self.battle.advance(self.char, self.tp(3, 0))

    def skill(self, target: Enemy | None) -> None:
        assert target is not None
        with self.action(ActionKind.SKILL, "skill", target) as act:
            self.buff_self(
                Modifier(
                    "Sheathed Blade",
                    stats={S.SPD_PCT: self.p("skill", 1)},
                    duration=int(self.p("skill", 2)),
                    stacking=Stacking.STACK,
                    max_stacks=int(self.ep(2, 0)) if self.e(2) else 1,
                )
            )
            act.hit(target, self.p("skill", 0), toughness=self.toughness("skill"), splits="data")

    def ult(self, target: Enemy | None) -> None:
        assert target is not None
        self.amplify()
        with self.action(ActionKind.ULT, "ult", target) as act:
            act.hit(target, self.p("ult", 0), toughness=self.toughness("ult"), splits="data")
        if self.e(6) and target.alive:
            self.battle.apply(Modifier("Butterfly Flurry", duration=1, kind=ModKind.DEBUFF), target, self.char)

    # ------------------------------------------------------------ talent
    def _on_action_end(self, ev: E.Ev) -> None:
        act = ev.action
        if act.owner is not self.char or act.kind not in (ActionKind.BASIC, ActionKind.SKILL, ActionKind.ULT):
            return
        if self.in_resurgence:
            return
        if any(t.hp <= 0 and t.alive for t in act.attacked):
            self.amplify()
            self.battle.queue_extra_turn(self.char)

    def _on_turn_start(self, ev: E.Ev) -> None:
        if ev.entity is self.char and ev.extra:
            self.in_resurgence = True

    def _on_turn_end(self, ev: E.Ev) -> None:
        if ev.entity is self.char and ev.extra:
            self.in_resurgence = False

    def _e1(self, ev: E.Ev) -> None:
        hit = ev.hit
        if hit.attacker is self.char and hit.target.hp_ratio <= self.ep(1, 0):
            hit.add(S.CRIT_RATE, self.ep(1, 1))

    def _e6_trigger(self, ev: E.Ev) -> None:
        for t in ev.attack.attacked:
            if t.has_mod("Butterfly Flurry") and t.hp > 0:
                self.battle.additional_damage(
                    self.char,
                    t,
                    self.ep(6, 0) * self.p("ult", 0),
                    label="E6 Butterfly Flurry",
                    tags=("additional",),
                )


@register_enhanced
class SeeleEnhanced(Seele):
    """Enhanced Seele: 3-turn Amplification, auto-Skill on low-HP targets, True DMG Butterfly Flurry (E6)."""

    def setup(self) -> None:
        super().setup()
        self.auto_ready = True
        self.last_ult_damage = 0.0
        self.on(E.ATTACK_END, self._auto_skill)
        if self.trace(1):
            self.on(E.KILL, self._nightshade)
        if self.e(1):
            self.on(E.BEFORE_HIT, self._e1_def)

    def _on_turn_start(self, ev: E.Ev) -> None:
        super()._on_turn_start(ev)
        if ev.entity is self.char:
            self.auto_ready = True

    def _nightshade(self, ev: E.Ev) -> None:
        self.buff_self(
            Modifier(
                "Nightshade",
                stats={S.DMG_PCT: self.tp(1, 0)},
                duration=int(self.tp(1, 2)),
                stacking=Stacking.STACK,
                max_stacks=int(self.tp(1, 1)),
            )
        )

    def _e1_def(self, ev: E.Ev) -> None:
        hit = ev.hit
        if hit.attacker is self.char and hit.target.hp_ratio <= self.ep(1, 0):
            hit.add(S.DEF_IGNORE, self.ep(1, 2))

    def _auto_skill(self, ev: E.Ev) -> None:
        act = ev.attack
        if not self.auto_ready or act.owner is None or act.owner.side != self.char.side or act.data.get("auto"):
            return
        hits = [t for t in act.attacked if t.alive and t.hp > 0 and t.hp_ratio <= self.p("skill", 3)]
        if not hits:
            return
        self.auto_ready = False
        target = hits[0]

        def auto() -> None:
            t = target if target.alive and target.hp > 0 else None
            if t is None:
                pool = [e for e in self.enemies() if e.hp > 0]
                if not pool:
                    return
                t = min(pool, key=lambda e: e.hp_ratio)
            self.skill(t, auto=True)

        self.battle.queue_action(auto, self.char, "Seele auto Skill")

    def skill(self, target: Enemy | None, auto: bool = False) -> None:
        assert target is not None
        kw = {"sp": 0, "energy": 0} if auto else {}
        with self.action(ActionKind.SKILL, "skill", target, **kw) as act:
            act.data["auto"] = auto
            self.buff_self(
                Modifier(
                    "Sheathed Blade",
                    stats={S.SPD_PCT: self.p("skill", 1)},
                    duration=int(self.p("skill", 2)),
                    stacking=Stacking.STACK,
                    max_stacks=int(self.ep(2, 0)) if self.e(2) else 1,
                )
            )
            act.hit(target, self.p("skill", 0), toughness=self.toughness("skill"), splits="data")

    def ult(self, target: Enemy | None) -> None:
        assert target is not None
        self.amplify()
        with self.action(ActionKind.ULT, "ult", target) as act:
            hits = act.hit(target, self.p("ult", 0), toughness=self.toughness("ult"), splits="data")
        self.last_ult_damage = sum(h.damage for h in hits)
        if self.e(6) and target.alive:
            self.battle.apply(
                Modifier("Butterfly Flurry", duration=int(self.ep(6, 1)), kind=ModKind.DEBUFF), target, self.char
            )

    def _e6_trigger(self, ev: E.Ev) -> None:
        for t in ev.attack.attacked:
            if t.has_mod("Butterfly Flurry") and t.hp > 0 and self.last_ult_damage > 0:
                self.battle.true_damage(self.last_ult_damage, self.ep(6, 0), t, self.char, "E6 Butterfly Flurry")

    def _on_action_end(self, ev: E.Ev) -> None:
        act = ev.action
        if self.in_resurgence:
            return
        mine = act.owner is self.char and act.kind in (ActionKind.BASIC, ActionKind.SKILL, ActionKind.ULT)
        flurry_kill = self.e(6) and any(t.hp <= 0 and t.alive and t.has_mod("Butterfly Flurry") for t in act.attacked)
        if (mine or flurry_kill) and any(t.hp <= 0 and t.alive for t in act.attacked):
            self.amplify()
            self.battle.queue_extra_turn(self.char)

    def technique(self) -> None:
        self.amplify()
        pool = self.enemies()
        if pool:
            with self.action(ActionKind.EXTRA, None, label="Seele Technique", energy=0, sp=0) as act:
                act.hit(self.battle.rng.choice(pool), self.p("skill", 0), extra={S.CRIT_RATE: 1.0})
