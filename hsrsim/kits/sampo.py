"""Sampo (桑博) — Nihility / Wind. Stacking Wind Shear on every hit, DoT vulnerability ultimate.

Options: ``rotation`` (``"skill"`` default / ``"basic"``).
"""

from __future__ import annotations

from .. import events as E
from .. import stats as S
from ..battle import Battle
from ..entities import Enemy, Entity
from ..enums import ActionKind, DmgTag, Element
from ..modifiers import DotModifier, Modifier, ModKind, Stacking
from . import register
from .base import Kit

ATTACK_KINDS = (ActionKind.BASIC, ActionKind.SKILL, ActionKind.ULT, ActionKind.FUA)
WIND_SHEAR = "Wind Shear (Sampo)"
WS_TAG = "wind_shear_sampo"
# approximation: bounce hits after the first reduce half the Toughness of the first (game ability config;
# not in the skill data)
BOUNCE_TOUGHNESS_RATIO = 0.5


@register
class Sampo(Kit):
    char_id = "1108"

    def setup(self) -> None:
        self.on(E.AFTER_HIT, self._talent)
        if self.trace(3):
            self.passive("Spice Up", {}, dyn=self._a6, dyn_keys={S.MITIGATION})
        if self.e(2):
            self.on(E.KILL, self._e2)

    def technique(self) -> None:
        p = self.sk("technique")["params"][0]
        if self.battle.rng.random() < p[0]:  # fixed chance
            for e in self.enemies():
                self.battle.delay(e, p[1])

    # -------------------------------------------------------- Wind Shear
    def ws_mult(self) -> float:
        return self.p("talent", 1) + (self.ep(6, 0) if self.e(6) else 0.0)

    def wind_shear(self, target: Enemy, chance: float, stacks: int = 1) -> None:
        sampo = self.char

        def dmg(mod: DotModifier, b: Battle, ratio: float) -> float:
            return b.dot_damage(
                sampo,
                target,
                Element.WIND,
                self.ws_mult() * mod.stacks,
                label=WIND_SHEAR,
                tags=(DmgTag.DOT, "wind_shear"),
                ratio=ratio,
            )

        dur = int(self.p("talent", 2)) + (int(self.tp(1, 0)) if self.trace(1) else 0)
        mod = DotModifier(
            WIND_SHEAR,
            dot_type="wind_shear",
            damage_fn=dmg,
            duration=dur,
            stacks=stacks,
            max_stacks=int(self.p("talent", 3)),
            stacking=Stacking.STACK,
            tags={WS_TAG},
        )
        self.battle.try_debuff(mod, target, sampo, chance)

    def ws_stacks(self, e: Entity) -> int:
        return sum(m.stacks for m in e.mods(WIND_SHEAR) if m.source is self.char)

    # ------------------------------------------------------------ talent
    def _talent(self, ev: E.Ev) -> None:
        hit = ev.hit
        act = hit.action
        if act is None or act.owner is not self.char or act.kind not in ATTACK_KINDS:
            return
        if hit.target.hp > 0:
            self.wind_shear(hit.target, self.p("talent", 0))

    def _a6(self, mod: Modifier, key: str, ent: Entity) -> float:
        act = self.battle.current_action
        if act is not None and act.kind == ActionKind.ENEMY and self.ws_stacks(act.actor) > 0:
            return self.tp(3, 0)
        return 0.0

    def _e2(self, ev: E.Ev) -> None:
        if self.ws_stacks(ev.target) <= 0:
            return
        for e in self.enemies():
            if e is not ev.target and e.hp > 0:
                self.wind_shear(e, self.ep(2, 0), stacks=int(self.ep(2, 1)))

    # ----------------------------------------------------------- actions
    def basic(self, target: Enemy | None) -> None:
        assert target is not None
        self.simple_basic(target)

    def _skill_hit(self, act: object, t: Enemy, tough: float, primary: bool) -> None:
        from ..battle import Action

        assert isinstance(act, Action)
        act.hit(t, self.p("skill", 1), toughness=tough, primary=primary)
        if self.e(4) and t.hp > 0 and self.ws_stacks(t) >= self.ep(4, 0):
            self.battle.detonate(t, self.ep(4, 1), kinds=(WS_TAG,))

    def skill(self, target: Enemy | None) -> None:
        assert target is not None
        n = 1 + int(self.p("skill", 0)) + (int(self.ep(1, 0)) if self.e(1) else 0)
        energy = float(self.sk("skill")["energy"]) * n  # bounce skills regenerate Energy per hit
        tough = self.toughness("skill")
        with self.action(ActionKind.SKILL, "skill", target, energy=energy) as act:
            self._skill_hit(act, target, tough, True)
            for _ in range(n - 1):
                pool = [e for e in self.enemies() if e.hp > 0] or self.enemies()
                if not pool:
                    break
                self._skill_hit(act, self.battle.rng.choice(pool), tough * BOUNCE_TOUGHNESS_RATIO, False)

    def ult(self, target: Enemy | None) -> None:
        with self.action(ActionKind.ULT, "ult", target) as act:
            act.aoe(self.p("ult", 0), toughness=self.toughness("ult", 1), main_target=target, splits="data")
            for e in [e for e in self.enemies() if e.hp > 0]:
                self.battle.try_debuff(
                    Modifier(
                        "Surprise Present",
                        stats={f"{S.VULN}:{DmgTag.DOT}": self.p("ult", 1)},
                        duration=int(self.p("ult", 2)),
                        kind=ModKind.DEBUFF,
                    ),
                    e,
                    self.char,
                    self.p("ult", 3),
                )
            if self.trace(2):
                act.energy += self.tp(2, 0)
