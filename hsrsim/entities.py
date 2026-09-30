"""Combat entities: characters, enemies, summons/memosprites and timeline-only units."""

from __future__ import annotations

import itertools
from collections import defaultdict
from collections.abc import Callable, Iterable
from typing import TYPE_CHECKING, Any

from . import stats as S
from .enums import Element, EnemyRank, Path, Side
from .formulas import AV_BASE, enemy_base_def
from .modifiers import Modifier

if TYPE_CHECKING:
    from .battle import Battle
    from .kits.base import Kit

_uid = itertools.count(1)


class Entity:
    """Anything that holds stats/modifiers and (optionally) takes turns."""

    side: Side = Side.ALLY
    on_timeline: bool = True
    targetable: bool = True

    def __init__(self, name: str, level: int = 80, base: dict[str, float] | None = None) -> None:
        self.uid = next(_uid)
        self.name = name
        self.level = level
        self.base: dict[str, float] = defaultdict(float, base or {})
        self.modifiers: list[Modifier] = []
        self.gauge = AV_BASE
        self.hp = 0.0
        self.alive = True
        self.battle: Battle | None = None
        self.slot = 0
        self.ref = ""  # stable id within a battle ("a0", "e3", "s1"), see hsrsim.control
        self.last_hit_by: Entity | None = None
        self.data_flags: dict[str, object] = {}
        self._mods_cache: tuple[int, list[Modifier]] | None = None
        self._computing: set[str] = set()

    # ------------------------------------------------------------------ stats
    def raw(self, key: str) -> float:
        """Sum of the base value and all modifier contributions to ``key``."""
        total = self.base.get(key, 0.0)
        guard = key in self._computing
        self._computing.add(key)
        try:
            for m in self._stat_mods():
                if guard and m.dyn is not None and key in m.dyn_keys:
                    total += m.stats.get(key, 0.0) * (m.stacks if m.per_stack else 1)
                elif m.touches(key):
                    total += m.value(key, self)
        finally:
            if not guard:
                self._computing.discard(key)
        return total

    def _stat_mods(self) -> list[Modifier]:
        """Own modifiers (without scope) plus every battle field whose scope covers this entity.

        Cached until any modifier in the battle is applied/merged/removed (``battle.mod_version``)."""
        b = self.battle
        if b is not None and self._mods_cache is not None and self._mods_cache[0] == b.mod_version:
            return self._mods_cache[1]
        own = self._collect_mods()
        if b is not None:
            self._mods_cache = (b.mod_version, own)
        return own

    def _collect_mods(self) -> list[Modifier]:
        own = [m for m in self.modifiers if m.scope is None]
        if self.battle is not None and self.battle.fields:
            seen: set[str] = set()
            for m in self.battle.fields:
                if m.removed or m.scope is None or not m.scope(self):
                    continue
                if m._key is not None:  # explicitly keyed fields ("cannot be stacked") count once
                    if m._key in seen:
                        continue
                    seen.add(m._key)
                own.append(m)
        return own

    def stat(self, key: str, extra: dict[str, float] | None = None) -> float:
        v = self.raw(key)
        if extra:
            v += extra.get(key, 0.0)
        return v

    def stat_q(self, key: str, quals: Iterable[str], extra: dict[str, float] | None = None) -> float:
        """Sum of ``key`` and every ``key:qualifier`` (qualified stat lookup)."""
        return sum(self.stat(k, extra) for k in S.qualified(key, tuple(quals)))

    def factors(self, key: str, quals: Iterable[str]) -> list[float]:
        """Individual contributions of a multiplicative key (e.g. DMG mitigation)."""
        out: list[float] = []
        for k in S.qualified(key, tuple(quals)):
            if self.base.get(k):
                out.append(self.base[k])
            for m in self._stat_mods():
                if m.touches(k):
                    v = m.value(k, self)
                    if v:
                        out.append(v)
        return out

    def _final(self, base_key: str, pct_key: str, flat_key: str, extra: dict[str, float] | None = None) -> float:
        v = self.raw(base_key) * (1.0 + self.raw(pct_key)) + self.raw(flat_key)
        if extra:
            v += self.raw(base_key) * extra.get(pct_key, 0.0) + extra.get(flat_key, 0.0)
        return v

    @property
    def atk(self) -> float:
        return self._final(S.BASE_ATK, S.ATK_PCT, S.ATK_FLAT)

    @property
    def defense(self) -> float:
        return self._final(S.BASE_DEF, S.DEF_PCT, S.DEF_FLAT)

    @property
    def max_hp(self) -> float:
        return self._final(S.BASE_HP, S.HP_PCT, S.HP_FLAT)

    @property
    def spd(self) -> float:
        return max(1.0, self._final(S.BASE_SPD, S.SPD_PCT, S.SPD_FLAT))

    def scaling(self, attr: str, extra: dict[str, float] | None = None) -> float:
        """Value of a scaling attribute used in a skill multiplier (with hit-local extras)."""
        if attr == "atk":
            return self._final(S.BASE_ATK, S.ATK_PCT, S.ATK_FLAT, extra)
        if attr == "hp":
            return self._final(S.BASE_HP, S.HP_PCT, S.HP_FLAT, extra)
        if attr == "def":
            return self._final(S.BASE_DEF, S.DEF_PCT, S.DEF_FLAT, extra)
        if attr == "spd":
            return max(1.0, self._final(S.BASE_SPD, S.SPD_PCT, S.SPD_FLAT, extra))
        return self.stat(attr, extra)

    @property
    def hp_ratio(self) -> float:
        mh = self.max_hp
        return self.hp / mh if mh > 0 else 0.0

    @property
    def av(self) -> float:
        """Action value until this entity's next turn."""
        return self.gauge / self.spd

    # -------------------------------------------------------------- modifiers
    def mods(self, name: str | None = None, tag: str | None = None) -> list[Modifier]:
        return [
            m
            for m in self.modifiers
            if not m.removed and (name is None or m.name == name) and (tag is None or tag in m.tags)
        ]

    def get_mod(self, name: str) -> Modifier | None:
        for m in self.modifiers:
            if m.name == name and not m.removed:
                return m
        return None

    def has_mod(self, name: str) -> bool:
        return self.get_mod(name) is not None

    def has_tag(self, tag: str) -> bool:
        return any(tag in m.tags and not m.removed for m in self.modifiers)

    @property
    def debuffs(self) -> list[Modifier]:
        return [m for m in self.modifiers if m.is_debuff and not m.removed]

    @property
    def buffs(self) -> list[Modifier]:
        return [m for m in self.modifiers if m.is_buff and not m.removed]

    # ------------------------------------------------------------------ turns
    def take_turn(self, battle: Battle) -> None:
        """Perform this entity's action for the turn (overridden)."""

    def __repr__(self) -> str:
        return f"{type(self).__name__}({self.name})"


