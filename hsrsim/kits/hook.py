"""Hook (虎克) — Destruction / Fire. Burn Skill, Enhanced blast Skill after the Ultimate,
Additional DMG when attacking Burned enemies.

Options: ``rotation`` (``"skill"`` default / ``"basic"``).
"""

from __future__ import annotations

from .. import events as E
from .. import stats as S
from ..battle import Battle
from ..control import MenuItem
from ..entities import Enemy
from ..enums import ActionKind, DmgTag, Element
from ..modifiers import DotModifier
from . import register
from .base import Kit

ATTACK_KINDS = (ActionKind.BASIC, ActionKind.SKILL, ActionKind.ULT, ActionKind.FUA)
ENHANCED_SKILL = "110909"
BURN = "Burn (Hook)"


@register
class Hook(Kit):
    char_id = "1109"

    def setup(self) -> None:
        self.enhanced_skill = False
        self._key = f"hook_burned#{self.char.uid}"
        self.on(E.BEFORE_HIT, self._before_hit)
        self.on(E.ATTACK_END, self._talent)
        if self.trace(2):
            self.passive("Naivete", {f"{S.DEBUFF_RES}:cc": self.tp(2, 0)})  # enemies rarely CC in the engine

    def technique(self) -> None:
        p = self.sk("technique")["params"][0]
        alive = self.enemies()
        if not alive:
            return
        with self.action(ActionKind.EXTRA, None, label="Hook Technique", energy=0, sp=0) as act:
            # not modelled: Toughness reduction of the overworld attack that starts the battle
            act.hit(self.battle.rng.choice(alive), p[3])
            for e in self.enemies():
                self.burn(e, p[0], int(p[2]), p[1])

    # -------------------------------------------------------------- burn
    def burn(self, target: Enemy, chance: float, turns: int, mult: float) -> None:
        hook = self.char

        def dmg(mod: DotModifier, b: Battle, ratio: float) -> float:
            return b.dot_damage(hook, target, Element.FIRE, mult, label=BURN, tags=(DmgTag.DOT, "burn"), ratio=ratio)

        self.battle.try_debuff(DotModifier(BURN, dot_type="burn", damage_fn=dmg, duration=turns), target, hook, chance)

    def skill_burn(self, target: Enemy, params: list[float] | None = None) -> None:
        """Burn "equivalent to that of Skill" (``params`` = the used Skill's level parameters)."""
        lv = params if params is not None else self.sk("skill")["params"][self.level_of(self.sk("skill")) - 1]
        turns = int(lv[2]) + (int(self.ep(2, 0)) if self.e(2) else 0)
        self.burn(target, lv[1], turns, lv[3])

    # ------------------------------------------------------------ talent
    def _before_hit(self, ev: E.Ev) -> None:
        hit = ev.hit
        if hit.attacker is not self.char:
            return
        burned = hit.target.has_tag("burn")
        if self.e(6) and burned:
            hit.add(S.DMG_PCT, self.ep(6, 0))
        act = hit.action
        if burned and act is not None and act.owner is self.char and act.kind in ATTACK_KINDS:
            act.data.setdefault(self._key, []).append(hit.target)

    def _talent(self, ev: E.Ev) -> None:
        act = ev.attack
        burned: list[Enemy] = list(dict.fromkeys(act.data.get(self._key, [])))
        targets = [t for t in burned if t.hp > 0]
        if not targets:
            return
        # approximation: one trigger (Additional DMG, A2 heal) per Burned enemy attacked; Energy once per attack
        for t in targets:
            self.battle.additional_damage(
                self.char, t, self.p("talent", 0), element=Element.FIRE, label="Ha! Oil to the Flames!"
            )
            if self.trace(1):
                self.battle.heal(self.char, self.tp(1, 0) * self.char.max_hp, self.char)
        self.battle.gain_energy(self.char, self.p("talent", 1))
        main = act.target if isinstance(act.target, Enemy) else targets[0]
        if self.e(4):
            for adj in self.battle.adjacent(main):
                if adj.hp > 0:
                    self.skill_burn(adj, None)

    # ----------------------------------------------------------- policy
    def take_turn(self) -> None:
        target = self.pick_target()
        if target is None:
            return
        if self.opts.get("rotation", "skill") != "basic" and self.can_skill():
            self.skill(target)
        else:
            self.basic(target)

    # ----------------------------------------------------------- actions
    def menu(self) -> list[MenuItem]:
        """After the Ultimate the next Skill is enhanced (Blast)."""
        if self.enhanced_skill:
            return [self.basic_item(), self.skill_item(self.sk(ENHANCED_SKILL))]
        return super().menu()

    def basic(self, target: Enemy | None) -> None:
        assert target is not None
        self.simple_basic(target)

    def skill(self, target: Enemy | None) -> None:
        assert target is not None
        if self.enhanced_skill:
            self.enhanced_skill = False
            rec = self.sk(ENHANCED_SKILL)
            lv = [float(x) for x in rec["params"][self.level_of(rec) - 1]]
            extra = {S.DMG_PCT: self.ep(1, 0)} if self.e(1) else None
            with self.action(ActionKind.SKILL, rec, target) as act:
                act.blast(
                    target,
                    lv[0],
                    lv[4],
                    toughness=(self.toughness(ENHANCED_SKILL, 0), self.toughness(ENHANCED_SKILL, 2)),
                    splits="data",
                    extra=extra,
                )
                if target.hp > 0:
                    self.skill_burn(target, lv)
            return
        rec = self.sk("skill")
        with self.action(ActionKind.SKILL, rec, target) as act:
            act.hit(target, self.p("skill", 0), toughness=self.toughness("skill"), splits="data")
            if target.hp > 0:
                self.skill_burn(target, [float(x) for x in rec["params"][self.level_of(rec) - 1]])

    def ult(self, target: Enemy | None) -> None:
        assert target is not None
        with self.action(ActionKind.ULT, "ult", target) as act:
            act.hit(target, self.p("ult", 0), toughness=self.toughness("ult"), splits="data")
            if self.trace(3):
                act.energy += self.tp(3, 0)
        self.enhanced_skill = True
        if self.trace(3):
            self.battle.advance(self.char, self.tp(3, 1))
