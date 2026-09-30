"""Welt (瓦尔特) — Nihility / Imaginary. Bouncing Slow Skill, AoE Imprison ultimate, Additional DMG vs Slowed.

Base kit only (the enhanced kit is not implemented yet). Options: ``rotation`` (``"skill"`` / ``"basic"``).
"""

from __future__ import annotations

from .. import events as E
from .. import stats as S
from ..entities import Enemy
from ..enums import ActionKind, Element
from ..modifiers import Modifier, ModKind, Stacking
from . import register, register_enhanced
from .base import Kit
from .dan_heng import is_slowed

# Skill: "additionally deals 2 instances of DMG" / E6: "deals DMG for 1 extra time" (literals in the text)
SKILL_EXTRA_BOUNCES = 2
E6_EXTRA_BOUNCES = 1
# Ultimate / Technique: "Imprisoned for 1 turn" (literal in the text)
IMPRISON_TURNS = 1


@register
class Welt(Kit):
    char_id = "1004"

    def setup(self) -> None:
        if self.char.enhanced:
            raise NotImplementedError("Welt enhanced kit is not implemented yet")
        self.e1_left = 0
        self._slowed_hits: set[int] = set()
        self.on(E.BEFORE_HIT, self._before_hit)
        self.on(E.AFTER_HIT, self._after_hit)

    def technique(self) -> None:
        p = self.sk("technique")["params"][0]
        for e in self.enemies():
            self.imprison(e, p[0], p[1], p[2])

    # ------------------------------------------------------------ helpers
    def imprison(self, target: Enemy, chance: float, delay: float, slow: float) -> None:
        mod = Modifier(
            "Imprisoned (Welt)",
            stats={S.SPD_PCT: -slow},
            duration=IMPRISON_TURNS,
            kind=ModKind.DEBUFF,
            tags={"cc", "imprisonment"},
            skip_first_tick=False,  # LifeStepImmediately
        )
        if self.battle.try_debuff(mod, target, self.char, chance, debuff_type="imprisonment") is not None:
            self.battle.delay(target, delay)

    def slow(self, target: Enemy) -> None:
        chance = self.p("skill", 1) + (self.ep(4, 0) if self.e(4) else 0.0)
        self.battle.try_debuff(
            Modifier(
                "Slow (Welt)",
                stats={S.SPD_PCT: -self.p("skill", 2)},
                duration=int(self.p("skill", 3)),
                kind=ModKind.DEBUFF,
                tags={"slow"},
            ),
            target,
            self.char,
            chance,
        )

    def _e1_extra(self, target: Enemy, mult: float) -> None:
        if self.e1_left <= 0:
            return
        self.e1_left -= 1
        if target.hp > 0:
            self.battle.additional_damage(self.char, target, mult, element=Element.IMAGINARY, label="Legacy of Honor")

    # ------------------------------------------------------------ talent
    def _before_hit(self, ev: E.Ev) -> None:
        hit = ev.hit
        if hit.attacker is not self.char:
            return
        if self.trace(3) and hit.target.broken:
            hit.add(S.DMG_PCT, self.tp(3, 0))
        if hit.action is not None and is_slowed(hit.target):  # "already Slowed" before this hit
            self._slowed_hits.add(id(hit))

    def _after_hit(self, ev: E.Ev) -> None:
        hit = ev.hit
        if id(hit) not in self._slowed_hits:
            return
        self._slowed_hits.discard(id(hit))
        if hit.target.hp <= 0:
            return
        self.battle.additional_damage(
            self.char, hit.target, self.p("talent", 0), element=Element.IMAGINARY, label="Time Distortion"
        )
        if self.e(2):
            self.battle.gain_energy(self.char, self.ep(2, 0))

    # ----------------------------------------------------------- actions
    def basic(self, target: Enemy | None) -> None:
        assert target is not None
        with self.action(ActionKind.BASIC, "basic", target) as act:
            act.hit(target, self.p("basic", 0), toughness=self.toughness("basic"), splits="data")
            if self.e(1):
                self._e1_extra(target, self.ep(1, 0) * self.p("basic", 0))

    def skill(self, target: Enemy | None) -> None:
        assert target is not None
        n = 1 + SKILL_EXTRA_BOUNCES + (E6_EXTRA_BOUNCES if self.e(6) else 0)
        energy = float(self.sk("skill")["energy"]) * n  # bounce skills regenerate Energy per hit
        with self.action(ActionKind.SKILL, "skill", target, energy=energy) as act:
            for i in range(n):
                if i == 0:
                    t = target
                else:
                    pool = [e for e in self.enemies() if e.hp > 0] or self.enemies()
                    if not pool:
                        break
                    t = self.battle.rng.choice(pool)
                act.hit(t, self.p("skill", 0), toughness=self.toughness("skill"), primary=i == 0)
                if t.hp > 0:
                    self.slow(t)
            if self.e(1):
                self._e1_extra(target, self.ep(1, 1) * self.p("skill", 0))

    def ult(self, target: Enemy | None) -> None:
        with self.action(ActionKind.ULT, "ult", target) as act:
            act.aoe(self.p("ult", 0), toughness=self.toughness("ult", 1), main_target=target, splits="data")
            for e in [e for e in self.enemies() if e.hp > 0]:
                self.imprison(e, self.p("ult", 2), self.p("ult", 1), self.p("ult", 3))
                if self.trace(1):
                    self.battle.try_debuff(
                        Modifier(
                            "Retribution",
                            stats={S.VULN: self.tp(1, 1)},
                            duration=int(self.tp(1, 2)),
                            kind=ModKind.DEBUFF,
                        ),
                        e,
                        self.char,
                        self.tp(1, 0),
                    )
            if self.trace(2):
                act.energy += self.tp(2, 0)
        if self.e(1):
            self.e1_left = int(self.ep(1, 2))