class Character(Entity):
    side = Side.ALLY

    def __init__(self, name: str, data: dict[str, Any], level: int = 80) -> None:
        super().__init__(name, level)
        self.data = data
        self.char_id: str = data["id"]
        self.path = Path(data["path"])
        self.element = Element(data["element"])
        self.eidolon = 0
        self.max_energy = float(data.get("max_energy") or 0.0)
        self.energy = 0.0
        self.skill_levels: dict[str, int] = {}
        self.kit: Kit | None = None
        self.light_cone: Any = None
        self.relic_sets: list[Any] = []
        self.traces_enabled = True
        self.enhanced = False
        self.summons: list[Summon] = []
        self.build_notes: list[str] = []

    @property
    def ult_ready(self) -> bool:
        if self.kit is not None:
            return self.kit.ult_ready()
        return self.max_energy > 0 and self.energy >= self.max_energy

    def take_turn(self, battle: Battle) -> None:
        assert self.kit is not None, f"{self.name} has no kit"
        self.kit.take_turn()


class Enemy(Entity):
    side = Side.ENEMY

    def __init__(
        self,
        name: str,
        *,
        level: int = 95,
        hp: float = 1_000_000.0,
        atk: float = 1000.0,
        spd: float = 150.0,
        toughness: float = 100.0,
        weaknesses: Iterable[Element] = (),
        res: dict[Element, float] | None = None,
        default_res: float = 0.2,
        weak_res: float = 0.0,
        effect_res: float = 0.3,
        rank: EnemyRank = EnemyRank.ELITE,
        def_value: float | None = None,
        debuff_res: dict[str, float] | None = None,
        ai: Callable[[Enemy, Battle], None] | None = None,
        hit_energy: float | None = None,
        initial_delay: float = 1.0,
    ) -> None:
        super().__init__(name, level)
        self.hit_energy = hit_energy  # Energy a character gains when hit by this enemy (None: config default)
        self.initial_delay = initial_delay  # action gauge at spawn = 10000 x initial_delay
        self.base[S.BASE_HP] = hp
        self.base[S.BASE_ATK] = atk
        self.base[S.BASE_DEF] = enemy_base_def(level) if def_value is None else def_value
        self.base[S.BASE_SPD] = spd
        self.base[S.EFFECT_RES] = effect_res
        self.weaknesses: set[Element] = set(weaknesses)
        for el in Element:
            r = weak_res if el in self.weaknesses else default_res
            if res and el in res:
                r = res[el]
            self.base[f"{S.RES}:{el.value}"] = r
        for k, v in (debuff_res or {}).items():
            self.base[f"{S.DEBUFF_RES}:{k}"] = v
        self.max_toughness = toughness
        self.toughness = toughness
        self.broken = False
        self.rank = rank
        self.ai = ai
        self.wave = 0

    @property
    def rank_key(self) -> str:
        return self.rank.value

    def res_to(self, element: Element) -> float:
        return self.raw(f"{S.RES}:{element.value}")

    def is_weak_to(self, element: Element) -> bool:
        return element in self.weaknesses or self.has_tag(f"weak:{element.value}")

    def take_turn(self, battle: Battle) -> None:
        if self.ai is not None:
            self.ai(self, battle)
        else:
            battle.enemy_basic_attack(self)


