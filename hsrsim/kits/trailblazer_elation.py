"""Trailblazer (Elation) (开拓者·欢愉) — Elation / Lightning. Certified Banger battery, ally Elation Skill trigger.

Options:
  ``target``: name of the ally receiving the Ultimate (default: the first teammate with an Elation Skill,
      else the first teammate).
  ``technique_hearty_chance``: probability of "Hearty Laughter" from the Technique (default: the
      Technique's second parameter; the other outcome is "Irrepressible Laughter").
"""

from __future__ import annotations

from .. import events as E
from .. import stats as S
from ..entities import Character, Enemy, Entity
from ..enums import ActionKind
from ..modifiers import Modifier, ModKind
from . import register
from ._batch8_util import grant_banger, has_elation_skill
from .base import Kit


class _TrailblazerElation(Kit):
    has_elation_skill = True
    ult_targets_ally = True
    default_opts = {"target": None, "technique_hearty_chance": None}

    def setup(self) -> None:
        self.a6_bonus = 0  # extra Certified Banger on the next Skill (A6)
        self.e1_stacks = 0
        self.tech_bonus = 0.0
        if self.trace(1):
            self.passive("On Cloud Nine", {}, dyn=self._a2, dyn_keys={S.ELATION_DMG_PCT})
        if self.trace(2):
            self.passive("Screw It, We Ball", {S.CRIT_RATE: self.tp(2, 0)})
        self.on(E.ATTACK_END, self._talent)
        if self.trace(3):
            self.on(E.ACTION_END, self._a6)

    def technique(self) -> None:
        p = self.sk("technique")["params"][0]
        chance = self.opts.get("technique_hearty_chance")
        chance = float(p[1]) if chance is None else float(chance)
        value = float(p[0]) if self.battle.rng.random() < chance else float(p[2])
        for c in self.allies():
            self.buff(c, Modifier("We Are So Back!", stats={S.ELATION_DMG_PCT: value}, duration=int(p[4])))

    def _a2(self, mod: Modifier, key: str, ent: Entity) -> float:
        over = self.char.atk - self.tp(1, 0)
        if over <= 0:
            return 0.0
        return min(self.tp(1, 3), int(over / self.tp(1, 1)) * self.tp(1, 2))

    # ----------------------------------------------------------- targeting
    def ult_ally(self) -> Character:
        if self.opts.get("target"):
            return self.main_dps()
        for c in self.teammates():
            if has_elation_skill(c):
                return c
        return self.main_dps()

    # -------------------------------------------------------------- talent
    def _talent(self, ev: E.Ev) -> None:
        act = ev.attack
        if act.owner is not self.char or not act.attacked:
            return
        self.battle.gain_energy(self.char, self.p("talent", 0), fixed=True)
        self.gain_punchline(int(self.p("talent", 1)))

    def _a6(self, ev: E.Ev) -> None:
        act = ev.action
        if act.kind == ActionKind.ELATION and isinstance(act.owner, Character):
            self.a6_bonus += int(self.tp(3, 0))

    def _highest_banger(self) -> int:
        return max((self.battle.elation.certified_banger(c) for c in self.allies()), default=0)

    # ------------------------------------------------------------- actions
    def basic(self, target: Enemy | None) -> None:
        assert target is not None
        self.simple_basic(target)

    def skill(self, target: Enemy | None) -> None:
        with self.action(ActionKind.SKILL, "skill", target) as act:
            act.aoe(self.p("skill", 0), toughness=self.toughness("skill", 1), main_target=target)
            grant_banger(self.battle, self.char, self.p("skill", 1) + self.a6_bonus, self.char)
            self.a6_bonus = 0
            if self.banger() > 0:
                p = self._highest_banger()
                for e in self.enemies():
                    self.elation_hit(e, self.p("talent", 2), p, label="That Smile Hits Different", action=act)
        if self.e(1):
            self.e1_stacks = min(int(self.ep(1, 1)), self.e1_stacks + 1)

    def ult(self, target: Enemy | None) -> None:
        ally = self.ult_ally()
        with self.action(ActionKind.ULT, "ult", ally):
            self.gain_punchline(int(self.p("ult", 5)))
            self.buff(
                ally,
                Modifier("Fly You Starward", stats={S.CRIT_DMG: self.p("ult", 0)}, duration=int(self.p("ult", 1))),
            )
            # not modelled: dispelling Crowd Control debuffs (enemies do not inflict them here)
            if self.e(2):
                self.buff(
                    ally,
                    Modifier(
                        "History in the Making", stats={S.ELATION_DMG_PCT: self.ep(2, 0)}, duration=int(self.ep(2, 1))
                    ),
                )
            if has_elation_skill(ally):
                gain = self.p("ult", 3) + (self.ep(1, 0) * self.e1_stacks if self.e(1) else 0.0)
                grant_banger(self.battle, ally, gain, self.char)
                fixed = self.p("ult", 4)
                kit = ally.kit
                assert kit is not None
                self.battle.queue_action(
                    lambda: kit.elation_skill(fixed) if ally.alive else None,
                    ally,
                    "Fly You Starward: Elation Skill",
                    priority=5,
                )
            else:
                self.battle.advance(ally, self.p("ult", 2))
        self.e1_stacks = 0
        if self.trace(2):
            self.battle.gain_sp(int(self.tp(2, 1)), self.char)

    # ------------------------------------------------------- elation skill
    def elation_skill(self, punchline: float) -> None:
        rec = self.sk(self.elation_skill_id)
        lv = rec["params"][self.level_of(rec) - 1]
        tough = rec["toughness"]
        with self.action(ActionKind.ELATION, rec, label=rec["name"]) as act:
            if self.e(4):
                for e in self.enemies():
                    self.battle.try_debuff(
                        Modifier(
                            "Save the World",
                            stats={S.VULN: self.ep(4, 0)},
                            duration=int(self.ep(4, 1)),
                            kind=ModKind.DEBUFF,
                        ),
                        e,
                        self.char,
                        1.0,
                    )
            if self.e(6):
                self.buff_self(
                    Modifier(
                        "The Cosmic Legend Cometh!", stats={S.CRIT_DMG: self.ep(6, 0)}, duration=int(self.ep(6, 1))
                    )
                )
            for _ in range(int(lv[0])):
                pool = [e for e in self.enemies() if e.hp > 0] or self.enemies()
                if not pool:
                    break
                self.elation_hit(
                    self.battle.rng.choice(pool),
                    lv[1],
                    punchline,
                    label="I Said Elation (bounce)",
                    action=act,
                    tags=("elation_skill",),
                    toughness=tough[0],
                )
            enemies = self.enemies()
            for e in enemies:  # split evenly among all enemies
                self.elation_hit(
                    e,
                    lv[2] / len(enemies),
                    punchline,
                    label="I Said Elation (split)",
                    action=act,
                    tags=("elation_skill",),
                    toughness=tough[1],
                )


@register
class TrailblazerElation(_TrailblazerElation):
    char_id = "8009"
    elation_skill_id = "800920"


@register
class TrailblazerElationF(_TrailblazerElation):
    char_id = "8010"
    elation_skill_id = "801020"
