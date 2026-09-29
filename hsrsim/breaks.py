"""Weakness Break status effects (Bleed, Burn, Freeze, Shock, Wind Shear, Entanglement, Imprisonment).

Each break status is applied with a 150% base chance (affected by Effect Hit
Rate and the enemy's Effect RES / specific debuff RES). Break DoT DMG uses the
Break DMG formula: it scales with Break Effect, cannot crit and ignores DMG%.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from . import events as E
from . import formulas as F
from . import stats as S
from .enums import DmgTag, Element
from .modifiers import DotModifier, Modifier, ModKind, Stacking, Tick

if TYPE_CHECKING:
    from .battle import Battle
    from .entities import Enemy, Entity

BREAK_EFFECT_CHANCE = 1.5

DOT_TYPE = {
    Element.PHYSICAL: "bleed",
    Element.FIRE: "burn",
    Element.LIGHTNING: "shock",
    Element.WIND: "wind_shear",
    Element.ICE: "freeze",
    Element.QUANTUM: "entanglement",
    Element.IMAGINARY: "imprisonment",
}


def _level(battle: Battle, attacker: Entity) -> float:
    return battle.data.break_base(attacker.level)


def bleed_base(battle: Battle, attacker: Entity, target: Enemy) -> float:
    cap = F.BLEED_HP_CAP[target.rank_key] * target.max_hp
    return min(cap, F.BLEED_MULT * _level(battle, attacker) * F.toughness_multiplier(target.max_toughness))


def make_break_dot(
    battle: Battle,
    attacker: Entity,
    target: Enemy,
    element: Element,
    credited: Entity | None = None,
    *,
    duration: int = 2,
    stacks: int = 1,
    name: str | None = None,
) -> DotModifier:
    """Create (not apply) the break DoT for ``element`` (Bleed/Burn/Shock/Wind Shear)."""
    dot_type = DOT_TYPE[element]
    credited = credited or attacker

    def dmg(mod: DotModifier, b: Battle, ratio: float) -> float:
        lvl = _level(b, attacker)
        if dot_type == "bleed":
            base = bleed_base(b, attacker, target)
        elif dot_type == "burn":
            base = F.BURN_MULT * lvl
        elif dot_type == "shock":
            base = F.SHOCK_MULT * lvl
        else:  # wind shear
            base = F.WIND_SHEAR_MULT * lvl * mod.stacks
        d = b.special_damage(
            attacker,
            target,
            element,
            base * ratio,
            tags=(DmgTag.DOT, DmgTag.BREAK, dot_type),
            label=f"Break DoT ({dot_type})",
            credited=credited,
        )
        b.events.emit(E.DOT_TRIGGERED, mod=mod, target=target, damage=d)
        return d

    is_ws = dot_type == "wind_shear"
    return DotModifier(
        name or dot_type.replace("_", " ").title(),
        dot_type=dot_type,
        damage_fn=dmg,
        duration=duration,
        stacks=stacks,
        max_stacks=F.WIND_SHEAR_MAX if is_ws else 1,
        stacking=Stacking.STACK if is_ws else Stacking.REFRESH,
        tags={"break_dot"},
    )


class Entanglement(DotModifier):
    def __init__(self, attacker: Entity, target: Enemy, credited: Entity) -> None:
        def dmg(mod: DotModifier, b: Battle, ratio: float) -> float:
            base = (
                F.ENTANGLE_MULT
                * mod.stacks
                * _level(b, attacker)
                * F.toughness_multiplier(target.max_toughness)
                * ratio
            )
            return b.special_damage(
                attacker,
                target,
                Element.QUANTUM,
                base,
                tags=(DmgTag.BREAK, "entanglement"),
                label="Entanglement",
                credited=credited,
            )

        super().__init__(
            "Entanglement",
            dot_type="entanglement",
            damage_fn=dmg,
            duration=1,
            is_dot=False,
            max_stacks=F.ENTANGLE_MAX,
            tags={"cc"},
        )

    def on_apply(self, battle: Battle) -> None:
        def on_attack_end(ev: E.Ev) -> None:
            if self.holder in ev.attack.attacked and self.stacks < self.max_stacks:
                self.stacks += 1

        self.listen(E.ATTACK_END, on_attack_end)


class Freeze(DotModifier):
    def __init__(self, attacker: Entity, target: Enemy, credited: Entity, duration: int = 1, mult: float = 1.0):
        def dmg(mod: DotModifier, b: Battle, ratio: float) -> float:
            base = F.FREEZE_MULT * _level(b, attacker) * mult * ratio
            return b.special_damage(
                attacker, target, Element.ICE, base, tags=(DmgTag.BREAK, "freeze"), label="Freeze", credited=credited
            )

        super().__init__(
            "Frozen",
            dot_type="freeze",
            damage_fn=dmg,
            duration=duration,
            is_dot=False,
            skip_turn=True,
            tags={"cc"},
        )

    def on_remove(self, battle: Battle) -> None:
        if self.holder is not None and self.holder.alive:
            battle.advance(self.holder, F.FREEZE_THAW_ADVANCE)


def apply_break_effect(
    battle: Battle, attacker: Entity, target: Enemy, element: Element, be: float, credited: Entity
) -> None:
    dot_type = DOT_TYPE[element]
    mod: Modifier
    if element in (Element.PHYSICAL, Element.FIRE, Element.LIGHTNING):
        mod = make_break_dot(battle, attacker, target, element, credited)
    elif element == Element.WIND:
        mod = make_break_dot(battle, attacker, target, element, credited, stacks=F.WIND_SHEAR_STACKS[target.rank_key])
    elif element == Element.ICE:
        mod = Freeze(attacker, target, credited)
    elif element == Element.QUANTUM:
        battle.delay(target, F.QUANTUM_BREAK_DELAY * (1.0 + be))
        mod = Entanglement(attacker, target, credited)
    else:  # Imaginary
        battle.delay(target, F.IMAGINARY_BREAK_DELAY * (1.0 + be))
        mod = Modifier(
            "Imprisoned",
            stats={S.SPD_PCT: -F.IMPRISON_SLOW},
            duration=1,
            tick=Tick.HOLDER_TURN_START,
            kind=ModKind.DEBUFF,
            tags={"cc", "imprisonment"},
        )
    battle.try_debuff(mod, target, attacker, BREAK_EFFECT_CHANCE, debuff_type=dot_type)
