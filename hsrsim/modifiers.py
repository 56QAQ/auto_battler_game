"""Status effects (buffs, debuffs, DoTs, crowd control, hidden states).

A :class:`Modifier` lives on a *holder* entity, was applied by a *source*
entity, may carry stat contributions (static or dynamic), may have a duration
that ticks down on a configurable turn boundary, and may register event
listeners that are removed automatically with it.

Duration semantics are explicit per modifier (``tick``) because the game uses
several conventions (holder turn end, caster turn start, ...). Whether an
application during the ticking entity's own turn skips the first tick is
``skip_first_tick`` (``None`` = use the battle-wide default rule).
"""

from __future__ import annotations

import itertools
from collections.abc import Callable
from enum import Enum
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .battle import Battle
    from .entities import Entity
    from .events import Callback


class Tick(str, Enum):
    HOLDER_TURN_END = "holder_turn_end"
    HOLDER_TURN_START = "holder_turn_start"
    SOURCE_TURN_END = "source_turn_end"
    SOURCE_TURN_START = "source_turn_start"
    NONE = "none"  # removed manually or never

    @property
    def at_start(self) -> bool:
        return self in (Tick.HOLDER_TURN_START, Tick.SOURCE_TURN_START)

    @property
    def by_source(self) -> bool:
        return self in (Tick.SOURCE_TURN_START, Tick.SOURCE_TURN_END)


class ModKind(str, Enum):
    BUFF = "buff"
    DEBUFF = "debuff"
    OTHER = "other"  # neither (hidden states, marks, counters)


class Stacking(str, Enum):
    REFRESH = "refresh"  # replace the existing instance (new values, new duration)
    STACK = "stack"  # add stacks up to max_stacks, refresh duration
    INDEPENDENT = "independent"  # always a new instance


# dyn(mod, key, entity): contribution of ``mod`` to stat ``key`` of ``entity`` (the queried unit;
# for fields this is any unit in scope, otherwise the holder)
DynFn = Callable[["Modifier", str, "Entity"], float]

_uid = itertools.count(1)


