"""Kafka (卡芙卡) — Nihility / Lightning. Shock DoT, DoT detonation, follow-up on allies' Basic ATK.

Base kit only (the enhanced kit is not implemented yet).
"""

from __future__ import annotations

from .. import events as E
from .. import stats as S
from ..battle import Battle
from ..entities import Character, Enemy, Entity
from ..enums import ActionKind, DmgTag, Element
from ..modifiers import DotModifier, Modifier, ModKind
from . import register, register_enhanced
from .base import Kit


@register
class Kafka(Kit):
    char_id = "1005"

    def setup(self) -> None:
        self.fua_ready = True
        # M_Kafka_Passive re-arms the follow-up in Kafka's own turn-end phase (OnPhase2)
        self.on(E.TURN_END, self._rearm)
        self.on(E.ACTION_END, self._talent)
        if self.trace(2):
            self.on(E.KILL, self._a4)
        if self.e(2):
            self.passive("Fortississimo", {f"{S.DMG_PCT}:{DmgTag.DOT}": self.ep(2, 0)}, scope=self.ally_scope)

    def technique(self) -> None:
        p = self.sk("technique")["params"][0]
        with self.action(ActionKind.EXTRA, None, label="Kafka Technique", energy=0, sp=0) as act:
            act.aoe(p[2])
            for e in self.enemies():
                self.shock(e, p[0])

    def _rearm(self, ev: E.Ev) -> None:
        if ev.entity is self.char:
            self.fua_ready = True

    # ------------------------------------------------------------- shock
    def shock_mult(self) -> float:
        return self.p("ult", 3) + (self.ep(6, 0) if self.e(6) else 0.0)

    def _shock_bonus(self) -> float:
        """A6 "Thorns" (base kit) raises the Shock base chance."""
        return self.tp(3, 0) if self.trace(3) else 0.0

    def shock(self, target: Enemy, base_chance: float) -> None:
        chance = base_chance + self._shock_bonus()
        kafka = self.char

        def dmg(mod: DotModifier, b: Battle, ratio: float) -> float:
            d = b.dot_damage(
                kafka,
                target,
                Element.LIGHTNING,
                self.shock_mult(),
                label="Shock (Kafka)",
                tags=(DmgTag.DOT, "shock"),
                ratio=ratio,
            )
            if self.e(4):
                b.gain_energy(kafka, self.ep(4, 0))
            return d

        dur = int(self.p("ult", 2)) + (int(self.ep(6, 1)) if self.e(6) else 0)
        self.battle.try_debuff(
            DotModifier("Shock (Kafka)", dot_type="shock", damage_fn=dmg, duration=dur), target, self.char, chance
        )

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
                self.p("skill", 2),
                toughness=(self.toughness("skill", 0), self.toughness("skill", 2)),
            )
            if target.alive and target.has_tag("dot"):
                self.battle.detonate(target, self.p("skill", 1))

    def ult(self, target: Enemy | None) -> None:
        with self.action(ActionKind.ULT, "ult", target) as act:
            act.aoe(self.p("ult", 0), toughness=self.toughness("ult", 1), main_target=target)
            for e in self.enemies():
                self.shock(e, self.p("ult", 1))
                if self.trace(1):
                    self.battle.detonate(e, self.p("ult", 4))
                else:
                    self.battle.detonate(e, self.p("ult", 4), kinds=("shock",))

    # ------------------------------------------------------------- talent
    def _talent(self, ev: E.Ev) -> None:
        act = ev.action
        owner = act.owner
        if not self.fua_ready or act.kind != ActionKind.BASIC or owner is self.char:
            return
        if not isinstance(owner, Character) or not act.attacked:
            return
        target = act.attacked[0]
        self.fua_ready = False

        def fua() -> None:
            t = target if target.alive else self.battle.default_target()
            if t is None:
                return
            with self.action(ActionKind.FUA, "talent", t) as a:
                a.hit(t, self.p("talent", 0), toughness=self.toughness("talent"))
                if t.alive:
                    self.shock(t, self.p("talent", 1))
                    if self.e(1):
                        self.battle.try_debuff(
                            Modifier(
                                "Da Capo",
                                stats={f"{S.VULN}:{DmgTag.DOT}": self.ep(1, 1)},
                                duration=int(self.ep(1, 2)),
                                kind=ModKind.DEBUFF,
                            ),
                            t,
                            self.char,
                            self.ep(1, 0),
                        )

        self.battle.queue_action(fua, self.char, "Kafka follow-up")

    def _a4(self, ev: E.Ev) -> None:
        if any(m.name == "Shock (Kafka)" for m in ev.target.modifiers) or ev.target.has_tag("shock"):
            self.battle.gain_energy(self.char, self.tp(2, 0))


