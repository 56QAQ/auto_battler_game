"""Battle engine: timeline, turn structure, actions, hits, toughness and break.

Turn structure (one entity's turn)::

    gauge reset to 10000
    [enemy] DoTs trigger -> broken Toughness recovers
    TURN_START event -> modifiers ticking at turn start count down
    ult window (allies may cast Ultimates)
    action (unless a crowd-control effect skips it)
    TURN_END event -> modifiers ticking at turn end count down
    insert queue: Ultimates (policy), follow-ups, extra turns ...

Anything whose exact in-game order is uncertain is a switch in
:class:`BattleConfig` so it can be calibrated against the real game.
"""

from __future__ import annotations

import copy
import itertools
import math
import random
from collections.abc import Callable, Iterable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from . import events as E
from . import formulas as F
from . import stats as S
from .data import get_data
from .entities import Character, Enemy, Entity, Summon
from .enums import ActionKind, DmgTag, Element, Side
from .modifiers import DotModifier, Modifier, ModKind, Stacking, Tick

if TYPE_CHECKING:
    from .report import Report

Mult = float | dict[str, float]
CC_TYPES = frozenset({"freeze", "entanglement", "imprisonment", "cc"})


@dataclass
class BattleConfig:
    crit_mode: str = "expected"  # "expected" (average) or "random"
    seed: int = 0
    first_cycle_av: float = 150.0
    cycle_av: float = 100.0
    max_av: float | None = None
    start_energy: float = 0.5  # fraction of max energy at battle start (MoC-style)
    start_sp: int = 3
    max_sp: int = 5
    # an effect applied during the ticking entity's own turn skips that turn's end tick
    skip_tick_if_applied_in_own_turn: bool = True
    # at an enemy's turn start: DoTs trigger before its broken Toughness recovers
    dot_before_recovery: bool = True
    allies_immortal: bool = True
    enemy_hit_energy: float = 10.0  # energy a character gains when hit (single target)
    kill_energy: float = 10.0
    ult_energy_refund: bool = True  # gain the Ultimate's own SPBase (usually 5) after casting
    techniques: bool = False
    max_turns: int = 10000


@dataclass
class Hit:
    attacker: Entity
    target: Enemy
    element: Element
    tags: frozenset[str]
    mult: dict[str, float]
    flat: float = 0.0
    toughness: float = 0.0
    label: str = ""
    owner: Entity | None = None
    can_crit: bool = True
    ignore_weakness: bool = False
    extra: dict[str, float] = field(default_factory=dict)
    action: Action | None = None
    primary: bool = True
    ratio: float = 1.0  # split ratio (already applied to mult/toughness)
    crit_override: tuple[float, float] | None = None  # fixed (CRIT Rate, CRIT DMG) for this hit
    # --- results ---
    base: float = 0.0
    damage: float = 0.0
    parts: F.DamageParts | None = None
    crit: bool | None = None
    was_broken: bool = False
    toughness_potential: float = 0.0
    toughness_reduced: float = 0.0
    broke: bool = False

    @property
    def quals(self) -> tuple[str, ...]:
        return (self.element.value, *self.tags)

    def add(self, key: str, value: float) -> None:
        """Add a hit-local stat contribution (use from BEFORE_HIT listeners)."""
        self.extra[key] = self.extra.get(key, 0.0) + value

    @property
    def credited(self) -> Entity:
        return self.owner or self.attacker


@dataclass
class DamageRecord:
    time: float
    cycle: int
    owner: str
    attacker: str
    label: str
    tags: frozenset[str]
    element: Element
    target: str
    amount: float
    overkill: float = 0.0
    wave: int = 0


