"""Evernight (长夜月) — Remembrance / Ice. Memosprite Evey (Max HP scaling). "Memoria" builds from HP loss (Evernight's
own HP costs included), abilities and Evey's attacks; at #3 of "Dream, Dissolving, as Dew" Evey immediately acts,
spends every point on an AoE and disappears (Evernight gains SPD). The Skill costs HP instead of SP, (re)summons
Evey and buffs every ally memosprite's CRIT DMG; the Ultimate enters "Darkest Riddle" (vulnerability, DMG boost,
extra Memoria from the Skill) for a number of Evey's "Dream" uses.

Options (``default_opts``):
  * ``rotation``: ``"skill"`` (Skill every turn, default: it costs HP, not SP), ``"auto"`` (Skill only when Evey is
    absent or the memosprite CRIT DMG buff is about to expire, Basic ATK otherwise) or ``"basic"``.

Cyrene protocol: ``on_cyrene_ode(cyrene)`` ("Ode to Time").

# approximation: the Skill's memosprite CRIT DMG conversion always uses the displayed Skill value (141302 #1); the
#   variant used while Evey is on the field (141309) carries an undisplayed #1 of 40% at Lv. 10. Both variants add the
#   same file-level modifier (MAvatar_Evernight_00_Skill02_Buff -> _Buff_Buff, CriticalDamageConvert = dyn) and the
#   ability summary cannot show which skill's parameter the dynamic value reads.
# approximation: Evey's "increased chance of getting attacked" is Aggro +(Memosprite Talent #2) (AggroAddedRatio).
# approximation: "once per target for each received attack" is keyed on the enemy action; every HP consumption
#   (Skill, A2 for Evernight and Evey, Evey's "Dream") counts as a separate HP loss.
# not modelled: Crowd Control immunity / dispels.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from .. import events as E
from .. import stats as S
from ..entities import Enemy, Entity, Summon
from ..enums import ActionKind, DmgTag, Path, Side
from ..modifiers import Modifier, Tick, hidden
from . import register
from .aglaea import memo_hit
from .base import Kit

if TYPE_CHECKING:
    from ..battle import Battle

SKILL_ON_FIELD = "141309"
WHIRL = "1141301"
MEMO_TALENT = "1141303"
PARTING = "1141306"
DREAM = "1141307"
ODE_ID = "1141524"  # Cyrene's "Ode to Time"
ABILITY_KINDS = (ActionKind.BASIC, ActionKind.SKILL, ActionKind.ULT)
# literal numbers of the skill text (not parameters)
DREAM_CHARGE_COST = 1  # Ultimate: "Evey consumes 1 point after it uses Dream, Dissolving, as Dew"
A2_SP = 1  # A2: "recovers 1 Skill Point for allies"


@register
class Evernight(Kit):
    char_id = "1413"
    default_opts = {"rotation": "skill"}

    def setup(self) -> None:
        self.memoria = 0.0
        self.charge = 0
        self.riddle: list[Modifier] = []
        self.trigger_armed = True
        self.skill_buff: Modifier | None = None
        self.last_target: Enemy | None = None
        self.ode: list[float] | None = None
        self.on(E.HP_CHANGED, self._on_hp)
        self.on(E.ACTION_START, self._on_action)
        self.on(E.ACTION_END, lambda ev: ev.action.actor is self.char and self._check_trigger())
        self.on(E.UNIT_ADDED, lambda ev: self._memo_buffs(ev.unit))
        self.on(E.TURN_START, self._turn_start)
        self.passive("Solitude, Drifting, In Murk", {}, dyn=self._memo_talent_dmg, dyn_keys={S.DMG_PCT})
        if self.trace(1):
            self.passive("Dark the Night, Still the Moon", {S.CRIT_RATE: self.tp(1, 0)})
        if self.e(1):
            self.on(E.BEFORE_HIT, self._e1)
        if self.e(2):
            self.passive("Listen Up, the Slumber Speaks Soft", {S.CRIT_DMG: self.ep(2, 2)})
        if self.e(6):
            self.passive("Like This, Always", {S.RES_PEN: self.ep(6, 1)}, scope=self.ally_scope)

    def on_battle_start(self) -> None:
        for u in self.battle.units:
            self._memo_buffs(u)
        if self.trace(2):
            self.battle.gain_energy(self.char, self.tp(2, 1))
            self.gain_memoria(self.tp(2, 2))
        self.summon_evey()  # Talent: "When entering combat, summons memosprite Evey"

    def technique(self) -> None:
        p = self.sk("technique")["params"][0]
        self._skill_buff()
        self.gain_memoria(p[0])

    # ------------------------------------------------------------- helpers
    def _lv(self, sid: str) -> list[Any]:
        rec = self.sk(sid)
        return list(rec["params"][self.level_of(rec) - 1])

    def evey(self) -> Summon | None:
        return self.memosprite()

    @property
    def in_riddle(self) -> bool:
        return bool(self.riddle)

    def _memo_talent_dmg(self, mod: Modifier, key: str, ent: Entity) -> float:
        return self._lv(MEMO_TALENT)[0] if self.evey() is not None else 0.0

    # -------------------------------------------------------------- Memoria
    def gain_memoria(self, n: float) -> None:
        if n <= 0:
            return
        if self.e(2):
            n += self.ep(2, 0)
        self.memoria += n

    def _check_trigger(self) -> None:
        """Talent: at #6 Memoria Evey immediately takes action (with "Dream, Dissolving, as Dew"). The game checks
        when Evernight's action ends (MAvatar_Evernight_00_Passive_Endurance_Control OnActionEnd) and when Evey is
        summoned (MServant_EvernightServant_00_InsertControl), not on every Memoria gain."""
        evey = self.evey()
        if self.trigger_armed and evey is not None and self.memoria >= self.p("talent", 5) and self.enemies():
            self.trigger_armed = False  # re-armed after Evey uses "Dream, Dissolving, as Dew"
            self.battle.advance(evey, 1.0)  # "it immediately takes action"

    def _on_hp(self, ev: E.Ev) -> None:
        ent = ev.entity
        if ev.delta >= 0 or (ent is not self.char and ent is not self.evey()):
            return
        act = self.battle.current_action
        if act is not None and isinstance(act.actor, Enemy):
            # "only once per target for each received attack": remembered on the action itself (id() values are
            # reused once an action is gone, which made results depend on earlier runs)
            seen = act.data.setdefault("evernight_hp_seen", set())
            if ent.uid in seen:
                return
            seen.add(ent.uid)
        self.buff_self(
            Modifier("With Me, This Night", stats={S.CRIT_DMG: self.p("talent", 1)}, duration=int(self.p("talent", 2)))
        )
        self.gain_memoria(self.p("talent", 0))

    def _on_action(self, ev: E.Ev) -> None:
        act = ev.action
        mine = act.actor is self.char and act.kind in ABILITY_KINDS
        memo = isinstance(act.actor, Summon) and act.actor.is_memosprite and act.actor.side == Side.ALLY
        if not (mine or memo):
            return
        # A2 "this unit": Evernight (MAvatar_Evernight_00_PointB1_Aura) and Evey (MAvatar_Evernight_00_PointB1_Servant)
        if self.trace(1) and (mine or act.actor is self.evey()):
            unit = act.actor
            self.battle.lose_hp(unit, self.tp(1, 1) * unit.hp, self.char)
            self.buff_self(
                Modifier("Dark the Night (CRIT DMG)", stats={S.CRIT_DMG: self.tp(1, 2)}, duration=int(self.tp(1, 3)))
            )
        if self.trace(2):
            self.battle.gain_energy(self.char, self.tp(2, 3))
            self.gain_memoria(self.tp(2, 0))

    def _turn_start(self, ev: E.Ev) -> None:
        if ev.entity is not self.char:
            return
        self.battle.remove_named(self.char, "You, Parting, Beyond Reach")
        if self.in_riddle and self.charge <= 0:
            for m in self.riddle:
                self.battle.remove_modifier(m)
            self.riddle = []

    # ------------------------------------------------ memosprite CRIT DMG
    def remembrance_count(self) -> int:
        return sum(1 for c in self.battle.team if c.path == Path.REMEMBRANCE)

    def _skill_cd(self, mod: Modifier, key: str, ent: Entity) -> float:
        if self.skill_buff is None or self.skill_buff.removed or not self.char.alive:
            return 0.0
        ratio = self.p("skill", 0) + (self.ode[2] if self.ode is not None else 0.0)
        value = ratio * self.char.stat(S.CRIT_DMG)
        if self.trace(3):
            n = min(4, self.remembrance_count())
            if n > 0:
                value += self.tp(3, n - 1)
        return value

    def _memo_buffs(self, unit: Entity) -> None:
        if not (isinstance(unit, Summon) and unit.is_memosprite and unit.side == Side.ALLY):
            return
        if unit.has_mod("Day Gently Slips (memosprites)"):
            return
        self.battle.apply(
            hidden("Day Gently Slips (memosprites)", {}, dyn=self._skill_cd, dyn_keys={S.CRIT_DMG}), unit, self.char
        )
        if self.e(4):
            eff = self.ep(4, 0) + (self.ep(4, 1) if unit.owner is self.char else 0.0)
            self.battle.apply(hidden("Wake Up, the Tomorrow is Yours", {S.BREAK_EFF: eff}), unit, self.char)

    def _skill_buff(self) -> None:
        self.skill_buff = self.buff_self(
            Modifier("Day Gently Slips", duration=int(self.p("skill", 1)), tick=Tick.HOLDER_TURN_START)
        )

    # ----------------------------------------------------------------- Evey
    def summon_evey(self) -> Summon:
        evey = self.evey()
        if evey is not None:
            return evey
        evey = self.summon_memosprite("Evey", on_turn=self._evey_turn)
        evey.hp = evey.max_hp
        self.battle.apply(
            hidden("Solitude, Drifting, In Murk (Aggro)", {S.AGGRO_PCT: self._lv(MEMO_TALENT)[1]}), evey, self.char
        )
        self.battle.advance(evey, 1.0)  # "When summoned, this unit immediately takes action"
        self._check_trigger()
        return evey

    def _evey_turn(self, evey: Summon, battle: Battle) -> None:
        if not self.enemies():
            return
        if not self.trigger_armed and self.memoria >= self._lv(DREAM)[2]:  # MServant_..._TriggerNormal maps Dream
            self.dream(evey)
        else:
            self.whirl(evey)

    def whirl(self, evey: Summon) -> None:
        rec = self.sk(WHIRL)
        lv = self._lv(WHIRL)
        last = self.last_target
        target = last if last is not None and last.alive else self.pick_target()
        if target is None:
            return
        mult = lv[0] + lv[1] * int(self.memoria // lv[2])
        with self.battle.action(evey, ActionKind.MEMOSPRITE, skill=rec, target=target) as act:
            act.hit(target, mult, stat="hp", toughness=float(rec["toughness"][0]))
        self.gain_memoria(lv[3])

    def dream(self, evey: Summon) -> None:
        rec = self.sk(DREAM)
        lv = self._lv(DREAM)
        t = rec["toughness"]
        last = self.last_target
        target = last if last is not None and last.alive else self.pick_target()
        if target is None:
            return
        extra = {S.DMG_PCT: self.ode[0]} if self.ode is not None else None
        with self.battle.action(evey, ActionKind.MEMOSPRITE, skill=rec, target=target) as act:
            points = self.memoria  # incl. the Memoria gained when the ability starts (A2 HP cost, A4)
            act.hit(target, lv[0] * points, stat="hp", toughness=float(t[0]), extra=extra)
            for e in self.enemies():
                if e is not target:
                    act.hit(e, lv[1] * points, stat="hp", toughness=float(t[1]), extra=extra, primary=False)
        self.memoria = 0.0
        self.battle.lose_hp(evey, evey.hp, self.char)  # "consumes all Memoria and HP"
        if self.in_riddle:
            self.charge -= DREAM_CHARGE_COST
        if self.trace(1):
            self.battle.gain_sp(A2_SP, self.char)
        self.trigger_armed = True
        self._dismiss(evey, points)
        if self.e(6):
            self.gain_memoria(int(self.ep(6, 0) * points))

    def _dismiss(self, evey: Summon, consumed: float) -> None:
        """Evey disappears: Evernight gains SPD until the start of her next turn (#3 Memoria at most)."""
        self.battle.remove_unit(evey)
        p = self._lv(PARTING)
        spd = p[0] + p[1] * min(p[2], consumed)
        self.buff_self(Modifier("You, Parting, Beyond Reach", stats={S.SPD_PCT: spd}, tick=Tick.NONE))

    # ------------------------------------------------------------- policy
    def take_turn(self) -> None:
        target = self.pick_target()
        if target is None:
            return
        policy = self.opts.get("rotation", "skill")
        expiring = self.skill_buff is None or self.skill_buff.removed or (self.skill_buff.duration or 0) <= 1
        if policy == "basic" or (policy == "auto" and self.evey() is not None and not expiring):
            self.basic(target)
        else:
            self.skill(target)

    # ------------------------------------------------------------ actions
    def basic(self, target: Enemy | None) -> None:
        assert target is not None
        self.last_target = target
        with self.action(ActionKind.BASIC, "basic", target) as act:
            act.hit(target, self.p("basic", 0), stat="hp", toughness=self.toughness("basic"), splits="data")

    def skill(self, target: Enemy | None) -> None:
        evey = self.evey()
        rec = self.sk(SKILL_ON_FIELD) if evey is not None else self.sk("skill")
        lv = list(rec["params"][self.level_of(rec) - 1])
        with self.action(ActionKind.SKILL, rec, evey or self.char):
            self.battle.lose_hp(self.char, lv[5] * self.char.hp, self.char)
            if evey is not None:
                self.battle.heal(evey, lv[3] * evey.max_hp, self.char)
            self._skill_buff()
            self.gain_memoria(lv[2] + (lv[4] if self.in_riddle else 0.0))
            if evey is None:
                self.summon_evey()
            if self.ode is not None:  # Ode to Time (OnAfterSkillUse, before the action ends)
                self.gain_memoria(self.ode[1])

    def ult(self, target: Enemy | None) -> None:
        with self.action(ActionKind.ULT, "ult", target) as act:
            evey = self.summon_evey()
            for e in self.enemies():
                memo_hit(
                    act,
                    evey,
                    e,
                    self.p("ult", 0),
                    stat="hp",
                    toughness=self.toughness("ult", 1),
                    tags=(DmgTag.ULT, DmgTag.MEMOSPRITE),
                    primary=e is target,
                )
            self.charge += int(self.p("ult", 1)) + (int(self.ep(2, 1)) if self.e(2) else 0)
            if not self.in_riddle:
                self.riddle = [
                    self.buff_self(hidden("Darkest Riddle", {S.DMG_PCT: self.p("ult", 2)})),
                    self.buff_self(
                        hidden(
                            "Darkest Riddle (Vulnerability)",
                            {S.VULN: self.p("ult", 3)},
                            scope=self.enemy_scope,
                            key="Darkest Riddle (Vulnerability)",
                        )
                    ),
                ]
            if self.ode is not None:  # Ode to Time (OnAfterSkillUse, before the action ends)
                self.gain_memoria(self.ode[1])

    # ------------------------------------------------------------ eidolons
    def _e1(self, ev: E.Ev) -> None:
        h = ev.hit
        a = h.attacker
        if not (isinstance(a, Summon) and a.is_memosprite and a.side == Side.ALLY) or not self.char.alive:
            return
        n = len(self.enemies())
        if n <= 0:
            return
        factor = self.ep(1, 3) if n == 1 else self.ep(1, 2) if n == 2 else self.ep(1, 1) if n == 3 else self.ep(1, 0)
        h.add(S.FINAL_DMG, factor - 1.0)

    # ---------------------------------------------------- Cyrene protocol
    def on_cyrene_ode(self, cyrene: Kit) -> None:
        """Cyrene's "Ode to Time" (for the entire battle): Dream DMG, extra Memoria, stronger Skill CRIT DMG buff."""
        self.ode = cyrene.ode_params(ODE_ID)  # type: ignore[attr-defined]