class Modifier:
    def __init__(
        self,
        name: str,
        *,
        stats: dict[str, float] | None = None,
        duration: int | None = None,
        tick: Tick = Tick.HOLDER_TURN_END,
        kind: ModKind = ModKind.BUFF,
        stacks: int = 1,
        max_stacks: int = 1,
        per_stack: bool = True,
        stacking: Stacking = Stacking.REFRESH,
        dispellable: bool = True,
        skip_first_tick: bool | None = None,
        key: str | None = None,
        tags: set[str] | frozenset[str] = frozenset(),
        dyn: DynFn | None = None,
        dyn_keys: set[str] | frozenset[str] = frozenset(),
        skip_turn: bool = False,
        scope: Callable[[Entity], bool] | None = None,
    ) -> None:
        self.uid = next(_uid)
        self.name = name
        self.stats: dict[str, float] = dict(stats or {})
        self.duration = duration
        self.tick = tick
        self.kind = kind
        self.stacks = stacks
        self.max_stacks = max(max_stacks, stacks)
        self.per_stack = per_stack
        self.stacking = stacking
        self.dispellable = dispellable
        self.skip_first_tick = skip_first_tick
        self._key = key
        self.tags = set(tags)
        self.dyn = dyn
        self.dyn_keys = frozenset(dyn_keys)
        self.skip_turn = skip_turn
        # A modifier with a scope is a *field*: it lives on its holder (for duration and
        # removal) but its stats apply to every entity for which scope(entity) is True.
        self.scope = scope
        self.holder: Entity | None = None
        self.source: Entity | None = None
        self.battle: Battle | None = None
        self.removed = False
        self.skip_next_tick = False
        self.applied_at: float = 0.0
        self.data: dict[str, Any] = {}  # free-form storage for kit logic

    # -------------------------------------------------------------- identity
    @property
    def key(self) -> str:
        if self._key is not None:
            return self._key
        src = self.source.uid if self.source is not None else 0
        return f"{self.name}#{src}"

    @property
    def is_debuff(self) -> bool:
        return self.kind == ModKind.DEBUFF

    @property
    def is_buff(self) -> bool:
        return self.kind == ModKind.BUFF

    # ----------------------------------------------------------------- stats
    def value(self, key: str, entity: Entity | None = None) -> float:
        v = self.stats.get(key, 0.0)
        if v and self.per_stack:
            v *= self.stacks
        if self.dyn is not None and key in self.dyn_keys:
            ent = entity if entity is not None else self.holder
            assert ent is not None
            v += self.dyn(self, key, ent)
        return v

    def touches(self, key: str) -> bool:
        return key in self.stats or key in self.dyn_keys

    # ------------------------------------------------------------- lifecycle
    def listen(self, event: str, fn: Callback, priority: int = 0) -> None:
        """Register an event listener living as long as this modifier."""
        assert self.battle is not None, "listen() must be called from on_apply()"
        self.battle.events.on(event, fn, owner=self, priority=priority)

    def on_apply(self, battle: Battle) -> None:
        """Hook: called once when first applied (register listeners here)."""

    def on_remove(self, battle: Battle) -> None:
        """Hook: called once when removed."""

    def on_merge(self, battle: Battle, incoming: Modifier) -> None:
        """Hook: an identical-key modifier was applied again (after default merge)."""

    def merge(self, incoming: Modifier) -> None:
        if self.stacking == Stacking.STACK:
            self.stacks = min(self.max_stacks, self.stacks + incoming.stacks)
        else:
            self.stacks = incoming.stacks
        self.stats = incoming.stats
        self.dyn = incoming.dyn or self.dyn
        self.dyn_keys = incoming.dyn_keys or self.dyn_keys
        if incoming.duration is not None:
            self.duration = incoming.duration
        self.skip_next_tick = incoming.skip_next_tick
        self.data.update(incoming.data)

    def tick_down(self, battle: Battle) -> None:
        if self.duration is None or self.removed:
            return
        if self.skip_next_tick:
            self.skip_next_tick = False
            return
        self.duration -= 1
        if self.duration <= 0:
            battle.remove_modifier(self)

    def __repr__(self) -> str:
        dur = "" if self.duration is None else f" {self.duration}t"
        st = f" x{self.stacks}" if self.max_stacks > 1 else ""
        return f"<{self.name}{st}{dur}>"


class DotModifier(Modifier):
    """Damage over time. Triggers at the start of the holder's turn, then ticks down.

    ``damage_fn(mod, battle, ratio)`` performs the damage (``ratio`` < 1 when a
    detonation such as Kafka's only triggers part of the DoT).
    """

    def __init__(
        self,
        name: str,
        *,
        dot_type: str,
        damage_fn: Callable[[DotModifier, Battle, float], float],
        duration: int = 2,
        is_dot: bool = True,
        **kw: Any,
    ) -> None:
        # Freeze/Entanglement also trigger at turn start but are not DoTs (is_dot=False)
        tags = set(kw.pop("tags", set())) | {dot_type} | ({"dot"} if is_dot else set())
        kw.setdefault("stacking", Stacking.REFRESH)
        super().__init__(name, duration=duration, tick=Tick.HOLDER_TURN_START, kind=ModKind.DEBUFF, tags=tags, **kw)
        self.dot_type = dot_type
        self.damage_fn = damage_fn
        self.turn_start = False  # True while triggering at the holder's turn start

    def trigger(self, battle: Battle, ratio: float = 1.0, turn_start: bool = False) -> float:
        self.turn_start = turn_start
        try:
            return self.damage_fn(self, battle, ratio)
        finally:
            self.turn_start = False


def buff(name: str, stats: dict[str, float], duration: int | None = None, **kw: Any) -> Modifier:
    return Modifier(name, stats=stats, duration=duration, kind=ModKind.BUFF, **kw)


def debuff(name: str, stats: dict[str, float], duration: int | None = None, **kw: Any) -> Modifier:
    return Modifier(name, stats=stats, duration=duration, kind=ModKind.DEBUFF, **kw)


def hidden(name: str, stats: dict[str, float] | None = None, **kw: Any) -> Modifier:
    """Permanent non-dispellable effect (traces, passives, light cone stats)."""
    kw.setdefault("tick", Tick.NONE)
    return Modifier(name, stats=stats, kind=ModKind.OTHER, dispellable=False, **kw)
