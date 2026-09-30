"""Natasha (娜塔莎) — Abundance / Physical. Single-target heal + heal over time, team heal Ultimate.

Healing is modelled with ``battle.heal`` (outgoing healing bonus and the Talent's low-HP bonus applied).

Options (``default_opts``):

* ``rotation``: ``"auto"`` (default: Skill on the lowest-HP ally when one is below ``heal_threshold``,
  else Basic ATK), ``"skill"`` (Skill whenever SP allows) or ``"basic"``.
* ``heal_threshold``: HP ratio below which ``"auto"`` uses the Skill (default 0.5).
* ``target``: ally name that receives the Skill (default: the lowest-HP ally).
"""

from __future__ import annotations

from collections.abc import Callable

from .. import events as E
from .. import stats as S
from ..battle import Battle
from ..entities import Character, Enemy, Entity
from ..enums import ActionKind
from ..modifiers import Modifier, ModKind, Tick
from . import register
from .base import Kit


class HealOverTime(Modifier):
    """Continuous healing: ``heal_fn(holder)`` at the start of each of the holder's turns."""

    def __init__(self, name: str, heal_fn: Callable[[Entity], None], duration: int) -> None:
        super().__init__(name, duration=duration, tick=Tick.HOLDER_TURN_START, kind=ModKind.BUFF)
        self.heal_fn = heal_fn

    def on_apply(self, battle: Battle) -> None:
        self.listen(E.TURN_START, self._on_turn_start)

    def _on_turn_start(self, ev: E.Ev) -> None:
        if ev.entity is self.holder and not self.removed:
            self.heal_fn(ev.entity)


@register
class Natasha(Kit):
    char_id = "1105"
    ult_targets_ally = True
    default_opts = {"rotation": "auto", "heal_threshold": 0.5, "target": None}

    def setup(self) -> None:
        self.e1_used = False
        if self.trace(2):
            self.passive("Healer", {S.HEAL_PCT: self.tp(2, 0)})
        if self.e(1) or self.e(4):
            self.on(E.ALLY_ATTACKED, self._on_attacked)

    def technique(self) -> None:
        p = self.sk("technique")["params"][0]  # [Weaken chance, Weaken, turns, DMG multiplier]
        enemies = self.enemies()
        if not enemies:
            return
        target = self.battle.rng.choice(enemies)
        # approximation: the Technique's in-battle DMG does not reduce Toughness
        with self.action(ActionKind.EXTRA, None, target, label="Hypnosis Research", energy=0, sp=0) as act:
            act.hit(target, p[3])
        # not modelled: the engine's enemy attacks ignore Weaken, the debuff is applied for bookkeeping only
        for e in self.enemies():
            self.battle.try_debuff(
                Modifier("Weakened (Natasha)", stats={S.WEAKEN: p[1]}, duration=int(p[2]), kind=ModKind.DEBUFF),
                e,
                self.char,
                p[0],
            )

    # ------------------------------------------------------------ healing
    def _heal(self, ally: Entity, amount: float) -> None:
        bonus = self.char.stat(S.HEAL_PCT)
        if ally.hp_ratio <= self.p("talent", 0):
            bonus += self.p("talent", 1)
        self.battle.heal(ally, amount * (1.0 + bonus), self.char)

    def _hot(self, ally: Entity, ratio: float, flat: float, turns: int, name: str) -> None:
        def tick(holder: Entity) -> None:
            self._heal(holder, ratio * self.char.max_hp + flat)

        self.buff(ally, HealOverTime(name, tick, turns))

    def _heal_target(self) -> Character:
        if self.opts.get("target"):
            return self.main_dps()
        return min(self.allies(), key=lambda c: (c.hp_ratio, c.slot))

    # ------------------------------------------------------------- policy
    def take_turn(self) -> None:
        target = self.pick_target()
        if target is None:
            return
        policy = self.opts.get("rotation", "auto")
        low = self._heal_target().hp_ratio < float(self.opts.get("heal_threshold", 0.5))
        if self.can_skill() and (policy == "skill" or (policy == "auto" and low)):
            self.skill(target)
        else:
            self.basic(target)

    # ------------------------------------------------------------ actions
    def basic(self, target: Enemy | None) -> None:
        assert target is not None
        mult: dict[str, float] = {"atk": self.p("basic", 0)}
        if self.e(6):
            mult["hp"] = self.ep(6, 0)
        with self.action(ActionKind.BASIC, "basic", target) as act:
            act.hit(target, mult, toughness=self.toughness("basic"), splits="data")

    def skill(self, target: Enemy | None) -> None:
        ally = self._heal_target()
        with self.action(ActionKind.SKILL, "skill", ally):
            if self.trace(1):
                for m in [m for m in ally.debuffs if m.dispellable][: int(self.tp(1, 0))]:
                    self.battle.remove_modifier(m)
            self._heal(ally, self.p("skill", 0) * self.char.max_hp + self.p("skill", 3))
            turns = int(self.p("skill", 2)) + (int(self.tp(3, 0)) if self.trace(3) else 0)
            self._hot(ally, self.p("skill", 1), self.p("skill", 4), turns, "Love, Heal, and Choose")

    def ult(self, target: Enemy | None) -> None:
        with self.action(ActionKind.ULT, "ult"):
            low = [c for c in self.allies() if c.hp_ratio <= self.ep(2, 0)] if self.e(2) else []
            for c in self.allies():
                self._heal(c, self.p("ult", 0) * self.char.max_hp + self.p("ult", 1))
            for c in low:
                self._hot(c, self.ep(2, 2), self.ep(2, 3), int(self.ep(2, 1)), "Clinical Research")

    # ------------------------------------------------------------ eidolons
    def _on_attacked(self, ev: E.Ev) -> None:
        c = self.char
        if c not in ev.targets:
            return
        if self.e(1) and not self.e1_used and c.hp_ratio <= self.ep(1, 0):
            self.e1_used = True
            self._heal(c, self.ep(1, 1) * c.max_hp + self.ep(1, 2))
        if self.e(4):
            self.battle.gain_energy(c, self.ep(4, 0))
