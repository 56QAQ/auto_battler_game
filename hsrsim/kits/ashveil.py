"""Ashveil (不死途) — Hunt / Lightning. "Bait" mark (team DEF shred), Charge-based follow-ups when allies hit the
Bait, "Gluttony" stacks consumed by the Ultimate's enhanced follow-up.

Policy: Skill on the Bait when Skill Points allow (re-marking the Bait refunds the Skill Point), else Basic ATK.
"""

from __future__ import annotations

from .. import events as E
from .. import stats as S
from ..entities import Enemy
from ..enums import ActionKind, DmgTag, Side
from ..modifiers import Modifier, ModKind, Tick
from . import register
from .base import Kit

BAIT = "Bait"


@register
class Ashveil(Kit):
    char_id = "1504"

    def setup(self) -> None:
        self.charge = int(self.p("talent", 0))
        self.gluttony = 0
        self.gained = 0  # Gluttony stacks gained this battle (E6)
        self.bait: Enemy | None = None
        self.passive(
            "Bait (DEF reduction)",
            {},
            scope=self.enemy_scope,
            dyn=lambda m, k, e: self.p("skill", 3) if self._bait_alive() else 0.0,
            dyn_keys={S.DEF_REDUCTION},
        )
        if self.trace(2):
            self.passive(
                "Phantom Limb",
                {},
                dyn=lambda m, k, e: self.tp(2, 0) + int(self.gluttony / self.tp(2, 1)) * self.tp(2, 2),
                dyn_keys={f"{S.DMG_PCT}:{DmgTag.FUA}"},
            )
        if self.trace(3):
            self.passive(
                "First Fang",
                {S.CRIT_DMG: self.tp(3, 0), f"{S.CRIT_DMG}:{DmgTag.FUA}": self.tp(3, 1)},
                scope=self.ally_scope,
            )
        if self.e(1):
            self.passive(
                "Beware: Venture Not at Full Moon",
                {},
                scope=self.enemy_scope,
                dyn=lambda m, k, e: self.ep(1, 2) if e.hp_ratio <= self.ep(1, 1) else self.ep(1, 0),
                dyn_keys={S.VULN},
            )
        if self.e(6):
            self.passive(
                "Finale (RES)",
                {},
                scope=self.enemy_scope,
                dyn=lambda m, k, e: self.ep(6, 0) if self._bait_alive() else 0.0,
                dyn_keys={S.RES_REDUCTION},
            )
            self.passive(
                "Finale (DMG)",
                {},
                dyn=lambda m, k, e: self.ep(6, 1) * min(self.gained, int(self.ep(6, 2))),
                dyn_keys={S.DMG_PCT},
            )
        self.on(E.ATTACK_END, self._talent)
        self.on(E.KILL, self._on_kill)
        self.on(E.WAVE_START, lambda ev: self._ensure_bait())

    def on_battle_start(self) -> None:
        self._ensure_bait()

    def technique(self) -> None:
        p = self.sk("technique")["params"][0]
        with self.action(ActionKind.EXTRA, None, label="Ashveil Technique", energy=0, sp=0) as act:
            act.aoe(p[1], toughness=self.toughness("technique"))
        self.charge = min(int(self.p("talent", 1)), self.charge + int(p[2]))

    # ----------------------------------------------------------------- Bait
    def _bait_alive(self) -> bool:
        return self.bait is not None and self.bait.alive and self.bait.hp > 0

    def set_bait(self, e: Enemy) -> None:
        if self.bait is not None and self.bait is not e:
            self.battle.remove_named(self.bait, BAIT)
        self.bait = e
        self.battle.apply(
            Modifier(BAIT, kind=ModKind.OTHER, tick=Tick.NONE, dispellable=False, key="Ashveil Bait"), e, self.char
        )

    def _ensure_bait(self) -> Enemy | None:
        if self._bait_alive():
            return self.bait
        pool = [e for e in self.enemies() if e.hp > 0]
        if not pool:
            return None
        self.set_bait(min(pool, key=lambda e: e.hp))
        return self.bait

    def _on_kill(self, ev: E.Ev) -> None:
        if ev.target is self.bait:
            self.bait = None
            self._ensure_bait()

    # ------------------------------------------------------------- Gluttony
    def gluttony_cap(self) -> int:
        return int(self.ep(2, 0)) if self.e(2) else int(self.p("talent", 5))

    def add_gluttony(self, n: int) -> None:
        if n <= 0:
            return
        self.gluttony = min(self.gluttony_cap(), self.gluttony + n)
        self.gained += n

    # --------------------------------------------------------------- talent
    def _talent(self, ev: E.Ev) -> None:
        act = ev.attack
        owner = act.owner
        if owner is None or owner is self.char or getattr(owner, "side", None) != Side.ALLY:
            return
        bait = self.bait
        if bait is None or bait not in act.attacked or self.charge < int(self.p("talent", 2)):
            return
        # approximation: the fixed Energy is granted only when a Charge is available for the follow-up
        self.battle.gain_energy(self.char, self.p("talent", 6), fixed=True)
        self.charge -= int(self.p("talent", 2))
        self.battle.queue_action(lambda: self.follow_up(enhanced=False), self.char, "Ashveil follow-up")

    def follow_up(self, enhanced: bool) -> None:
        target = self._ensure_bait()
        if target is None:
            return
        killed: set[int] = set()
        removed = 0
        with self.action(ActionKind.FUA, "talent", target, label="Rancor: Enmity Reprisal") as act:
            act.hit(target, self.p("talent", 3), toughness=self.toughness("talent"))
            if target.hp <= 0:
                killed.add(id(target))
            if enhanced:
                per = int(self.p("ult", 2))
                while self.gluttony >= per:
                    t = target if target.hp > 0 else self._next_bait(killed)
                    if t is None:
                        break
                    target = t
                    self.gluttony -= per
                    removed += per
                    act.hit(t, self.p("ult", 3), toughness=self.toughness("talent"), label="Banquet: Gluttony")
                    if t.hp <= 0:
                        killed.add(id(t))
        if self.trace(1) and killed:
            self.add_gluttony(int(len(killed) / self.tp(1, 2)) * int(self.tp(1, 3)))
        if enhanced and self.e(2) and removed:
            self.add_gluttony(int(removed * self.ep(2, 1)))
        self.add_gluttony(int(self.p("talent", 4)))

    def _next_bait(self, killed: set[int]) -> Enemy | None:
        pool = [e for e in self.enemies() if e.hp > 0 and id(e) not in killed]
        if not pool:
            return None
        t = min(pool, key=lambda e: e.hp)
        self.set_bait(t)
        return t

    # -------------------------------------------------------------- actions
    def pick_target(self) -> Enemy | None:
        return self._ensure_bait() or self.battle.default_target()

    def basic(self, target: Enemy | None) -> None:
        assert target is not None
        self.simple_basic(target)

    def skill(self, target: Enemy | None) -> None:
        assert target is not None
        was_bait = target is self.bait and self._bait_alive()
        self.set_bait(target)
        with self.action(ActionKind.SKILL, "skill", target) as act:
            act.hit(target, self.p("skill", 0), toughness=self.toughness("skill"))
            if was_bait:
                act.hit(target, self.p("skill", 2), label="Flog: Smite Evil (Bait)")
        if was_bait:
            self.battle.gain_sp(int(self.p("skill", 4)), self.char)
        if self.trace(1):
            self.add_gluttony(int(self.tp(1, 0)))
        self._ensure_bait()

    def ult(self, target: Enemy | None) -> None:
        t = target if target is not None else self._ensure_bait()
        if t is None:
            return
        self.set_bait(t)
        with self.action(ActionKind.ULT, "ult", t) as act:
            act.hit(t, self.p("ult", 0), toughness=self.toughness("ult"), splits="data")
            self.charge = min(int(self.p("talent", 1)), self.charge + int(self.p("ult", 1)))
            if self.trace(1):
                self.add_gluttony(int(self.tp(1, 1)))
            if self.e(4):
                self.buff_self(
                    Modifier("Heed: Swallow Truth Whole", stats={S.ATK_PCT: self.ep(4, 0)}, duration=int(self.ep(4, 1)))
                )
        self._ensure_bait()
        self.follow_up(enhanced=True)  # "then immediately launches 1 enhanced Talent Follow-Up ATK"
