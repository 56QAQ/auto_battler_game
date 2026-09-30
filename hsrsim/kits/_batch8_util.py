"""Small helpers shared by the batch-8 kits (4.x Elation characters, Himeko • Nova, Fate collaboration).

Not a kit: nothing here is registered.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from ..elation import CERTIFIED_BANGER_TURNS
from ..entities import Entity
from ..enums import Path
from ..modifiers import Modifier, ModKind, Stacking

if TYPE_CHECKING:
    from ..battle import Battle

BANGER = "Certified Banger"


def banger_turns(target: Entity) -> int:
    """Duration of a Certified Banger stack gained by ``target`` (2 turns + kit extensions)."""
    kit = getattr(target, "kit", None)
    extra = int(kit.banger_extra_turns()) if kit is not None else 0
    return CERTIFIED_BANGER_TURNS + extra


def grant_banger(battle: Battle, target: Entity, amount: float, source: Entity | None, **data: Any) -> Modifier | None:
    """``target`` gains ``amount`` points of Certified Banger (one independent stack, like the Aha Instant's)."""
    if amount <= 0:
        return None
    mod = Modifier(
        BANGER,
        duration=banger_turns(target),
        kind=ModKind.BUFF,
        stacking=Stacking.INDEPENDENT,
        dispellable=False,
    )
    mod.data["punchline"] = float(amount)
    mod.data.update(data)
    return battle.apply(mod, target, source)


def elation_count(battle: Battle) -> int:
    return sum(1 for c in battle.team if c.path == Path.ELATION)


def elation_priority(battle: Battle, c: Entity) -> int:
    """Elation Skill participant priority (lower acts first in an Aha Instant; 999 = no Elation Skill)."""
    kit = getattr(c, "kit", None)
    sid = getattr(kit, "elation_skill_id", "") if kit is not None else ""
    if not sid or not getattr(kit, "has_elation_skill", False):
        return 999
    return int(battle.data.tables.get("elation_skill_priority", {}).get(str(sid), 999))


def has_elation_skill(c: Entity) -> bool:
    kit = getattr(c, "kit", None)
    return bool(kit is not None and getattr(kit, "has_elation_skill", False))