class Summon(Entity):
    """An allied unit owned by a character (memosprite, Lightning-Lord, Numby, countdowns ...).

    ``stat_mode``:
      * ``"owner"`` – every stat query except SPD is forwarded to the owner (the unit only
        contributes timing). Use for units whose DMG is computed from the owner's stats.
      * ``"sync"``  – memosprites: own HP/SPD/aggro (set by the kit from
        ``AvatarServantConfig``), every other stat is synced from the owner
        (``ServantSyncPropertyList``). Modifiers placed directly on the memosprite add on
        top; team-wide fields are counted once, through the owner.
      * ``"self"``  – fully independent stats (base + own modifiers + ``inherit`` keys).
    """

    side = Side.ALLY
    OWN_KEYS = frozenset({S.BASE_HP, S.HP_PCT, S.HP_FLAT, S.BASE_SPD, S.SPD_PCT, S.SPD_FLAT, S.AGGRO, S.AGGRO_PCT})
    _SPD_KEYS = frozenset({S.BASE_SPD, S.SPD_PCT, S.SPD_FLAT})

    def __init__(
        self,
        name: str,
        owner: Character,
        *,
        spd: float | None = None,
        stat_mode: str = "owner",
        inherit: Iterable[str] = (),
        targetable: bool = False,
        on_turn: Callable[[Summon, Battle], None] | None = None,
        on_timeline: bool = True,
    ) -> None:
        super().__init__(name, owner.level)
        self.owner = owner
        self.stat_mode = stat_mode
        self.inherit = set(inherit)
        self.targetable = targetable
        self.on_turn = on_turn
        self.on_timeline = on_timeline
        if spd is not None:
            self.base[S.BASE_SPD] = spd
        self._dyn_base: dict[str, Callable[[], float]] = {}
        self.element = owner.element
        self.path = owner.path

    @property
    def is_memosprite(self) -> bool:
        return self.stat_mode == "sync"

    def apply_dyn_base(self, key: str, fn: Callable[[], float]) -> None:
        """Make a base stat follow the owner (e.g. memosprite Max HP = x% of owner Max HP + flat)."""
        self._dyn_base[key] = fn

    def _own_raw(self, key: str, fields: bool) -> float:
        total = self._dyn_base[key]() if key in self._dyn_base else self.base.get(key, 0.0)
        for m in self.modifiers:
            if m.scope is None and m.touches(key):
                total += m.value(key, self)
        if fields and self.battle is not None:
            for m in self.battle.fields:
                if not m.removed and m.scope is not None and m.scope(self) and m.touches(key):
                    total += m.value(key, self)
        return total

    def raw(self, key: str) -> float:
        if self.stat_mode == "owner":
            return super().raw(key) if key in self._SPD_KEYS else self.owner.raw(key)
        if self.stat_mode == "sync":
            if key in self.OWN_KEYS:
                return self._own_raw(key, fields=True)
            return self.owner.raw(key) + self._own_raw(key, fields=False)
        v = super().raw(key)
        if key in self.inherit:
            v += self.owner.raw(key)
        return v

    def take_turn(self, battle: Battle) -> None:
        if self.on_turn is not None:
            self.on_turn(self, battle)
