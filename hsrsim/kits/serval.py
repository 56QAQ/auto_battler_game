"""Serval (希露瓦) — Erudition / Lightning. Blast Shock Skill, Additional DMG to every Shocked enemy after attacking.

Options: ``rotation`` (``"skill"`` default / ``"basic"``).
"""

from __future__ import annotations

from .. import events as E
from .. import stats as S
from ..battle import Battle
from ..entities import Enemy
from ..enums import ActionKind, DmgTag, Element
from ..modifiers import DotModifier, Modifier
from . import register
from .base import Kit

ATTACK_KINDS = (ActionKind.BASIC, ActionKind.SKILL, ActionKind.ULT, ActionKind.FUA)
SHOCK = "Shock (Serval)"


@register
class Serval(Kit):
    char_id = "1103"

    def setup(self) -> None:
        self.on(E.ATTACK_END, self._talent)
        if self.trace(3):
            self.on(E.KILL, self._a6)
        if self.e(6):
            self.on(E.BEFORE_HIT, self._e6)

    def on_battle_start(self) -> None:
        if self.trace(2):
            self.battle.gain_energy(self.char, self.tp(2, 0), fixed=True)

    def technique(self) -> None:
        p = self.sk("technique")["params"][0]
        alive = self.enemies()
        if not alive:
            return
        with self.action(ActionKind.EXTRA, None, label="Serval Technique", energy=0, sp=0) as act:
            # not modelled: Toughness reduction of the overworld attack that starts the battle
            act.hit(self.battle.rng.choice(alive), p[3])
            for e in self.enemies():
                self.shock(e, p[0], int(p[2]), p[1])

    # ------------------------------------------------------------- shock
    def shock(self, target: Enemy, chance: float, turns: int, mult: float) -> None:
        serval = self.char

        def dmg(mod: DotModifier, b: Battle, ratio: float) -> float:
            return b.dot_damage(
                serval, target, Element.LIGHTNING, mult, label=SHOCK, tags=(DmgTag.DOT, "shock"), ratio=ratio
            )

        self.battle.try_debuff(
            DotModifier(SHOCK, dot_type="shock", damage_fn=dmg, duration=turns), target, serval, chance
        )

    def skill_shock(self, target: Enemy, chance: float) -> None:
        self.shock(target, chance, int(self.p("skill", 3)), self.p("skill", 4))

    def _own_shock(self, e: Enemy) -> DotModifier | None:
        for m in e.mods(SHOCK):
            if m.source is self.char and isinstance(m, DotModifier):
                return m
        return None

    # ------------------------------------------------------------ talent
    def _talent(self, ev: E.Ev) -> None:
        act = ev.attack
        if act.owner is not self.char or act.kind not in ATTACK_KINDS:
            return
        shocked = [e for e in self.enemies() if e.hp > 0 and e.has_tag("shock")]
        for e in shocked:
            self.battle.additional_damage(
                self.char, e, self.p("talent", 0), element=Element.LIGHTNING, label="Galvanic Chords"
            )
        if shocked and self.e(2):  # approximation: once per Talent trigger (not per enemy)
            self.battle.gain_energy(self.char, self.ep(2, 0))

    def _a6(self, ev: E.Ev) -> None:
        if ev.killer is self.char:
            self.buff_self(Modifier("Mania", stats={S.ATK_PCT: self.tp(3, 0)}, duration=int(self.tp(3, 1))))

    def _e6(self, ev: E.Ev) -> None:
        hit = ev.hit
        if hit.attacker is self.char and hit.target.has_tag("shock"):
            hit.add(S.DMG_PCT, self.ep(6, 0))

    # ----------------------------------------------------------- actions
    def basic(self, target: Enemy | None) -> None:
        assert target is not None
        with self.action(ActionKind.BASIC, "basic", target) as act:
            act.hit(target, self.p("basic", 0), toughness=self.toughness("basic"), splits="data")
            if self.e(1):
                adj = [e for e in self.battle.adjacent(target) if e.hp > 0]
                if adj:
                    act.hit(self.battle.rng.choice(adj), self.p("basic", 0) * self.ep(1, 0), primary=False)

    def skill(self, target: Enemy | None) -> None:
        assert target is not None
        with self.action(ActionKind.SKILL, "skill", target) as act:
            hits = act.blast(
                target,
                self.p("skill", 0),
                self.p("skill", 1),
                toughness=(self.toughness("skill", 0), self.toughness("skill", 2)),
                splits="data",
            )
            chance = self.p("skill", 2) + (self.tp(1, 0) if self.trace(1) else 0.0)
            for t in dict.fromkeys(h.target for h in hits):
                if t.hp > 0:
                    self.skill_shock(t, chance)

    def ult(self, target: Enemy | None) -> None:
        with self.action(ActionKind.ULT, "ult", target) as act:
            if self.e(4):
                # the ability script Shocks the non-Shocked enemies before the damage (so E6 and the extension
                # below already apply to them)
                for e in [e for e in self.enemies() if e.hp > 0 and not e.has_tag("shock")]:
                    self.skill_shock(e, self.ep(4, 0))
            act.aoe(self.p("ult", 0), toughness=self.toughness("ult", 1), main_target=target, splits="data")
            for e in [e for e in self.enemies() if e.hp > 0]:
                own = self._own_shock(e)
                if own is not None:
                    # approximation: only Serval's own Shock is extended
                    own.duration = (own.duration or 0) + int(self.p("ult", 1))
