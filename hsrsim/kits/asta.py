"""Asta (艾丝妲) — Harmony / Fire. Charging stacks (team ATK%), team SPD ultimate, Fire DMG aura.

Options: ``rotation``: ``"auto"`` (Skill when several enemies are alive and SP allows, else Basic ATK;
both give the same Charging on a single target), ``"skill"`` or ``"basic"``.
"""

from __future__ import annotations

from .. import events as E
from .. import stats as S
from ..battle import Battle
from ..entities import Enemy, Entity
from ..enums import ActionKind, DmgTag, Element
from ..modifiers import DotModifier, Modifier
from . import register
from .base import Kit

ATTACK_KINDS = (ActionKind.BASIC, ActionKind.SKILL, ActionKind.ULT, ActionKind.FUA)
# Skill: "further deals DMG for 4 extra times" / E1: "deals DMG for 1 extra time" (literals in the text)
SKILL_EXTRA_BOUNCES = 4
E1_EXTRA_BOUNCES = 1
# approximation: bounce hits after the first reduce half the Toughness of the first (game ability config;
# not in the skill data)
BOUNCE_TOUGHNESS_RATIO = 0.5
# Talent: "1 stack of Charging for every different enemy hit ... plus an extra stack if ... Fire Weakness"
CHARGING_PER_ENEMY = 1
CHARGING_FIRE_WEAK = 1


@register
class Asta(Kit):
    char_id = "1009"
    ult_targets_ally = True
    default_opts = {"rotation": "auto"}

    def setup(self) -> None:
        self.charging = 0
        self.own_turns = 0
        self.keep_next = False
        self.atk_per_stack = self.p("talent", 0)
        self.passive("Astrometry", {}, scope=self.ally_scope, dyn=self._atk, dyn_keys={S.ATK_PCT})
        if self.trace(2):
            self.passive("Ignite", {f"{S.DMG_PCT}:{Element.FIRE.value}": self.tp(2, 0)}, scope=self.ally_scope)
        if self.trace(3):
            self.passive("Constellation", {}, dyn=self._a6, dyn_keys={S.DEF_PCT})
        if self.e(4):
            self.passive("Aurora Basks in Beauty and Bliss", {}, dyn=self._e4, dyn_keys={S.ERR})
        self.on(E.ATTACK_END, self._gain_charging)
        self.on(E.TURN_START, self._turn_start)

    def technique(self) -> None:
        p = self.sk("technique")["params"][0]
        with self.action(ActionKind.EXTRA, None, label="Asta Technique", energy=0, sp=0) as act:
            # not modelled: Toughness reduction of the overworld attack that starts the battle
            act.aoe(p[0])

    # --------------------------------------------------------- Charging
    def _atk(self, mod: Modifier, key: str, ent: Entity) -> float:
        return self.atk_per_stack * self.charging

    def _a6(self, mod: Modifier, key: str, ent: Entity) -> float:
        return self.tp(3, 0) * self.charging

    def _e4(self, mod: Modifier, key: str, ent: Entity) -> float:
        return self.ep(4, 1) if self.charging >= self.ep(4, 0) else 0.0

    def _gain_charging(self, ev: E.Ev) -> None:
        act = ev.attack
        # approximation: the Technique's damage does not grant Charging
        if act.owner is not self.char or act.kind not in ATTACK_KINDS:
            return
        hit = set(act.attacked)
        n = CHARGING_PER_ENEMY * len(hit) + CHARGING_FIRE_WEAK * sum(1 for e in hit if e.is_weak_to(Element.FIRE))
        self.charging = min(int(self.p("talent", 1)), self.charging + n)

    def _turn_start(self, ev: E.Ev) -> None:
        if ev.entity is not self.char or ev.extra:
            return
        self.own_turns += 1
        if self.own_turns < 2:  # "Starting from her second turn"
            return
        if self.keep_next:  # E2
            self.keep_next = False
            return
        lose = int(self.p("talent", 2)) - (int(self.ep(6, 0)) if self.e(6) else 0)
        self.charging = max(0, self.charging - lose)

    # ------------------------------------------------------------ policy
    def take_turn(self) -> None:
        target = self.pick_target()
        if target is None:
            return
        rotation = self.opts.get("rotation", "auto")
        if rotation == "basic" or not self.can_skill():
            self.basic(target)
        elif rotation == "skill" or len(self.enemies()) > 1:
            self.skill(target)
        else:
            self.basic(target)

    # ----------------------------------------------------------- actions
    def basic(self, target: Enemy | None) -> None:
        assert target is not None
        self.simple_basic(target)
        if self.trace(1) and target.alive and target.hp > 0:
            asta = self.char
            mult = self.tp(1, 2) * self.p("basic", 0)  # "50% of DMG dealt by Asta's Basic ATK" (its multiplier)

            def dmg(mod: DotModifier, b: Battle, ratio: float) -> float:
                return b.dot_damage(
                    asta, target, Element.FIRE, mult, label="Burn (Asta)", tags=(DmgTag.DOT, "burn"), ratio=ratio
                )

            self.battle.try_debuff(
                DotModifier("Burn (Asta)", dot_type="burn", damage_fn=dmg, duration=int(self.tp(1, 1))),
                target,
                self.char,
                self.tp(1, 0),
            )

    def skill(self, target: Enemy | None) -> None:
        assert target is not None
        n = 1 + SKILL_EXTRA_BOUNCES + (E1_EXTRA_BOUNCES if self.e(1) else 0)
        energy = float(self.sk("skill")["energy"]) * n  # bounce skills regenerate Energy per hit
        tough = self.toughness("skill")
        with self.action(ActionKind.SKILL, "skill", target, energy=energy) as act:
            act.hit(target, self.p("skill", 0), toughness=tough)
            for _ in range(n - 1):
                pool = [e for e in self.enemies() if e.hp > 0] or self.enemies()
                if not pool:
                    break
                t = self.battle.rng.choice(pool)
                act.hit(t, self.p("skill", 0), toughness=tough * BOUNCE_TOUGHNESS_RATIO, primary=False)

    def ult(self, target: Enemy | None) -> None:
        with self.action(ActionKind.ULT, "ult"):
            for c in self.allies():
                self.buff(
                    c,
                    Modifier("Astral Blessing", stats={S.SPD_FLAT: self.p("ult", 0)}, duration=int(self.p("ult", 1))),
                )
            if self.e(2):
                self.keep_next = True
