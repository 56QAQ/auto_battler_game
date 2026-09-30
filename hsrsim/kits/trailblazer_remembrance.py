"""Trailblazer (Remembrance) (开拓者·记忆) — Remembrance / Ice. Memosprite Mem: team CRIT DMG aura, Charge
from the team's Energy, and at 100% Charge "Lemme! Help You!" (action advance + "Mem's Support" True DMG).

Options (``default_opts``):
  * ``rotation``: ``"auto"`` (Skill only to summon Mem, default), ``"skill"`` (Skill whenever SP allows, for
    Mem's Charge) or ``"basic"``.
  * ``target``: name of the ally that receives "Lemme! Help You!" (default: the first other team slot).

# not modelled: Mem disappearing (allies cannot die with ``allies_immortal``), so "No... Regrets" never triggers;
#   dispelling Crowd Control from Mem.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from .. import events as E
from .. import stats as S
from ..entities import Character, Enemy, Entity, Summon
from ..enums import ActionKind, DmgTag
from ..modifiers import Modifier, Tick
from . import register
from .aglaea import memo_hit
from .base import Kit

if TYPE_CHECKING:
    from ..battle import Battle

SERVANT_ID = "18007"  # both Trailblazer IDs share the memosprite record
SUPPORT = "Mem's Support"
ACTIVE_KINDS = (ActionKind.BASIC, ActionKind.SKILL, ActionKind.ULT)
CHARGE_PER_STEP = 0.01  # Talent "Mem gains 1% Charge" per #3 Energy (literal)


class _TrailblazerRemembrance(Kit):
    default_opts = {"rotation": "auto", "target": None}

    def setup(self) -> None:
        self.charge = 0.0  # Mem's Charge, 1.0 = 100%
        self.energy_acc = 0.0
        self.epic = 0
        self.summoned_once = False
        self.e2_ready = True
        self._cd_guard = False
        self.on(E.ENERGY_GAINED, self._on_energy)
        self.on(E.AFTER_HIT, self._support_true_dmg)
        if self.e(2):
            self.on(E.ACTION_START, self._e2)
            self.on(E.TURN_START, lambda ev: ev.entity is self.char and setattr(self, "e2_ready", True))
        if self.e(4):
            self.on(E.ACTION_START, self._e4)

    def on_battle_start(self) -> None:
        if self.trace(1):
            self.battle.advance(self.char, self.tp(1, 0))

    def technique(self) -> None:
        p = self.sk("technique")["params"][0]
        for e in self.enemies():
            self.battle.delay(e, p[1])
        with self.action(ActionKind.EXTRA, None, label="Memories Back as Echoes (Technique)", energy=0, sp=0) as act:
            act.aoe(p[2], toughness=self.toughness("technique"))

    # --------------------------------------------------------------- data
    def _lv(self, sid: str) -> list[Any]:
        rec = self.sk(sid)
        return list(rec["params"][self.level_of(rec) - 1])

    def epic_max(self) -> int:
        tid = f"{self.prefix}501"  # "Unfinished Epilogue"
        if not self.char.traces_enabled or tid not in self.gd.traces:
            return 0
        return int(self.gd.traces[tid]["params"][0])

    # ---------------------------------------------------------------- Mem
    def mem(self) -> Summon | None:
        return self.memosprite()

    def summon_mem(self) -> Summon:
        mem = self.mem()
        if mem is not None:
            return mem
        mem = self.summon_memosprite("Mem", on_turn=self._mem_turn, servant_id=SERVANT_ID)
        # HP/SPD from this Trailblazer's own Talent record (the servant config points at the 8007 Talent)
        hp_flat, hp_ratio, owner = self.p("talent", 3), self.p("talent", 1), self.char
        mem.base[S.BASE_SPD] = self.p("talent", 0)
        mem.apply_dyn_base(S.BASE_HP, lambda: hp_flat + hp_ratio * owner.max_hp)
        mem.hp = mem.max_hp
        self.battle.apply(
            Modifier(
                "Friends! Together!",
                tick=Tick.NONE,
                scope=self.ally_scope,
                dyn=self._team_cd,
                dyn_keys={S.CRIT_DMG},
                dispellable=False,
                key="Friends! Together!",
            ),
            mem,
            self.char,
        )
        self.add_charge(self._lv("1800705")[0])
        if self.trace(1) and not self.summoned_once:
            self.add_charge(self.tp(1, 1))
        self.summoned_once = True
        return mem

    def _team_cd(self, mod: Modifier, key: str, ent: Entity) -> float:
        """#1% of Mem's CRIT DMG + #2% (Mem's CRIT DMG excluding this aura itself)."""
        mem = self.mem()
        if mem is None or self._cd_guard:
            return 0.0
        self._cd_guard = True
        try:
            cd = mem.stat(S.CRIT_DMG)
        finally:
            self._cd_guard = False
        lv = self._lv("1800703")
        return lv[0] * cd + lv[1]

    def add_charge(self, x: float) -> None:
        mem = self.mem()
        if mem is None or x <= 0:
            return
        before = self.charge
        self.charge = min(1.0, self.charge + x)
        if before < 1.0 <= self.charge + 1e-9:
            self.charge = 1.0
            self.battle.advance(mem, 1.0)  # "When the Charge reaches 100%, Mem immediately takes action"

    def _on_energy(self, ev: E.Ev) -> None:
        if not isinstance(ev.entity, Character) or self.mem() is None:
            return
        self.energy_acc += ev.amount
        step = self.p("talent", 2)
        n = int(self.energy_acc / step)
        if n:
            self.energy_acc -= n * step
            self.add_charge(n * CHARGE_PER_STEP)

    def _mem_turn(self, mem: Summon, battle: Battle) -> None:
        if self.charge >= 1.0 - 1e-9:
            self.lemme(mem, self.main_dps())
        else:
            self.baddies(mem)

    def baddies(self, mem: Summon) -> None:
        rec = self.sk("1800701")
        lv = rec["params"][self.level_of(rec) - 1]
        tough = rec["toughness"]
        target = self.pick_target()
        with self.battle.action(mem, ActionKind.MEMOSPRITE, skill=rec, target=target) as act:
            act.bounce(None, int(lv[1]), lv[0], toughness=float(tough[0]))
            act.aoe(lv[2], toughness=float(tough[1]), main_target=target)
        if self.trace(2):
            self.add_charge(self.tp(2, 0))

    def lemme(self, mem: Summon, ally: Character) -> None:
        rec = self.sk("1800707")
        lv = rec["params"][self.level_of(rec) - 1]
        with self.battle.action(mem, ActionKind.MEMOSPRITE, skill=rec, target=ally):
            self.charge = 0.0
            stats = {S.CRIT_RATE: self.ep(1, 0)} if self.e(1) else {}
            self.buff(ally, Modifier(SUPPORT, stats=stats, duration=int(lv[1]), key=SUPPORT))
        if ally is not mem:
            self.battle.advance(ally, lv[2])

    # --------------------------------------------------------- Mem's Support
    def _support_holder(self, attacker: Entity) -> Character | None:
        if isinstance(attacker, Character) and attacker.has_mod(SUPPORT):
            return attacker
        if self.e(1) and isinstance(attacker, Summon) and attacker.is_memosprite and attacker.owner.has_mod(SUPPORT):
            return attacker.owner  # E1: also applies to the holder's memosprite
        return None

    def support_ratio(self, holder: Character) -> float:
        ratio = float(self._lv("1800707")[0])
        if self.trace(3) and holder.max_energy > self.tp(3, 0):
            steps = int((holder.max_energy - self.tp(3, 0)) / self.tp(3, 1))
            ratio += min(self.tp(3, 3), steps * self.tp(3, 2))
        if self.e(4) and holder.max_energy <= 0:
            ratio += self.ep(4, 1)
        return ratio

    def _support_true_dmg(self, ev: E.Ev) -> None:
        h = ev.hit
        if h.damage <= 0 or DmgTag.TRUE in h.tags:
            return
        holder = self._support_holder(h.attacker)
        if holder is None:
            return
        self.battle.true_damage(h, self.support_ratio(holder), h.target, h.credited, "Mem's Support (True DMG)")

    # ------------------------------------------------------------ eidolons
    def _e2(self, ev: E.Ev) -> None:
        a = ev.action.actor
        if not self.e2_ready or a is self.mem() or not (isinstance(a, Summon) and a.is_memosprite):
            return
        self.e2_ready = False
        self.battle.gain_energy(self.char, self.ep(2, 0))

    def _e4(self, ev: E.Ev) -> None:
        act = ev.action
        if act.kind in ACTIVE_KINDS and isinstance(act.actor, Character) and act.actor.max_energy <= 0:
            self.add_charge(self.ep(4, 0))

    # -------------------------------------------------------------- policy
    def take_turn(self) -> None:
        target = self.pick_target()
        if target is None:
            return
        policy = self.opts.get("rotation", "auto")
        if policy != "basic" and self.can_skill() and (self.mem() is None or policy == "skill"):
            self.skill(target)
        else:
            self.basic(target)

    # ------------------------------------------------------------- actions
    def basic(self, target: Enemy | None) -> None:
        assert target is not None
        mem = self.mem()
        if self.epic <= 0 or mem is None:
            self.simple_basic(target)
            return
        self.epic -= 1
        rec = self.sk(f"{self.char.char_id}08")
        lv = rec["params"][self.level_of(rec) - 1]
        tough = float(rec["toughness"][1])
        with self.action(ActionKind.BASIC, rec, target) as act:
            act.aoe(lv[0], toughness=tough, main_target=target)
            for e in self.enemies():
                memo_hit(act, mem, e, lv[1], tags=(DmgTag.BASIC, DmgTag.MEMOSPRITE), primary=e is target)
        self.add_charge(lv[2])

    def skill(self, target: Enemy | None) -> None:
        mem = self.mem()
        rec = self.sk(f"{self.char.char_id}09") if mem is not None else self.sk("skill")
        with self.action(ActionKind.SKILL, rec, mem):
            if mem is not None:
                self.battle.heal(mem, self.p("skill", 0) * mem.max_hp, self.char)
                self.add_charge(self.p("skill", 1))
            else:
                self.summon_mem()

    def ult(self, target: Enemy | None) -> None:
        with self.action(ActionKind.ULT, "ult", target) as act:
            mem = self.summon_mem()
            self.add_charge(self.p("ult", 1))
            extra = {S.CRIT_RATE: self.ep(6, 0)} if self.e(6) else None
            for e in self.enemies():
                memo_hit(
                    act,
                    mem,
                    e,
                    self.p("ult", 0),
                    toughness=self.toughness("ult", 1),
                    tags=(DmgTag.ULT, DmgTag.MEMOSPRITE),
                    primary=e is target,
                    extra=extra,
                )
        self.epic = min(self.epic_max(), self.epic + 1)


@register
class TrailblazerRemembrance(_TrailblazerRemembrance):
    char_id = "8007"


@register
class TrailblazerRemembranceF(_TrailblazerRemembrance):
    char_id = "8008"
