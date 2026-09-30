"""Dan Heng • Imbibitor Lunae (丹恒•饮月) — Destruction / Imaginary. Enhanced Basic ATKs costing 1-3 SP,
Righteous Heart (DMG% per hit), Outroar (CRIT DMG per hit), Squama Sacrosancta (SP substitute).

Options (``default_opts``):
* ``rotation``: ``"greedy"`` (default: the strongest enhanced Basic ATK the SP + Squama allow, up to
  ``max_enhance``), ``"full"`` (only ``max_enhance``-level attacks, else the plain Basic ATK) or ``"basic"``.
* ``max_enhance``: highest enhancement used (1 Transcendence, 2 Divine Spear, 3 Fulgurant Leap; default 3).

Manual control: the menu lists Beneficent Lotus and the three enhancement levels ("enhanced_basic:1..3"), each
enabled when Skill Points + Squama Sacrosancta cover its cost (Squama is spent first).
"""

from __future__ import annotations

from typing import Any

from .. import events as E
from .. import stats as S
from ..control import MenuItem
from ..entities import Character, Enemy, Entity
from ..enums import ActionKind, Element
from ..modifiers import Modifier, Stacking
from . import register
from .base import Kit

# Hit splits of Divine Spear / Fulgurant Leap: the ability config scales DamagePercentage per hit instead of
# using HitSplitRatio, so they are not in the skill data (Basic ATK, Transcendence and the Ultimate use "splits")
DIVINE_SPEAR_SPLITS = (0.2, 0.2, 0.2, 0.2, 0.2)
DIVINE_SPEAR_ADJ = (0.0, 0.0, 0.0, 0.5, 0.5)  # adjacent targets from the 4th hit
FULGURANT_SPLITS = (0.142, 0.142, 0.142, 0.142, 0.142, 0.142, 0.148)
FULGURANT_ADJ = (0.0, 0.0, 0.0, 0.25, 0.25, 0.25, 0.25)
OUTROAR_FROM_HIT = 4  # Skill text "starting from the fourth hit, 1 stack of Outroar is gained before every hit"
E1_EXTRA_STACKS = 1  # E1 text "gains 1 extra stack of Righteous Heart for each hit"
E2_ADVANCE = 1.0  # E2 text "action advances by 100%"
E2_EXTRA_SQUAMA = 1  # E2 text "gains 1 extra Squama Sacrosancta"
E4_EXTRA_TURNS = 1  # E4 text "lasts until the end of this unit's next turn"
ENHANCED = {1: "121308", 2: "121310", 3: "121312"}  # Transcendence, Divine Spear, Fulgurant Leap


