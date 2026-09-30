"""Cyrene (昔涟) — Remembrance / Ice. No Energy: "Recollection" (Talent #4 for the first Ultimate, #5 afterwards, up to
#3) comes from her Basic ATK / Skill and from teammates acting with "Future". Her Skill Zone makes every ally DMG
instance deal an extra True DMG instance; the Talent boosts the team's DMG. The Ultimate (once per battle) summons the
memosprite Demiurge (SPD 0, off the Action Order), gives it an extra turn, fills every teammate's Ultimate, keeps the
Zone up for the rest of the battle and enhances her Basic ATK; later Ultimates ("Reunion at First Sight") only give
Demiurge extra turns. On its extra turns Demiurge casts an "Ode" on an ally (character-specific special effects for
Chrysos Heirs, DMG boost otherwise) or attacks with "Minuet of Blooms and Plumes" ("Ode to Ego" bounces, "Story").

Options (``default_opts``):
  * ``rotation``: ``"auto"`` (Skill when the Zone is missing or about to expire, Basic ATK otherwise; default),
    ``"skill"`` (Skill whenever SP allows) or ``"basic"``.
  * ``ode_targets``: ally names in priority order for Demiurge's Ode (default: ``target`` / the first teammate, then
    the other teammates in slot order). Each Ode goes to the first ally that has not received one yet, then to the
    first ally whose Ode can usefully be cast again (non-Chrysos Heirs and one-time Odes); otherwise Demiurge attacks.
  * ``target``: see ``ode_targets``.

Cyrene protocol (for the teammates' kits): ``ode_params(skill_id)`` returns the parameters of one of Demiurge's
Memosprite Skills; a teammate kit may implement ``on_cyrene_ode(cyrene)`` (its Ode), ``on_demiurge_skill(cyrene)``
(called whenever Demiurge uses a Memosprite Skill) and ``fill_special_resource()`` (Cyrene's Ultimate).
Odes implemented here for kits without the hook: Trailblazer (Remembrance) "Genesis", Aglaea "Romance", Tribbie
"Passage" (DEF ignore), Mydei "Strife", Anaxa "Reason", Cipher "Trickery", Hyacine "Sky" (Energy only).

# not modelled: Castorice "Ode to Life and Death" (Newbud overflow lives inside her kit); Tribbie's extra Zone
#   Additional DMG instance; Anaxa's extra Skill DMG instances; Hyacine's "Ode to Sky" healing tally; other kits'
#   special resources unless they implement ``fill_special_resource``; Demiurge's own effect durations ticking after
#   its abilities; Crowd Control dispels; the Zone being dispelled when Cyrene is downed (allies are immortal).
# approximation: "Future" is consumed at the end of the holder's turn.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from .. import events as E
from .. import stats as S
from ..entities import Character, Enemy, Entity, Summon
from ..enums import ActionKind, DmgTag, Element, Path, Side
from ..modifiers import Modifier, Tick, hidden
from . import register
from .base import Kit

if TYPE_CHECKING:
    from ..battle import Hit

ENHANCED_BASIC = "141508"
REUNION = "141514"
MINUET = "1141501"
ODE_NORMAL = "1141502"
WAITING = "1141503"
EGO = "1141526"
GENESIS, ROMANCE, PASSAGE, STRIFE, LIFE_DEATH, REASON = "1141513", "1141514", "1141515", "1141516", "1141517", "1141518"
SKY, TRICKERY, WORLDBEARING, OCEAN, LAW, TIME, EARTH = (
    "1141519",
    "1141520",
    "1141521",
    "1141522",
    "1141523",
    "1141524",
    "1141525",
)
# Chrysos Heirs and their special Odes (character tag, not part of the skill data)
ODE_BY_CHAR = {
    "1402": ROMANCE,
    "1403": PASSAGE,
    "1404": STRIFE,
    "1405": REASON,
    "1406": TRICKERY,
    "1407": LIFE_DEATH,
    "1408": WORLDBEARING,
    "1409": SKY,
    "1410": OCEAN,
    "1412": LAW,
    "1413": TIME,
    "1414": EARTH,
    "8007": GENESIS,
    "8008": GENESIS,
}
CHRYSOS_HEIRS = frozenset(ODE_BY_CHAR) | {"1415"}
REPEATABLE = frozenset({ODE_NORMAL, ROMANCE, STRIFE, REASON, SKY, OCEAN, EARTH})  # one-time / refreshable Odes
ZONE = "Bloom, Elysium of Beyond"
STORY_GAIN = 1  # Ode to Ego: "Demiurge immediately gains 1 Story" (literal)


@register
class Cyrene(Kit):
    char_id = "1415"
    default_opts = {"rotation": "auto", "ode_targets": None, "target": None}

    def setup(self) -> None:
        self.char.max_energy = 0.0  # "Recollection" replaces Energy
        self.char.energy = 0.0
        self.recollection = 0.0
        self.rippled = False  # "Ripples of Past Reverie" (after the first Ultimate)
        self.zone: Modifier | None = None
        self.future: set[int] = set()
        self.contributors: set[str] = set()  # teammates Cyrene gained Recollection from ("Ode to Ego")
        self.story = 0
        self.ode_given: dict[int, int] = {}
        self.e4_stacks = 0
        self.ego_triggers = 0
        self.genesis: set[int] = set()
        self.on(E.TURN_END, self._turn_end)
        self.on(E.AFTER_HIT, self._zone_true_dmg)
        self.on(E.ACTION_END, self._genesis_minuet)
        if self.trace(1):
            self.on(E.UNIT_ADDED, self._a2)
        self.passive("Hearts Gather as One", {S.DMG_PCT: self.p("talent", 1)}, scope=self.ally_scope)
        if self.trace(3):
            self.passive("Causality in Trichotomy", {}, dyn=self._a6_dmg, dyn_keys={S.DMG_PCT}, scope=self.ally_scope)
            self.passive("Causality in Trichotomy (RES PEN)", {}, dyn=self._a6_pen, dyn_keys={self._ice_pen})
        if self.e(6):
            self.passive(
                "Remembrance, Sung in Ripples", {}, dyn=self._e6_def, dyn_keys={S.DEF_REDUCTION}, scope=self.enemy_scope
            )

    def on_battle_start(self) -> None:
        self._grant_future()
        if self.trace(2):
            n = sum(
                1
                for c in self.battle.team
                if c is not self.char and (c.char_id in CHRYSOS_HEIRS or c.path == Path.REMEMBRANCE)
            )
            if n > 0:
                self.gain_recollection(self.tp(2, min(3, n) - 1))
        if self.e(2):
            self.gain_recollection(self.ep(2, 0))

    def technique(self) -> None:
        self._deploy_zone(permanent=False)

    # ------------------------------------------------------------- helpers
    def _lv(self, sid: str) -> list[Any]:
        rec = self.sk(sid)
        return list(rec["params"][self.level_of(rec) - 1])

    def ode_params(self, sid: str) -> list[float]:
        """Parameters of one of Demiurge's Memosprite Skills (the Odes) at Cyrene's level."""
        return [float(x) for x in self._lv(sid)]

    def demiurge(self) -> Summon | None:
        return self.memosprite()

    @property
    def _ice_pen(self) -> str:
        return f"{S.RES_PEN}:{Element.ICE.value}"

    def _a6_dmg(self, mod: Modifier, key: str, ent: Entity) -> float:
        return self.tp(3, 3) if self.char.spd >= self.tp(3, 0) else 0.0

    def _a6_pen(self, mod: Modifier, key: str, ent: Entity) -> float:
        over = min(self.tp(3, 2), int(self.char.spd - self.tp(3, 0)))
        return self.tp(3, 1) * over if over > 0 else 0.0

    def _e6_def(self, mod: Modifier, key: str, ent: Entity) -> float:
        return self.ep(6, 1) if self.ego_triggers >= 1 and self.demiurge() is not None else 0.0

    # --------------------------------------------------------- Recollection
    def rec_cap(self) -> float:
        return self.p("talent", 2)

    def gain_recollection(self, n: float, source: Entity | None = None) -> None:
        if source is not None and source is not self.char and source is not self.demiurge():
            # a re-summoned memosprite is the same teammate
            key = f"memo{source.owner.uid}" if isinstance(source, Summon) else f"char{source.uid}"
            self.contributors.add(key)
        self.recollection = min(self.rec_cap(), self.recollection + n)

    def _ult_cost(self) -> float:
        return self.p("talent", 4) if self.rippled else self.p("talent", 3)

    def ult_ready(self) -> bool:
        if self.rippled and self.demiurge() is None:
            return False
        return self.recollection >= self._ult_cost() - 1e-9

    def pay_ult_cost(self) -> None:
        self.recollection = max(0.0, self.recollection - self._ult_cost())

    # --------------------------------------------------------------- Future
    def _grant_future(self) -> None:
        for c in self.battle.team:
            if c is not self.char:
                self.future.add(c.uid)
                for s in c.summons:
                    if s.is_memosprite:
                        self.future.add(s.uid)

    def _a2(self, ev: E.Ev) -> None:
        u = ev.unit
        if isinstance(u, Summon) and u.is_memosprite and u.owner is not self.char and u.side == Side.ALLY:
            self.future.add(u.uid)  # A2: a teammate's memosprite gains "Future" when summoned

    def _turn_end(self, ev: E.Ev) -> None:
        ent = ev.entity
        if ent is self.char:
            self._grant_future()  # "after Cyrene takes action"
            return
        if ent.uid not in self.future:
            return
        memo = isinstance(ent, Summon) and ent.is_memosprite
        if not (isinstance(ent, Character) or memo):
            return
        if not (memo and self.trace(1)):  # A2: "Future" held by memosprites is not consumed
            self.future.discard(ent.uid)
        self.gain_recollection(self.p("talent", 0), source=ent)

    # ----------------------------------------------------------------- Zone
    def zone_active(self) -> bool:
        return self.zone is not None and not self.zone.removed

    def _deploy_zone(self, permanent: bool) -> None:
        if self.zone is not None and not self.zone.removed:
            if permanent:
                self.zone.duration = None
                return
            if self.zone.duration is None:
                return
        duration = None if permanent else int(self.p("skill", 1))
        self.zone = self.buff_self(Modifier(ZONE, duration=duration, tick=Tick.HOLDER_TURN_START, key=ZONE))

    def zone_ratio(self) -> float:
        ratio = self.p("skill", 0)
        if self.e(2):
            ratio += min(self.ep(2, 3), self.ep(2, 2) * len(self.ode_given))
        return ratio

    def _zone_true_dmg(self, ev: E.Ev) -> None:
        h: Hit = ev.hit
        if not self.zone_active() or h.damage <= 0 or DmgTag.TRUE in h.tags:
            return
        if h.credited.side != Side.ALLY:
            return
        self.battle.true_damage(h, self.zone_ratio(), h.target, h.credited, "Cyrene Zone (True DMG)")

    # -------------------------------------------------------------- policy
    def take_turn(self) -> None:
        target = self.pick_target()
        if target is None:
            return
        policy = self.opts.get("rotation", "auto")
        expiring = not self.zone_active() or (self.zone is not None and (self.zone.duration or 99) <= 1)
        if self.rippled or policy == "basic" or not self.can_skill():
            self.basic(target)
        elif policy == "skill" or expiring:
            self.skill(target)
        else:
            self.basic(target)

    # ------------------------------------------------------------- actions
    def basic(self, target: Enemy | None) -> None:
        assert target is not None
        if not self.rippled:
            self.gain_recollection(self.p("basic", 1))
            with self.action(ActionKind.BASIC, "basic", target) as act:
                act.hit(target, self.p("basic", 0), stat="hp", toughness=self.toughness("basic"), splits="data")
            return
        rec = self.sk(ENHANCED_BASIC)
        lv = self._lv(ENHANCED_BASIC)
        t = rec["toughness"]
        self.gain_recollection(lv[1])
        with self.action(ActionKind.BASIC, rec, target) as act:
            act.hit(target, lv[2], stat="hp", toughness=float(t[0]))
            act.aoe(lv[0], stat="hp", toughness=float(t[1]), main_target=target)

    def skill(self, target: Enemy | None) -> None:
        with self.action(ActionKind.SKILL, "skill", None):
            self.gain_recollection(self.p("skill", 2))
            self._deploy_zone(permanent=False)

    def ult(self, target: Enemy | None) -> None:
        if self.rippled:
            with self.action(ActionKind.ULT, self.sk(REUNION), None):
                self._add_story()
            self._demiurge_act(False)  # "Enables Demiurge to immediately gain 1 extra turn"
            return
        with self.action(ActionKind.ULT, "ult", None):
            self.rippled = True
            self._summon_demiurge()
            for c in self.teammates():  # "activates all teammates' Ultimate"
                fill = getattr(c.kit, "fill_special_resource", None)
                if callable(fill):
                    fill()
                if c.max_energy > 0 and c.energy < c.max_energy:
                    self.battle.gain_energy(c, c.max_energy - c.energy, fixed=True)
            self.buff_self(hidden("Ripples of Past Reverie", {S.CRIT_RATE: self.p("ult", 2)}))
            self._deploy_zone(permanent=True)
            self._add_story()  # "when Demiurge is summoned"
            self._add_story()  # "after Cyrene uses Ultimate"
        # approximation: Demiurge's extra turn resolves right after the Ultimate, before other Ultimates (the game
        # holds Phainon's automatic Ultimate until the Ode is cast, _M_Cyrene_00_Phainon_ForbidAutoUltraBefore...)
        self._demiurge_act(False)
        if self.e(6):
            for u in self._allies_on_bar():
                self.battle.advance(u, self.ep(6, 0))

    def _allies_on_bar(self) -> list[Entity]:
        out: list[Entity] = list(self.allies())
        out += [u for u in self.battle.units if u.alive and u.is_memosprite and u.on_timeline]
        return out

    # ------------------------------------------------------------- Demiurge
    def _summon_demiurge(self) -> Summon:
        demi = self.demiurge()
        if demi is not None:
            return demi
        demi = self.summon_memosprite("Demiurge", on_turn=lambda unit, battle: None)
        demi.on_timeline = False  # "SPD remains at 0 ... will not appear on the Action Order"
        demi.targetable = False  # "considered as Out-of-Bounds"
        hp = self._lv(WAITING)[0]
        self.buff_self(hidden("Waiting, In Every Past", {}, dyn=self._waiting_hp, dyn_keys={S.HP_PCT}))
        self.battle.apply(hidden("Waiting, In Every Past", {S.HP_PCT: hp}), demi, self.char)
        demi.hp = demi.max_hp
        return demi

    def _waiting_hp(self, mod: Modifier, key: str, ent: Entity) -> float:
        return self._lv(WAITING)[0] if self.demiurge() is not None else 0.0

    def _add_story(self) -> None:
        if self.demiurge() is None:
            return
        self.story += STORY_GAIN
        if self.story >= int(self._lv(EGO)[1]):
            self.story = 0
            self._demiurge_extra_turn(force_minuet=True)

    def _demiurge_extra_turn(self, force_minuet: bool = False) -> None:
        demi = self.demiurge()
        if demi is None:
            return
        self.battle.queue_action(lambda: self._demiurge_act(force_minuet), demi, "Demiurge extra turn", 0)

    def _demiurge_act(self, force_minuet: bool) -> None:
        demi = self.demiurge()
        if demi is None:
            return
        ally = None if force_minuet else self._ode_target()
        if ally is not None:
            self.ode(demi, ally)
        elif self.enemies():
            self.minuet(demi)

    def _ode_candidates(self) -> list[Character]:
        names = self.opts.get("ode_targets")
        out: list[Character] = []
        if names:
            for n in names:
                c = self.battle.character(n)
                if c is not self.char and c not in out:
                    out.append(c)
        else:
            out.append(self.main_dps())
        for c in self.battle.team:
            if c is not self.char and c not in out:
                out.append(c)
        return [c for c in out if c.alive and c is not self.char]

    def _ode_id(self, c: Character) -> str:
        return ODE_BY_CHAR.get(c.char_id, ODE_NORMAL)

    def _ode_target(self) -> Character | None:
        cands = self._ode_candidates()
        for c in cands:
            if c.uid not in self.ode_given:
                return c
        for c in cands:
            if self._ode_id(c) in REPEATABLE:
                return c
        return None

    def ode(self, demi: Summon, ally: Character) -> None:
        """Demiurge's "This Ode, to All Lives": a Chrysos Heir gets its special effect, anyone else a DMG boost."""
        rec = self.sk(ODE_NORMAL)
        with self.battle.action(demi, ActionKind.MEMOSPRITE, skill=rec, target=ally):
            if ally.char_id in CHRYSOS_HEIRS:
                hook = getattr(ally.kit, "on_cyrene_ode", None)
                if callable(hook):
                    hook(self)
                else:
                    self._builtin_ode(ally)
            else:
                lv = self._lv(ODE_NORMAL)
                self.buff(ally, Modifier("This Ode, to All Lives", stats={S.DMG_PCT: lv[1]}, duration=int(lv[2])))
            self.ode_given[ally.uid] = self.ode_given.get(ally.uid, 0) + 1
        self._after_demiurge_skill()

    def minuet(self, demi: Summon) -> None:
        rec = self.sk(MINUET)
        lv = self._lv(MINUET)
        t = rec["toughness"]
        target = self.pick_target()
        with self.battle.action(demi, ActionKind.MEMOSPRITE, skill=rec, target=target) as act:
            act.aoe(lv[0], stat="hp", toughness=float(t[1]), main_target=target)
            bounces = len(self.contributors)
            if bounces > 0:  # "Ode to Ego"
                self.ego_triggers += 1
                ego = self._lv(EGO)
                mult = ego[0] + (self.ep(4, 0) * self.e4_stacks if self.e(4) else 0.0)
                if self.e(1):
                    bounces += int(self.ep(1, 1))
                    self.gain_recollection(self.ep(1, 0))
                act.bounce(None, bounces, mult, stat="hp", toughness=float(t[0]))
                if self.e(6) and self.ego_triggers >= 2:
                    for u in self._allies_on_bar():
                        self.battle.advance(u, self.ep(6, 2))
        if self.e(4):
            self.e4_stacks = min(int(self.ep(4, 1)), self.e4_stacks + 1)
        self._after_demiurge_skill()

    def _after_demiurge_skill(self) -> None:
        for c in self.teammates():
            hook = getattr(c.kit, "on_demiurge_skill", None)
            if callable(hook):
                hook(self)

    # --------------------------------------------- Odes for kits without hooks
    def _builtin_ode(self, ally: Character) -> None:
        sid = self._ode_id(ally)
        p = self.ode_params(sid)
        if sid == GENESIS:
            self._ode_genesis(ally, p)
        elif sid == ROMANCE:
            self._ode_romance(ally, p)
        elif sid == PASSAGE:
            self.buff(ally, hidden("Ode to Passage", {S.DEF_IGNORE: p[1]}, key="Ode to Passage"))
        elif sid == STRIFE:
            self._ode_strife(ally, p)
        elif sid == REASON:
            self._ode_reason(ally, p)
        elif sid == TRICKERY:
            self._ode_trickery(ally, p)
        elif sid == SKY:
            self.battle.gain_energy(ally, p[1])
        # LIFE_DEATH (Castorice) and hooks-only Odes: not modelled without the target kit's hook

    def _ode_genesis(self, ally: Character, p: list[float]) -> None:
        if ally.uid in self.genesis:
            return

        def dyn(mod: Modifier, key: str, ent: Entity) -> float:
            demi = self.demiurge()
            if demi is None:
                return 0.0
            return p[0] * demi.max_hp if key == S.ATK_FLAT else p[1] * demi.stat(S.CRIT_RATE)

        self.genesis.add(ally.uid)
        self.buff(ally, hidden("Ode to Genesis", {}, dyn=dyn, dyn_keys={S.ATK_FLAT, S.CRIT_RATE}))

    def _genesis_minuet(self, ev: E.Ev) -> None:
        act = ev.action
        if act.kind != ActionKind.BASIC or act.actor.uid not in self.genesis or act.skill is None:
            return
        if str(act.skill.get("id", "")).endswith("08"):  # the Trailblazer's Enhanced Basic ATK
            self._demiurge_extra_turn(force_minuet=True)

    def _ode_romance(self, ally: Character, p: list[float]) -> None:
        kit: Any = ally.kit
        if hasattr(kit, "gm_stacks") and callable(getattr(kit, "max_stacks", None)):
            kit.gm_stacks = kit.max_stacks()  # Garmentmaker's SPD Boost stacks to the upper limit
        mod = self.buff(ally, hidden("Ode to Romance", {S.DMG_PCT: p[1], S.DEF_IGNORE: p[2]}, key="Ode to Romance"))
        mod.data["romance"] = True

        def after_attack(ev: E.Ev) -> None:
            if mod.data.get("romance") and ev.attack.owner is ally:
                mod.data["romance"] = False  # consume "Romance"
                self.battle.gain_energy(ally, p[0])

        def gm_left(ev: E.Ev) -> None:
            if ev.owner is ally and getattr(ev.unit, "is_memosprite", False):
                self.battle.remove_modifier(mod)  # "until Aglaea exits the Supreme Stance state"

        self.battle.events.on(E.ATTACK_END, after_attack, owner=mod)
        self.battle.events.on(E.UNIT_REMOVED, gm_left, owner=mod)

    def _ode_strife(self, ally: Character, p: list[float]) -> None:
        kit: Any = ally.kit
        if getattr(kit, "vendetta", None) is not None and callable(getattr(kit, "godslayer", None)):

            def free_godslayer() -> None:
                cost = kit.godslayer_cost() if callable(getattr(kit, "godslayer_cost", None)) else 0.0
                before = kit.charge
                kit.charge = before + cost  # "without consuming Charge"
                cd = self.buff(ally, hidden("Ode to Strife", {S.CRIT_DMG: p[0]}))
                try:
                    kit.godslayer()
                finally:
                    self.battle.remove_modifier(cd)
                    kit.charge = before

            self.battle.queue_action(free_godslayer, ally, "Ode to Strife", 0)
        else:
            self.battle.advance(ally, p[1])

    def _ode_reason(self, ally: Character, p: list[float]) -> None:
        self.battle.gain_sp(int(p[3]), self.char)
        self.battle.advance(ally, 1.0)  # "enables Anaxa to take action immediately"
        armed = {"on": True}

        def knowledge(ev: E.Ev) -> None:
            act = ev.action
            if not armed["on"] or act.actor is not ally or act.kind not in (ActionKind.BASIC, ActionKind.SKILL):
                return
            armed["on"] = False
            self.battle.apply(
                Modifier(
                    "True Knowledge",
                    stats={S.ATK_PCT: p[2], f"{S.DMG_PCT}:{DmgTag.SKILL}": p[1]},
                    duration=1,
                    tick=Tick.SOURCE_TURN_START,
                    scope=lambda e: e.side == Side.ALLY and getattr(e, "path", None) == Path.ERUDITION,
                    key="True Knowledge",
                ),
                ally,
                ally,
            )

        self.on(E.ACTION_END, knowledge)

    def _ode_trickery(self, ally: Character, p: list[float]) -> None:
        self.buff(ally, hidden("Ode to Trickery", {S.DMG_PCT: p[0]}, key="Ode to Trickery"))

        def def_down(mod: Modifier, key: str, ent: Entity) -> float:
            return p[1] if ent.has_mod("Patron") else p[2]

        self.battle.apply(
            hidden(
                "Ode to Trickery (DEF)",
                {},
                dyn=def_down,
                dyn_keys={S.DEF_REDUCTION},
                scope=self.enemy_scope,
                key="Ode to Trickery (DEF)",
            ),
            ally,
            self.char,
        )
