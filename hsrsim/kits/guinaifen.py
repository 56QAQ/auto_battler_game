"""Guinaifen (桂乃芬) — Nihility / Fire. Burn DoT, Burn detonation and Firekiss (DMG taken) on Burn ticks.

Options (``default_opts``):
* ``rotation``: ``"skill"`` (default: Skill whenever SP allows) or ``"basic"``.
"""

from __future__ import annotations

from .. import events as E
from .. import stats as S
from ..battle import Battle
from ..entities import Enemy
from ..enums import ActionKind, DmgTag, Element
from ..modifiers import DotModifier, Modifier, ModKind, Stacking
from . import register
from .base import Kit

BURN = "Burn (Guinaifen)"


@register
class Guinaifen(Kit):
    char_id = "1210"
    default_opts = {"rotation": "skill"}

    def setup(self) -> None:
        self.on(E.DOT_TRIGGERED, self._on_dot)
        if self.trace(3):
            self.on(E.BEFORE_HIT, self._a6)

    def on_battle_start(self) -> None:
        if self.trace(2):
            self.battle.advance(self.char, self.tp(2, 0))

    def technique(self) -> None:
        p = self.sk("technique")["params"][0]
        # approximation: the in-battle hits of the Technique reduce no Toughness (none is given in the data)
        with self.action(ActionKind.EXTRA, None, label="Skill Showcase", energy=0, sp=0) as act:
            for _ in range(int(p[1])):
                hits = act.bounce(None, 1, p[0])
                for h in hits:
                    if h.target.alive:
                        self.firekiss(h.target, p[2])

    # ------------------------------------------------------------ burn
    def burn(self, target: Enemy, chance: float) -> None:
        mult = self.p("skill", 3)
        if self.e(2) and target.has_tag("burn"):
            mult += self.ep(2, 0)
        gui = self.char

        def dmg(mod: DotModifier, b: Battle, ratio: float) -> float:
            d = b.dot_damage(
                gui, target, Element.FIRE, mod.data["mult"], label=BURN, tags=(DmgTag.DOT, "burn"), ratio=ratio
            )
            if self.e(4):
                b.gain_energy(gui, self.ep(4, 0))
            return d

        mod = DotModifier(BURN, dot_type="burn", damage_fn=dmg, duration=int(self.p("skill", 4)))
        mod.data["mult"] = mult
        self.battle.try_debuff(mod, target, gui, chance)

    def firekiss(self, target: Enemy, chance: float) -> None:
        max_stacks = int(self.p("talent", 5)) + (int(self.ep(6, 0)) if self.e(6) else 0)
        self.battle.try_debuff(
            Modifier(
                "Firekiss",
                stats={S.VULN: self.p("talent", 3)},
                duration=int(self.p("talent", 4)),
                kind=ModKind.DEBUFF,
                stacking=Stacking.STACK,
                max_stacks=max_stacks,
                key="Firekiss",
            ),
            target,
            self.char,
            chance,
        )

    def _on_dot(self, ev: E.Ev) -> None:
        # any Burn (incl. other characters' and Weakness Break Burn) causing DMG, also when detonated
        t = ev.target
        if "burn" in ev.mod.tags and isinstance(t, Enemy) and t.alive and t.hp > 0:
            self.firekiss(t, self.p("talent", 0))

    def _a6(self, ev: E.Ev) -> None:
        hit = ev.hit
        if hit.attacker is self.char and hit.target.has_tag("burn"):
            hit.add(S.DMG_PCT, self.tp(3, 0))

    # ------------------------------------------------------------ actions
    def basic(self, target: Enemy | None) -> None:
        assert target is not None
        with self.action(ActionKind.BASIC, "basic", target) as act:
            act.hit(target, self.p("basic", 0), toughness=self.toughness("basic"))
            if self.trace(1) and target.alive:
                self.burn(target, self.tp(1, 0))

    def skill(self, target: Enemy | None) -> None:
        assert target is not None
        with self.action(ActionKind.SKILL, "skill", target) as act:
            hits = act.blast(
                target,
                self.p("skill", 0),
                self.p("skill", 1),
                toughness=(self.toughness("skill", 0), self.toughness("skill", 2)),
            )
            for t in dict.fromkeys(h.target for h in hits):
                if not t.alive:
                    continue
                if self.e(1):
                    self.battle.try_debuff(
                        Modifier(
                            "Slurping Noodles During Handstand",
                            stats={S.EFFECT_RES: -self.ep(1, 1)},
                            duration=int(self.ep(1, 2)),
                            kind=ModKind.DEBUFF,
                        ),
                        t,
                        self.char,
                        self.ep(1, 0),
                    )
                self.burn(t, self.p("skill", 2))

    def ult(self, target: Enemy | None) -> None:
        with self.action(ActionKind.ULT, "ult", target) as act:
            act.aoe(self.p("ult", 0), toughness=self.toughness("ult", 1), main_target=target)
            for e in self.enemies():
                if e.has_tag("burn"):
                    self.battle.detonate(e, self.p("ult", 1), kinds=("burn",))
