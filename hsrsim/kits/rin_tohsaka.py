"""Rin Tohsaka — Erudition / Quantum. "Gem Energy" from every Skill Point consumed or recovered by allies (plus a
CRIT DMG buff on that ally), "Second Magic Experiment" Enhanced Skill that drains Skill Points into Gem Energy and
spends it on bounces, Joint Follow-Up ATK with Archer during his "Circuit Connection".

Options:
  ``sp_reserve``: Skill Points to keep for teammates before using the normal (1 SP) Skill (default 0).
  ``rotation``: ``"skill"`` (default) or ``"basic"`` (Basic ATK unless the Skill is enhanced).

Policy: the Enhanced Skill whenever it is available (it is the Skill button then), else the normal Skill when
Skill Points allow, else Basic ATK. The Joint Follow-Up ATK is resolved by ``archer_skill_used`` (called by the
Archer kit after each of his Skills).
"""

from __future__ import annotations

from typing import Any, ClassVar

from .. import events as E
from .. import stats as S
from ..control import MenuItem
from ..entities import Character, Enemy, Entity
from ..enums import ActionKind, DmgTag, Side
from ..modifiers import Modifier, ModKind, Stacking
from . import register
from .base import Kit

ENHANCED_ID = "150809"  # Enhanced Skill "Second Magic Experiment"
JOINT_ID = "150805"  # Talent "Freeform Tohsaka Style" (Joint Follow-Up ATK with Archer)
ARCHER_ID = "1015"