class Action:
    """One action (Basic ATK, Skill, Ultimate, follow-up, enemy attack ...)."""

    def __init__(
        self,
        battle: Battle,
        actor: Entity,
        kind: ActionKind,
        *,
        tags: Iterable[str] = (),
        skill: dict[str, Any] | None = None,
        target: Entity | None = None,
        label: str = "",
        energy: float | None = None,
        sp: int | None = None,
        owner: Entity | None = None,
    ) -> None:
        self.battle = battle
        self.actor = actor
        self.owner = owner or (actor.owner if isinstance(actor, Summon) else actor)
        self.kind = kind
        self.tags = frozenset(tags) or _default_tags(kind)
        self.skill = skill
        self.target = target
        self.label = label or (skill["name"] if skill else kind.value)
        # energy gained at the end of the action (None: use skill data)
        self.energy = energy if energy is not None else float(_scalar(skill.get("energy", 0))) if skill else 0.0
        if sp is not None:
            self.sp = sp
        elif skill is not None:
            need = _scalar(skill.get("sp_need", -1))
            add = _scalar(skill.get("sp_add", 0))
            self.sp = int(add) - (int(need) if need and need > 0 else 0)
        else:
            self.sp = 0
        self.hits: list[Hit] = []
        self.attacked: list[Enemy] = []
        self.attack_started = False
        self.data: dict[str, Any] = {}

    @property
    def is_attack(self) -> bool:
        return self.attack_started

    # ------------------------------------------------------------ hit helpers
    def hit(
        self,
        target: Enemy,
        mult: Mult,
        *,
        stat: str = "atk",
        toughness: float = 0.0,
        splits: list[float] | None = None,
        element: Element | None = None,
        tags: Iterable[str] | None = None,
        label: str | None = None,
        flat: float = 0.0,
        can_crit: bool = True,
        ignore_weakness: bool = False,
        extra: dict[str, float] | None = None,
        primary: bool = True,
    ) -> list[Hit]:
        """Deal DMG to one target, optionally split into several hits (ratios sum to 1)."""
        out = []
        for r in splits or [1.0]:
            out.append(
                self.battle.do_hit(
                    self._make(
                        target,
                        mult,
                        stat,
                        toughness,
                        r,
                        element,
                        tags,
                        label,
                        flat,
                        can_crit,
                        ignore_weakness,
                        extra,
                        primary,
                    )
                )
            )
        return out

    def blast(
        self,
        target: Enemy,
        main: Mult,
        adj: Mult,
        *,
        stat: str = "atk",
        toughness: tuple[float, float] = (0.0, 0.0),
        splits: list[float] | None = None,
        **kw: Any,
    ) -> list[Hit]:
        out = []
        adjs = self.battle.adjacent(target)
        for r in splits or [1.0]:
            for t, m, tg, prim in [(target, main, toughness[0], True)] + [(a, adj, toughness[1], False) for a in adjs]:
                out.append(self.battle.do_hit(self._make(t, m, stat, tg, r, primary=prim, **kw)))
        return out

    def aoe(
        self,
        mult: Mult,
        *,
        stat: str = "atk",
        toughness: float = 0.0,
        splits: list[float] | None = None,
        main_target: Enemy | None = None,
        **kw: Any,
    ) -> list[Hit]:
        out = []
        for r in splits or [1.0]:
            for t in self.battle.alive_enemies():
                prim = main_target is None or t is main_target
                out.append(self.battle.do_hit(self._make(t, mult, stat, toughness, r, primary=prim, **kw)))
        return out

    def bounce(
        self,
        first: Enemy | None,
        count: int,
        mult: Mult,
        *,
        stat: str = "atk",
        toughness: float = 0.0,
        **kw: Any,
    ) -> list[Hit]:
        """``count`` bounces: the first on ``first`` (if given), the rest on random enemies."""
        out = []
        for i in range(count):
            enemies = [e for e in self.battle.alive_enemies() if e.hp > 0] or self.battle.alive_enemies()
            if not enemies:
                break
            t = first if (i == 0 and first is not None and first.alive) else self.battle.rng.choice(enemies)
            out.append(self.battle.do_hit(self._make(t, mult, stat, toughness, 1.0, primary=i == 0, **kw)))
        return out

    def _make(
        self,
        target: Enemy,
        mult: Mult,
        stat: str,
        toughness: float,
        ratio: float,
        element: Element | None = None,
        tags: Iterable[str] | None = None,
        label: str | None = None,
        flat: float = 0.0,
        can_crit: bool = True,
        ignore_weakness: bool = False,
        extra: dict[str, float] | None = None,
        primary: bool = True,
    ) -> Hit:
        m = {stat: mult} if isinstance(mult, (int, float)) else dict(mult)
        m = {k: v * ratio for k, v in m.items()}
        el = element or getattr(self.actor, "element", None) or Element.PHYSICAL
        return Hit(
            attacker=self.actor,
            target=target,
            element=el,
            tags=frozenset(tags) if tags is not None else self.tags,
            mult=m,
            flat=flat * ratio,
            toughness=toughness * ratio,
            label=label or self.label,
            owner=self.owner,
            can_crit=can_crit,
            ignore_weakness=ignore_weakness,
            extra=dict(extra or {}),
            action=self,
            primary=primary,
            ratio=ratio,
        )


def _scalar(x: Any) -> Any:
    return x[0] if isinstance(x, list) else x


def _default_tags(kind: ActionKind) -> frozenset[str]:
    return {
        ActionKind.BASIC: frozenset({DmgTag.BASIC}),
        ActionKind.SKILL: frozenset({DmgTag.SKILL}),
        ActionKind.ULT: frozenset({DmgTag.ULT}),
        ActionKind.FUA: frozenset({DmgTag.FUA}),
        ActionKind.MEMOSPRITE: frozenset({DmgTag.MEMOSPRITE}),
        ActionKind.ELATION: frozenset({DmgTag.ELATION}),
        ActionKind.ENEMY: frozenset({DmgTag.ENEMY}),
    }.get(kind, frozenset())


@dataclass
class InfiniteWave:
    """Pure Fiction style wave: ``on_field`` enemies at a time, replaced from ``pool`` as they die,
    until ``max_count`` enemies have been spawned (and killed)."""

    pool: list[Enemy]
    max_count: int
    on_field: int = 5
    spawned: int = 0
    killed: int = 0


@dataclass(order=True)
class _Queued:
    priority: int
    seq: int
    fn: Callable[[], None] = field(compare=False)
    owner: Entity | None = field(compare=False, default=None)
    label: str = field(compare=False, default="")
    needs_enemies: bool = field(compare=False, default=True)


