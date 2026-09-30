"""March 7th (三月七, Preservation) — Preservation / Ice. Skill Shield + taunt, Counter, AoE Freeze ultimate.

Options (``default_opts``):

* ``target``: name of the ally receiving the Skill Shield (default ``None`` = March 7th herself).
* ``rotation``: ``"auto"`` (Skill when the shield target has no Skill Shield or it is about to expire,
  else Basic ATK), ``"skill"`` (Skill whenever SP allows) or ``"basic"``.
"""

from __future__ import annotations

from .. import events as E
from .. import stats as S
from ..battle import Battle
from ..entities import Character, Enemy, Entity
from ..enums import ActionKind, Element
from ..modifiers import DotModifier, Modifier
from . import register
from .base import Kit

SKILL_SHIELD = "The Power of Cuteness"
# approximation: "greatly increases the chance of enemies attacking that ally" has no parameter in the
# data; the game's modifier adds +500% aggro.
SKILL_SHIELD_AGGRO_PCT = 5.0
# E4: "The Talent's Counter effect can be triggered 1 more time in each turn" (literal in the text)
E4_EXTRA_COUNTERS = 1
# Ultimate hit splits from the ability script (Skill03_Phase02: 4 x split=0.25 on all enemies; AoE splits are not in
# the data snapshot)
ULT_SPLITS = [0.25, 0.25, 0.25, 0.25]


@register
class March7thPreservation(Kit):
    char_id = "1001"
    default_opts = {"target": None, "rotation": "auto"}

    def setup(self) -> None:
        self.counters_left = self._counter_limit()
        self._shielded_uids: set[int] = set()
        self.on(E.TURN_START, self._turn_start)
        self.on(E.ACTION_START, self._enemy_action_start)
        self.on(E.ALLY_ATTACKED, self._ally_attacked)

    def on_battle_start(self) -> None:
        if self.e(2):
            ally = min(self.allies(), key=lambda c: c.hp_ratio)  # ties -> first slot
            self.battle.add_shield(
                ally,
                self.ep(2, 0) * self.char.defense + self.ep(2, 2),
                self.char,
                duration=int(self.ep(2, 1)),
                name="Memory of It",
            )

    def technique(self) -> None:
        # not modelled: Toughness reduction of the overworld attack that starts the battle
        p = self.sk("technique")["params"][0]
        alive = self.enemies()
        if alive:
            self.freeze(self.battle.rng.choice(alive), p[0], int(p[1]), p[2])

    def _counter_limit(self) -> int:
        return int(self.p("talent", 1)) + (E4_EXTRA_COUNTERS if self.e(4) else 0)

    def _turn_start(self, ev: E.Ev) -> None:
        ent = ev.entity
        if ent is self.char:
            self.counters_left = self._counter_limit()  # "can be triggered N time(s) each turn"
        if self.e(6) and isinstance(ent, Character) and self._skill_shield(ent) is not None:
            self.battle.heal(ent, self.ep(6, 0) * ent.max_hp + self.ep(6, 1), self.char)

    # ------------------------------------------------------------ policy
    def shield_target(self) -> Character:
        name = self.opts.get("target")
        return self.battle.character(name) if name else self.char

    def _skill_shield(self, ally: Entity) -> Modifier | None:
        for m in ally.mods(SKILL_SHIELD):
            if m.source is self.char:
                return m
        return None

    def take_turn(self) -> None:
        target = self.pick_target()
        if target is None:
            return
        rotation = self.opts.get("rotation", "auto")
        if rotation == "basic" or not self.can_skill():
            self.basic(target)
            return
        if rotation == "skill":
            self.skill(target)
            return
        shield = self._skill_shield(self.shield_target())
        if shield is None or (shield.duration or 0) <= 1:
            self.skill(target)
        else:
            self.basic(target)

    # ------------------------------------------------------------ freeze
    def freeze(self, target: Enemy, chance: float, turns: int, mult: float) -> bool:
        """Frozen: the enemy skips its turn and takes Ice Additional DMG (``mult`` x ATK) at its turn start."""
        march = self.char

        def dmg(mod: DotModifier, b: Battle, ratio: float) -> float:
            return b.additional_damage(
                march, target, mult * ratio, element=Element.ICE, label="Frozen (March 7th)"
            ).damage

        mod = DotModifier(
            "Frozen (March 7th)",
            dot_type="freeze",
            damage_fn=dmg,
            duration=turns,
            is_dot=False,
            skip_turn=True,
            tags={"cc"},
            key="March 7th Freeze",
        )
        return self.battle.try_debuff(mod, target, self.char, chance, debuff_type="freeze") is not None

    # ----------------------------------------------------------- actions
    def basic(self, target: Enemy | None) -> None:
        assert target is not None
        self.simple_basic(target)

    def skill(self, target: Enemy | None) -> None:
        ally = self.shield_target()
        with self.action(ActionKind.SKILL, "skill", ally):
            if self.trace(1):  # A2 Purify: dispel 1 debuff
                deb = next((m for m in ally.debuffs if m.dispellable), None)
                if deb is not None:
                    self.battle.remove_modifier(deb)
            dur = int(self.p("skill", 1)) + (int(self.tp(2, 0)) if self.trace(2) else 0)
            value = self.p("skill", 0) * self.char.defense + self.p("skill", 3)
            shield = self.battle.add_shield(ally, value, self.char, duration=dur, name=SKILL_SHIELD)
            if ally.hp_ratio >= self.p("skill", 2):
                shield.stats[S.AGGRO_PCT] = SKILL_SHIELD_AGGRO_PCT
            else:
                shield.stats.pop(S.AGGRO_PCT, None)

    def ult(self, target: Enemy | None) -> None:
        with self.action(ActionKind.ULT, "ult", target) as act:
            act.aoe(self.p("ult", 0), toughness=self.toughness("ult", 1), main_target=target, splits=ULT_SPLITS)
            chance = self.p("ult", 1) + (self.tp(3, 0) if self.trace(3) else 0.0)
            for e in [e for e in self.enemies() if e.hp > 0]:
                if self.freeze(e, chance, int(self.p("ult", 2)), self.p("ult", 3)) and self.e(1):
                    self.battle.gain_energy(self.char, self.ep(1, 0))

    # ------------------------------------------------------------ talent
    def _enemy_action_start(self, ev: E.Ev) -> None:
        if ev.action.kind == ActionKind.ENEMY:
            # a Shield broken by the attack itself still counts as "a Shielded ally is attacked"
            self._shielded_uids = {a.uid for a in self.battle.allies(include_summons=True) if a.has_tag("shield")}

    def _ally_attacked(self, ev: E.Ev) -> None:
        if self.counters_left <= 0:
            return
        if not any(t.uid in self._shielded_uids or t.has_tag("shield") for t in ev.targets):
            return
        attacker = ev.attacker
        self.counters_left -= 1

        def counter() -> None:
            t = attacker if isinstance(attacker, Enemy) and attacker.alive else self.battle.default_target()
            if t is None:
                return
            mult = {"atk": self.p("talent", 0)}
            if self.e(4):
                mult["def"] = self.ep(4, 0)
            with self.action(ActionKind.FUA, "talent", t, label="Girl Power (Counter)") as act:
                act.hit(t, mult, toughness=self.toughness("talent"), splits="data")

        self.battle.queue_action(counter, self.char, "March 7th Counter")