@register
class RinTohsaka(Kit):
    char_id = "1508"
    default_opts: ClassVar[dict[str, Any]] = {"sp_reserve": 0}

    def setup(self) -> None:
        self.gem = 0
        self.shadow = 0  # E1 "Shadow Gem"
        self.joint_used = False
        self.joints = 0
        self.gem_gained = 0
        if self.trace(1):
            self.battle.max_sp += int(self.tp(1, 0))  # "while Rin Tohsaka is on the field"
        if self.e(2):
            self.passive("Dimensional Traveler", {f"{S.DMG_PCT}:{DmgTag.SKILL}": self.ep(2, 0)})
            self.passive(
                "Dimensional Traveler (team)",
                {f"{S.FINAL_DMG}:{DmgTag.SKILL}": self.ep(2, 1) - 1.0},
                scope=self.ally_scope,
                key="Rin Tohsaka E2",
            )
        if self.e(6):
            self.passive("Nailed It This Time!", {S.RES_PEN: self.ep(6, 0)})
        self.on(E.SP_CHANGED, self._on_sp)
        self.on(E.TURN_END, self._on_turn_end)

    def on_battle_start(self) -> None:
        self.gain_gem(int(self.p("talent", 0)))
        if self.trace(1):
            stats = {S.ATK_PCT: self.tp(1, 1), f"{S.RES_PEN}:Quantum": self.tp(1, 2)}
            self.passive("Elegant Conduct", stats)
            archer = self._archer()
            if archer is not None:
                self.passive("Elegant Conduct (Archer)", stats, target=archer)
        if self.trace(2):
            self._a4()

    def technique(self) -> None:
        p = self.sk("technique")["params"][0]
        self.gain_gem(int(p[0]))

    # ------------------------------------------------------------ helpers
    def _archer(self) -> Character | None:
        return next((c for c in self.battle.team if c.char_id == ARCHER_ID and c.alive), None)

    def gem_cap(self) -> int:
        return int(self.p("talent", 5))

    def gain_gem(self, n: int) -> None:
        if n > 0:
            self.gem = min(self.gem_cap(), self.gem + n)
            self.gem_gained += n

    def enhanced_ready(self) -> bool:
        if self.e(1) and self.shadow > 0:
            return True
        return self.gem >= self.p("talent", 4) or self.battle.sp >= self.p("talent", 3)

    def _a4(self) -> None:
        self.buff_self(Modifier("Ladylike Poise", stats={S.SPD_PCT: self.tp(2, 0)}, duration=int(self.tp(2, 1))))

    # ------------------------------------------------------------- talent
    def _on_sp(self, ev: E.Ev) -> None:
        n = abs(int(ev.delta))
        if n <= 0:
            return
        self.gain_gem(n)
        who: Entity | None = ev.entity
        if who is None or who.side != Side.ALLY or not who.targetable or not who.alive:
            return
        mine = who is self.char
        stack = mine and self.e(4)
        self.buff(
            who,
            Modifier(
                "Gem Magecraft",
                stats={S.CRIT_DMG: self.p("talent", 2)},
                duration=int(self.p("talent", 1)),
                stacking=Stacking.STACK if stack else Stacking.REFRESH,
                max_stacks=int(self.ep(4, 0)) if stack else 1,
            ),
        )

    def _on_turn_end(self, ev: E.Ev) -> None:
        if ev.entity is self.char:
            self.joint_used = False  # "the trigger count resets when Rin Tohsaka's turn ends"

    # ------------------------------------------------------ joint follow-up
    def archer_skill_used(self, archer_kit: Any) -> None:
        """Called by the Archer kit after each Skill ("Caladbolg II") he uses."""
        if not self.char.alive or self.joint_used or not self.enemies():
            return
        rec = self.sk(JOINT_ID)
        lv = rec["params"][self.level_of(rec) - 1]
        cap_reached = archer_kit.cc_count >= int(archer_kit.p("skill", 4))
        if self.battle.sp > int(lv[2]) and not cap_reached:
            return
        self.joint_used = True
        self.joint_follow_up(archer_kit.char)

    def joint_follow_up(self, archer: Character) -> None:
        rec = self.sk(JOINT_ID)
        lv = rec["params"][self.level_of(rec) - 1]
        target = self.pick_target()
        self.joints += 1
        with self.action(ActionKind.FUA, rec, target) as act:
            act.data["joint_with"] = (self.char, archer)
            act.aoe(lv[0], toughness=rec["toughness"][1], main_target=target)
        if archer.alive and self.enemies():
            # approximation: Archer's share is his own Follow-Up action (no Energy, no Toughness DMG in the data)
            with self.battle.action(
                archer, ActionKind.FUA, target=target, label=f"{rec['name']} (Archer)", energy=0, sp=0
            ) as act2:
                act2.data["joint_with"] = (self.char, archer)
                act2.aoe(lv[3], main_target=target)
        self.battle.gain_sp(int(lv[1]), self.char)

    # --------------------------------------------------------------- policy
    def take_turn(self) -> None:
        target = self.pick_target()
        if target is None:
            return
        if self.enhanced_ready():
            self.enhanced_skill(target)
        elif self.opts.get("rotation", "skill") == "skill" and self.battle.sp >= 1 + int(self.opts["sp_reserve"]):
            self.skill(target)
        else:
            self.basic(target)

    # -------------------------------------------------------------- actions
    def menu(self) -> list[MenuItem]:
        """With enough Gem Energy / Skill Points the Skill is "Second Magic Experiment" (no fixed SP cost: it spends
        the Skill Points above the floor for Gem Energy; E1's Shadow skips that)."""
        if not self.enhanced_ready():
            return super().menu()
        rec = self.sk(ENHANCED_ID)
        floor = int(rec["params"][self.level_of(rec) - 1][3])
        spent = 0 if (self.e(1) and self.shadow > 0) else max(0, self.battle.sp - floor)
        note = f"消耗战技点至{floor}点" if spent else ""
        return [self.basic_item(), self.skill_item(rec, sp=-spent, enabled=True, note=note)]

    def basic(self, target: Enemy | None) -> None:
        assert target is not None
        self.simple_basic(target)

    def skill(self, target: Enemy | None) -> None:
        assert target is not None
        if self.enhanced_ready():
            self.enhanced_skill(target)
            return
        with self.action(ActionKind.SKILL, "skill", target) as act:
            act.hit(target, self.p("skill", 0), toughness=self.toughness("skill"))

    def enhanced_skill(self, target: Enemy) -> None:
        rec = self.sk(ENHANCED_ID)
        lv = rec["params"][self.level_of(rec) - 1]
        shadow = self.e(1) and self.shadow > 0
        cost = int(lv[1])
        with self.action(ActionKind.SKILL, rec, target, sp=0) as act:
            if not shadow:
                floor = int(lv[3])
                if self.battle.sp > floor:
                    n = self.battle.sp - floor
                    self.battle.use_sp(n, self.char)  # Talent: +1 Gem Energy per point, CRIT DMG buff
                    self.gain_gem(n * int(lv[4]))
            act.aoe(lv[0], toughness=rec["toughness"][1], main_target=target)
            pool = self.shadow if shadow else self.gem
            spent = 0
            for _ in range(int(lv[5])):
                if pool < cost:
                    break
                alive = [e for e in self.enemies() if e.hp > 0]
                if not alive:
                    break
                pool -= cost
                spent += cost
                act.hit(self.battle.rng.choice(alive), lv[2], toughness=rec["toughness"][0], primary=False)
            if shadow:
                self.shadow = 0  # "consumes all Shadow Gem" and no Gem Energy
            else:
                self.gem = pool
                if self.e(1) and spent >= self.ep(1, 0):
                    self.shadow = spent
        if self.trace(2):
            self._a4()

    def ult(self, target: Enemy | None) -> None:
        assert target is not None
        with self.action(ActionKind.ULT, "ult", target) as act:
            self.battle.gain_sp(int(self.p("ult", 3)), self.char)
            for e in self.enemies():
                self.battle.apply(
                    Modifier(
                        "An Gal Ta Ki Gal Šè",
                        stats={S.VULN: self.p("ult", 4)},
                        duration=int(self.p("ult", 5)),
                        kind=ModKind.DEBUFF,
                    ),
                    e,
                    self.char,
                )
            act.hit(target, self.p("ult", 0), toughness=self.toughness("ult", 0))
            for e in self.enemies():
                if e is not target:
                    act.hit(e, self.p("ult", 1), toughness=self.toughness("ult", 1), primary=False)
        if self.trace(3):
            self.gain_gem(int(self.tp(3, 0)))
        if self.e(6):
            self.gain_gem(int(self.ep(6, 1)))
            self.battle.queue_extra_turn(self.char)
