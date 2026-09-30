"""Test helpers: a data-driven generic kit usable with any character (smoke tests only)."""

from __future__ import annotations

from hsrsim.build import Build
from hsrsim.data import get_data
from hsrsim.enums import ActionKind
from hsrsim.kits.base import Kit

# one representative character per Path (kit logic is replaced by GenericKit)
PATH_CHAR = {
    "Rogue": "Seele",
    "Warrior": "Clara",
    "Mage": "Himeko",
    "Shaman": "Bronya",
    "Warlock": "Kafka",
    "Knight": "Gepard",
    "Priest": "Luocha",
    "Memory": "Aglaea",
    "Elation": "Sparxie",
}


class GenericKit(Kit):
    """NOT a faithful kit: first parameter of each skill as a single-target ATK multiplier."""

    def _hit(self, kind: str, akind: ActionKind, target) -> None:
        try:
            rec = self.sk(kind)
            mult = float(rec["params"][self.level_of(rec) - 1][0]) if rec["params"] and rec["params"][0] else 1.0
        except (KeyError, IndexError):
            rec, mult = None, 1.0
        with self.battle.action(self.char, akind, skill=rec, target=target) as act:
            if target is not None:
                act.hit(target, min(mult, 5.0), toughness=10)

    def basic(self, target):
        self._hit("basic", ActionKind.BASIC, target)

    def skill(self, target):
        self._hit("skill", ActionKind.SKILL, target)

    def ult(self, target):
        self._hit("ult", ActionKind.ULT, target)


def generic_build(name: str, **kw) -> Build:
    return Build(name, kit=GenericKit, **kw)


def path_char(path: str) -> str:
    return PATH_CHAR[path]


def lc_path(lc_id: str) -> str:
    return get_data().light_cone(lc_id)["path"]
