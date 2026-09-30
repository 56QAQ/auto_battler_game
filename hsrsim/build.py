"""Character builds: turn a declarative config into a ready-to-fight :class:`Character`.

Example::

    Build(
        character="Seele", eidolon=0,
        light_cone="In the Night", superimposition=1,
        relics={"Genius of Brilliant Stars": 4, "Rutilant Arena": 2},
        main_stats={"body": "crit_dmg", "feet": "atk%", "sphere": "elemental", "rope": "atk%"},
        substats={"crit_rate": "8r", "crit_dmg": "10r", "atk%": "4r", "spd": "3r"},
    )

Substat values are either final numbers (``0.25`` = 25%) or roll counts
(``"8r"`` = 8 average rolls of a 5-star relic).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from . import stats as S
from .data import get_data
from .entities import Character
from .enums import Element, Path
from .equipment import LIGHT_CONES, RELIC_SETS, load_gear
from .kits import get_kit
from .modifiers import hidden

# stat key -> datamine property name (for relic main/sub stat values)
STAT_TO_PROP: dict[str, str] = {v: k for k, v in S.PROPERTY_MAP.items() if k != "BaseSpeed"}
STAT_TO_PROP[S.SPD_FLAT] = "SpeedDelta"

MAIN_SLOTS = ("head", "hands", "body", "feet", "sphere", "rope")


@dataclass
class Build:
    character: str
    eidolon: int = 0
    level: int = 80
    light_cone: str | None = None
    superimposition: int = 1
    lc_level: int = 80
    relics: dict[str, int] = field(default_factory=dict)
    main_stats: dict[str, str] = field(default_factory=dict)
    substats: dict[str, float | str] = field(default_factory=dict)
    relic_level: int = 15
    skill_levels: dict[str, int] = field(default_factory=dict)  # by kind ("skill") or skill ID
    traces: bool = True
    enhanced: bool = False  # use the "enhanced" kit variant (characters that received one)
    options: dict[str, Any] = field(default_factory=dict)  # kit options
    lc_options: dict[str, Any] = field(default_factory=dict)
    relic_options: dict[str, Any] = field(default_factory=dict)
    extra_stats: dict[str, float] = field(default_factory=dict)
    name: str | None = None
    kit: Any = None  # custom Kit subclass (overrides the registered kit)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> Build:
        return cls(**d)


def _stat_value(key: str, element: Element) -> str:
    key = S.normalize_stat(key)
    if key == "elemental":
        return f"{S.DMG_PCT}:{element.value}"
    return key


def _promotion(promos: list[dict[str, Any]], level: int) -> dict[str, Any]:
    for p in promos:
        if level <= p["max_level"]:
            return p
    return promos[-1]


def _lvl(pair: list[float], level: int) -> float:
    return float(pair[0] + pair[1] * (level - 1))


def make_character(build: Build) -> Character:
    gd = get_data()
    load_gear()
    data = gd.character(build.character)
    char = Character(build.name or data["name"], data, build.level)
    kit_data = data
    if build.enhanced:
        if "enhanced" not in data:
            raise ValueError(f"{data['name']} has no enhanced version")
        kit_data = data["enhanced"]
        char.enhanced = True
        char.max_energy = float(kit_data["max_energy"] or 0.0)
    char.eidolon = build.eidolon
    char.traces_enabled = build.traces
    base = char.base

    promo = _promotion(data["promotions"], build.level)
    base[S.BASE_HP] = _lvl(promo["hp"], build.level)
    base[S.BASE_ATK] = _lvl(promo["atk"], build.level)
    base[S.BASE_DEF] = _lvl(promo["def"], build.level)
    base[S.BASE_SPD] = float(promo["spd"])
    base[S.CRIT_RATE] = float(promo["crit_rate"])
    base[S.CRIT_DMG] = float(promo["crit_dmg"])
    base[S.AGGRO] = float(promo["aggro"])

    passives: dict[str, float] = {}

    def add(key: str, v: float) -> None:
        passives[key] = passives.get(key, 0.0) + v

    # ---------------------------------------------------------- skill levels
    for tid in kit_data["traces"]:
        t = gd.traces[tid]
        if t["type"] == 1 and build.traces:
            for prop, v in t["stats"]:
                add(S.normalize_stat(prop), float(v))
        for sid in t.get("skills", []):
            char.skill_levels[sid] = t["max_level"]
    for n in range(1, build.eidolon + 1):
        rank = gd.ranks.get(kit_data["ranks"][n - 1])
        if rank:
            for sid, lv in rank["skill_add_level"].items():
                char.skill_levels[sid] = char.skill_levels.get(sid, 1) + int(lv)
    kinds = {"basic": "Normal", "skill": "BPSkill", "ult": "Ultra", "talent": "Talent"}
    for k, lv in build.skill_levels.items():
        if k.isdigit():
            char.skill_levels[k] = lv
        else:
            for sid in kit_data["skills"]:
                if gd.skills.get(sid, {}).get("type") == kinds.get(k, k):
                    char.skill_levels[sid] = lv

    # ------------------------------------------------------------ light cone
    if build.light_cone:
        lc = gd.light_cone(build.light_cone)
        lp = _promotion(lc["promotions"], build.lc_level)
        base[S.BASE_HP] += _lvl(lp["hp"], build.lc_level)
        base[S.BASE_ATK] += _lvl(lp["atk"], build.lc_level)
        base[S.BASE_DEF] += _lvl(lp["def"], build.lc_level)
        if lc["path"] == data["path"]:
            for prop, v in lc["props"][build.superimposition - 1]:
                add(S.normalize_stat(prop), float(v))
            cls = LIGHT_CONES.get(lc["id"])
            if cls is not None:
                char.light_cone = cls(char, lc, build.superimposition, build.lc_options)
            elif lc["desc"]:
                char.build_notes.append(f"light cone '{lc['name']}': only static stats modelled")
        else:
            char.build_notes.append(f"light cone '{lc['name']}' path mismatch: passive inactive")

    # ---------------------------------------------------------------- relics
    for set_key, count in build.relics.items():
        rs = gd.relic_set(set_key)
        active = [int(n) for n in rs["pieces"] if int(n) <= count]
        for n in active:
            for prop, v in rs["pieces"][str(n)]["props"]:
                add(S.normalize_stat(prop), float(v))
        if active:
            cls_r = RELIC_SETS.get(rs["id"])
            if cls_r is not None:
                char.relic_sets.append(cls_r(char, rs, max(active), build.relic_options))
            elif any(rs["pieces"][str(n)]["params"] != [p[1] for p in rs["pieces"][str(n)]["props"]] for n in active):
                char.build_notes.append(f"relic set '{rs['name']}': only static stats modelled")

    mains = {"head": "hp", "hands": "atk", **build.main_stats}
    for slot, stat in mains.items():
        key = _stat_value(stat, char.element)
        prop = STAT_TO_PROP.get(key)
        if prop is None:
            raise ValueError(f"unknown main stat {stat!r} for {slot}")
        add(key, gd.relic_main_value(slot, prop, level=build.relic_level))

    for stat, value in build.substats.items():
        key = _stat_value(stat, char.element)
        if isinstance(value, str):
            rolls = float(value.lower().replace("rolls", "").replace("r", "").strip())
            prop = STAT_TO_PROP[key]
            add(key, rolls * gd.relic_sub_roll(prop))
        else:
            add(key, float(value))

    for k, v in build.extra_stats.items():
        add(_stat_value(k, char.element), float(v))

    for k, v in passives.items():
        base[k] += v

    kit_cls = build.kit or get_kit(data["id"], enhanced=build.enhanced)
    char.kit = kit_cls(char, build.options)
    return char


def attach(char: Character) -> None:
    """Called by the battle at setup: register light cone / relic conditional effects."""
    if char.light_cone is not None:
        char.light_cone.setup()
    for rs in char.relic_sets:
        rs.setup()


def stat_sheet(char: Character) -> dict[str, float]:
    """Out-of-combat stat sheet (what the in-game character screen shows)."""
    out = {
        "HP": char.max_hp,
        "ATK": char.atk,
        "DEF": char.defense,
        "SPD": char.spd,
        "CRIT Rate": char.stat(S.CRIT_RATE),
        "CRIT DMG": char.stat(S.CRIT_DMG),
        "Break Effect": char.stat(S.BREAK_EFFECT),
        "Energy Regen": 1.0 + char.stat(S.ERR),
        "Effect Hit Rate": char.stat(S.EHR),
        "Effect RES": char.stat(S.EFFECT_RES),
        f"{char.element.value} DMG": char.stat(f"{S.DMG_PCT}:{char.element.value}") + char.stat(S.DMG_PCT),
    }
    if char.path == Path.ELATION:
        out["Elation"] = char.stat(S.ELATION_DMG_PCT)  # 欢愉度
    return out


__all__ = ["Build", "make_character", "stat_sheet", "hidden"]