@register_enhanced
class KafkaEnhanced(Kafka):
    """Enhanced Kafka: follow-up after any teammate attack (charges), wider detonations, ATK for high-EHR allies."""

    def setup(self) -> None:
        self.charges = int(self.p("talent", 4))
        self.on(E.TURN_END, self._regain)
        self.on(E.ATTACK_END, self._talent_enh)
        if self.trace(1):
            self.passive("Torture", {}, scope=self.ally_scope, dyn=self._a2, dyn_keys={S.ATK_PCT})
        if self.trace(2):
            self.on(E.KILL, self._a4)
        if self.e(2):
            self.passive("Fortississimo", {f"{S.DMG_PCT}:{DmgTag.DOT}": self.ep(2, 0)}, scope=self.ally_scope)
        if self.e(1):
            self.on(E.ATTACK_END, self._e1_enh)

    def _a2(self, mod: Modifier, key: str, ent: Entity) -> float:
        return self.tp(1, 1) if ent.stat(S.EHR) >= self.tp(1, 0) - 1e-9 else 0.0

    def _shock_bonus(self) -> float:
        return 0.0  # the enhanced A6 does not change the Shock chance

    def _regain(self, ev: E.Ev) -> None:
        if ev.entity is self.char:
            self.charges = min(int(self.p("talent", 4)), self.charges + int(self.p("talent", 3)))

    def _e1_enh(self, ev: E.Ev) -> None:
        act = ev.attack
        if act.owner is not self.char:
            return
        for t in act.attacked:
            if t.alive:
                self.battle.try_debuff(
                    Modifier(
                        "Da Capo",
                        stats={f"{S.VULN}:{DmgTag.DOT}": self.ep(1, 1)},
                        duration=int(self.ep(1, 2)),
                        kind=ModKind.DEBUFF,
                    ),
                    t,
                    self.char,
                    self.ep(1, 0),
                )

    def skill(self, target: Enemy | None) -> None:
        assert target is not None
        with self.action(ActionKind.SKILL, "skill", target) as act:
            adjs = self.battle.adjacent(target)
            act.blast(
                target,
                self.p("skill", 0),
                self.p("skill", 2),
                toughness=(self.toughness("skill", 0), self.toughness("skill", 2)),
            )
            if target.alive and target.has_tag("dot"):
                self.battle.detonate(target, self.p("skill", 1))
            for a in adjs:
                if a.alive and a.has_tag("dot"):
                    self.battle.detonate(a, self.p("skill", 3))

    def ult(self, target: Enemy | None) -> None:
        with self.action(ActionKind.ULT, "ult", target) as act:
            act.aoe(self.p("ult", 0), toughness=self.toughness("ult", 1), main_target=target)
            for e in self.enemies():
                self.shock(e, self.p("ult", 1))
                if e.has_tag("shock"):
                    self.battle.detonate(e, self.p("ult", 4))
        if self.trace(3):
            self.charges = min(int(self.p("talent", 4)), self.charges + 1)

    def _talent(self, ev: E.Ev) -> None:  # the base kit's Basic-ATK-only trigger is replaced
        return

    def _talent_enh(self, ev: E.Ev) -> None:
        act = ev.attack
        owner = act.owner
        if self.charges <= 0 or owner is self.char or not isinstance(owner, Character) or not act.attacked:
            return
        target = act.attacked[0]
        self.charges -= 1

        def fua() -> None:
            t = target if target.alive else self.battle.default_target()
            if t is None:
                return
            with self.action(ActionKind.FUA, "talent", t) as a:
                a.hit(t, self.p("talent", 0), toughness=self.toughness("talent"))
                if t.alive:
                    self.shock(t, self.p("talent", 1))
                    if self.trace(3):
                        self.battle.detonate(t, self.tp(3, 0))

        self.battle.queue_action(fua, self.char, "Kafka follow-up")
