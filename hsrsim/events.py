"""Synchronous event bus.

Listeners are called in (priority, registration) order. A listener may be bound
to an ``owner`` object (a Modifier, a kit, a light cone ...) so everything it
registered can be removed at once when the owner goes away.
"""

from __future__ import annotations

import itertools
from collections import defaultdict
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

# Event names --------------------------------------------------------------
BATTLE_START = "battle_start"
WAVE_START = "wave_start"
WAVE_END = "wave_end"
TURN_START = "turn_start"  # ev.entity
TURN_END = "turn_end"  # ev.entity
ACTION_START = "action_start"  # ev.action
ACTION_END = "action_end"  # ev.action
ATTACK_START = "attack_start"  # ev.attack
ATTACK_END = "attack_end"  # ev.attack
BEFORE_HIT = "before_hit"  # ev.hit  (mutate ev.hit.extra to add hit-local stats)
AFTER_HIT = "after_hit"  # ev.hit  (ev.hit.damage filled in)
BREAK = "break"  # ev.target, ev.attacker, ev.hit
KILL = "kill"  # ev.target, ev.killer
MOD_APPLIED = "mod_applied"  # ev.mod, ev.target
MOD_REMOVED = "mod_removed"  # ev.mod, ev.target
ULT_USED = "ult_used"  # ev.entity
SP_CHANGED = "sp_changed"  # ev.delta, ev.entity (who caused it)
ENERGY_GAINED = "energy_gained"  # ev.entity, ev.amount
HP_CHANGED = "hp_changed"  # ev.entity, ev.delta, ev.source
ALLY_ATTACKED = "ally_attacked"  # ev.attacker (enemy), ev.targets
DOT_TRIGGERED = "dot_triggered"  # ev.mod, ev.target, ev.damage
ENEMY_SPAWNED = "enemy_spawned"  # ev.enemy
DAMAGE_DEALT = "damage_dealt"  # ev.record (every damage instance, incl. DoT/break)
PRE_TURN = "pre_turn"  # ev.entity; set ev.data["cancel"] = True to cancel the turn (e.g. Rebloom)
BEFORE_RECOVER = "before_recover"  # ev.enemy; set ev.data["cancel"] = True to stay broken
RECOVERED = "recovered"  # ev.enemy recovered from Weakness Break


@dataclass
class Ev:
    name: str
    data: dict[str, Any] = field(default_factory=dict)

    def __getattr__(self, item: str) -> Any:
        try:
            return self.data[item]
        except KeyError as exc:
            raise AttributeError(item) from exc


Callback = Callable[[Ev], Any]


@dataclass(order=True)
class _Listener:
    priority: int
    seq: int
    callback: Callback = field(compare=False)
    owner: object = field(compare=False, default=None)
    once: bool = field(compare=False, default=False)


class EventBus:
    def __init__(self) -> None:
        self._listeners: dict[str, list[_Listener]] = defaultdict(list)
        self._seq = itertools.count()

    def on(
        self, name: str, callback: Callback, owner: object = None, priority: int = 0, once: bool = False
    ) -> _Listener:
        lst = _Listener(priority, next(self._seq), callback, owner, once)
        self._listeners[name].append(lst)
        self._listeners[name].sort()
        return lst

    def off_owner(self, owner: object) -> None:
        for name, lst in self._listeners.items():
            self._listeners[name] = [x for x in lst if x.owner is not owner]

    def emit(self, name: str, **data: Any) -> Ev:
        ev = Ev(name, data)
        # iterate over a snapshot: callbacks may add/remove listeners
        for lst in list(self._listeners.get(name, ())):
            if lst.owner is not None and getattr(lst.owner, "removed", False):
                continue
            lst.callback(ev)
            if lst.once:
                self._listeners[name] = [x for x in self._listeners[name] if x is not lst]
        return ev
