"""Light cones and relic sets.

Always-on stats of light cones (``AbilityProperty``) and relic set bonuses
(``PropertyList``) are applied automatically from the data for *every* item.
Conditional effects need a small class registered here (see ``hsrsim/gear``).
Items without a class still get their unconditional stats; the build records
a note so reports can flag the missing conditional part.
"""

from __future__ import annotations

import importlib
import pkgutil
from typing import TYPE_CHECKING, Any, ClassVar, TypeVar

if TYPE_CHECKING:
    from .battle import Battle
    from .entities import Character


class LightCone:
    lc_id: ClassVar[str] = ""

    def __init__(self, char: Character, data: dict[str, Any], superimposition: int, opts: dict[str, Any]) -> None:
        self.char = char
        self.data = data
        self.s = superimposition
        self.opts = opts

    def p(self, i: int) -> float:
        return float(self.data["params"][self.s - 1][i])

    @property
    def battle(self) -> Battle:
        assert self.char.battle is not None
        return self.char.battle

    def setup(self) -> None:
        """Register conditional effects (static stats are already applied)."""

    def on(self, event: str, fn: Any, priority: int = 0) -> None:
        self.battle.events.on(event, fn, owner=self, priority=priority)

    removed = False


class RelicSet:
    set_id: ClassVar[str] = ""

    def __init__(self, char: Character, data: dict[str, Any], pieces: int, opts: dict[str, Any]) -> None:
        self.char = char
        self.data = data
        self.pieces = pieces
        self.opts = opts

    def p(self, pieces: int, i: int) -> float:
        return float(self.data["pieces"][str(pieces)]["params"][i])

    @property
    def battle(self) -> Battle:
        assert self.char.battle is not None
        return self.char.battle

    def setup(self) -> None:
        """Register conditional effects (static 2pc/4pc stats are already applied)."""

    def on(self, event: str, fn: Any, priority: int = 0) -> None:
        self.battle.events.on(event, fn, owner=self, priority=priority)

    removed = False


LIGHT_CONES: dict[str, type[LightCone]] = {}
RELIC_SETS: dict[str, type[RelicSet]] = {}
L = TypeVar("L", bound=type[LightCone])
R = TypeVar("R", bound=type[RelicSet])


def register_lc(cls: L) -> L:
    LIGHT_CONES[cls.lc_id] = cls
    return cls


def register_relic(cls: R) -> R:
    RELIC_SETS[cls.set_id] = cls
    return cls


def load_gear() -> None:
    from . import gear

    for mod in pkgutil.iter_modules(gear.__path__):
        importlib.import_module(f"{gear.__name__}.{mod.name}")
