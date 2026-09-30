"""Monster traits: passive skills of datamined enemies that change the combat state.

Enemies built from endgame data carry their template name (``Enemy.template``, e.g. ``"W3_TV_03"``) and the
parameters of their passive skills (``Enemy.passives["SkillP01"]``, from ``MonsterSkillConfig``). A trait is
registered for a (template, passive key) pair and attached when the enemy spawns; numbers come from the passive's
parameters. Enemies without a registered trait behave as plain stat blocks.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING

from . import events as E
from .enums import Side

if TYPE_CHECKING:
    from .battle import Battle
    from .entities import Enemy

Trait = Callable[["Battle", "Enemy", list[float]], None]
TRAITS: dict[tuple[str, str], Trait] = {}


def trait(template: str, passive: str) -> Callable[[Trait], Trait]:
    def deco(fn: Trait) -> Trait:
        TRAITS[(template, passive)] = fn
        return fn

    return deco


def attach_monster_traits(battle: Battle, enemy: Enemy) -> None:
    for key, params in enemy.passives.items():
        fn = TRAITS.get((enemy.template, key))
        if fn is not None:
            fn(battle, enemy, params)


@trait("W3_TV_03", "SkillP01")
def smile_magic(battle: Battle, enemy: Enemy, params: list[float]) -> None:
    """ "Smile Magic" (微笑魔法): the first time this enemy is attacked, the player's team gains #1 Punchline and it
    casts "Happiness Spell" (幸福魔咒).

    not modelled: "Happiness Spell" (random: own ATK up / all enemies' action advanced / other enemies get a
    debuff); only the Punchline, which feeds the Elation path, is simulated."""
    amount = int(params[0]) if params else 0

    def after_hit(ev: E.Ev) -> None:
        h = ev.hit
        if h.target is not enemy or h.action is None or getattr(h.attacker, "side", None) != Side.ALLY:
            return
        battle.events.off_owner(enemy_key)
        if amount > 0 and battle.elation.enabled:
            battle.log(f"{enemy.name}: Smile Magic -> +{amount} Punchline")
            battle.elation.gain(amount, enemy)

    enemy_key = object()  # listener owner: removed after the first trigger
    battle.events.on(E.AFTER_HIT, after_hit, owner=enemy_key)
