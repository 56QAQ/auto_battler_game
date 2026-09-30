"""Phainon (白厄) — Destruction / Physical. No Energy: "Coreflame" (Ultimate at #4 of the Talent) comes from the
Skill and from being targeted by abilities. The Ultimate transforms him into Khaslana: teammates depart, all enemies
gain a Physical Weakness and Khaslana acts only on #4 extra turns ("battle events" at #3 x Phainon's base SPD, evenly
spread over one of their gauges; the last one launches the final hit). Khaslana uses the Enhanced Basic ATK
"Creation" and the Enhanced Skills "Calamity" (Soulscorch + Counter) and "Foundation" (consumes "Scourge").

Options (``default_opts``):
  * ``rotation``: ``"skill"`` (Skill whenever SP allows, default) or ``"basic"``.
  * ``khaslana``: Khaslana's policy: ``"auto"`` (default: Foundation at 4+ Scourge or on the last action while any
    Scourge is left, Calamity when at least ``calamity_enemies`` enemies are on the field, Creation otherwise),
    ``"creation"`` (never Calamity) or ``"calamity"`` (Calamity whenever Foundation is not used).
  * ``calamity_enemies``: enemy count from which ``"auto"`` prefers Calamity over Creation (default 3).
  * ``ignition_refreshes``: cap on the "Eternal Ignition" refreshes per transformation (Cyrene's "Ode to
    Worldbearing"); ``None`` (default) = unlimited as in the game, where only a killing blow ends it.
  * ``wait_for_cyrene``: with Cyrene in the team, hold the Ultimate until her Demiurge has cast its Ode on Phainon
    (default True; the game's auto-battle does the same, ``_M_Cyrene_00_Phainon_ForbidAutoUltraBeforeCyreneUltra``).

Cyrene protocol: ``on_cyrene_ode(cyrene)`` ("Ode to Worldbearing") and ``fill_special_resource()`` (Cyrene's Ultimate
sets every teammate's Energy / special resource to its maximum).

# approximation: departed teammates (and their memosprites / countdowns) are taken out of the battle for the duration
#   (``alive = False``: no turns, no Ultimates, not targetable, queued follow-ups dropped). Their action gauges (and
#   Phainon's own) are frozen and restored afterwards (the ability script records the Action Order; the "SPD +15% for
#   1 turn" on return only matters if the gauges did not keep running).
# approximation: the Energy bar is only used to detect "Energy Regeneration from a teammate's ability" (A4): any Energy
#   gained is discarded, Coreflame is tracked by the kit.
# approximation: "targeted by an ability" counts single-target ally abilities (ALLY_TARGETED) and enemy attacks.
# not modelled: Crowd Control immunity; the ability-target rules of the Calamity Counter for enemies that act twice.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from .. import events as E
from .. import formulas as F
from .. import stats as S
from ..entities import Character, Enemy, Entity, Summon
from ..enums import ActionKind, DmgTag, Element, Side
from ..modifiers import Modifier, ModKind, Stacking, Tick, hidden
from . import register
from .base import Kit

if TYPE_CHECKING:
    from ..battle import Battle

KHASLANA_TALENT = "140805"
CREATION = "140808"
CALAMITY = "140809"
FOUNDATION = "140811"
ODE_ID = "1141521"  # Cyrene's "Ode to Worldbearing"
CYRENE_ID = "1415"
SCOURGE_MAX = 7  # "Skill22_Energy_Max" in the ability script (not part of the skill data)
TERRITORY = "Ruinous Irontomb"
# literal numbers of the skill text (not parameters)
TARGETED_COREFLAME = 1  # Talent: "When Phainon is targeted by an ability ... gains 1 Coreflame point"
SOULSCORCH_STEP = 1  # Calamity: "1 stack of Soulscorch" / "gains 1 more stack"
END_SPD_TURNS = 1  # Khaslana's Talent: "increases all allies' SPD by #6 for 1 turn"


@register
class Phainon(Kit):
    char_id = "1408"
    default_opts = {
        "rotation": "skill",
        "khaslana": "auto",
        "calamity_enemies": 3,
        "ignition_refreshes": None,
        "wait_for_cyrene": True,
    }

    def setup(self) -> None:
        self.char.energy = 0.0
        self.coreflame = 0.0
        self.kept_overflow = 0.0  # Coreflame above the Ultimate cost, returned when the transformation ends
        self.excess = 0.0
        self.scourge = 0
        self.transformed = False
        self.k_mod: Modifier | None = None
        self.bes: list[Summon] = []  # remaining Khaslana extra turns (battle events)
        self.departed: list[tuple[Entity, float]] = []
        self.k_turn = False  # a Khaslana extra turn is in progress
        self.soulscorch = 0
        self.soul_mod: Modifier | None = None
        self.marked: set[int] = set()
        self.counter_queued = False
        self.kills = 0
        self.refreshes = 0
        self.ode: list[float] | None = None
        self.lethal = False
        self.a4_turn = -1
        self.on(E.ALLY_TARGETED, self._targeted)
        self.on(E.ALLY_ATTACKED, self._attacked)
        self.on(E.ENERGY_GAINED, self._energy)
        self.on(E.ATTACK_END, self._after_attack)
        self.on(E.TURN_END, self._enemy_turn_end)
        self.on(E.KILL, self._on_kill)
        self.on(E.ENEMY_SPAWNED, lambda ev: self.transformed and self._territory(ev.enemy))
        self.on(E.BEFORE_ALLY_HIT, self._before_hit_taken)
        self.on(E.ACTION_END, self._after_enemy_action)
        if self.trace(2):
            self.on(E.HEALED, self._a4_heal)
            self.on(E.MOD_APPLIED, self._a4_shield)

    def on_battle_start(self) -> None:
        if self.trace(1):
            self.add_coreflame(self.tp(1, 1))
        if self.e(6):
            self.add_coreflame(self.ep(6, 1))
        if self.trace(3):
            self._a6()

    def technique(self) -> None:
        p = self.sk("technique")["params"][0]
        for c in self.teammates():  # FixedAddValue in the ability script
            self.battle.gain_energy(c, p[2], fixed=True)
        self.scourge = min(SCOURGE_MAX, self.scourge + int(p[1]))
        self.battle.gain_sp(int(p[3]), self.char)
        self._technique_hit(p[0])
        self.on(E.WAVE_START, lambda ev: ev.wave > 0 and self._technique_hit(p[0]))

    def _technique_hit(self, mult: float) -> None:
        if not self.enemies():
            return
        with self.action(ActionKind.EXTRA, None, label="Beginning of the End (Technique)", energy=0, sp=0) as act:
            act.aoe(mult, toughness=self.toughness("technique"))

    # ------------------------------------------------------------ helpers
    def _lv(self, sid: str) -> list[Any]:
        rec = self.sk(sid)
        return list(rec["params"][self.level_of(rec) - 1])

    def _a6(self) -> None:
        self.buff_self(
            hidden(
                "Shine with Valor",
                {S.ATK_PCT: self.tp(3, 0)},
                stacking=Stacking.STACK,
                max_stacks=int(self.tp(3, 1)),
            )
        )

    # ----------------------------------------------------------- Coreflame
    def coreflame_cap(self) -> float:
        need = self.p("talent", 3)
        return float("inf") if self.e(6) else need + self.p("talent", 2)

    def add_coreflame(self, n: float) -> None:
        self.coreflame = min(self.coreflame_cap(), self.coreflame + n)

    def fill_special_resource(self) -> None:
        """Cyrene's Ultimate: Coreflame to the Ultimate cost (existing overflow is kept)."""
        self.coreflame = max(self.coreflame, self.p("talent", 3))

    def ult_ready(self) -> bool:
        return not self.transformed and self.coreflame >= self.p("talent", 3) - 1e-9

    def want_ult(self) -> bool:
        if not self.opts.get("ult", True):
            return False
        if self.opts.get("wait_for_cyrene", True) and self.ode is None:
            for c in self.battle.team:
                if c.char_id == CYRENE_ID and c.alive and c.kit is not None and not getattr(c.kit, "rippled", True):
                    return False  # Cyrene's first Ultimate has not come yet
        return True

    def pay_ult_cost(self) -> None:
        self.excess = max(0.0, self.coreflame - self.p("talent", 3))
        self.kept_overflow = self.excess
        self.coreflame = 0.0

    def _energy(self, ev: E.Ev) -> None:
        if ev.entity is not self.char:
            return
        self.char.energy = 0.0
        act = self.battle.current_action
        if self.trace(2) and act is not None and act.owner is not self.char and act.owner.side == Side.ALLY:
            self.add_coreflame(self.tp(2, 2))  # A4: Energy Regeneration from a teammate's ability

    def _targeted(self, ev: E.Ev) -> None:
        # the listener is gated on "not transformed" (PassiveSkill01: ByIsContainModifier NOT MAvatar_Phainon_00_Ultra)
        if ev.target is not self.char or ev.source is self.char or self.transformed:
            return
        self.add_coreflame(TARGETED_COREFLAME)
        if ev.source is not None and ev.source.side == Side.ALLY:
            self.buff_self(
                Modifier("Pyric Corpus", stats={S.CRIT_DMG: self.p("talent", 0)}, duration=int(self.p("talent", 1)))
            )

    def _attacked(self, ev: E.Ev) -> None:
        if self.char in ev.targets and not self.transformed:
            self.add_coreflame(TARGETED_COREFLAME)

    # ------------------------------------------------------------------ A4
    def _a4(self) -> None:
        if self.a4_turn == self.battle.turns:
            return  # "cannot trigger repeatedly within one turn"
        self.a4_turn = self.battle.turns
        self.buff_self(Modifier("Bide in Flames", stats={S.DMG_PCT: self.tp(2, 0)}, duration=int(self.tp(2, 1))))

    def _a4_heal(self, ev: E.Ev) -> None:
        src = ev.source
        if ev.entity is self.char and src is not None and src is not self.char and src.side == Side.ALLY:
            self._a4()

    def _a4_shield(self, ev: E.Ev) -> None:
        src = ev.mod.source
        if ev.target is not self.char or "shield" not in ev.mod.tags or src is None or src is self.char:
            return
        if src.side == Side.ALLY:
            self._a4()

    # ---------------------------------------------------- Cyrene protocol
    def on_cyrene_ode(self, cyrene: Kit) -> None:
        """Cyrene's "Ode to Worldbearing": #8 Coreflame now, "Eternal Ignition" on every later transformation."""
        self.ode = cyrene.ode_params(ODE_ID)  # type: ignore[attr-defined]
        self.add_coreflame(self.ode[7])

    # ------------------------------------------------------------- policy
    def take_turn(self) -> None:
        if self.transformed:
            if self.k_turn:
                self._khaslana_action()
            return  # "Khaslana does not enter his own turn"
        target = self.pick_target()
        if target is None:
            return
        if self.opts.get("rotation", "skill") == "basic" or not self.can_skill():
            self.basic(target)
        else:
            self.skill(target)

    # ------------------------------------------------------------ actions
    def basic(self, target: Enemy | None) -> None:
        assert target is not None
        self.simple_basic(target)

    def skill(self, target: Enemy | None) -> None:
        assert target is not None
        self.add_coreflame(self.p("skill", 2))
        with self.action(ActionKind.SKILL, "skill", target) as act:
            act.blast(
                target,
                self.p("skill", 0),
                self.p("skill", 1),
                toughness=(self.toughness("skill", 0), self.toughness("skill", 2)),
            )

    def ult(self, target: Enemy | None) -> None:
        with self.action(ActionKind.ULT, "ult", target):
            if self.e(1):
                self.buff_self(
                    Modifier("Fire and Light Bind", stats={S.CRIT_DMG: self.ep(1, 1)}, duration=int(self.ep(1, 2)))
                )
            self._transform()

    # ------------------------------------------------------ transformation
    def _transform(self) -> None:
        b = self.battle
        kt = self._lv(KHASLANA_TALENT)
        self.transformed = True
        self.refreshes = 0
        self.scourge = min(SCOURGE_MAX, self.scourge + int(kt[0]))
        cur = b.current_turn
        if isinstance(cur, Character) and cur.alive:
            for m in cur.buffs:  # "the duration of all buffs on that target is extended by 1 turn"
                if m.duration is not None:
                    m.duration += 1
        ratio = self.char.hp_ratio
        stats = {S.ATK_PCT: kt[3], S.HP_PCT: kt[4]}
        if self.e(2):
            stats[f"{S.RES_PEN}:{Element.PHYSICAL.value}"] = self.ep(2, 1)
        if self.ode is not None:  # "Eternal Ignition"
            stats[S.CRIT_RATE] = self.ode[0]
            over = max(0, int(self.excess + self.p("talent", 3) - self.ode[4]))
            stats[S.CRIT_DMG] = min(self.ode[6], self.ode[5] * over)
        self.k_mod = self.buff_self(hidden("Khaslana", stats))
        self.char.hp = ratio * self.char.max_hp
        for e in self.enemies():
            self._territory(e)
        self._depart()
        self._spawn_extra_turns()

    def _territory(self, e: Enemy) -> None:
        mod = Modifier(
            TERRITORY,
            kind=ModKind.OTHER,
            tick=Tick.NONE,
            tags={f"weak:{Element.PHYSICAL.value}"},
            dispellable=False,
            key=TERRITORY,
        )
        self.battle.apply(mod, e, self.char)

    def _depart(self) -> None:
        """Teammates (and their units) depart; Phainon leaves his own place on the Action Order."""
        b = self.battle
        ents: list[Entity] = [c for c in b.team if c.alive]
        ents += [u for u in b.units if isinstance(u, Summon) and u.alive and u.owner is not self.char]
        ents = [e for e in ents if e is self.char or e.side == Side.ALLY]
        ents.sort(key=b._order_key)  # the ability script records this order and restores it afterwards
        self.departed = [(e, e.gauge) for e in ents]
        for e in ents:
            if e is self.char:
                e.on_timeline = False
            else:
                e.alive = False

    def _return(self) -> None:
        b = self.battle
        for e, gauge in self.departed:
            if isinstance(e, Summon) and e not in b.units:
                continue  # removed while departed
            if e is self.char:
                e.on_timeline = True
            else:
                e.alive = True
            e.gauge = gauge  # frozen while departed
            if e.gauge <= 0:
                b.advance(e, 0.0)  # ties at 0 AV resolve in the recorded order
        self.departed = []

    def _be_speed(self) -> float:
        ratio = self.p("ult", 2)
        if self.e(1):
            ratio = min(self.ep(1, 3), self.ep(1, 4) + self.ep(1, 0) * self.kills)
        return ratio * self.char.raw(S.BASE_SPD)

    def _spawn_extra_turns(self) -> None:
        n = int(self.p("ult", 3))
        spd = self._be_speed()
        self.bes = []
        for i in range(n):
            u = Summon(f"Khaslana Extra Turn {i + 1}", self.char, spd=spd, stat_mode="self", on_turn=self._be_turn)
            u.data_flags["final"] = i == n - 1
            self.battle.add_unit(u)
            u.gauge = F.AV_BASE * i / max(1, n - 1)  # SetActionDelay BE_Index / (BE_Count - 1)
            if u.gauge <= 0:
                self.battle.advance(u, 0.0)
            self.bes.append(u)

    def _be_turn(self, unit: Summon, battle: Battle) -> None:
        final = bool(unit.data_flags.get("final"))
        if unit in self.bes:
            self.bes.remove(unit)
        self.battle.remove_unit(unit)
        if not self.transformed:
            return
        if final:  # "When the last of Khaslana's extra turns starts, immediately launches a final hit"
            self.battle.queue_action(lambda: self._final_hit(0), self.char, "Khaslana final hit", 0, False)
        else:
            self.battle.queue_action(self._khaslana_turn, self.char, "Khaslana extra turn", 0)

    def _khaslana_turn(self) -> None:
        if not self.transformed:
            return
        self.k_turn = True
        try:
            self.battle.take_turn(self.char, extra_turn=True)
        finally:
            self.k_turn = False

    def _can_refresh(self) -> bool:
        cap = self.opts.get("ignition_refreshes")
        return self.ode is not None and (cap is None or self.refreshes < int(cap))

    def _final_hit(self, remaining: int) -> None:
        if not self.transformed:
            return
        kt = self._lv(KHASLANA_TALENT)
        enemies = self.enemies()
        if enemies:
            mult = self.p("ult", 0) * max(0.0, 1.0 - kt[2] * remaining)
            n = len(enemies)
            tough = self.toughness("ult", 1) / n
            with self.action(ActionKind.EXTRA, "ult", None, tags=(DmgTag.ULT,), label="Khaslana: Final Hit") as act:
                for e in enemies:  # "distributed evenly across all enemies"
                    act.hit(e, mult / n, toughness=tough)
        if remaining == 0 and self._can_refresh():
            assert self.ode is not None
            self.refreshes += 1
            self.scourge = min(SCOURGE_MAX, self.scourge + int(self.ode[8]))
            self._spawn_extra_turns()
            return
        self._end_transformation()

    def _end_transformation(self) -> None:
        kt = self._lv(KHASLANA_TALENT)
        self.transformed = False
        if self.k_mod is not None:
            self.battle.remove_modifier(self.k_mod)
            self.k_mod = None
        self._clear_soulscorch()
        for u in self.bes:
            self.battle.remove_unit(u)
        self.bes = []
        for e in self.battle.enemies:
            self.battle.remove_named(e, TERRITORY)
        self.char.hp = min(self.char.hp, self.char.max_hp)
        self.add_coreflame(self.kept_overflow)
        self.kept_overflow = 0.0
        if self.trace(1):
            self.add_coreflame(self.tp(1, 0))
        if self.trace(3):
            self._a6()
        self._return()
        allies: list[Entity] = list(self.allies())
        allies += [u for u in self.battle.units if u.alive and u.is_memosprite]
        for a in allies:
            self.buff(a, Modifier("Khaslana: SPD Boost", stats={S.SPD_PCT: kt[5]}, duration=END_SPD_TURNS))

    # ------------------------------------------------------- Khaslana turn
    def _khaslana_action(self) -> None:
        if self.ode is not None:  # "At the start of extra turns, Khaslana consumes HP"
            self.battle.lose_hp(self.char, self.ode[1] * self.char.hp, self.char)
        if self.soulscorch > 0:  # "If Soulscorch is still active at the start of Khaslana's extra turn"
            self._counter()
        target = self.pick_target()
        if target is None or not self.transformed:
            return
        choice = self._choose()
        if choice == "foundation":
            self.foundation(target)
        elif choice == "calamity":
            self.calamity(target)
        else:
            self.creation(target)

    def _choose(self) -> str:
        need = int(self._lv(FOUNDATION)[3])
        if self.scourge >= need:
            return "foundation"
        last = not any(not u.data_flags.get("final") for u in self.bes) and not self._can_refresh()
        if last and self.scourge > 0:
            return "foundation"
        policy = self.opts.get("khaslana", "auto")
        if policy == "calamity":
            return "calamity"
        if policy == "auto" and len(self.enemies()) >= int(self.opts.get("calamity_enemies", 3)):
            return "calamity"
        return "creation"

    def creation(self, target: Enemy) -> None:
        rec = self.sk(CREATION)
        lv = self._lv(CREATION)
        t = rec["toughness"]
        self.scourge = min(SCOURGE_MAX, self.scourge + int(lv[2]))
        with self.action(ActionKind.BASIC, rec, target) as act:
            act.blast(target, lv[0], lv[1], toughness=(float(t[0]), float(t[2])), splits="data")

    def calamity(self, target: Enemy) -> None:
        rec = self.sk(CALAMITY)
        lv = self._lv(CALAMITY)
        with self.action(ActionKind.SKILL, rec, target):
            enemies = self.enemies()
            self.scourge = min(SCOURGE_MAX, self.scourge + len(enemies))
            self.soulscorch += SOULSCORCH_STEP + (int(self.ep(4, 0)) if self.e(4) else 0)
            if self.soul_mod is None:
                self.soul_mod = self.buff_self(
                    Modifier("Soulscorch", stats={S.MITIGATION: lv[1]}, tick=Tick.NONE, dispellable=False)
                )
            self.marked = {e.uid for e in enemies}
            self.counter_queued = False
            for e in enemies:  # "causes all enemies to immediately take action"
                self.battle.advance(e, 1.0)

    def foundation(self, target: Enemy) -> None:
        rec = self.sk(FOUNDATION)
        lv = self._lv(FOUNDATION)
        t = rec["toughness"]
        need, per = int(lv[3]), int(lv[2])
        used = min(self.scourge, need)
        self.scourge -= used
        for m in self.char.debuffs:  # "Dispels all debuffs on this unit"
            if m.dispellable:
                self.battle.remove_modifier(m)
        with self.action(ActionKind.SKILL, rec, target) as act:
            if used:
                act.bounce(None, used * per, lv[1], toughness=float(t[0]))
            if used >= need:
                enemies = self.enemies()
                n = len(enemies)
                for e in enemies:  # "evenly distributed across all enemies"
                    act.hit(e, lv[0] / n, toughness=float(t[1]) / n, primary=e is target)
        if self.e(6) and act.hits:
            alive = self.enemies()
            if alive:
                total = sum(h.damage for h in act.hits)
                top = max(alive, key=lambda e: e.hp)
                self.battle.true_damage(total, self.ep(6, 0), top, self.char, "Embers of Old Rise Still (True DMG)")
        if self.e(2) and used >= int(self.ep(2, 0)):
            self.battle.queue_action(self._khaslana_turn, self.char, "Khaslana extra turn (E2)", 20)

    # -------------------------------------------------- Soulscorch / Counter
    def _clear_soulscorch(self) -> None:
        self.soulscorch = 0
        self.marked = set()
        self.counter_queued = False
        if self.soul_mod is not None:
            self.battle.remove_modifier(self.soul_mod)
            self.soul_mod = None

    def _maybe_counter(self) -> None:
        if self.soulscorch <= 0 or self.counter_queued:
            return
        if any(e.uid in self.marked for e in self.enemies()):
            return
        self.counter_queued = True
        self.battle.queue_action(self._counter, self.char, "Calamity Counter")

    def _enemy_turn_end(self, ev: E.Ev) -> None:
        if self.soulscorch > 0 and isinstance(ev.entity, Enemy):
            self.soulscorch += SOULSCORCH_STEP  # "After an enemy target attacks or takes action"
            self.marked.discard(ev.entity.uid)
            self._maybe_counter()

    def _counter(self) -> None:
        stacks = self.soulscorch
        if stacks <= 0 or not self.transformed:
            return
        self._clear_soulscorch()
        if not self.enemies():
            return
        rec = self.sk(CALAMITY)
        lv = self._lv(CALAMITY)
        t = rec["toughness"]
        factor = 1.0 + lv[4] * stacks
        with self.action(ActionKind.FUA, rec, None, tags=(DmgTag.SKILL,), label="Calamity: Counter") as act:
            act.aoe(lv[0] * factor, toughness=float(t[1]))
            act.bounce(None, int(lv[2]), lv[3] * factor, toughness=float(t[0]))

    # ----------------------------------------------------- after attacks
    def _after_attack(self, ev: E.Ev) -> None:
        act = ev.attack
        if act.actor is not self.char or not self.transformed:
            return
        kt = self._lv(KHASLANA_TALENT)
        self.battle.heal(self.char, kt[6] * self.char.max_hp, self.char)
        if self.ode is not None:
            for _ in range(int(self.ode[2])):
                alive = self.enemies()
                if not alive:
                    break
                self.battle.additional_damage(
                    self.char,
                    self.battle.rng.choice(alive),
                    self.ode[3],
                    element=Element.FIRE,
                    label="Eternal Ignition (Additional DMG)",
                )

    def _on_kill(self, ev: E.Ev) -> None:
        self.kills += 1
        if self.e(1):
            spd = self._be_speed()
            for u in self.bes:
                u.base[S.BASE_SPD] = spd
        self.marked.discard(ev.target.uid)
        if self.soulscorch > 0:
            self._maybe_counter()

    # ------------------------------------------------------- killing blow
    def _before_hit_taken(self, ev: E.Ev) -> None:
        if not self.transformed or ev.target is not self.char:
            return
        if ev.damage - self.battle.shield_value(self.char) >= self.char.hp:
            self.lethal = True

    def _after_enemy_action(self, ev: E.Ev) -> None:
        if not self.lethal or not isinstance(ev.action.actor, Enemy):
            return
        self.lethal = False
        if not self.transformed:
            return
        kt = self._lv(KHASLANA_TALENT)
        self.battle.heal(self.char, kt[1] * self.char.max_hp, self.char)
        remaining = len(self.bes)
        for u in self.bes:
            self.battle.remove_unit(u)
        self.bes = []
        self.battle.queue_action(lambda: self._final_hit(remaining), self.char, "Khaslana final hit", 0, False)
