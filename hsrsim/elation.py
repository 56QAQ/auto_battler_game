"""Elation path system: Punchline, the "Aha" unit, Aha Instant, Certified Banger and Elation DMG.

Rules implemented (see docs/mechanics_memo.md §11; parts marked there as community
knowledge are configurable here):

* Punchline is a team-wide counter. Elation abilities grant it.
* Path rules (``StageAbility_Elation``, ``MLevel_Elation_Common`` / ``MBattleEvent_Elation_ListenElationTimeEnd``):
  on entering battle (wave 1) the team gains 1 Punchline per Elation character and every Elation character
  gains 20 points of Certified Banger (2 turns); every Aha Instant ends by granting Certified Banger, consuming
  the Punchline (unless fixed) and then gaining 1 Punchline per Elation character again.
* When the team has Punchline, "Aha" (battle event 70001) is on the action bar with
  SPD = 80 + Σ SPD_i / (5·2^min(i,3)) over Elation characters sorted by SPD (desc).
* Aha's turn = "Aha Instant": every Elation character uses its Elation Skill once
  (ordered by ``ElationSkill.PriorityValue``, lower first), with P = Punchline counted.
  Then all Punchline is consumed and each participant gains "Certified Banger" for 2 turns,
  storing P (stacks are independent, each with its own duration).
* Some abilities grant Aha an extra turn with a fixed P that does not consume Punchline.
* Elation DMG = ElationBase(Lv) × scaling × (1+Elation) × (1+Merrymake) × (1 + 5P/(P+240))
  × DEF × RES × Vuln × Mitigation × Toughness × Weaken × Final DMG × CRIT  (no DMG% boosts).
"""

from __future__ import annotations

from dataclasses import replace
from typing import TYPE_CHECKING, Any

from . import events as E
from . import stats as S
from .entities import Character, Entity
from .enums import DmgTag, Element, Path, Side
from .formulas import AV_BASE
from .modifiers import Modifier, ModKind, Stacking

if TYPE_CHECKING:
    from .battle import Battle, Hit

AHA_BASE_SPD = 80.0
CERTIFIED_BANGER_TURNS = 2
ENTER_BATTLE_BANGER = 20  # StageAbility_Elation: AddElationEchoPoint AddValue=20 on wave 1 OnEnterBattle
PUNCHLINE_PER_ELATION_CHAR = 1  # StageAbility_Elation: ModifyElationPoint Add = Elation character count x 1
PUNCHLINE_CURVE_K = 240.0

PUNCHLINE_CHANGED = "punchline_changed"  # ev.delta, ev.total, ev.source
AHA_INSTANT_START = "aha_instant_start"  # ev.punchline, ev.participants, ev.fixed
AHA_INSTANT_END = "aha_instant_end"  # ev.punchline, ev.participants, ev.fixed


def punchline_multiplier(p: float) -> float:
    return 1.0 + 5.0 * p / (p + PUNCHLINE_CURVE_K) if p > 0 else 1.0


def aha_speed(speeds: list[float]) -> float:
    return AHA_BASE_SPD + sum(s / (5 * 2 ** min(i, 3)) for i, s in enumerate(sorted(speeds, reverse=True)))


class Aha(Entity):
    """Neutral action-bar unit that triggers Aha Instants (not targetable, no stats of its own)."""

    side = Side.ALLY
    targetable = False
    owner = None
    is_memosprite = False
    stat_mode = "none"

    def __init__(self, system: ElationSystem) -> None:
        super().__init__("Aha", 80)
        self.system = system
        self.on_timeline = False
        self.slot = 90

    @property
    def spd(self) -> float:
        return aha_speed([c.spd for c in self.system.elation_chars()])

    def take_turn(self, battle: Battle) -> None:
        self.system.aha_turn()