ENHANCED_SKILL_EXTRA_BOUNCES = 4  # enhanced Skill: "additionally deals DMG 4 times" (literal in the text)


@register_enhanced
class WeltEnhanced(Welt):
    """Enhanced Welt: "Weightless" (DEF shred, delay on hit), team DMG stacks, EHR-to-ATK, Additional DMG."""

    def setup(self) -> None:
        self.weightless_hits: dict[tuple[int, int], int] = {}
        self.on(E.BEFORE_HIT, self._before_hit_enh)
        self.on(E.AFTER_HIT, self._after_hit)
        self.on(E.ATTACK_END, self._on_attack)
        self._slowed_hits = set()
        if self.trace(3):
            self.passive("Punishment", {}, dyn=self._a6, dyn_keys={S.ATK_PCT})

    def on_battle_start(self) -> None:
        if self.trace(1):
            self.battle.gain_energy(self.char, self.tp(1, 3), fixed=True)

    def _a6(self, mod: Modifier, key: str, ent: object) -> float:
        over = self.char.stat(S.EHR) - self.tp(3, 0)
        return min(self.tp(3, 3), int(over / self.tp(3, 1) + 1e-9) * self.tp(3, 2)) if over > 0 else 0.0

    def _before_hit_enh(self, ev: E.Ev) -> None:
        hit = ev.hit
        if hit.attacker is not self.char:
            return
        if hit.action is not None and is_slowed(hit.target):
            self._slowed_hits.add(id(hit))
            if self.e(6) and hit.action.kind in (ActionKind.SKILL, ActionKind.ULT):
                hit.add(S.CRIT_RATE, self.ep(6, 0))
                hit.add(S.CRIT_DMG, self.ep(6, 1))

    def _on_attack(self, ev: E.Ev) -> None:
        act = ev.attack
        owner = act.owner
        if owner is None or owner.side != self.char.side:
            return
        for t in act.attacked:
            if not t.alive or not t.has_mod("Weightless"):
                continue
            key = (self.battle.turns, t.uid)
            if self.weightless_hits.get(key, 0) < self.p("ult", 5):
                self.weightless_hits[key] = self.weightless_hits.get(key, 0) + 1
                self.battle.delay(t, self.p("ult", 4))
            if self.trace(1):
                self.battle.apply(
                    Modifier(
                        "Retribution",
                        stats={S.DMG_PCT: self.tp(1, 0)},
                        duration=int(self.tp(1, 2)),
                        stacking=Stacking.STACK,
                        max_stacks=int(self.tp(1, 1)),
                    ),
                    owner,
                    self.char,
                )

    def _e1_weightless(self, act: object, targets: list[Enemy]) -> None:
        if not self.e(1):
            return
        for t in targets:
            if t.alive and t.hp > 0 and t.has_mod("Weightless"):
                self.battle.additional_damage(
                    self.char, t, self.ep(1, 0) * self.p("ult", 0), element=Element.IMAGINARY, label="Legacy of Honor"
                )

    def basic(self, target: Enemy | None) -> None:
        assert target is not None
        with self.action(ActionKind.BASIC, "basic", target) as act:
            act.hit(target, self.p("basic", 0), toughness=self.toughness("basic"), splits="data")
            if self.trace(2) and target.hp > 0:
                self.battle.additional_damage(
                    self.char, target, self.tp(2, 0) * self.p("basic", 0), element=Element.IMAGINARY, label="Judgment"
                )

    def skill(self, target: Enemy | None) -> None:
        assert target is not None
        n = 1 + ENHANCED_SKILL_EXTRA_BOUNCES
        energy = float(self.sk("skill")["energy"]) * n  # bounce skills regenerate Energy per hit
        with self.action(ActionKind.SKILL, "skill", target, energy=energy) as act:
            for i in range(n):
                if i == 0:
                    t = target
                else:
                    pool = [e for e in self.enemies() if e.hp > 0] or self.enemies()
                    if not pool:
                        break
                    t = self.battle.rng.choice(pool)
                act.hit(t, self.p("skill", 0), toughness=self.toughness("skill"), primary=i == 0)
                if t.hp > 0:
                    self.slow(t)
            if self.trace(2) and target.hp > 0:
                self.battle.additional_damage(
                    self.char, target, self.tp(2, 1) * self.p("skill", 0), element=Element.IMAGINARY, label="Judgment"
                )
            self._e1_weightless(act, list(act.attacked))

    def slow(self, target: Enemy) -> None:
        self.battle.try_debuff(
            Modifier(
                "Slow (Welt)",
                stats={S.SPD_PCT: -self.p("skill", 2)},
                duration=int(self.p("skill", 3)),
                kind=ModKind.DEBUFF,
                tags={"slow"},
            ),
            target,
            self.char,
            self.p("skill", 1),
        )

    def ult(self, target: Enemy | None) -> None:
        with self.action(ActionKind.ULT, "ult", target) as act:
            act.aoe(self.p("ult", 0), toughness=self.toughness("ult", 1), main_target=target, splits="data")
            for e in [e for e in self.enemies() if e.hp > 0]:
                self.imprison(e, self.p("ult", 2), self.p("ult", 1), self.p("ult", 3))
            self._e1_weightless(act, list(act.attacked))
            stats = {S.DEF_REDUCTION: self.p("talent", 1), S.SPD_PCT: -self.p("talent", 2)}
            if self.e(4):
                stats[S.RES_REDUCTION] = self.ep(4, 0)
            for e in [e for e in self.enemies() if e.hp > 0]:
                self.battle.apply(
                    Modifier(
                        "Weightless",
                        stats=stats,
                        duration=int(self.p("ult", 6)),
                        kind=ModKind.DEBUFF,
                        tags={"slow"},
                        key="Weightless",
                    ),
                    e,
                    self.char,
                )
            if self.trace(3):
                act.energy += self.tp(3, 4)
