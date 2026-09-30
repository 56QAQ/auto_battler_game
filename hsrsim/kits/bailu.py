"""Bailu (白露) — Abundance / Lightning. Healer: Invigoration (heal when hit), bouncing Skill heal.

Healing is modelled as far as it drives other effects (A2 Max HP, E1 Energy, E4 DMG buff).

Options (``default_opts``):
* ``rotation``: ``"auto"`` (default: Skill when an ally's HP is below ``heal_below`` and SP allows, else Basic ATK),
  ``"skill"`` (Skill whenever SP allows) or ``"basic"``.
* ``heal_below``: HP ratio threshold of the ``"auto"`` rotation (default 0.5).
* ``target``: name of the ally the Skill heals first (default: the ally with the lowest HP ratio).
"""

from __future__ import annotations

from .. import events as E
from .. import stats as S
from ..entities import Character, Enemy
from ..enums import ActionKind
from ..modifiers import Modifier, Stacking
from . import register
from .base import Kit

INVIGORATION = "Invigoration"
ULT_EXTEND = 1  # Ultimate text "extends the duration of their Invigoration by 1 turn"


@register
class Bailu(Kit):
    char_id = "1211"
    ult_targets_ally = True
    default_opts = {"rotation": "auto", "heal_below": 0.5, "target": None}

    def setup(self) -> None:
        self.on(E.ALLY_ATTACKED, self._on_attacked)
        if self.trace(1):
            self.on(E.HEALED, self._a2)
        if self.e(1):
            self.on(E.MOD_REMOVED, self._e1)
        # not modelled: the Talent's / E6's revive of allies receiving a killing blow (allies are immortal)

    def technique(self) -> None:
        turns = int(self.sk("technique")["params"][0][0])
        for c in self.allies():
            self.invigorate(c, turns)

    # ------------------------------------------------------ invigoration
    def _trigger_count(self) -> int:
        return int(self.p("talent", 4)) + (int(self.tp(2, 0)) if self.trace(2) else 0)

    def invigorate(self, ally: Character, turns: int) -> None:
        cur = ally.get_mod(INVIGORATION)
        if cur is not None and cur.duration is not None:
            cur.duration += ULT_EXTEND
            return
        stats = {S.MITIGATION: self.tp(3, 0)} if self.trace(3) else {}
        mod = Modifier(INVIGORATION, stats=stats, duration=turns, skip_first_tick=False, key=INVIGORATION)
        mod.data["left"] = self._trigger_count()
        self.buff(ally, mod)  # LifeStepImmediately in the ability config

    def _on_attacked(self, ev: E.Ev) -> None:
        for t in ev.targets:
            mod = t.get_mod(INVIGORATION)
            if mod is None or mod.data.get("left", 0) <= 0:
                continue
            mod.data["left"] -= 1
            self.battle.heal(t, self.p("talent", 0) * self.char.max_hp + self.p("talent", 1), self.char)

    def _a2(self, ev: E.Ev) -> None:
        if ev.source is self.char and isinstance(ev.entity, Character) and ev.amount > ev.effective + 1e-9:
            self.buff(
                ev.entity,
                Modifier("Qihuang Analects", stats={S.HP_PCT: self.tp(1, 0)}, duration=int(self.tp(1, 1))),
            )

    def _e1(self, ev: E.Ev) -> None:
        mod, ally = ev.mod, ev.target
        if mod.name != INVIGORATION or mod.source is not self.char or not isinstance(ally, Character):
            return
        if ally.hp >= ally.max_hp - 1e-6:
            # MAvatar_Bailu_Heal_Mark OnDestroy: ModifySPNew FixedAddValue (ignores ERR)
            self.battle.gain_energy(ally, self.ep(1, 0), fixed=True)

    # ------------------------------------------------------------ policy
    def _heal_target(self) -> Character:
        name = self.opts.get("target")
        if name:
            return self.battle.character(name)
        return min(self.allies(), key=lambda c: c.hp_ratio)

    def take_turn(self) -> None:
        target = self.pick_target()
        if target is None:
            return
        mode = self.opts.get("rotation", "auto")
        low = min(c.hp_ratio for c in self.allies()) < float(self.opts.get("heal_below", 0.5))
        if self.can_skill() and (mode == "skill" or (mode == "auto" and low)):
            self.skill(target)
        else:
            self.basic(target)

    # ----------------------------------------------------------- actions
    def basic(self, target: Enemy | None) -> None:
        assert target is not None
        self.simple_basic(target)

    def _skill_heal(self, ally: Character, amount: float) -> None:
        self.battle.heal(ally, amount, self.char)
        if self.e(4):
            self.buff(
                ally,
                Modifier(
                    "Evil Excision",
                    stats={S.DMG_PCT: self.ep(4, 0)},
                    duration=int(self.ep(4, 2)),
                    stacking=Stacking.STACK,
                    max_stacks=int(self.ep(4, 1)),
                ),
            )

    def skill(self, target: Enemy | None) -> None:
        ally = self._heal_target()
        with self.action(ActionKind.SKILL, "skill", ally):
            amount = self.p("skill", 0) * self.char.max_hp + self.p("skill", 1)
            self._skill_heal(ally, amount)
            for _ in range(int(self.p("skill", 3))):
                amount *= 1.0 - self.p("skill", 2)
                self._skill_heal(self.battle.rng.choice(self.allies()), amount)

    def ult(self, target: Enemy | None) -> None:
        with self.action(ActionKind.ULT, "ult"):
            for c in self.allies():
                self.battle.heal(c, self.p("ult", 0) * self.char.max_hp + self.p("ult", 1), self.char)
                self.invigorate(c, int(self.p("ult", 2)))
            if self.e(2):
                self.buff_self(
                    Modifier("Sylphic Slumber", stats={S.HEAL_PCT: self.ep(2, 0)}, duration=int(self.ep(2, 1)))
                )
