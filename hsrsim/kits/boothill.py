"""Boothill (波提欧) — Hunt / Physical. Standoff, Enhanced Basic ATK, Pocket Trickshot Break DMG.

Options:
  rotation: "skill" (default) re-enters Standoff whenever it ends and SP allows; "basic" never uses the Skill
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from .. import events as E
from .. import stats as S
from ..entities import Enemy, Entity
from ..enums import ActionKind, Element
from ..modifiers import Modifier, ModKind, Tick
from . import register
from .base import Kit

if TYPE_CHECKING:
    from ..battle import Battle

ENHANCED_BASIC = "08"  # skill ID suffix of "Fanning the Hammer"


class _Standoff(Modifier):
    """Boothill's side of the Standoff; its removal ends the Standoff."""

    def on_remove(self, battle: Battle) -> None:
        kit = self.data.get("kit")
        if kit is not None:
            kit.standoff_ended()


@register
class Boothill(Kit):
    char_id = "1315"
    default_opts = {"rotation": "skill"}

    def setup(self) -> None:
        self.trickshot = 0
        self.standoff: _Standoff | None = None
        self.standoff_target: Enemy | None = None
        self.in_enhanced = False
        self.break_pending = False
        self.e2_turn = -1
        self.technique_pending = False
        self.on(E.BEFORE_HIT, self._standoff_vuln)
        self.on(E.BREAK, self._on_break)
        self.on(E.KILL, self._on_kill)
        if self.trace(1):
            self.passive("Ghost Load", {}, dyn=self._a2, dyn_keys={S.CRIT_RATE, S.CRIT_DMG})
        if self.e(1):
            self.passive("Dusty Trail's Lone Star", {S.DEF_IGNORE: self.ep(1, 0)})

    def on_battle_start(self) -> None:
        if self.e(1):
            self._gain_trickshot(in_standoff=False)

    def technique(self) -> None:
        self.technique_pending = True

    # ------------------------------------------------------------ helpers
    @property
    def max_trickshot(self) -> int:
        return int(self.p("talent", 4))

    def _a2(self, mod: Modifier, key: str, ent: Entity) -> float:
        be = self.char.stat(S.BREAK_EFFECT)
        if key == S.CRIT_RATE:
            return min(self.tp(1, 1), self.tp(1, 0) * be)
        return min(self.tp(1, 3), self.tp(1, 2) * be)

    @property
    def in_standoff(self) -> bool:
        t = self.standoff_target
        return self.standoff is not None and not self.standoff.removed and t is not None and t.alive

    def physical_weakness(self, target: Enemy, turns: int) -> None:
        self.battle.apply(
            Modifier(
                "Physical Weakness (Boothill)",
                duration=turns,
                kind=ModKind.DEBUFF,
                tags={f"weak:{Element.PHYSICAL.value}"},
                key="Boothill Physical Weakness",
            ),
            target,
            self.char,
        )

    # ------------------------------------------------------------ Standoff
    def standoff_ended(self) -> None:
        t = self.standoff_target
        self.standoff = None
        self.standoff_target = None
        if t is not None:
            self.battle.remove_named(t, "Standoff (target)")

    def _end_standoff(self) -> None:
        if self.standoff is not None and not self.standoff.removed:
            self.battle.remove_modifier(self.standoff)
        else:
            self.standoff_ended()

    def _gain_trickshot(self, in_standoff: bool) -> None:
        self.trickshot = min(self.max_trickshot, self.trickshot + 1)
        if not in_standoff:
            return
        if self.trace(3):
            self.battle.gain_energy(self.char, self.tp(3, 0))
        if self.e(2) and self.e2_turn != self.battle.turns:
            self.e2_turn = self.battle.turns
            self.battle.gain_sp(int(self.ep(2, 0)), self.char)
            self.buff_self(
                Modifier("Milestonemonger", stats={S.BREAK_EFFECT: self.ep(2, 1)}, duration=int(self.ep(2, 2)))
            )

    def _resolve_standoff(self) -> None:
        """The Standoff target was Weakness Broken or defeated (once per Standoff)."""
        if self.standoff is None or self.standoff.removed:
            return
        self.break_pending = False
        self._gain_trickshot(in_standoff=True)
        self._end_standoff()

    def _on_break(self, ev: E.Ev) -> None:
        if ev.target is self.standoff_target and self.in_standoff:
            if self.in_enhanced:
                self.break_pending = True  # resolved after the Talent's Break DMG of this attack
            else:
                self._resolve_standoff()

    def _on_kill(self, ev: E.Ev) -> None:
        if ev.target is self.standoff_target:
            self._resolve_standoff()

    def _standoff_vuln(self, ev: E.Ev) -> None:
        h = ev.hit
        if h.credited is self.char and h.target is self.standoff_target and self.in_standoff:
            h.add(S.VULN, self.p("skill", 0) + (self.ep(4, 0) if self.e(4) else 0.0))

    # ------------------------------------------------------------- policy
    def take_turn(self) -> None:
        target = self.pick_target()
        if target is None:
            return
        if self.in_standoff:
            self.basic(self.standoff_target)
        elif self.opts.get("rotation", "skill") == "skill" and self.can_skill():
            self.skill(target)
        else:
            self.basic(target)

    # ------------------------------------------------------------ actions
    def basic(self, target: Enemy | None) -> None:
        if self.in_standoff:
            self._enhanced_basic()
            return
        assert target is not None
        self.simple_basic(target)

    def _talent_mult(self, stacks: int) -> float:
        if stacks <= 0:
            return 0.0
        return self.p("talent", min(stacks, self.max_trickshot) - 1)  # 70% / 120% / 170%

    def _enhanced_basic(self) -> None:
        target = self.standoff_target
        assert target is not None
        rec = self.sk(self.char.char_id + ENHANCED_BASIC)
        lv = rec["params"][self.level_of(rec) - 1]
        stacks = self.trickshot  # read before the attack (ability script: "_enhance_before_attack")
        tough = float(rec["toughness"][0]) * (1.0 + self.p("talent", 3) * stacks)
        self.in_enhanced = True
        try:
            with self.action(ActionKind.BASIC, rec, target, sp=0) as act:
                act.hit(target, lv[0], toughness=tough)
                mult = self._talent_mult(stacks)
                if target.broken and mult > 0:
                    cap = self.p("talent", 5) * self.toughness("basic")
                    b = self.battle
                    b.break_damage(
                        self.char,
                        target,
                        Element.PHYSICAL,
                        mult=mult,
                        max_toughness=min(target.max_toughness, cap),
                        label="Five Peas in a Pod",
                    )
                    if self.e(6):
                        b.break_damage(
                            self.char,
                            target,
                            Element.PHYSICAL,
                            mult=mult * self.ep(6, 0),
                            max_toughness=min(target.max_toughness, cap),
                            label="Crowbar Hotel's Raccoon",
                        )
                        for adj in b.adjacent(target):
                            b.break_damage(
                                self.char,
                                adj,
                                Element.PHYSICAL,
                                mult=mult * self.ep(6, 1),
                                max_toughness=min(adj.max_toughness, cap),
                                label="Crowbar Hotel's Raccoon",
                            )
        finally:
            self.in_enhanced = False
        if self.break_pending:
            self._resolve_standoff()

    def skill(self, target: Enemy | None) -> None:
        assert target is not None
        with self.action(ActionKind.SKILL, "skill", target):
            self._end_standoff()
            mod = _Standoff(
                "Standoff", duration=int(self.p("skill", 2)), tick=Tick.HOLDER_TURN_START, kind=ModKind.OTHER
            )
            mod.data["kit"] = self
            self.standoff = mod
            self.standoff_target = target
            self.buff_self(mod)
            # not modelled: Taunt; the DMG Boothill takes from the target (+15%, E4 offset) and A4's reduction
            self.battle.apply(
                Modifier("Standoff (target)", kind=ModKind.DEBUFF, tick=Tick.NONE, dispellable=False), target, self.char
            )
            if self.technique_pending:
                self.technique_pending = False
                self.physical_weakness(target, int(self.sk("technique")["params"][0][0]))
        # "After using this Skill, the current turn does not end"
        if self.in_standoff and not self.battle.finished:
            self._enhanced_basic()

    def ult(self, target: Enemy | None) -> None:
        t = self.standoff_target if self.in_standoff else target
        assert t is not None
        with self.action(ActionKind.ULT, "ult", t) as act:
            self.physical_weakness(t, int(self.p("ult", 2)))
            act.hit(t, self.p("ult", 0), toughness=self.toughness("ult"), splits="data")
        if t.alive:
            self.battle.delay(t, self.p("ult", 1))