class ElationSystem:
    def __init__(self, battle: Battle, leave_when_empty: bool = True) -> None:
        self.battle = battle
        self.punchline = 0
        self.total_gained = 0
        self.leave_when_empty = leave_when_empty
        self.aha = Aha(self)
        self.aha.battle = battle
        self.instants = 0
        self.current_p: float | None = None  # P of the Aha Instant in progress
        self.current_fixed = False

    # ------------------------------------------------------------- queries
    def elation_chars(self) -> list[Character]:
        return [c for c in self.battle.team if c.alive and c.path == Path.ELATION]

    @property
    def enabled(self) -> bool:
        return bool(self.elation_chars())

    def participants(self) -> list[Character]:
        prio = self.battle.data.tables.get("elation_skill_priority", {})

        def key(c: Character) -> tuple[int, int]:
            kit = c.kit
            sid = getattr(kit, "elation_skill_id", None) if kit is not None else None
            return (int(prio.get(str(sid), 999)) if sid else 999, c.slot)

        return sorted([c for c in self.battle.team if c.alive and getattr(c.kit, "has_elation_skill", False)], key=key)

    @staticmethod
    def certified_banger(c: Entity) -> int:
        """Total Punchline stored in the unit's Certified Banger stacks."""
        return int(
            sum(m.data.get("punchline", 0) for m in c.modifiers if m.name == "Certified Banger" and not m.removed)
        )

    def grant_banger(self, target: Entity, amount: float, source: Entity | None = None, **data: Any) -> Modifier | None:
        """``target`` gains ``amount`` points of Certified Banger: one independent stack lasting 2 turns (plus kit
        extensions such as Yao Guang's A6)."""
        if amount <= 0:
            return None
        kit = getattr(target, "kit", None)
        extra = int(kit.banger_extra_turns()) if kit is not None and hasattr(kit, "banger_extra_turns") else 0
        mod = Modifier(
            "Certified Banger",
            duration=CERTIFIED_BANGER_TURNS + extra,
            kind=ModKind.BUFF,
            stacking=Stacking.INDEPENDENT,
            dispellable=False,
        )
        mod.data["punchline"] = amount
        mod.data.update(data)
        return self.battle.apply(mod, target, source)

    def per_character_gain(self) -> None:
        """Path rule: gain 1 Punchline per (living) Elation character."""
        n = len(self.elation_chars())
        if n > 0:
            self.gain(n * PUNCHLINE_PER_ELATION_CHAR, self.aha)

    def on_enter_battle(self) -> None:
        """Path rule on entering battle (wave 1 only): Certified Banger for every Elation character, then Punchline
        per Elation character."""
        chars = self.elation_chars()
        if not chars:
            return
        for c in chars:
            self.grant_banger(c, ENTER_BATTLE_BANGER, c)
        self.per_character_gain()

    # ----------------------------------------------------------- punchline
    def gain(self, n: int, source: Entity | None = None) -> None:
        if n <= 0:
            return
        self.punchline += n
        self.total_gained += n
        self.battle.events.emit(PUNCHLINE_CHANGED, delta=n, total=self.punchline, source=source)
        self._ensure_aha()

    def _ensure_aha(self) -> None:
        if not self.aha.on_timeline and self.punchline > 0 and self.enabled:
            self.aha.on_timeline = True
            self.aha.alive = True
            self.aha.gauge = AV_BASE
            if self.aha not in self.battle.units:
                self.battle.units.append(self.aha)  # type: ignore[arg-type]

    # ---------------------------------------------------------- aha turns
    def aha_turn(self) -> None:
        if self.punchline > 0:
            self.instant(self.punchline, consume=True)
        if self.leave_when_empty and self.punchline <= 0:
            self.aha.on_timeline = False

    def extra_turn(self, fixed_p: int, source: Entity | None = None) -> None:
        """Aha immediately gains an extra turn counting ``fixed_p`` Punchline, without consuming any."""
        self.battle.queue_action(lambda: self.instant(fixed_p, consume=False), source, "Aha extra turn", priority=5)

    def instant(self, p: float, consume: bool) -> None:
        b = self.battle
        parts = self.participants()
        self.instants += 1
        self.current_p, self.current_fixed = p, not consume
        b.log(f"** Aha Instant: Punchline {p} ({'consumed' if consume else 'fixed, not consumed'})")
        b.events.emit(AHA_INSTANT_START, punchline=p, participants=parts, fixed=not consume)
        prev = b.current_turn
        b.current_turn = self.aha
        try:
            for c in parts:
                if c.alive and b.alive_enemies():
                    c.kit.elation_skill(p)  # type: ignore[union-attr]
        finally:
            b.current_turn = prev
            self.current_p = None
        for c in parts:
            self.grant_banger(c, p, c)
        if consume:
            before = self.punchline
            self.punchline = 0
            b.events.emit(PUNCHLINE_CHANGED, delta=-before, total=0, source=self.aha)
        self.per_character_gain()  # after every Aha Instant, fixed ones included
        b.events.emit(AHA_INSTANT_END, punchline=p, participants=parts, fixed=not consume)

    # ------------------------------------------------------------- damage
    def damage(
        self,
        attacker: Entity,
        target: Any,
        scaling: float,
        *,
        punchline: float,
        element: Element | None = None,
        label: str,
        credited: Entity | None = None,
        extra: dict[str, float] | None = None,
        min_elation: float = 0.0,
        can_crit: bool = True,
        action: Any = None,
        tags: tuple[str, ...] = (),
        toughness: float = 0.0,
    ) -> Hit:
        """One instance of Elation DMG. With ``action`` it counts as part of that attack
        (ATTACK_START/END, attacked targets) and may reduce Toughness."""
        from .battle import Hit

        b = self.battle
        el: Element = element or Element(getattr(attacker, "element", Element.PHYSICAL))
        hit = Hit(
            attacker=attacker,
            target=target,
            element=el,
            tags=frozenset({DmgTag.ELATION, *tags}),
            mult={},
            label=label,
            owner=credited,
            can_crit=can_crit,
            extra=dict(extra or {}),
            action=action,
            toughness=toughness,
        )
        if action is not None:
            if not action.attack_started:
                action.attack_started = True
                b.events.emit(E.ATTACK_START, attack=action, action=action)
            action.hits.append(hit)
            if target not in action.attacked:
                action.attacked.append(target)
        hit.was_broken = target.broken
        b.events.emit(E.BEFORE_HIT, hit=hit)
        q, ex = hit.quals, hit.extra
        base = b.data.elation_base(attacker.level) * scaling
        elation = max(attacker.stat_q(S.ELATION_DMG_PCT, (), ex), min_elation)
        merry = attacker.stat_q(S.MERRYMAKE_PCT, (), ex)
        crit = 1.0
        if can_crit:
            cr, cd = attacker.stat_q(S.CRIT_RATE, q, ex), attacker.stat_q(S.CRIT_DMG, q, ex)
            if b.cfg.crit_mode == "random":
                hit.crit = b.rng.random() < cr
                crit = 1.0 + cd if hit.crit else 1.0
            else:
                crit = 1.0 + min(1.0, max(0.0, cr)) * cd
        hit.base = base
        hit.parts = replace(
            b._parts(attacker, target, el, q, ex, base=base, boost=1.0, crit=crit),
            elation_mult=1.0 + elation,
            merry_mult=1.0 + merry,
            punch_mult=punchline_multiplier(punchline),
            punchline=float(punchline),
        )
        hit.damage = hit.parts.total
        b.deal(target, hit.damage, hit.credited, attacker, label, hit.tags, el, hit.parts)
        if toughness > 0:
            b._toughness(hit)
        b.events.emit(E.AFTER_HIT, hit=hit)
        return hit