@register
class ImbibitorLunae(Kit):
    char_id = "1213"
    default_opts = {"rotation": "greedy", "max_enhance": 3}

    def setup(self) -> None:
        self.squama = 0
        self.e6_stacks = 0
        if self.trace(3):
            self.on(E.BEFORE_HIT, self._a6)
        if self.e(6):
            self.on(E.ULT_USED, self._e6)
        # not modelled: A4 (Crowd Control resistance), enemy CC is not simulated

    def on_battle_start(self) -> None:
        if self.trace(1):
            self.battle.gain_energy(self.char, self.tp(1, 0))

    def technique(self) -> None:
        p = self.sk("technique")["params"][0]
        with self.action(ActionKind.EXTRA, None, label="Heaven-Quelling Prismadrakon", energy=0, sp=0) as act:
            act.aoe(p[2])
        self.squama = min(int(self.p("ult", 3)), self.squama + int(p[0]))

    def _a6(self, ev: E.Ev) -> None:
        hit = ev.hit
        if hit.attacker is self.char and hit.target.is_weak_to(Element.IMAGINARY):
            hit.add(S.CRIT_DMG, self.tp(3, 0))

    def _e6(self, ev: E.Ev) -> None:
        ent = ev.entity
        if isinstance(ent, Character) and ent is not self.char:
            self.e6_stacks = min(int(self.ep(6, 1)), self.e6_stacks + 1)

    # ----------------------------------------------------- per-hit stacks
    def _righteous_heart(self) -> None:
        n = 1 + (E1_EXTRA_STACKS if self.e(1) else 0)
        cap = int(self.p("talent", 1)) + (int(self.ep(1, 0)) if self.e(1) else 0)
        # "lasting until the end of his turn": gained outside his turn it lasts until the end of his next turn
        self.buff_self(
            Modifier(
                "Righteous Heart",
                stats={S.DMG_PCT: self.p("talent", 0)},
                duration=1,
                skip_first_tick=False,
                stacking=Stacking.STACK,
                stacks=n,
                max_stacks=cap,
            )
        )

    def _outroar(self) -> None:
        self.buff_self(
            Modifier(
                "Outroar",
                stats={S.CRIT_DMG: self.p("skill", 0)},
                duration=1 + (E4_EXTRA_TURNS if self.e(4) else 0),
                skip_first_tick=False,  # LifeStepImmediately in the ability config
                stacking=Stacking.STACK,
                max_stacks=int(self.p("skill", 1)),
            )
        )

    def _segments(
        self,
        act: Any,
        target: Enemy,
        main: float,
        adj: float,
        splits: tuple[float, ...],
        adj_splits: tuple[float, ...] | None,
        tough: tuple[float, float],
        outroar: bool = False,
        extra: dict[str, float] | None = None,
    ) -> None:
        for i, r in enumerate(splits):
            if outroar and i + 1 >= OUTROAR_FROM_HIT:
                self._outroar()
            act.hit(target, main, toughness=tough[0], splits=[r], extra=extra)
            ar = adj_splits[i] if adj_splits else 0.0
            if ar:
                for a in self.battle.adjacent(target):
                    act.hit(a, adj, toughness=tough[1], splits=[ar], extra=extra, primary=False)
            self._righteous_heart()  # "After each hit dealt during an attack"

    @staticmethod
    def _data_splits(rec: dict[str, Any]) -> tuple[float, ...]:
        return tuple(rec.get("splits") or (1.0,))

    # ------------------------------------------------------------- policy
    def budget(self) -> int:
        return self.battle.sp + self.squama

    def pick_level(self) -> int:
        mode = self.opts.get("rotation", "greedy")
        top = max(0, min(3, int(self.opts.get("max_enhance", 3))))
        if mode == "basic":
            return 0
        if mode == "full":
            return top if self.budget() >= top else 0
        return min(top, self.budget())

    def can_skill(self) -> bool:
        return self.budget() >= 1

    def take_turn(self) -> None:
        target = self.pick_target()
        if target is None:
            return
        level = self.pick_level()
        if level > 0:
            self.enhanced_basic(target, level)
        else:
            self.basic(target)

    # ------------------------------------------------------ manual control
    @staticmethod
    def _cost(rec: dict[str, Any]) -> int:
        need = rec["sp_need"]
        return int(need[0] if isinstance(need, list) else need)

    def menu(self) -> list[MenuItem]:
        """Dracore Libre is not an action: the enhancement level (1-3) is chosen together with the attack."""
        items = [self.basic_item()]
        for level, sid in ENHANCED.items():
            rec = self.sk(sid)
            need = self._cost(rec)
            squama = min(self.squama, need)
            ok = self.budget() >= need
            if not ok:
                note = f"需要{need}点战技点/逆鳞"
            else:
                note = f"消耗{squama}逆鳞+{need - squama}战技点" if squama else ""
            items.append(
                self.basic_item(
                    rec, id=f"enhanced_basic:{level}", kind="skill", sp=squama - need, enabled=ok, note=note
                )
            )
        return items

    def perform(self, item: str, target: Entity | None) -> None:
        if item.startswith("enhanced_basic:"):
            level = int(item.split(":", 1)[1])
            self.with_target(target, lambda t: self.enhanced_basic(t, level))
            return
        super().perform(item, target)

    # ------------------------------------------------------------ actions
    def basic(self, target: Enemy | None) -> None:
        assert target is not None
        with self.action(ActionKind.BASIC, "basic", target) as act:
            splits = self._data_splits(self.sk("basic"))
            self._segments(act, target, self.p("basic", 0), 0.0, splits, None, (self.toughness("basic"), 0.0))

    def skill(self, target: Enemy | None) -> None:
        """Dracore Libre is not an action: it selects the enhanced Basic ATK (strongest affordable)."""
        assert target is not None
        level = min(3, self.budget())
        if level > 0:
            self.enhanced_basic(target, level)
        else:
            self.basic(target)

    def enhanced_basic(self, target: Enemy, level: int) -> None:
        sid = ENHANCED[level]
        rec = self.sk(sid)
        lv = rec["params"][self.level_of(rec) - 1]
        need = rec["sp_need"]
        need = int(need[0] if isinstance(need, list) else need)
        from_squama = min(self.squama, need)
        self.squama -= from_squama
        tough = (self.toughness(sid, 0), self.toughness(sid, 2))
        extra: dict[str, float] | None = None
        if level == 3 and self.e(6) and self.e6_stacks:
            extra = {f"{S.RES_PEN}:{Element.IMAGINARY.value}": self.ep(6, 0) * self.e6_stacks}
            self.e6_stacks = 0
        with self.action(ActionKind.BASIC, rec, target, sp=-(need - from_squama)) as act:
            if from_squama:  # "Consuming Squama Sacrosancta is considered equivalent to consuming skill points"
                self.battle.events.emit(E.SP_CHANGED, delta=-from_squama, entity=self.char, squama=True)
            if level == 1:
                self._segments(act, target, lv[0], 0.0, self._data_splits(rec), None, tough)
            elif level == 2:
                self._segments(act, target, lv[0], lv[1], DIVINE_SPEAR_SPLITS, DIVINE_SPEAR_ADJ, tough, outroar=True)
            else:
                self._segments(
                    act, target, lv[0], lv[1], FULGURANT_SPLITS, FULGURANT_ADJ, tough, outroar=True, extra=extra
                )

    def ult(self, target: Enemy | None) -> None:
        if target is None:
            return
        splits = self._data_splits(self.sk("ult"))  # adjacent targets are hit with the same splits
        with self.action(ActionKind.ULT, "ult", target) as act:
            self._segments(
                act,
                target,
                self.p("ult", 0),
                self.p("ult", 1),
                splits,
                splits,
                (self.toughness("ult", 0), self.toughness("ult", 2)),
            )
        gain = int(self.p("ult", 2)) + (E2_EXTRA_SQUAMA if self.e(2) else 0)
        self.squama = min(int(self.p("ult", 3)), self.squama + gain)
        if self.e(2):
            self.battle.advance(self.char, E2_ADVANCE)
