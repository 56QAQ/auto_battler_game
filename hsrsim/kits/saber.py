"""Saber — Destruction / Wind. "Core Resonance" (8 fixed Energy each), overflow Energy, empowered Skill when
Core Resonance can refill her Energy, "Release, the Golden Scepter" Enhanced Basic ATK after the Ultimate.

Policy: the Enhanced Basic ATK when it is pending, else Skill when Skill Points allow, else Basic ATK.
Joint Follow-Up ATKs with Gilgamesh are implemented in the Gilgamesh kit.
"""

from __future__ import annotations

from .. import events as E
from .. import stats as S
from ..control import MenuItem
from ..entities import Character, Enemy
from ..enums import ActionKind, DmgTag
from ..modifiers import Modifier, Stacking
from . import register
from .base import Kit

RELEASE_ID = "101408"  # Enhanced Basic ATK "Release, the Golden Scepter"


@register
class Saber(Kit):
    char_id = "1014"

    def setup(self) -> None:
        self.cr = 0  # Core Resonance
        self.cr_gained = 0
        self.mana_burst = False
        self.release_next = False
        self.ults = 0
        self.overflow = 0.0
        if self.trace(2):
            self.on(E.ENERGY_OVERFLOW, self._energy_overflow)
        self.on(E.ULT_USED, self._talent)
        if self.trace(1):
            self.passive("Knight of the Dragon", {S.CRIT_RATE: self.tp(1, 0)})
            self.on(E.ACTION_END, lambda ev: self._check_mana_burst())
        if self.trace(3):
            self.passive(
                "Crown of the Star",
                {},
                dyn=lambda m, k, e: self.tp(3, 2) * min(self.cr_gained, int(self.tp(3, 3))),
                dyn_keys={S.CRIT_DMG},
            )
        if self.e(1):
            self.passive("The Lost White Walls", {f"{S.DMG_PCT}:{DmgTag.ULT}": self.ep(1, 0)})
        if self.e(2):
            self.passive(
                "The Lost Oath of the Round Table",
                {},
                dyn=lambda m, k, e: self.ep(2, 1) * min(self.cr_gained, int(self.ep(2, 2))),
                dyn_keys={S.DEF_IGNORE},
            )
        if self.e(4):
            self.passive("The Saga of Sixteen Winter Days", {f"{S.RES_PEN}:Wind": self.ep(4, 0)})
        if self.e(6):
            self.passive("The Long Fated Night", {f"{S.RES_PEN}:{DmgTag.ULT}": self.ep(6, 0)})

    def on_battle_start(self) -> None:
        self.gain_cr(int(self.p("talent", 7)))
        if self.trace(2):
            floor = self.tp(2, 2) * self.char.max_energy
            if self.char.energy < floor:
                self.char.energy = self.tp(2, 1) * self.char.max_energy
        if self.trace(1):
            self.mana_burst = True
            self._check_mana_burst()

    def technique(self) -> None:
        p = self.sk("technique")["params"][0]
        self.buff_self(Modifier("Behold, the King of Knights", stats={S.ATK_PCT: p[0]}, duration=int(p[1])))
        self.gain_cr(int(p[2]))

    # ------------------------------------------------------ Core Resonance
    def overflow_cap(self) -> float:
        return self.ep(6, 3) if self.e(6) else self.tp(2, 0)

    def _energy_overflow(self, ev: E.Ev) -> None:
        if ev.entity is self.char:
            self._on_overflow(ev.amount)

    def _on_overflow(self, amount: float) -> None:
        self.overflow = min(self.overflow_cap(), self.overflow + amount)

    def gain_cr(self, n: int) -> None:
        if n <= 0:
            return
        self.cr += n
        self.cr_gained += n
        self._check_mana_burst()

    def consume_cr(self) -> None:
        n, self.cr = self.cr, 0
        if n:
            self.battle.gain_energy(self.char, n * self.p("talent", 4), fixed=True)

    def can_refill(self) -> bool:
        """Holding Core Resonance, and a Skill + consuming it would fully regenerate Saber's Energy."""
        if self.cr <= 0:
            return False
        skill_energy = float(self.sk("skill")["energy"]) * (1.0 + self.char.stat(S.ERR))
        return self.char.energy + skill_energy + self.cr * self.p("talent", 4) >= self.char.max_energy - 1e-9

    def _check_mana_burst(self) -> None:
        if self.mana_burst and self.trace(1) and self.can_refill():
            self.mana_burst = False
            self.battle.gain_sp(1, self.char)  # "recover 1 Skill Point for allies" (literal)
            self.battle.advance(self.char, 1.0)

    def _talent(self, ev: E.Ev) -> None:
        if not isinstance(ev.entity, Character):
            return
        self.buff_self(
            Modifier("Dragon Reactor Core", stats={S.DMG_PCT: self.p("talent", 2)}, duration=int(self.p("talent", 3)))
        )
        self.gain_cr(int(self.p("talent", 0)))

    # --------------------------------------------------------------- policy
    def take_turn(self) -> None:
        target = self.pick_target()
        if target is None:
            return
        if self.release_next:
            self.release(target)
        elif self.opts.get("rotation", "skill") == "skill" and self.can_skill():
            self.skill(target)
        else:
            self.basic(target)

    def menu(self) -> list[MenuItem]:
        """After the Ultimate only "Release, the Golden Scepter" (the next Basic ATK) can be used."""
        if self.release_next:
            return [
                self.basic_item(self.sk(RELEASE_ID)),
                self.skill_item(enabled=False, note="仅能施放【解放的金色王权】"),
            ]
        return super().menu()

    # -------------------------------------------------------------- actions
    def basic(self, target: Enemy | None) -> None:
        assert target is not None
        if self.release_next:
            self.release(target)
            return
        self.simple_basic(target)
        if self.e(1):
            self.gain_cr(int(self.ep(1, 1)))

    def release(self, target: Enemy) -> None:
        rec = self.sk(RELEASE_ID)
        lv = rec["params"][self.level_of(rec) - 1]
        self.release_next = False
        with self.action(ActionKind.BASIC, rec, target) as act:
            self.gain_cr(int(lv[1]))
            n = len(self.enemies())
            act.aoe(lv[0], toughness=rec["toughness"][1], main_target=target)
            if n in (1, 2):
                extra = lv[3] if n == 1 else lv[2]
                act.aoe(extra, toughness=0.0, main_target=target, label=f"{rec['name']} (extra)")
        if self.e(1):
            self.gain_cr(int(self.ep(1, 1)))
        if self.trace(1):
            self.mana_burst = True
            self._check_mana_burst()

    def skill(self, target: Enemy | None) -> None:
        assert target is not None
        empowered = self.can_refill()
        main, adj = self.p("skill", 0), self.p("skill", 1)
        if empowered:
            per = self.p("skill", 3) + (self.ep(2, 0) if self.e(2) else 0.0)
            main += per * self.cr
            adj += per * self.cr
        with self.action(ActionKind.SKILL, "skill", target) as act:
            act.blast(target, main, adj, toughness=(self.toughness("skill", 0), self.toughness("skill", 2)))
            if self.trace(3):
                self.buff_self(
                    Modifier(
                        "Crown of the Star (Skill)", stats={S.CRIT_DMG: self.tp(3, 0)}, duration=int(self.tp(3, 1))
                    )
                )
        if empowered:
            self.consume_cr()
        else:
            self.gain_cr(int(self.p("skill", 2)))
        if self.e(1):
            self.gain_cr(int(self.ep(1, 1)))

    def ult(self, target: Enemy | None) -> None:
        refund = self.overflow
        self.overflow = 0.0
        with self.action(ActionKind.ULT, "ult", target) as act:
            act.aoe(self.p("ult", 0), toughness=self.toughness("ult", 1), main_target=target)
            n = int(self.p("ult", 2))
            # approximation: the data's 20 Toughness is read as the total over the bounces (2 each, like Gilgamesh's
            # Enuma Elish [2, 40]); 20 per bounce would be 200 Toughness on one target
            act.bounce(None, n, self.p("ult", 1), toughness=self.toughness("ult", 0) / n)
        self.release_next = True
        self.ults += 1
        if self.e(4):
            self.buff_self(
                Modifier(
                    "The Saga of Sixteen Winter Days (stack)",
                    stats={f"{S.RES_PEN}:Wind": self.ep(4, 1)},
                    stacking=Stacking.STACK,
                    max_stacks=int(self.ep(4, 2)),
                )
            )
        if refund > 0:
            self.battle.gain_energy(self.char, refund, fixed=True)
        if self.e(6) and (self.ults - 1) % int(self.ep(6, 1)) == 0:
            self.battle.gain_energy(self.char, self.ep(6, 2), fixed=True)
