"""Access to the bundled datamined game-data snapshot.

The snapshot lives in ``hsrsim/data/gamedata`` and is produced by
``tools/build_gamedata.py``. Every lookup accepts an ID or a name (EN or CN,
case-insensitive). Numbers are exact client values (no display rounding).
"""

from __future__ import annotations

import json
from functools import cached_property, lru_cache
from pathlib import Path
from typing import Any

DATA_DIR = Path(__file__).resolve().parent / "gamedata"

# Readable names for the Trailblazer variants and duplicate names in the data.
TRAILBLAZER_PATHS = {
    "8001": "Destruction",
    "8003": "Preservation",
    "8005": "Harmony",
    "8007": "Remembrance",
    "8009": "Elation",
}
TRAILBLAZER_CN = {
    "Destruction": "毁灭",
    "Preservation": "存护",
    "Harmony": "同谐",
    "Remembrance": "记忆",
    "Elation": "欢愉",
}
EXTRA_ALIASES = {
    "1224": ["March 7th (Hunt)", "三月七（巡猎）", "三月七·巡猎", "March 7th Imaginary"],
    "1001": ["March 7th (Preservation)", "三月七（存护）"],
}

RELIC_SLOTS = {"head": 1, "hands": 2, "body": 3, "feet": 4, "sphere": 5, "rope": 6}


def _load(name: str) -> dict[str, Any]:
    return json.loads((DATA_DIR / f"{name}.json").read_text(encoding="utf-8"))


def _norm(name: str) -> str:
    return "".join(ch for ch in name.lower() if ch.isalnum())


class GameData:
    """Lazy-loaded view over the snapshot."""

    @cached_property
    def characters(self) -> dict[str, Any]:
        chars = _load("characters")
        for cid, path in TRAILBLAZER_PATHS.items():
            for offset in (0, 1):
                key = str(int(cid) + offset)
                if key in chars:
                    chars[key]["name"] = f"Trailblazer ({path})"
                    chars[key]["name_cn"] = f"开拓者（{TRAILBLAZER_CN[path]}）"
        return chars

    @cached_property
    def skills(self) -> dict[str, Any]:
        return _load("skills")

    @cached_property
    def ranks(self) -> dict[str, Any]:
        return _load("ranks")

    @cached_property
    def traces(self) -> dict[str, Any]:
        return _load("traces")

    @cached_property
    def light_cones(self) -> dict[str, Any]:
        return _load("light_cones")

    @cached_property
    def relic_sets(self) -> dict[str, Any]:
        return _load("relic_sets")

    @cached_property
    def tables(self) -> dict[str, Any]:
        return _load("tables")

    @cached_property
    def memosprites(self) -> dict[str, Any]:
        """Memosprite (servant) HP/SPD formulas keyed by servant ID ("1" + owner ID)."""
        return _load("memosprites")

    @cached_property
    def endgame(self) -> dict[str, Any]:
        """Recent Memory of Chaos ("moc"), Apocalyptic Shadow ("as") and Pure Fiction ("pf") stages."""
        return _load("endgame")

    @property
    def version(self) -> str:
        return str(self.tables["version"]["version"])

    # ------------------------------------------------------------------ lookup
    @cached_property
    def _char_index(self) -> dict[str, list[str]]:
        idx: dict[str, list[str]] = {}
        for cid, c in self.characters.items():
            names = [cid, c["name"], c.get("name_cn", ""), c.get("tag") or ""]
            names += EXTRA_ALIASES.get(cid, [])
            for n in names:
                if n:
                    idx.setdefault(_norm(n), [])
                    if cid not in idx[_norm(n)]:
                        idx[_norm(n)].append(cid)
        return idx

    def character(self, key: str | int) -> dict[str, Any]:
        key = str(key)
        if key in self.characters:
            return self.characters[key]
        hits = self._char_index.get(_norm(key), [])
        # Trailblazer variants come in identical pairs (M/F): prefer the lower ID.
        if len(hits) == 2 and hits[0].startswith("8") and int(hits[1]) - int(hits[0]) == 1:
            hits = hits[:1]
        if len(hits) == 1:
            return self.characters[hits[0]]
        if not hits:
            raise KeyError(f"unknown character {key!r}")
        options = ", ".join(f"{h} ({self.characters[h]['name']})" for h in hits)
        raise KeyError(f"ambiguous character {key!r}: {options}")

    def _find(self, table: dict[str, Any], key: str | int, what: str) -> dict[str, Any]:
        key = str(key)
        if key in table:
            return table[key]
        n = _norm(key)
        hits = [r for r in table.values() if n in (_norm(r.get("name", "")), _norm(r.get("name_cn", "")))]
        if len(hits) == 1:
            return hits[0]
        if not hits:
            raise KeyError(f"unknown {what} {key!r}")
        raise KeyError(f"ambiguous {what} {key!r}: {[h['id'] for h in hits]}")

    def light_cone(self, key: str | int) -> dict[str, Any]:
        return self._find(self.light_cones, key, "light cone")

    def relic_set(self, key: str | int) -> dict[str, Any]:
        return self._find(self.relic_sets, key, "relic set")

    def skill(self, sid: str | int) -> dict[str, Any]:
        return self.skills[str(sid)]

    # ------------------------------------------------------------------ tables
    def break_base(self, level: int) -> float:
        """Level multiplier of Break DMG (``AvatarBreakDamage``), attacker level."""
        return float(self.tables["break_level_base"][str(level)])

    def elation_base(self, level: int) -> float:
        return float(self.tables["elation_level_base"][str(level)])

    def character_group(self, name: str) -> frozenset[str]:
        """Character IDs of a named group from the game config (e.g. "AstralExpress" = Trailblaze Companions)."""
        return frozenset(self.tables.get("character_groups", {}).get(name, []))

    def relic_main_value(self, slot: str, prop: str, rarity: int = 5, level: int = 15) -> float:
        group = self.tables["relic_main_affix"][f"{rarity}{RELIC_SLOTS[slot]}"]
        if prop not in group:
            raise KeyError(f"{prop} is not a main stat for {slot}: {sorted(group)}")
        rec = group[prop]
        return float(rec["base"] + rec["add"] * level)

    def relic_sub_roll(self, prop: str, quality: str | float = "avg", rarity: int = 5) -> float:
        """Value of a single sub-stat roll. quality: low/mid/high/avg or a step count."""
        rec = self.tables["relic_sub_affix"][str(rarity)][prop]
        steps = {"low": 0, "mid": 1, "high": 2, "avg": rec["step_num"] / 2}
        k = steps[quality] if isinstance(quality, str) else float(quality)
        return float(rec["base"] + rec["step"] * k)


@lru_cache(maxsize=1)
def get_data() -> GameData:
    return GameData()