class Battle:
    def __init__(
        self,
        team: list[Character],
        waves: list[list[Enemy] | InfiniteWave],
        config: BattleConfig | None = None,
    ) -> None:
        self.cfg = config or BattleConfig()
        self.data = get_data()
        self.rng = random.Random(self.cfg.seed)
        self.events = E.EventBus()
        self.team = list(team)
        for i, c in enumerate(self.team):
            c.slot = i
            c.battle = self
        self.waves = waves
        self.wave_index = -1
        self.enemies: list[Enemy] = []
        self.units: list[Summon] = []  # summons, memosprites, countdowns
        self.fields: list[Modifier] = []  # modifiers with a scope (team-wide auras, zones)
        self.time = 0.0
        self.sp = self.cfg.start_sp
        self.max_sp = self.cfg.max_sp
        self.current_turn: Entity | None = None
        self.current_action: Action | None = None
        self.queue: list[_Queued] = []
        self._qseq = itertools.count()
        self._tie = itertools.count()
        self._tiebreak: dict[int, int] = {}
        self.records: list[DamageRecord] = []
        self.log_lines: list[str] = []
        self.finished = False
        self.turns = 0
        self.turn_counts: dict[str, int] = {}
        self.cleared_at: float | None = None
        self.kills = 0
        self.infinite: InfiniteWave | None = None
        self.verbose = False
        from .elation import ElationSystem

        self.elation = ElationSystem(self)

    # =================================================================== setup
    def log(self, msg: str) -> None:
        line = f"[{self.time:8.2f}] {msg}"
        self.log_lines.append(line)
        if self.verbose:
            print(line)

    @property
    def cycle(self) -> int:
        return F.cycle_index(self.time, self.cfg.first_cycle_av, self.cfg.cycle_av)

    def cycle_end_av(self, cycles: int) -> float:
        return self.cfg.first_cycle_av + self.cfg.cycle_av * (cycles - 1)

    def start(self) -> None:
        from .build import attach

        for c in self.team:
            c.hp = c.max_hp
            c.energy = c.max_energy * self.cfg.start_energy
            c.gauge = F.AV_BASE
            if c.kit is not None:
                c.kit.setup()
            attach(c)
        self._next_wave()
        self.events.emit(E.BATTLE_START)
        for c in self.team:
            if c.kit is not None:
                c.kit.on_battle_start()
                if self.cfg.techniques:
                    c.kit.technique()
        self.process_queue()

    # ================================================================ timeline
    def timeline(self) -> list[Entity]:
        ents: list[Entity] = [c for c in self.team if c.alive]
        ents += [u for u in self.units if u.alive and u.on_timeline]
        ents += [e for e in self.enemies if e.alive]
        return ents

    def _order_key(self, e: Entity) -> tuple[float, int, int, int]:
        side = 0 if e.side == Side.ALLY else 1
        return (round(e.av, 9), self._tiebreak.get(e.uid, 1 << 30), side, e.slot)

    def next_actor(self) -> Entity | None:
        ents = self.timeline()
        return min(ents, key=self._order_key) if ents else None

    def _advance_time(self, dt: float) -> None:
        if dt <= 0:
            return
        for e in self.timeline():
            e.gauge = max(0.0, e.gauge - e.spd * dt)
        self.time += dt

    def advance(self, entity: Entity, pct: float) -> None:
        """Action Advance by ``pct`` (0.25 = 25%). Negative values delay."""
        if pct >= 0:
            entity.gauge = max(0.0, entity.gauge - pct * F.AV_BASE)
            if entity.gauge <= 0:
                self._tiebreak[entity.uid] = next(self._tie)
        else:
            self.delay(entity, -pct)

    def delay(self, entity: Entity, pct: float) -> None:
        entity.gauge += pct * F.AV_BASE
        self._tiebreak.pop(entity.uid, None)

    def set_av(self, entity: Entity, av: float) -> None:
        entity.gauge = max(0.0, av * entity.spd)

    # ==================================================================== run
    def run(self, max_av: float | None = None, max_cycles: int | None = None) -> Report:
        from .report import Report

        limit = max_av if max_av is not None else self.cfg.max_av
        if max_cycles is not None:
            limit = self.cycle_end_av(max_cycles) if limit is None else min(limit, self.cycle_end_av(max_cycles))
        if self.wave_index < 0:
            self.start()
        while not self.finished and self.turns < self.cfg.max_turns:
            actor = self.next_actor()
            if actor is None:
                break
            dt = actor.av
            if limit is not None and self.time + dt > limit + 1e-9:
                self._advance_time(limit - self.time)
                break
            self._advance_time(dt)
            self.ult_window()
            if self.finished:
                break
            actor = self.next_actor()  # an ult may have changed the order
            if actor is None or actor.av > 1e-9:
                continue
            pre = self.events.emit(E.PRE_TURN, entity=actor, cancel=False)
            if pre.data["cancel"]:
                if actor.gauge <= 0:  # a cancelled turn must push the actor back somewhere
                    actor.gauge = F.AV_BASE
                self.process_queue()
                continue
            self.take_turn(actor)
            self.process_queue()
        return Report(self)

    def take_turn(self, actor: Entity, extra_turn: bool = False) -> None:
        self.turns += 1
        self.turn_counts[actor.name] = self.turn_counts.get(actor.name, 0) + 1
        if not extra_turn:
            actor.gauge = F.AV_BASE
            self._tiebreak.pop(actor.uid, None)
        prev = self.current_turn
        self.current_turn = actor
        self.log(f"-- turn: {actor.name}{' (extra)' if extra_turn else ''}")
        skip = any(m.skip_turn for m in actor.modifiers if not m.removed)
        if isinstance(actor, Enemy):
            self._enemy_turn_start(actor)
        self.events.emit(E.TURN_START, entity=actor, extra=extra_turn)
        self._tick(actor, at_start=True)
        if actor.alive and not self.finished:
            if isinstance(actor, Character):
                self.ult_window()
            if not skip and actor.alive and not self.finished:
                actor.take_turn(self)
        self.events.emit(E.TURN_END, entity=actor, extra=extra_turn)
        self._tick(actor, at_start=False)
        self.current_turn = prev
        self._reap()

    def _enemy_turn_start(self, e: Enemy) -> None:
        def dots() -> None:
            for m in [m for m in e.modifiers if isinstance(m, DotModifier) and not m.removed]:
                if e.alive and not m.removed:
                    d = m.trigger(self, turn_start=True)
                    self.events.emit(E.DOT_TRIGGERED, mod=m, target=e, damage=d, turn_start=True, action=None)
            self._reap()

        if self.cfg.dot_before_recovery:
            dots()
        if e.broken and e.alive:
            ev = self.events.emit(E.BEFORE_RECOVER, enemy=e, cancel=False)
            if not ev.data["cancel"]:
                e.broken = False
                e.toughness = e.max_toughness
                self.log(f"{e.name} recovers Toughness")
                self.events.emit(E.RECOVERED, enemy=e)
        if not self.cfg.dot_before_recovery:
            dots()

    def _tick(self, entity: Entity, at_start: bool) -> None:
        for holder in self._all_entities():
            for m in list(holder.modifiers):
                if m.removed or m.tick == Tick.NONE or m.tick.at_start != at_start:
                    continue
                who = m.source if m.tick.by_source else m.holder
                if who is entity:
                    m.tick_down(self)

    def _all_entities(self) -> list[Entity]:
        return [*self.team, *self.units, *self.enemies]

    # ============================================================ insert queue
    def queue_action(
        self,
        fn: Callable[[], None],
        owner: Entity | None = None,
        label: str = "",
        priority: int = 10,
        needs_enemies: bool = True,
    ) -> None:
        """Queue an inserted action (follow-up, counter, extra turn ...) to run after the current one."""
        self.queue.append(_Queued(priority, next(self._qseq), fn, owner, label, needs_enemies))
        self.queue.sort()

    def queue_extra_turn(self, entity: Entity) -> None:
        self.queue_action(lambda: self.take_turn(entity, extra_turn=True), entity, "extra turn", priority=20)

    def process_queue(self) -> None:
        guard = 0
        while not self.finished and guard < 1000:
            guard += 1
            self.ult_window()
            self._check_wave()
            if self.finished or not self.queue:
                break
            item = self.queue.pop(0)
            if item.owner is not None and not item.owner.alive:
                continue
            if item.needs_enemies and not self.alive_enemies():
                continue
            item.fn()
            self._reap()

    def ult_window(self) -> None:
        """Let every ally whose policy wants to cast its Ultimate do so now."""
        for _ in range(20):
            casted = False
            for c in self.team:
                if self.finished or not self.alive_enemies():
                    return
                if c.alive and c.kit is not None and c.kit.ult_ready() and c.kit.want_ult():
                    c.kit.use_ult()
                    self._reap()
                    casted = True
            if not casted:
                return

    # =============================================================== actions
    @contextmanager
    def action(
        self,
        actor: Entity,
        kind: ActionKind,
        *,
        skill: dict[str, Any] | None = None,
        target: Entity | None = None,
        tags: Iterable[str] = (),
        label: str = "",
        energy: float | None = None,
        sp: int | None = None,
    ) -> Iterator[Action]:
        act = Action(self, actor, kind, skill=skill, target=target, tags=tags, label=label, energy=energy, sp=sp)
        prev = self.current_action
        self.current_action = act
        self.log(f"{actor.name}: {kind.value} {act.label}" + (f" -> {target.name}" if target else ""))
        if act.sp < 0:
            self.use_sp(-act.sp, actor)
        elif act.sp > 0:
            self.gain_sp(act.sp, actor)
        self.events.emit(E.ACTION_START, action=act)
        try:
            yield act
        finally:
            if act.attack_started:
                self.events.emit(E.ATTACK_END, attack=act, action=act)
            if isinstance(act.owner, Character) and act.energy:
                self.gain_energy(act.owner, act.energy)
            self.events.emit(E.ACTION_END, action=act)
            self.current_action = prev
            self._reap()

    # ========================================================= damage & hits
    def do_hit(self, hit: Hit) -> Hit:
        t = hit.target
        act = hit.action
        if act is not None:
            if not act.attack_started:
                act.attack_started = True
                self.events.emit(E.ATTACK_START, attack=act, action=act)
            act.hits.append(hit)
            if t not in act.attacked:
                act.attacked.append(t)
        hit.was_broken = t.broken
        self.events.emit(E.BEFORE_HIT, hit=hit)
        a = hit.attacker
        hit.base = sum(ratio * a.scaling(attr, hit.extra) for attr, ratio in hit.mult.items()) + hit.flat
        hit.parts = self.compute(hit)
        hit.damage = hit.parts.total
        self.deal(t, hit.damage, hit.credited, a, hit.label, hit.tags, hit.element)
        self._toughness(hit)
        self.events.emit(E.AFTER_HIT, hit=hit)
        return hit

    def compute(self, hit: Hit) -> F.DamageParts:
        a, t, q, ex = hit.attacker, hit.target, hit.quals, hit.extra
        crit = 1.0
        if hit.can_crit:
            if hit.crit_override is not None:
                cr, cd = hit.crit_override
                cd += ex.get(S.CRIT_DMG, 0.0)
            else:
                cr = a.stat_q(S.CRIT_RATE, q, ex)
                cd = a.stat_q(S.CRIT_DMG, q, ex)
            if self.cfg.crit_mode == "random":
                hit.crit = self.rng.random() < cr
                crit = 1.0 + cd if hit.crit else 1.0
            else:
                crit = F.crit_multiplier_expected(cr, cd)
        return self._parts(a, t, hit.element, q, ex, base=hit.base, boost=1.0 + a.stat_q(S.DMG_PCT, q, ex), crit=crit)

    def _parts(
        self,
        a: Entity,
        t: Entity,
        element: Element,
        q: tuple[str, ...],
        ex: dict[str, float],
        *,
        base: float,
        boost: float,
        crit: float = 1.0,
        broken_mult: float | None = None,
        extra_mult: float = 1.0,
    ) -> F.DamageParts:
        def_mult = F.def_multiplier(
            a.level,
            t.raw(S.BASE_DEF),
            def_bonus=t.stat(S.DEF_PCT),
            def_reduction=t.stat_q(S.DEF_REDUCTION, q, ex),
            def_ignore=a.stat_q(S.DEF_IGNORE, q, ex),
            def_flat=t.stat(S.DEF_FLAT),
        )
        res = t.stat(f"{S.RES}:{element.value}", ex)
        res_mult = F.res_multiplier(res, a.stat_q(S.RES_PEN, q, ex), t.stat_q(S.RES_REDUCTION, q, ex))
        vuln = F.vuln_multiplier(t.stat_q(S.VULN, q, ex))
        mit = F.mitigation_multiplier(t.factors(S.MITIGATION, q) + ([ex[S.MITIGATION]] if S.MITIGATION in ex else []))
        if broken_mult is None:
            broken_mult = F.BROKEN_MULT
            if isinstance(t, Enemy) and not t.broken and t.max_toughness > 0:
                broken_mult = F.NOT_BROKEN_MULT
        weaken = 1.0 - min(F.WEAKEN_MAX, max(0.0, a.stat_q(S.WEAKEN, q, ex)))
        final = a.factors(S.FINAL_DMG, q) + ([ex[S.FINAL_DMG]] if S.FINAL_DMG in ex else [])
        extra_mult *= F.final_dmg_multiplier(final)
        return F.DamageParts(base, boost, def_mult, res_mult, vuln, mit, broken_mult, weaken, crit, extra_mult)

    def deal(
        self,
        target: Entity,
        amount: float,
        credited: Entity,
        attacker: Entity,
        label: str,
        tags: frozenset[str],
        element: Element,
    ) -> DamageRecord:
        before = target.hp
        target.hp -= amount
        target.last_hit_by = credited
        overkill = max(0.0, amount - max(0.0, before))
        rec = DamageRecord(
            self.time,
            self.cycle,
            credited.name,
            attacker.name,
            label,
            tags,
            element,
            target.name,
            amount,
            overkill,
            self.wave_index,
        )
        if target.side == Side.ENEMY:
            self.records.append(rec)
            self.events.emit(E.DAMAGE_DEALT, record=rec, target=target, attacker=attacker, credited=credited)
        return rec

    # ------------------------------------------------------ toughness & break
    def _toughness(self, hit: Hit) -> None:
        t = hit.target
        if hit.toughness <= 0 or t.max_toughness <= 0:
            return
        if not (t.is_weak_to(hit.element) or hit.ignore_weakness):
            return
        a = hit.attacker
        pot = hit.toughness * (1.0 + a.stat_q(S.BREAK_EFF, hit.quals, hit.extra))
        hit.toughness_potential = pot
        if t.broken or t.toughness <= 0:
            return
        red = min(pot, t.toughness)
        t.toughness -= pot
        hit.toughness_reduced = red
        if t.toughness <= 1e-9:
            t.toughness = 0.0
            hit.broke = True
            self.weakness_break(t, a, hit.element, hit)

    def reduce_toughness(self, target: Enemy, attacker: Entity, amount: float, element: Element) -> None:
        """Direct Toughness reduction outside a hit (e.g. effects "reduce Toughness by X")."""
        if target.broken or target.max_toughness <= 0:
            return
        target.toughness -= amount
        if target.toughness <= 1e-9:
            target.toughness = 0.0
            self.weakness_break(target, attacker, element, None)

    def weakness_break(self, t: Enemy, attacker: Entity, element: Element, hit: Hit | None) -> None:
        from .breaks import apply_break_effect

        t.broken = True
        credited = hit.credited if hit is not None else attacker
        self.log(f"{t.name} Weakness Broken ({element.value}) by {credited.name}")
        self.break_damage(attacker, t, element, credited=credited)
        be = attacker.stat(S.BREAK_EFFECT)
        self.delay(t, F.BREAK_DELAY)
        apply_break_effect(self, attacker, t, element, be, credited)
        self.events.emit(E.BREAK, target=t, attacker=attacker, hit=hit, element=element, credited=credited)

    def break_damage(
        self,
        attacker: Entity,
        target: Enemy,
        element: Element,
        *,
        mult: float = 1.0,
        credited: Entity | None = None,
        label: str = "Break",
        tags: Iterable[str] = (DmgTag.BREAK,),
        max_toughness: float | None = None,
    ) -> float:
        """Break DMG as dealt on Weakness Break (``mult`` scales it, e.g. for "X% Break DMG" effects)."""
        lvl = self.data.break_base(attacker.level)
        mt = target.max_toughness if max_toughness is None else max_toughness
        base = F.break_base_damage(element, lvl, mt) * mult
        return self.special_damage(attacker, target, element, base, tags=tags, label=label, credited=credited)

    def super_break(
        self,
        attacker: Entity,
        target: Enemy,
        toughness_reduced: float,
        mult: float = 1.0,
        *,
        credited: Entity | None = None,
        label: str = "Super Break",
        element: Element | None = None,
    ) -> float:
        lvl = self.data.break_base(attacker.level)
        base = F.super_break_base(lvl, toughness_reduced) * mult
        el: Element = element or Element(getattr(attacker, "element", Element.PHYSICAL))
        return self.special_damage(
            attacker,
            target,
            el,
            base,
            tags=(DmgTag.BREAK, DmgTag.SUPER_BREAK),
            label=label,
            credited=credited,
            boost_key=S.SUPER_BREAK_DMG_PCT,
        )

    def detonate(self, target: Enemy, ratio: float, *, kinds: Iterable[str] = ("dot",)) -> float:
        """Make DoTs on ``target`` immediately deal ``ratio`` of their DMG (e.g. Kafka's Skill)."""
        total = 0.0
        for m in [m for m in target.modifiers if isinstance(m, DotModifier) and not m.removed]:
            if any(k in m.tags for k in kinds):
                d = m.trigger(self, ratio)
                total += d
                self.events.emit(
                    E.DOT_TRIGGERED, mod=m, target=target, damage=d, turn_start=False, action=self.current_action
                )
        return total

    @staticmethod
    def super_break_toughness(action: Action, target: Enemy) -> float:
        """Toughness this attack would have reduced on ``target`` counting only hits that landed
        while it was already Weakness Broken (the breaking hit itself does not count)."""
        return sum(h.toughness_potential for h in action.hits if h.target is target and h.was_broken)

    def true_damage(self, source: Hit | float, ratio: float, target: Enemy, credited: Entity, label: str) -> float:
        """True DMG: ``ratio`` x the final DMG of a source instance; no further multipliers."""
        base = source.damage if isinstance(source, Hit) else float(source)
        dmg = base * ratio
        attacker = source.attacker if isinstance(source, Hit) else credited
        self.deal(target, dmg, credited, attacker, label, frozenset({DmgTag.TRUE}), Element.PHYSICAL)
        return dmg

    def special_damage(
        self,
        attacker: Entity,
        target: Enemy,
        element: Element,
        base: float,
        *,
        tags: Iterable[str],
        label: str,
        credited: Entity | None = None,
        use_break_effect: bool = True,
        boost_key: str | None = None,
        broken_mult: float | None = None,
    ) -> float:
        """Break-type DMG (Break, Super Break, break DoTs): scales with Break Effect, cannot crit,
        does not benefit from DMG% boosts. BEFORE_HIT/AFTER_HIT fire with a hit whose ``action`` is
        None, so hit-local modifiers (DEF ignore, vulnerability, RES PEN ...) apply."""
        tg = frozenset(tags)
        hit = Hit(
            attacker=attacker,
            target=target,
            element=element,
            tags=tg,
            mult={},
            label=label,
            owner=credited,
            can_crit=False,
        )
        hit.was_broken = target.broken
        self.events.emit(E.BEFORE_HIT, hit=hit)
        q, ex = hit.quals, hit.extra
        boost = 1.0 + attacker.stat_q(S.BREAK_DMG_PCT, q, ex)
        if boost_key:
            boost += attacker.stat(boost_key, ex)
        be = 1.0 + attacker.stat(S.BREAK_EFFECT, ex) if use_break_effect else 1.0
        hit.base = base
        hit.parts = self._parts(attacker, target, element, q, ex, base=base * be, boost=boost, broken_mult=broken_mult)
        hit.damage = hit.parts.total
        self.deal(target, hit.damage, hit.credited, attacker, label, tg, element)
        self.events.emit(E.AFTER_HIT, hit=hit)
        return hit.damage

    def dot_damage(
        self,
        attacker: Entity,
        target: Enemy,
        element: Element,
        mult: Mult,
        *,
        stat: str = "atk",
        label: str,
        credited: Entity | None = None,
        tags: Iterable[str] = (DmgTag.DOT,),
        ratio: float = 1.0,
        extra: dict[str, float] | None = None,
    ) -> float:
        """Character DoT DMG: scales with ATK (or other stat) and DMG%, cannot crit."""
        m = {stat: mult} if isinstance(mult, (int, float)) else dict(mult)
        hit = Hit(
            attacker=attacker,
            target=target,
            element=element,
            tags=frozenset(tags),
            mult={k: v * ratio for k, v in m.items()},
            label=label,
            owner=credited,
            can_crit=False,
            extra=dict(extra or {}),
        )
        self.events.emit(E.BEFORE_HIT, hit=hit)
        hit.base = sum(r * attacker.scaling(k, hit.extra) for k, r in hit.mult.items())
        hit.parts = self.compute(hit)
        hit.damage = hit.parts.total
        self.deal(target, hit.damage, hit.credited, attacker, label, hit.tags, element)
        self.events.emit(E.AFTER_HIT, hit=hit)
        return hit.damage

    def additional_damage(
        self,
        attacker: Entity,
        target: Enemy,
        mult: Mult,
        *,
        stat: str = "atk",
        element: Element | None = None,
        label: str,
        credited: Entity | None = None,
        tags: Iterable[str] = (DmgTag.ADDITIONAL,),
        can_crit: bool = True,
        extra: dict[str, float] | None = None,
        crit_override: tuple[float, float] | None = None,
        flat: float = 0.0,
    ) -> Hit:
        """Additional DMG: a hit that does not reduce Toughness and is not an attack of its own.
        ``flat`` is added to the base DMG (for effects computed from something other than a stat)."""
        m = {stat: mult} if isinstance(mult, (int, float)) else dict(mult)
        hit = Hit(
            attacker=attacker,
            target=target,
            element=element or Element(getattr(attacker, "element", Element.PHYSICAL)),
            tags=frozenset(tags),
            mult=m,
            label=label,
            owner=credited,
            can_crit=can_crit,
            extra=dict(extra or {}),
            action=None,
            crit_override=crit_override,
            flat=flat,
        )
        hit.was_broken = target.broken
        self.events.emit(E.BEFORE_HIT, hit=hit)
        hit.base = sum(r * attacker.scaling(k, hit.extra) for k, r in hit.mult.items()) + hit.flat
        hit.parts = self.compute(hit)
        hit.damage = hit.parts.total
        self.deal(target, hit.damage, hit.credited, attacker, label, hit.tags, hit.element)
        self.events.emit(E.AFTER_HIT, hit=hit)
        return hit

    # ============================================================ modifiers
    def apply(self, mod: Modifier, target: Entity, source: Entity | None = None) -> Modifier:
        """Apply a modifier (no hit chance roll). Returns the live instance."""
        mod.holder = target
        mod.source = source if source is not None else mod.source
        mod.battle = self
        tick_ent = mod.source if mod.tick.by_source else target
        if mod.skip_first_tick is not None:
            mod.skip_next_tick = mod.skip_first_tick
        else:
            mod.skip_next_tick = (
                self.cfg.skip_tick_if_applied_in_own_turn
                and not mod.tick.at_start
                and mod.tick != Tick.NONE
                and tick_ent is not None
                and tick_ent is self.current_turn
            )
        if mod.stacking != Stacking.INDEPENDENT:
            for ex in target.modifiers:
                if not ex.removed and ex.key == mod.key:
                    ex.merge(mod)
                    ex.on_merge(self, mod)
                    self.events.emit(E.MOD_APPLIED, mod=ex, target=target, refreshed=True)
                    return ex
        target.modifiers.append(mod)
        if mod.scope is not None:
            self.fields.append(mod)
        mod.applied_at = self.time
        mod.on_apply(self)
        self.events.emit(E.MOD_APPLIED, mod=mod, target=target, refreshed=False)
        return mod

    def remove_modifier(self, mod: Modifier) -> None:
        if mod.removed or mod.holder is None:
            return
        mod.removed = True
        holder = mod.holder
        if mod in holder.modifiers:
            holder.modifiers.remove(mod)
        if mod in self.fields:
            self.fields.remove(mod)
        self.events.off_owner(mod)
        mod.on_remove(self)
        self.events.emit(E.MOD_REMOVED, mod=mod, target=holder)

    def remove_named(self, target: Entity, name: str) -> None:
        for m in target.mods(name):
            self.remove_modifier(m)

    def effect_chance(self, source: Entity, target: Entity, base: float, debuff_type: str | None = None) -> float:
        dres = target.stat(f"{S.DEBUFF_RES}:{debuff_type}") if debuff_type else 0.0
        if debuff_type in CC_TYPES:
            dres = 1.0 - (1.0 - dres) * (1.0 - target.stat(f"{S.DEBUFF_RES}:cc"))
        return F.effect_hit_chance(
            base, source.stat(S.EHR), target.stat(S.EFFECT_RES), dres, source.stat(S.EFFECT_RES_PEN)
        )

    def try_debuff(
        self,
        mod: Modifier,
        target: Entity,
        source: Entity,
        base_chance: float = 1.0,
        *,
        fixed: bool = False,
        debuff_type: str | None = None,
    ) -> Modifier | None:
        """Roll a debuff: ``fixed`` chances ignore Effect Hit Rate / Effect RES."""
        chance = base_chance if fixed else self.effect_chance(source, target, base_chance, debuff_type)
        if chance >= 1.0 or self.rng.random() < chance:
            return self.apply(mod, target, source)
        self.log(f"{mod.name} resisted by {target.name} ({chance:.0%})")
        return None

    # ================================================================ resources
    def gain_energy(self, c: Character, base: float, fixed: bool = False) -> None:
        if c.max_energy <= 0:
            return
        amount = base if fixed else base * (1.0 + c.stat(S.ERR))
        before = c.energy
        c.energy = min(c.max_energy, c.energy + amount)
        if c.energy != before:
            self.events.emit(E.ENERGY_GAINED, entity=c, amount=c.energy - before)

    def gain_sp(self, n: int, who: Entity | None = None) -> None:
        before = self.sp
        self.sp = min(self.max_sp, self.sp + n)
        overflow = max(0, before + n - self.max_sp)
        self.events.emit(E.SP_RECOVERED, amount=n, overflow=overflow, entity=who)
        if self.sp != before:
            self.events.emit(E.SP_CHANGED, delta=self.sp - before, entity=who)

    def use_sp(self, n: int, who: Entity | None = None) -> None:
        if n > self.sp:
            raise RuntimeError(f"{who} tried to use {n} SP with only {self.sp}")
        self.sp -= n
        self.events.emit(E.SP_CHANGED, delta=-n, entity=who)

    def add_shield(
        self,
        target: Entity,
        value: float,
        source: Entity,
        *,
        duration: int | None = 2,
        name: str = "Shield",
        tick: Tick = Tick.HOLDER_TURN_START,
        key: str | None = None,
    ) -> Modifier:
        """Shield absorbing enemy DMG. ``value`` is scaled by the source's Shield effect bonus (``shield%``)."""
        mod = Modifier(name, duration=duration, tick=tick, kind=ModKind.BUFF, tags={"shield"}, key=key)
        mod.data["value"] = value * (1.0 + source.stat(S.SHIELD_PCT))
        return self.apply(mod, target, source)

    def shield_value(self, target: Entity) -> float:
        return sum(m.data.get("value", 0.0) for m in target.modifiers if "shield" in m.tags and not m.removed)

    def absorb_shield(self, target: Entity, dmg: float) -> float:
        """Shields absorb DMG in parallel (each absorbs the full hit; the largest decides), as in the game."""
        shields = [m for m in target.modifiers if "shield" in m.tags and not m.removed]
        if not shields or dmg <= 0:
            return dmg
        biggest = max(m.data.get("value", 0.0) for m in shields)
        for m in shields:
            m.data["value"] = m.data.get("value", 0.0) - dmg
            if m.data["value"] <= 0:
                self.remove_modifier(m)
        return max(0.0, dmg - biggest)

    def heal(self, target: Entity, amount: float, source: Entity | None = None) -> None:
        before = target.hp
        target.hp = min(target.max_hp, target.hp + amount)
        self.events.emit(E.HEALED, entity=target, amount=amount, effective=target.hp - before, source=source)
        if target.hp != before:
            self.events.emit(E.HP_CHANGED, entity=target, delta=target.hp - before, source=source)

    def lose_hp(self, target: Entity, amount: float, source: Entity | None = None) -> float:
        """HP consumption / damage to allies. Returns HP actually lost."""
        before = target.hp
        floor = 1.0 if (target.side == Side.ALLY and self.cfg.allies_immortal) else 0.0
        target.hp = max(floor, target.hp - amount)
        lost = before - target.hp
        if lost:
            self.events.emit(E.HP_CHANGED, entity=target, delta=-lost, source=source)
        return lost

    # ================================================================ enemies
    def alive_enemies(self) -> list[Enemy]:
        return [e for e in self.enemies if e.alive]

    def adjacent(self, target: Enemy) -> list[Enemy]:
        alive = self.alive_enemies()
        if target not in alive:
            return []
        i = alive.index(target)
        return [alive[j] for j in (i - 1, i + 1) if 0 <= j < len(alive)]

    def default_target(self) -> Enemy | None:
        """Highest max-HP enemy (the boss/elite); ties -> leftmost."""
        alive = self.alive_enemies()
        if not alive:
            return None
        return max(alive, key=lambda e: (e.max_hp, -self.enemies.index(e)))

    def allies(self, include_summons: bool = False) -> list[Entity]:
        out: list[Entity] = [c for c in self.team if c.alive]
        if include_summons:
            out += [u for u in self.units if u.alive and u.targetable]
        return out

    def pick_aggro_target(self) -> Entity | None:
        cands = [c for c in self.allies(include_summons=True) if c.targetable]
        if not cands:
            return None
        weights = [max(0.0, c.stat(S.AGGRO) * (1.0 + c.stat(S.AGGRO_PCT))) for c in cands]
        if sum(weights) <= 0:
            return self.rng.choice(cands)
        return self.rng.choices(cands, weights=weights, k=1)[0]

    def enemy_basic_attack(self, e: Enemy, mult: float = 1.0, energy: float | None = None) -> None:
        """Default enemy AI: one single-target attack chosen by aggro."""
        target = self.pick_aggro_target()
        if target is None:
            return
        if energy is None:
            energy = e.hit_energy
        with self.action(e, ActionKind.ENEMY, target=target, label="Attack") as act:
            self.hit_ally(e, target, mult, energy=energy, action=act)
            self.events.emit(E.ALLY_ATTACKED, attacker=e, targets=[target], action=act)

    def hit_ally(
        self,
        e: Enemy,
        target: Entity,
        mult: float,
        *,
        energy: float | None = None,
        action: Action | None = None,
        element: Element = Element.PHYSICAL,
    ) -> float:
        dm = F.def_multiplier(e.level, target.defense)
        res = F.res_multiplier(target.stat(f"{S.RES}:{element.value}"))
        vuln = F.vuln_multiplier(target.stat(S.VULN))
        mit = F.mitigation_multiplier(target.factors(S.MITIGATION, (element.value,)))
        dmg = e.atk * mult * dm * res * vuln * mit
        dmg = self.absorb_shield(target, dmg)
        lost = self.lose_hp(target, dmg, e)
        if isinstance(target, Character):
            self.gain_energy(target, self.cfg.enemy_hit_energy if energy is None else energy)
        return lost

    # ================================================================== waves
    def _next_wave(self) -> None:
        self.wave_index += 1
        if self.wave_index >= len(self.waves):
            self.finished = True
            self.cleared_at = self.time
            self.log("all waves cleared")
            return
        wave = self.waves[self.wave_index]
        if isinstance(wave, InfiniteWave):
            self.infinite = wave
            first = [self._take_from_pool() for _ in range(min(wave.on_field, wave.max_count))]
            self.enemies = [e for e in first if e is not None]
        else:
            self.infinite = None
            self.enemies = list(wave)
        self.queue = [q for q in self.queue if not q.needs_enemies]
        for i, e in enumerate(self.enemies):
            self._spawn(e, i)
        self.log(f"=== wave {self.wave_index + 1}: {', '.join(e.name for e in self.enemies)}")
        self.events.emit(E.WAVE_START, wave=self.wave_index)

    def _take_from_pool(self) -> Enemy | None:
        inf = self.infinite
        if inf is None or inf.spawned >= inf.max_count or not inf.pool:
            return None
        template = inf.pool[inf.spawned % len(inf.pool)]
        e = copy.deepcopy(template)
        e.name = f"{template.name} #{inf.spawned + 1}"
        inf.spawned += 1
        return e

    def _spawn(self, e: Enemy, slot: int) -> None:
        e.battle = self
        e.slot = slot
        e.wave = self.wave_index
        e.alive = True
        e.hp = e.max_hp
        e.toughness = e.max_toughness
        e.gauge = F.AV_BASE * e.initial_delay
        self.events.emit(E.ENEMY_SPAWNED, enemy=e)

    def _refill(self) -> None:
        """Pure Fiction: replace defeated enemies from the wave's pool."""
        inf = self.infinite
        if inf is None:
            return
        for i, e in enumerate(list(self.enemies)):
            if not e.alive:
                new = self._take_from_pool()
                if new is None:
                    continue
                self.enemies[i] = new
                self._spawn(new, i)

    def _check_wave(self) -> None:
        if self.enemies and not self.alive_enemies() and not self.finished:
            self.events.emit(E.WAVE_END, wave=self.wave_index)
            self._next_wave()

    def _reap(self) -> None:
        """Resolve defeated enemies (deferred while an action is still in progress)."""
        if self.current_action is not None:
            return
        for e in self.enemies:
            if e.alive and e.hp <= 0:
                e.alive = False
                killer = e.last_hit_by
                self.log(f"{e.name} defeated")
                if isinstance(killer, Character):
                    self.gain_energy(killer, self.cfg.kill_energy)
                self.events.emit(E.KILL, target=e, killer=killer)  # modifiers still readable here
                for m in list(e.modifiers):
                    self.remove_modifier(m)
                self.kills += 1
                if self.infinite is not None:
                    self.infinite.killed += 1
        if self.infinite is not None:
            self._refill()

    # ================================================================== misc
    def add_unit(self, unit: Summon, av: float | None = None) -> Summon:
        unit.battle = self
        unit.slot = 100 + len(self.units)
        if av is None:
            unit.gauge = F.AV_BASE
        else:
            self.set_av(unit, av)
        unit.hp = unit.max_hp if unit.stat_mode in ("self", "sync") else 0.0
        self.units.append(unit)
        unit.owner.summons.append(unit)
        self.events.emit(E.UNIT_ADDED, unit=unit, owner=unit.owner)
        return unit

    def remove_unit(self, unit: Summon) -> None:
        unit.alive = False
        for m in list(unit.modifiers):
            self.remove_modifier(m)
        if unit in self.units:
            self.units.remove(unit)
        if unit in unit.owner.summons:
            unit.owner.summons.remove(unit)
        self.events.emit(E.UNIT_REMOVED, unit=unit, owner=unit.owner)

    def character(self, name: str) -> Character:
        for c in self.team:
            if c.name == name or c.char_id == name:
                return c
        raise KeyError(name)

    def total_damage(self) -> float:
        return math.fsum(r.amount for r in self.records)

    def with_kind(self, kind: ModKind) -> list[Modifier]:
        return [m for e in self._all_entities() for m in e.modifiers if m.kind == kind]
