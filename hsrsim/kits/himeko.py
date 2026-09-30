"""Himeko (姬子) — Erudition / Fire. Charge from Weakness Breaks -> AoE follow-up (Victory Rush), Burn.

Options: ``rotation`` (``"skill"`` default / ``"basic"``).
"""

from __future__ import annotations

from .. import events as E
from .. import stats as S
from ..battle import Battle
from ..entities import Character, Enemy, Entity
from ..enums import ActionKind, DmgTag, Element, Side
from ..modifiers import DotModifier, Modifier, ModKind
from . import register
from .base import Kit

ATTACK_KINDS = (ActionKind.BASIC, ActionKind.SKILL, ActionKind.ULT, ActionKind.FUA, ActionKind.MEMOSPRITE)
# Talent: "gains 1 point of Charge" per Weakness Break and "At the start of the battle, Himeko gains 1 point"
CHARGE_PER_BREAK = 1
START_CHARGE = 1
# E6: "Ultimate deals 2 extra instances of Fire DMG" (literal in the text)
E6_EXTRA_HITS = 2
# Victory Rush hit splits from the ability script (Passive1Atk02_Ability: a loop of split=0.2 AoE hits, then one of
# 0.4 -> 3 x 0.2 + 0.4; AoE splits are not in the data snapshot)
FUA_SPLITS = [0.2, 0.2, 0.2, 0.4]


@register
class Himeko(Kit):
    char_id = "1003"

    def setup(self) -> None:
        self.charge = 0
        self.fua_pending = False
        self.on(E.BREAK, self._on_break)
        self.on(E.ATTACK_END, self._on_attack_end)
        self.on(E.BEFORE_HIT, self._before_hit)
        if self.trace(3):
            self.passive("Benchmark", {}, dyn=self._a6, dyn_keys={S.CRIT_RATE})

    def on_battle_start(self) -> None:
        self.gain_charge(START_CHARGE)

    def technique(self) -> None:
        p = self.sk("technique")["params"][0]
        for e in self.enemies():
            self.battle.try_debuff(
                Modifier(
                    "Incomplete Combustion",
                    stats={f"{S.VULN}:{Element.FIRE.value}": p[1]},
                    duration=int(p[2]),
                    kind=ModKind.DEBUFF,
                ),
                e,
                self.char,
                p[0],
            )

    def _a6(self, mod: Modifier, key: str, ent: Entity) -> float:
        return self.tp(3, 1) if self.char.hp_ratio >= self.tp(3, 0) else 0.0

    @property
    def max_charge(self) -> int:
        return int(self.p("talent", 1))

    def gain_charge(self, n: int) -> None:
        self.charge = min(self.max_charge, self.charge + n)

    # ------------------------------------------------------------ talent
    def _on_break(self, ev: E.Ev) -> None:
        credited = ev.credited
        if credited is None or credited.side != Side.ALLY:
            return
        n = CHARGE_PER_BREAK
        hit = ev.hit
        act = hit.action if hit is not None else None
        if self.e(4) and act is not None and act.owner is self.char and act.kind == ActionKind.SKILL:
            n += int(self.ep(4, 0))
        self.gain_charge(n)

    def _on_attack_end(self, ev: E.Ev) -> None:
        act = ev.attack
        if act.owner is self.char and act.kind in ATTACK_KINDS and self.trace(1):
            for t in act.attacked:
                if t.hp > 0:
                    self.burn(t, self.tp(1, 0))
        if not isinstance(act.owner, Character) or act.kind not in ATTACK_KINDS:
            return
        if self.charge >= self.max_charge and not self.fua_pending:
            self.fua_pending = True
            self.battle.queue_action(self._victory_rush, self.char, "Himeko Victory Rush")

    def _victory_rush(self) -> None:
        self.fua_pending = False
        if self.charge < self.max_charge or not self.enemies():
            return
        self.charge = 0
        with self.action(ActionKind.FUA, "talent", self.battle.default_target()) as act:
            act.aoe(
                self.p("talent", 0), toughness=self.toughness("talent", 1), main_target=act.target, splits=FUA_SPLITS
            )
        if self.e(1):
            self.buff_self(Modifier("Childhood", stats={S.SPD_PCT: self.ep(1, 0)}, duration=int(self.ep(1, 1))))

    def burn(self, target: Enemy, chance: float) -> None:
        himeko = self.char
        mult = self.tp(1, 2)

        def dmg(mod: DotModifier, b: Battle, ratio: float) -> float:
            return b.dot_damage(
                himeko, target, Element.FIRE, mult, label="Burn (Himeko)", tags=(DmgTag.DOT, "burn"), ratio=ratio
            )

        self.battle.try_debuff(
            DotModifier("Burn (Himeko)", dot_type="burn", damage_fn=dmg, duration=int(self.tp(1, 1))),
            target,
            self.char,
            chance,
        )

    def _before_hit(self, ev: E.Ev) -> None:
        hit = ev.hit
        if hit.attacker is not self.char:
            return
        if self.trace(2) and DmgTag.SKILL in hit.tags and hit.target.has_tag("burn"):
            hit.add(S.DMG_PCT, self.tp(2, 0))
        if self.e(2) and hit.target.hp_ratio <= self.ep(2, 0):
            hit.add(S.DMG_PCT, self.ep(2, 1))

    # ----------------------------------------------------------- actions
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
                splits="data",
            )

    def ult(self, target: Enemy | None) -> None:
        with self.action(ActionKind.ULT, "ult", target) as act:
            act.aoe(self.p("ult", 0), toughness=self.toughness("ult", 1), main_target=target, splits="data")
            if self.e(6):
                for _ in range(E6_EXTRA_HITS):
                    pool = [e for e in self.enemies() if e.hp > 0] or self.enemies()
                    if not pool:
                        break
                    act.hit(self.battle.rng.choice(pool), self.p("ult", 0) * self.ep(6, 0), primary=False)
            kills = sum(1 for e in act.attacked if e.hp <= 0)
            act.energy += self.p("ult", 1) * kills
