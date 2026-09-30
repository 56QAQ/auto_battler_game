"""Gallagher (加拉赫) — Abundance / Fire. Besotted (Break DMG taken, heals attackers), Nectar Blitz.

Healing is modelled as far as it matters for other effects (``battle.heal`` with his Outgoing
Healing, A2); exact HP values are secondary in DMG simulations.

Options:
  rotation:        "auto" (default) Skill only when an ally is below ``heal_threshold`` HP ratio,
                   "skill" Skill whenever SP allows, "basic" never Skill
  heal_threshold:  HP ratio under which "auto" heals (default 0.5)
  target:          name of the ally healed by the Skill (default: lowest HP ratio)
"""

from __future__ import annotations

from .. import events as E
from .. import stats as S
from ..control import MenuItem
from ..entities import Character, Enemy, Entity
from ..enums import ActionKind, DmgTag
from ..modifiers import Modifier, ModKind
from . import register
from .base import Kit

NECTAR_BLITZ = "08"  # skill ID suffix of the enhanced Basic ATK "Nectar Blitz"
BESOTTED = "Besotted"
A4_ADVANCE = 1.0  # A4 "immediately advances action for this unit by 100%" (literal)


@register
class Gallagher(Kit):
    char_id = "1301"
    default_opts = {"rotation": "auto", "heal_threshold": 0.5, "target": None}

    def setup(self) -> None:
        self.nectar = False
        self.on(E.ATTACK_END, self._besotted_heal)
        if self.trace(1):
            self.passive("Novel Concoction", {}, dyn=self._a2, dyn_keys={S.HEAL_PCT})
        if self.e(1):
            self.passive("Salty Dog", {S.EFFECT_RES: self.ep(1, 1)})
        if self.e(6):
            self.passive("Blood and Sand", {S.BREAK_EFFECT: self.ep(6, 0), S.BREAK_EFF: self.ep(6, 1)})

    def on_battle_start(self) -> None:
        if self.e(1):
            self.battle.gain_energy(self.char, self.ep(1, 0))

    def technique(self) -> None:
        p = self.sk("technique")["params"][0]
        with self.action(ActionKind.EXTRA, None, label="Artisan Elixir (technique)", energy=0, sp=0) as act:
            for e in self.enemies():
                self.besot(e, int(p[0]))
            act.aoe(p[1])  # not modelled: Toughness reduction of the overworld hit

    # ------------------------------------------------------------ helpers
    def _a2(self, mod: Modifier, key: str, ent: Entity) -> float:
        return min(self.tp(1, 1), self.tp(1, 0) * self.char.stat(S.BREAK_EFFECT))

    def heal(self, ally: Character, amount: float) -> None:
        self.battle.heal(ally, amount, self.char)

    def besot(self, enemy: Enemy, turns: int) -> None:
        self.battle.apply(
            Modifier(
                BESOTTED,
                stats={f"{S.VULN}:{DmgTag.BREAK}": self.p("talent", 0)},
                duration=turns,
                kind=ModKind.DEBUFF,
                key="Besotted (Gallagher)",
            ),
            enemy,
            self.char,
        )

    def _heal_target(self) -> Character:
        name = self.opts.get("target")
        if name:
            return self.battle.character(name)
        return min(self.allies(), key=lambda c: c.hp_ratio)

    # ------------------------------------------------------------- policy
    def take_turn(self) -> None:
        target = self.pick_target()
        if target is None:
            return
        rot = self.opts.get("rotation", "auto")
        low = min((c.hp_ratio for c in self.allies()), default=1.0)
        wants_heal = rot == "skill" or (rot == "auto" and low < float(self.opts.get("heal_threshold", 0.5)))
        if not self.nectar and wants_heal and self.can_skill():
            self.skill(target)
        else:
            self.basic(target)

    # ------------------------------------------------------------ actions
    def menu(self) -> list[MenuItem]:
        """After the Ultimate the next Basic ATK is "Nectar Blitz"."""
        if self.nectar:
            return [self.basic_item(self.sk(self.char.char_id + NECTAR_BLITZ)), self.skill_item()]
        return super().menu()

    def basic(self, target: Enemy | None) -> None:
        assert target is not None
        if not self.nectar:
            self.simple_basic(target)
            return
        rec = self.sk(self.char.char_id + NECTAR_BLITZ)
        lv = rec["params"][self.level_of(rec) - 1]
        self.nectar = False
        with self.action(ActionKind.BASIC, rec, target) as act:
            act.data["nectar_blitz"] = True
            act.hit(target, lv[0], toughness=float(rec["toughness"][0]), splits="data")
            if target.alive:
                self.battle.apply(
                    Modifier(
                        "Nectar Blitz ATK Reduction",
                        stats={S.ATK_PCT: -lv[1]},
                        duration=int(lv[2]),
                        kind=ModKind.DEBUFF,
                    ),
                    target,
                    self.char,
                )

    def skill(self, target: Enemy | None) -> None:
        ally = self._heal_target()
        with self.action(ActionKind.SKILL, "skill", ally):
            self.heal(ally, self.p("skill", 0))
            if self.e(2):
                for m in [m for m in ally.debuffs if m.dispellable][: int(self.ep(2, 0))]:
                    self.battle.remove_modifier(m)
                self.buff(
                    ally, Modifier("Lion's Tail", stats={S.EFFECT_RES: self.ep(2, 1)}, duration=int(self.ep(2, 2)))
                )

    def ult(self, target: Enemy | None) -> None:
        turns = int(self.p("ult", 1)) + (int(self.ep(4, 0)) if self.e(4) else 0)
        with self.action(ActionKind.ULT, "ult", target) as act:
            for e in self.enemies():
                self.besot(e, turns)
            act.aoe(self.p("ult", 0), toughness=self.toughness("ult", 1), main_target=target)
        self.nectar = True
        if self.trace(2):
            self.battle.advance(self.char, A4_ADVANCE)

    # ------------------------------------------------------------- talent
    def _besotted_heal(self, ev: E.Ev) -> None:
        act = ev.attack
        owner = act.owner
        if not isinstance(owner, Character):
            return
        n = sum(1 for t in act.attacked if t.has_mod(BESOTTED))
        if not n:
            return
        amount = self.p("talent", 1)
        a6 = self.trace(3) and owner is self.char and act.data.get("nectar_blitz")
        for _ in range(n):  # one heal per Besotted target attacked
            self.heal(owner, amount)
            if a6:
                for c in self.teammates():
                    self.heal(c, amount)
