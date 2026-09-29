"""Base class for character kits.

A kit implements one character's Basic ATK / Skill / Ultimate / Talent,
major traces and eidolons on top of the engine. Numeric parameters are read
from the datamined skill/trace/eidolon records, so a kit only encodes *logic*.

Conventions
-----------
* ``self.p("skill", 0)`` -> first parameter of the Skill at the character's
  current Skill level (levels include eidolon boosts).
* ``self.trace(1)`` -> True if major trace A2 (1), A4 (2) or A6 (3) is active.
* ``self.e(n)`` -> True if eidolon >= n.
* ``take_turn`` implements the default rotation policy; ``want_ult`` the
  Ultimate timing. Both can be steered with ``self.opts`` (from the build config).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, ClassVar

from .. import events as E
from .. import stats as S
from ..entities import Summon
from ..enums import ActionKind, DmgTag, Side
from ..modifiers import Modifier, ModKind, Tick, hidden

if TYPE_CHECKING:
    from ..battle import Action, Battle
    from ..entities import Character, Enemy, Entity

SKILL_TYPES = {
    "basic": "Normal",
    "skill": "BPSkill",
    "ult": "Ultra",
    "talent": "Talent",
    "technique": "Maze",
    "memo_skill": "MemospriteSkill",
    "memo_talent": "MemospriteTalent",
}


class Kit:
    char_id: ClassVar[str] = ""
    # default option values; override per kit and via build config "options"
    default_opts: ClassVar[dict[str, Any]] = {}
    # the Ultimate targets allies (relevant for e.g. Messenger / Watchmaker 4pc)
    ult_targets_ally: ClassVar[bool] = False
    # Elation path: the kit implements elation_skill(punchline); elation_skill_id orders Aha Instants
    has_elation_skill: ClassVar[bool] = False
    elation_skill_id: ClassVar[str] = ""

    def __init__(self, char: Character, opts: dict[str, Any] | None = None) -> None:
        self.char = char
        self.opts: dict[str, Any] = {**self.default_opts, **(opts or {})}
        self._skills_by_type: dict[str, list[dict[str, Any]]] = {}
        data = char.battle.data if char.battle is not None else None
        from ..data import get_data

        gd = data or get_data()
        self.gd = gd
        for sid in self.skill_ids():
            rec = gd.skills.get(sid)
            if rec is not None:
                self._skills_by_type.setdefault(rec["type"], []).append(rec)
        self.state: dict[str, Any] = {}

    # ---------------------------------------------------------------- access
    @property
    def battle(self) -> Battle:
        assert self.char.battle is not None
        return self.char.battle

    @property
    def prefix(self) -> str:
        """ID prefix of skills/traces/eidolons: "<cid>" or "1<cid>" for the enhanced kit."""
        return ("1" + self.char.char_id) if self.char.enhanced else self.char.char_id

    def skill_ids(self) -> list[str]:
        """Skill IDs of this character's kit (variant-aware, incl. memosprite skills)."""
        cid = self.char.char_id
        out = []
        for k, rec in self.gd.skills.items():
            if self.char.enhanced:
                if k[:-2] == "1" + cid:
                    out.append(k)
            elif k[:-2] == cid or (k[:-2] == "1" + cid and rec["type"].startswith("Memosprite")):
                out.append(k)
        return sorted(out)

    def sk(self, kind: str, index: int = 0) -> dict[str, Any]:
        """Skill record by kind ("basic", "skill", ...) or by explicit skill ID."""
        if kind.isdigit():
            return self.gd.skills[kind]
        recs = self._skills_by_type.get(SKILL_TYPES.get(kind, kind), [])
        if not recs:
            raise KeyError(f"{self.char.name} has no {kind} skill")
        return recs[index]

    def level_of(self, rec: dict[str, Any]) -> int:
        return min(self.char.skill_levels.get(rec["id"], 1), len(rec["params"]))

    def p(self, kind: str, i: int, index: int = 0) -> float:
        rec = self.sk(kind, index)
        return float(rec["params"][self.level_of(rec) - 1][i])

    def trace_rec(self, n: int) -> dict[str, Any]:
        return self.gd.traces[f"{self.prefix}10{n}"]

    def trace(self, n: int) -> bool:
        return self.char.traces_enabled and f"{self.prefix}10{n}" in self.gd.traces

    def tp(self, n: int, i: int) -> float:
        """Parameter ``i`` of major trace ``n`` (1=A2, 2=A4, 3=A6)."""
        return float(self.trace_rec(n)["params"][i])

    def e(self, n: int) -> bool:
        return self.char.eidolon >= n

    def ep(self, n: int, i: int) -> float:
        """Parameter ``i`` of eidolon ``n``."""
        return float(self.gd.ranks[f"{self.prefix}0{n}"]["params"][i])

    # ------------------------------------------------------------- lifecycle
    def setup(self) -> None:
        """Called once when the battle starts, before wave 1 spawns. Register listeners here."""

    def on_battle_start(self) -> None:
        """Called after wave 1 spawned (battle-start effects)."""

    def technique(self) -> None:
        """Technique effect used before battle (only when BattleConfig.techniques)."""

    # ---------------------------------------------------------------- policy
    def take_turn(self) -> None:
        """Default rotation: Skill when SP allows (and the skill needs SP), else Basic ATK."""
        target = self.pick_target()
        if target is None:
            return
        policy = self.opts.get("rotation", "skill")
        if policy == "basic" or not self.can_skill():
            self.basic(target)
        else:
            self.skill(target)

    def can_skill(self) -> bool:
        need = self.sk("skill")["sp_need"]
        need = need[0] if isinstance(need, list) else need
        return self.battle.sp >= max(0, int(need))

    def pick_target(self) -> Enemy | None:
        return self.battle.default_target()

    def ult_ready(self) -> bool:
        return self.char.max_energy > 0 and self.char.energy >= self.char.max_energy - 1e-9

    def want_ult(self) -> bool:
        return bool(self.opts.get("ult", True))

    def use_ult(self) -> None:
        before = self.char.energy
        self.pay_ult_cost()
        spent = max(0.0, before - self.char.energy)
        self.char.data_flags["ult_energy_spent"] = spent
        self.battle.events.emit(E.ULT_USED, entity=self.char, energy=spent)
        self.ult(self.pick_target())

    def pay_ult_cost(self) -> None:
        self.char.energy = 0.0

    # --------------------------------------------------------------- actions
    def basic(self, target: Enemy | None) -> None:
        raise NotImplementedError(f"{self.char.name}: basic")

    def skill(self, target: Enemy | None) -> None:
        raise NotImplementedError(f"{self.char.name}: skill")

    def ult(self, target: Enemy | None) -> None:
        raise NotImplementedError(f"{self.char.name}: ult")

    def elation_skill(self, punchline: float) -> None:
        raise NotImplementedError(f"{self.char.name}: elation skill")

    def banger_extra_turns(self) -> int:
        """Extra turns added to Certified Banger gained by this character (e.g. traces)."""
        return 0

    # ------------------------------------------------------------ memosprites
    def _servant_value(self, expr: str, skill_id: str) -> float:
        if expr.startswith("#"):
            rec = self.gd.skills[skill_id]
            return float(rec["params"][self.level_of(rec) - 1][int(expr[1:]) - 1])
        return float(expr or 0)

    def summon_memosprite(
        self, name: str, on_turn: Any, servant_id: str | None = None, av: float | None = None
    ) -> Summon:
        """Create this character's memosprite with HP/SPD from ``AvatarServantConfig`` (stats synced
        from the owner otherwise). Call again to re-summon (returns the existing one if alive)."""
        for s in self.char.summons:
            if s.is_memosprite and s.alive:
                return s
        sv = self.gd.memosprites[servant_id or ("1" + self.char.char_id)]
        hp_base = self._servant_value(sv["hp_base"], sv["hp_skill"]) if sv["hp_skill"] else float(sv["hp_base"] or 0)
        hp_inh = self._servant_value(sv["hp_inherit"], sv["hp_skill"]) if sv["hp_skill"] else 0.0
        spd_base = (
            self._servant_value(sv["spd_base"], sv["spd_skill"]) if sv["spd_skill"] else float(sv["spd_base"] or 0)
        )
        spd_inh = self._servant_value(sv["spd_inherit"], sv["spd_skill"]) if sv["spd_skill"] else 0.0
        memo = Summon(name, self.char, stat_mode="sync", targetable=True, on_turn=on_turn)
        owner = self.char
        memo.base[S.BASE_HP] = hp_base
        memo.base[S.AGGRO] = float(sv["aggro"])
        memo.base[S.BASE_SPD] = spd_base
        if hp_inh:
            memo.apply_dyn_base(S.BASE_HP, lambda: hp_base + hp_inh * owner.max_hp)
        if spd_inh:
            memo.apply_dyn_base(S.BASE_SPD, lambda: spd_base + spd_inh * owner.spd)
        return self.battle.add_unit(memo, av=av)

    def memosprite(self) -> Summon | None:
        for s in self.char.summons:
            if s.is_memosprite and s.alive:
                return s
        return None

    # --------------------------------------------------------------- elation
    def gain_punchline(self, n: int) -> None:
        self.battle.elation.gain(n, self.char)

    def banger(self) -> int:
        """Punchline stored in this character's Certified Banger stacks (0 = no Certified Banger)."""
        return self.battle.elation.certified_banger(self.char)

    def elation_hit(self, target: Enemy, scaling: float, punchline: float, **kw: Any) -> Any:
        kw.setdefault("label", "Elation DMG")
        kw.setdefault("credited", self.char)
        return self.battle.elation.damage(self.char, target, scaling, punchline=punchline, **kw)

    # --------------------------------------------------------------- helpers
    def action(
        self, kind: ActionKind, skill: str | dict[str, Any] | None = None, target: Entity | None = None, **kw: Any
    ) -> Any:
        rec = self.sk(skill) if isinstance(skill, str) else skill
        if kind == ActionKind.ULT and "energy" not in kw and not self.battle.cfg.ult_energy_refund:
            kw["energy"] = 0.0
        return self.battle.action(self.char, kind, skill=rec, target=target, **kw)

    def simple_basic(self, target: Enemy, splits: list[float] | None = None) -> Action:
        with self.action(ActionKind.BASIC, "basic", target) as act:
            act.hit(target, self.p("basic", 0), toughness=self.toughness("basic"), splits=splits)
        return act

    def toughness(self, kind: str, which: int = 0, index: int = 0) -> float:
        t = self.sk(kind, index)["toughness"]
        if t and isinstance(t[0], list):
            t = t[self.level_of(self.sk(kind, index)) - 1]
        return float(t[which]) if t and len(t) > which else 0.0

    def buff_self(self, mod: Modifier) -> Modifier:
        return self.battle.apply(mod, self.char, self.char)

    def buff(self, target: Entity, mod: Modifier) -> Modifier:
        return self.battle.apply(mod, target, self.char)

    def passive(self, name: str, stats: dict[str, float], target: Entity | None = None, **kw: Any) -> Modifier:
        """Permanent hidden stat bonus (e.g. traces 'CRIT Rate +X%')."""
        return self.battle.apply(hidden(name, stats, **kw), target or self.char, self.char)

    def on(self, event: str, fn: Any, priority: int = 0) -> None:
        self.battle.events.on(event, fn, owner=self, priority=priority)

    def allies(self) -> list[Character]:
        return [c for c in self.battle.team if c.alive]

    def teammates(self) -> list[Character]:
        return [c for c in self.battle.team if c.alive and c is not self.char]

    def main_dps(self) -> Character:
        """Ally that receives single-target support (option "target": name; default first other slot)."""
        name = self.opts.get("target")
        if name:
            return self.battle.character(name)
        mates = self.teammates()
        return mates[0] if mates else self.char

    @staticmethod
    def ally_scope(e: Entity) -> bool:
        return e.side == Side.ALLY

    def teammate_scope(self, e: Entity) -> bool:
        return e.side == Side.ALLY and e is not self.char

    @staticmethod
    def enemy_scope(e: Entity) -> bool:
        return e.side == Side.ENEMY

    def enemies(self) -> list[Enemy]:
        return self.battle.alive_enemies()

    def is_mine(self, action: Action) -> bool:
        return action.owner is self.char

    @staticmethod
    def timed(
        name: str,
        stats: dict[str, float],
        duration: int,
        *,
        kind: ModKind = ModKind.BUFF,
        tick: Tick = Tick.HOLDER_TURN_END,
        **kw: Any,
    ) -> Modifier:
        return Modifier(name, stats=stats, duration=duration, kind=kind, tick=tick, **kw)

    removed = False  # kits are listener owners that never get removed


def tags_of(*t: str) -> frozenset[str]:
    return frozenset(t)


FUA = DmgTag.FUA
