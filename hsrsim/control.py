"""Manual control of a battle: decision points, action menus and decisions.

A :class:`Controller` attached to ``Battle.controller`` is asked

* at every **turn** of an ally (and of summons whose owner kit exposes a menu): which action to take
  (or to cast an Ultimate first, or to let the kit's policy decide), and
* at every **Ultimate window** (before each unit's turn, between queued follow-ups, inside actions that do
  not end the turn): whether to insert an Ultimate.

Without a controller the kits' own policies (``take_turn`` / ``want_ult``) run the battle as before.
Units are referred to by stable *refs* (``a0``..``a3`` allies, ``e<n>`` enemies in spawn order,
``s<n>`` summons in creation order) so that recorded decisions can be replayed on a fresh battle.
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .battle import Battle
    from .entities import Entity

# where an Ultimate window opens
BEFORE_TURN = "before_turn"  # before the next unit's turn (subject = that unit)
QUEUE = "queue"  # between inserted actions (follow-ups, counters, extra turns)
MID_ACTION = "mid_action"  # inside an action that does not end the turn (e.g. Blade's Skill)

# target kinds of menu items / Ultimates
ENEMY = "enemy"  # one enemy (the main target of single / blast / bounce abilities)
ENEMIES = "enemies"  # all enemies (a main target may still matter)
ALLY = "ally"  # one ally
ALLIES = "allies"  # the whole team
SELF = "self"  # no target


@dataclass
class MenuItem:
    """One action a unit can take on its turn."""

    id: str  # "basic", "skill" or a kit-defined id
    label: str  # display name (the ability's in-game name)
    target: str = ENEMY
    enabled: bool = True
    ends_turn: bool = True  # False: the turn continues afterwards (e.g. Qingque's Skill)
    sp: int = 0  # Skill Point change (negative = cost)
    kind: str = "basic"  # "basic" | "skill" | "other" (hotkeys: Q = basic, E = skill)
    note: str = ""  # short hint (why it is disabled, what it consumes ...)
    label_cn: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class Decision:
    """A controller's answer at a decision point."""

    kind: str  # "act" | "ult" | "continue" | "auto"
    item: str = ""  # menu item id (kind "act")
    who: str = ""  # ref of the Ultimate's caster (kind "ult")
    target: str = ""  # ref of the target ("" = default)
    extra: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {"kind": self.kind}
        for k in ("item", "who", "target"):
            if getattr(self, k):
                d[k] = getattr(self, k)
        if self.extra:
            d["extra"] = self.extra
        return d

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> Decision:
        return cls(
            kind=str(d["kind"]),
            item=str(d.get("item", "")),
            who=str(d.get("who", "")),
            target=str(d.get("target", "")),
            extra=dict(d.get("extra", {})),
        )


CONTINUE = Decision("continue")
AUTO = Decision("auto")


class Controller:
    """Base controller: behaves like the automatic policies (useful as a template)."""

    def turn(self, battle: Battle, actor: Entity, extra_turn: bool) -> Decision:
        return AUTO

    def window(self, battle: Battle, where: str, subject: Entity | None) -> Decision:
        for c in battle.team:
            if c.alive and c.kit is not None and c.kit.ult_ready() and c.kit.want_ult():
                return Decision("ult", who=c.ref)
        return CONTINUE


_TEAM_WORDS = re.compile(r"\ball (allies|teammates|party members|characters)\b|\bentire team\b|\bthe team\b", re.I)


def target_kind(rec: dict[str, Any] | None) -> str:
    """Target kind of an ability from its skill record (``effect`` + description)."""
    if not rec:
        return SELF
    eff = str(rec.get("effect") or "")
    if eff in ("SingleAttack", "Blast", "Bounce", "Impair"):
        return ENEMY
    if eff in ("AoEAttack", "MazeAttack"):
        return ENEMIES
    if eff in ("Support", "Restore", "Defence"):
        desc = str(rec.get("desc") or "")
        if _TEAM_WORDS.search(desc) and not re.search(
            r"\b(a|one) (single )?(designated )?(ally|teammate|target ally)\b", desc
        ):
            return ALLIES
        return ALLY
    return SELF
