"""Conditional effects of Abundance (Priest), Remembrance (Memory) and Elation light cones.

Always-on stats (the ``props`` of the data) are applied by the build code; the classes
below only add what depends on combat state. Every number is read from the data:
placeholder ``#n`` of the description is ``self.p(n - 1)``.

Engine gaps worked around here:

* there is no event for a memosprite being summoned or disappearing, so
  :class:`_MemoWatch` polls the wearer's memosprite around every action / turn;
* Elation: an "Elation Skill" is an action of kind ``ActionKind.ELATION`` or built from a
  skill record of type ``ElationDamage``. Punchline / Aha Instant hooks use the optional
  Elation system (``battle.elation``, ``hsrsim.elation``) and stay inert without it.
"""

from __future__ import annotations

import math
import re
from collections.abc import Callable, Iterable
from typing import TYPE_CHECKING, Any

from .. import events as E
from .. import stats as S
from ..entities import Character, Enemy, Entity, Summon
from ..enums import ActionKind, DmgTag, Path, Side
from ..equipment import LightCone, register_lc
from ..modifiers import Modifier, ModKind, Stacking, Tick, hidden

if TYPE_CHECKING:
    from ..battle import Action, Battle

try:  # Elation path system (Punchline / Aha Instant): optional, this module must load without it
    from ..elation import AHA_INSTANT_END, AHA_INSTANT_START
except ImportError:  # pragma: no cover
    AHA_INSTANT_START = AHA_INSTANT_END = ""

ELATION = S.ELATION_DMG_PCT  # the "Elation" stat
DEF_IGNORE_ELATION = f"{S.DEF_IGNORE}:{DmgTag.ELATION}"
VULN_ELATION = f"{S.VULN}:{DmgTag.ELATION}"
_ELATION_KIND = getattr(ActionKind, "ELATION", None)
_ALLY_EFFECTS = frozenset({"Support", "Restore", "Defence"})  # skill ``effect`` of abilities used on allies


def _ally(e: Entity) -> bool:
    return e.side == Side.ALLY


def _enemy(e: Entity) -> bool:
    return e.side == Side.ENEMY


def _memosprite_of(c: Character) -> Summon | None:
    for s in c.summons:
        if s.alive and s.is_memosprite:
            return s
    return None


def _is_memosprite(e: object) -> bool:
    return isinstance(e, Summon) and e.is_memosprite


def _is_elation_skill(act: Action | None) -> bool:
    """Elation Skill: an ``ELATION`` action, or one built from a skill record of type ``ElationDamage``."""
    if act is None:
        return False
    return act.kind == _ELATION_KIND or (act.skill is not None and act.skill.get("type") == "ElationDamage")


def _punchline(battle: Battle) -> float:
    """Team Punchline held (0 without the Elation system)."""
    return float(getattr(getattr(battle, "elation", None), "punchline", 0) or 0)


def _is_memo_skill(act: Action) -> bool:
    """Memosprite Skill: a memosprite action (with a ``MemospriteSkill`` record when one is given)."""
    if not _is_memosprite(act.actor):
        return False
    if act.skill is not None:
        return act.skill.get("type") == "MemospriteSkill"
    return act.kind == ActionKind.MEMOSPRITE


class _MemoWatch:
    """Tracks the wearer's memosprite and reports summons / disappearances.

    The engine emits no event when a unit is added or removed, so the memosprite is
    polled (before other listeners) on the events surrounding every action and turn.
    """

    EVENTS = (E.BATTLE_START, E.WAVE_START, E.TURN_START, E.TURN_END, E.ACTION_START, E.ACTION_END, E.HP_CHANGED)

    def __init__(
        self,
        lc: _LC,
        on_summon: Callable[[Summon], Any] | None = None,
        on_gone: Callable[[Summon], Any] | None = None,
    ) -> None:
        self.lc = lc
        self.cur: Summon | None = None
        self.on_summon = on_summon
        self.on_gone = on_gone
        for name in self.EVENTS:
            lc.on(name, self.check, priority=-100)

    def check(self, ev: E.Ev | None = None) -> None:
        m = _memosprite_of(self.lc.char)
        if m is self.cur:
            return
        old, self.cur = self.cur, m
        if old is not None and self.on_gone is not None:
            self.on_gone(old)
        if m is not None and self.on_summon is not None:
            self.on_summon(m)


class _LC(LightCone):
    def mine(self, act: Action) -> bool:
        """``act`` is performed by the wearer itself (not by one of its summons)."""
        return act.actor is self.char

    def is_my_memo(self, e: object) -> bool:
        return isinstance(e, Summon) and e.is_memosprite and e.owner is self.char

    def buff(self, target: Entity, mod: Modifier) -> Modifier:
        return self.battle.apply(mod, target, self.char)

    def passive(
        self, name: str, stats: dict[str, float] | None = None, target: Entity | None = None, **kw: Any
    ) -> Modifier:
        return self.battle.apply(hidden(name, stats, **kw), target or self.char, self.char)

    def team(self, memosprites: bool = False) -> list[Entity]:
        """Alive ally characters (+ memosprites: only for SPD buffs / heals, other stats are synced)."""
        out: list[Entity] = [c for c in self.battle.team if c.alive]
        if memosprites:
            out += [u for u in self.battle.units if u.alive and u.is_memosprite]
        return out

    def enemies(self, targets: Iterable[Enemy] | None = None) -> list[Enemy]:
        return [e for e in (self.battle.alive_enemies() if targets is None else targets) if e.alive]

    def heal(self, target: Entity, base: float) -> None:
        self.battle.heal(target, base, self.char)

    def healed_by_me(self, ev: E.Ev) -> bool:
        """HP_CHANGED listener check: a heal provided by the wearer (or its summon) to an ally."""
        src = ev.source
        owner = src.owner if isinstance(src, Summon) else src
        return ev.delta > 0 and owner is self.char and ev.entity.side == Side.ALLY

    def while_acting(self, kinds: tuple[ActionKind, ...], name: str, stats: dict[str, float]) -> None:
        """Hidden bonus that lasts while the wearer performs an action of ``kinds``."""

        def start(ev: E.Ev) -> None:
            if self.mine(ev.action) and ev.action.kind in kinds:
                self.passive(name, stats)

        def end(ev: E.Ev) -> None:
            if self.mine(ev.action) and ev.action.kind in kinds:
                self.battle.remove_named(self.char, name)

        self.on(E.ACTION_START, start)
        self.on(E.ACTION_END, end)


# ======================================================================= Abundance
@register_lc
class Cornucopia(_LC):
    lc_id = "20001"

    def setup(self) -> None:
        self.while_acting((ActionKind.SKILL, ActionKind.ULT), "Cornucopia", {S.HEAL_PCT: self.p(0)})


@register_lc
class FineFruit(_LC):
    lc_id = "20008"

    def setup(self) -> None:
        def start(ev: E.Ev) -> None:
            for c in self.battle.team:
                if c.alive:
                    self.battle.gain_energy(c, self.p(0))

        self.on(E.BATTLE_START, start)


@register_lc
class Multiplication(_LC):
    lc_id = "20015"

    def setup(self) -> None:
        def after_basic(ev: E.Ev) -> None:
            if self.mine(ev.action) and ev.action.kind == ActionKind.BASIC:
                self.battle.advance(self.char, self.p(0))

        self.on(E.ACTION_END, after_basic)


@register_lc
class PostOpConversation(_LC):
    lc_id = "21000"

    def setup(self) -> None:
        self.while_acting((ActionKind.ULT,), "Post-Op Conversation", {S.HEAL_PCT: self.p(1)})


@register_lc
class SharedFeeling(_LC):
    lc_id = "21007"

    def setup(self) -> None:
        def on_skill(ev: E.Ev) -> None:
            if self.mine(ev.action) and ev.action.kind == ActionKind.SKILL:
                for c in self.battle.team:
                    if c.alive:
                        self.battle.gain_energy(c, self.p(1))

        self.on(E.ACTION_START, on_skill)


@register_lc
class PerfectTiming(_LC):
    lc_id = "21014"

    def setup(self) -> None:
        self.passive(
            "Perfect Timing",
            dyn=lambda m, k, e: min(self.p(2), self.p(1) * self.char.stat(S.EFFECT_RES)),
            dyn_keys={S.HEAL_PCT},
        )


@register_lc
class QuidProQuo(_LC):
    lc_id = "21021"

    def setup(self) -> None:
        def turn_start(ev: E.Ev) -> None:
            if ev.entity is not self.char:
                return
            cands = [
                c
                for c in self.battle.team
                if c.alive and c is not self.char and c.max_energy > 0 and c.energy < self.p(0) * c.max_energy
            ]
            if cands:
                self.battle.gain_energy(self.battle.rng.choice(cands), self.p(1))

        self.on(E.TURN_START, turn_start)


@register_lc
class WarmthShortensColdNights(_LC):
    lc_id = "21028"

    def setup(self) -> None:
        def on_use(ev: E.Ev) -> None:
            if self.mine(ev.action) and ev.action.kind in (ActionKind.BASIC, ActionKind.SKILL):
                for a in self.team(memosprites=True):
                    self.heal(a, self.p(1) * a.max_hp)

        self.on(E.ACTION_START, on_use)


@register_lc
class WhatIsReal(_LC):
    lc_id = "21035"

    def setup(self) -> None:
        def after_basic(ev: E.Ev) -> None:
            if self.mine(ev.action) and ev.action.kind == ActionKind.BASIC:
                self.heal(self.char, self.p(1) * self.char.max_hp + self.p(2))

        self.on(E.ACTION_END, after_basic)


@register_lc
class DreamsMontage(_LC):
    lc_id = "21048"

    def setup(self) -> None:
        self.turn, self.used = -1, 0

        def attack_end(ev: E.Ev) -> None:
            act = ev.attack
            if not self.mine(act) or not any(t.broken for t in act.attacked):
                return
            if self.turn != self.battle.turns:  # "per turn": any unit's turn
                self.turn, self.used = self.battle.turns, 0
            if self.used < int(self.p(2)):
                self.used += 1
                self.battle.gain_energy(self.char, self.p(1))

        self.on(E.ATTACK_END, attack_end)


@register_lc
class UntoTomorrowsMorrow(_LC):
    lc_id = "21055"

    def setup(self) -> None:
        # every ally whose own current HP% >= threshold deals more DMG
        self.passive(
            "Unto Tomorrow's Morrow",
            scope=_ally,
            dyn_keys={S.DMG_PCT},
            dyn=lambda m, k, e: self.p(2) if e.hp_ratio >= self.p(1) - 1e-9 else 0.0,
        )


@register_lc
class HeyOverHere(_LC):
    lc_id = "22001"

    def setup(self) -> None:
        self.on(
            E.ACTION_START,
            lambda ev: self.mine(ev.action)
            and ev.action.kind == ActionKind.SKILL
            and self.buff(
                self.char, Modifier("Hey, Over Here", stats={S.HEAL_PCT: self.p(1)}, duration=int(self.p(2)))
            ),
        )


@register_lc
class EchoesOfTheCoffin(_LC):
    lc_id = "23008"

    def setup(self) -> None:
        def attack_end(ev: E.Ev) -> None:
            act = ev.attack
            if self.mine(act):
                n = min(len(act.attacked), int(self.p(3)))
                if n:
                    self.battle.gain_energy(self.char, self.p(2) * n)

        def after_ult(ev: E.Ev) -> None:
            if self.mine(ev.action) and ev.action.kind == ActionKind.ULT:
                # memosprites have their own SPD, so they get their own copy
                for a in self.team(memosprites=True):
                    self.buff(a, Modifier("Echoes of the Coffin", stats={S.SPD_FLAT: self.p(1)}, duration=1))

        self.on(E.ATTACK_END, attack_end)
        self.on(E.ACTION_END, after_ult)


@register_lc
class TimeWaitsForNoOne(_LC):
    lc_id = "23013"

    def setup(self) -> None:
        self.recorded = 0.0
        self.last_turn = -1

        def on_hp(ev: E.Ev) -> None:
            if self.healed_by_me(ev):
                self.recorded += ev.delta  # effective healing (the engine does not report overhealing)

        def attack_end(ev: E.Ev) -> None:
            act = ev.attack
            if act.owner.side != Side.ALLY or self.recorded <= 0 or self.last_turn == self.battle.turns:
                return
            targets = self.enemies(act.attacked)
            if not targets:
                return
            self.last_turn = self.battle.turns
            amount, self.recorded = self.recorded * self.p(2), 0.0  # the record is spent by the DMG
            # "not affected by other buffs": no DMG% / CRIT; enemy DEF/RES/vulnerability still apply
            self.battle.special_damage(
                self.char,
                self.battle.rng.choice(targets),
                self.char.element,
                amount,
                tags=(DmgTag.ADDITIONAL,),
                label="Time Waits for No One",
                use_break_effect=False,
            )

        self.on(E.HP_CHANGED, on_hp)
        self.on(E.ATTACK_END, attack_end)


@register_lc
class NightOfFright(_LC):
    lc_id = "23017"

    def setup(self) -> None:
        def on_ult(ev: E.Ev) -> None:
            if ev.entity.side != Side.ALLY:
                return
            team = [a for a in self.team(memosprites=True) if a.max_hp > 0]
            if team:
                t = min(team, key=lambda a: a.hp_ratio)
                self.heal(t, self.p(1) * t.max_hp)

        def on_hp(ev: E.Ev) -> None:
            # note: the engine only reports heals that restore HP (healing a full-HP ally is not seen)
            if self.healed_by_me(ev):
                self.buff(
                    ev.entity,
                    Modifier(
                        "Night of Fright",
                        stats={S.ATK_PCT: self.p(2)},
                        stacking=Stacking.STACK,
                        max_stacks=int(self.p(3)),
                        duration=int(self.p(4)),
                    ),
                )

        self.on(E.ULT_USED, on_ult)
        self.on(E.HP_CHANGED, on_hp)


@register_lc
class ScentAloneStaysTrue(_LC):
    lc_id = "23032"

    def setup(self) -> None:
        def woefree(mod: Modifier, key: str, ent: Entity) -> float:
            boosted = self.char.stat(S.BREAK_EFFECT) >= self.p(2) - 1e-9
            return self.p(1) + (self.p(3) if boosted else 0.0)

        def attack_end(ev: E.Ev) -> None:
            act = ev.attack
            if self.mine(act) and act.kind == ActionKind.ULT:
                for t in self.enemies(act.attacked):
                    self.buff(
                        t,
                        Modifier(
                            "Woefree", kind=ModKind.DEBUFF, duration=int(self.p(4)), dyn=woefree, dyn_keys={S.VULN}
                        ),
                    )

        self.on(E.ATTACK_END, attack_end)


# ===================================================================== Remembrance
@register_lc
class TimeWovenIntoGold(_LC):
    lc_id = "23036"

    def setup(self) -> None:
        def basic_bonus(mod: Modifier, key: str, ent: Entity) -> float:
            return self.p(2) * mod.stacks if mod.stacks >= mod.max_stacks else 0.0

        def attack_end(ev: E.Ev) -> None:
            actor = ev.attack.actor
            if actor is self.char or self.is_my_memo(actor):
                # held by the wearer; the memosprite syncs the wearer's CRIT DMG
                self.buff(
                    self.char,
                    Modifier(
                        "Brocade",
                        stats={S.CRIT_DMG: self.p(3)},
                        stacking=Stacking.STACK,
                        max_stacks=int(self.p(1)),
                        tick=Tick.NONE,
                        dyn=basic_bonus,
                        dyn_keys={f"{S.DMG_PCT}:{DmgTag.BASIC}"},
                    ),
                )

        self.on(E.ATTACK_END, attack_end)


@register_lc
class MakeFarewellsMoreBeautiful(_LC):
    lc_id = "23040"

    def setup(self) -> None:
        self.advance_ready = True

        def on_hp(ev: E.Ev) -> None:
            ent, cur = ev.entity, self.battle.current_turn
            if ev.delta >= 0 or not (ent is self.char or self.is_my_memo(ent)):
                return
            if cur is self.char or self.is_my_memo(cur):
                self.buff(self.char, Modifier("Death Flower", stats={S.DEF_IGNORE: self.p(1)}, duration=int(self.p(2))))

        def gone(memo: Summon) -> None:
            if self.advance_ready:
                self.advance_ready = False
                self.battle.advance(self.char, self.p(3))

        def on_ult(ev: E.Ev) -> None:
            if self.mine(ev.action) and ev.action.kind == ActionKind.ULT:
                self.advance_ready = True

        self.on(E.HP_CHANGED, on_hp)
        self.on(E.ACTION_START, on_ult)
        _MemoWatch(self, on_gone=gone)


@register_lc
class LongMayRainbowsAdornTheSky(_LC):
    lc_id = "23042"

    def setup(self) -> None:
        self.consumed = 0.0

        def on_use(ev: E.Ev) -> None:
            act = ev.action
            if self.mine(act) and act.kind in (ActionKind.BASIC, ActionKind.SKILL, ActionKind.ULT):
                for a in self.team(memosprites=True):
                    self.consumed += self.battle.lose_hp(a, self.p(1) * a.hp, self.char)

        def memo_attack(ev: E.Ev) -> None:
            act = ev.attack
            if not self.is_my_memo(act.actor) or self.consumed <= 0:
                return
            targets = self.enemies(act.attacked)
            if not targets:
                return
            target = act.target if isinstance(act.target, Enemy) and act.target in targets else targets[0]
            amount, self.consumed = self.consumed * self.p(5), 0.0
            self.battle.additional_damage(
                act.actor,
                target,
                {},
                flat=amount,
                tags=(DmgTag.ADDITIONAL, DmgTag.MEMOSPRITE),
                credited=self.char,
                label="Long May Rainbows Adorn the Sky",
            )

        def memo_skill(ev: E.Ev) -> None:
            act = ev.action
            if self.is_my_memo(act.actor) and _is_memo_skill(act):
                for e in self.enemies():
                    self.buff(
                        e,
                        Modifier(
                            "Long May Rainbows",
                            stats={S.VULN: self.p(3)},
                            kind=ModKind.DEBUFF,
                            duration=int(self.p(4)),
                            key="Long May Rainbows Adorn the Sky",
                        ),
                    )

        self.on(E.ACTION_START, on_use)
        self.on(E.ATTACK_END, memo_attack)
        self.on(E.ACTION_START, memo_skill)


@register_lc
class ToEvernightsStars(_LC):
    lc_id = "23049"

    def setup(self) -> None:
        def memo_ability(ev: E.Ev) -> None:
            if self.is_my_memo(ev.action.actor):
                # "Noctis": DMG +X% for the wearer (synced to the memosprite) while held
                self.passive("Noctis", {S.DMG_PCT: self.p(2)})

        def before_hit(ev: E.Ev) -> None:
            h = ev.hit
            if (
                _is_memosprite(h.attacker)
                and h.attacker.side == Side.ALLY
                and self.char.has_mod("Noctis")
                and not h.extra.get("lc:noctis")
            ):  # "effects of the same type cannot stack"
                h.add("lc:noctis", 1.0)
                h.add(S.DEF_IGNORE, self.p(1))

        self.on(E.ACTION_START, memo_ability)
        self.on(E.BEFORE_HIT, before_hit)
        _MemoWatch(self, on_gone=lambda memo: self.battle.gain_energy(self.char, self.p(3)))


@register_lc
class ThisLoveForever(_LC):
    lc_id = "23052"

    def setup(self) -> None:
        def boost(mod: Modifier) -> float:
            h = mod.holder
            both = h is not None and h.has_mod("Blank") and h.has_mod("Verse")
            return 1.0 + (self.p(3) if both else 0.0)

        def memo_skill(ev: E.Ev) -> None:
            act = ev.action
            memo, t = act.actor, act.target
            if not self.is_my_memo(memo) or not _is_memo_skill(act):
                return
            # both states are held by the memosprite (removed with it) and act as team-wide fields
            if t is not None and t.side == Side.ALLY:
                self.passive(
                    "Blank", target=memo, scope=_enemy, dyn_keys={S.VULN}, dyn=lambda m, k, e: self.p(2) * boost(m)
                )
            elif (t is not None and t.side == Side.ENEMY) or act.attacked:
                self.passive(
                    "Verse", target=memo, scope=_ally, dyn_keys={S.CRIT_DMG}, dyn=lambda m, k, e: self.p(1) * boost(m)
                )

        self.on(E.ACTION_END, memo_skill)


@register_lc
class RiseAndSing(_LC):
    lc_id = "23063"

    def setup(self) -> None:
        def start(ev: E.Ev) -> None:
            self.battle.advance(self.char, self.p(1))
            self.buff(
                self.char, Modifier("New Melody", stats={S.SPD_PCT: self.p(2)}, duration=int(self.p(3)), scope=_ally)
            )

        def after_ult(ev: E.Ev) -> None:
            if self.mine(ev.action) and ev.action.kind == ActionKind.ULT:
                self.battle.gain_sp(1, self.char)  # "recovers 1 Skill Point" (not a parameter)

        self.on(E.BATTLE_START, start)
        self.on(E.ACTION_END, after_ult)


@register_lc
class MemorysCurtainNeverFalls(_LC):
    lc_id = "24005"

    def setup(self) -> None:
        def after_skill(ev: E.Ev) -> None:
            if self.mine(ev.action) and ev.action.kind == ActionKind.SKILL:
                for c in self.team():
                    self.buff(
                        c,
                        Modifier("Memory's Curtain Never Falls", stats={S.DMG_PCT: self.p(1)}, duration=int(self.p(2))),
                    )

        self.on(E.ACTION_END, after_skill)


@register_lc
class VictoryInABlink(_LC):
    lc_id = "21050"

    def setup(self) -> None:
        def memo_ability(ev: E.Ev) -> None:
            act = ev.action
            if self.is_my_memo(act.actor) and act.target is not None and act.target.side == Side.ALLY:
                for c in self.team():
                    self.buff(c, Modifier("Victory In a Blink", stats={S.DMG_PCT: self.p(1)}, duration=int(self.p(2))))

        self.on(E.ACTION_START, memo_ability)


@register_lc
class GeniusesGreetings(_LC):
    lc_id = "21051"

    def setup(self) -> None:
        self.on(
            E.ACTION_END,
            lambda ev: self.mine(ev.action)
            and ev.action.kind == ActionKind.ULT
            and self.buff(
                self.char,
                Modifier(
                    "Geniuses' Greetings", stats={f"{S.DMG_PCT}:{DmgTag.BASIC}": self.p(1)}, duration=int(self.p(2))
                ),
            ),
        )


@register_lc
class SweatNowCryLess(_LC):
    lc_id = "21052"

    def setup(self) -> None:
        self.passive(
            "Sweat Now, Cry Less",
            dyn_keys={S.DMG_PCT},
            dyn=lambda m, k, e: self.p(1) if _memosprite_of(self.char) else 0.0,
        )


@register_lc
class TheStorysNextPage(_LC):
    lc_id = "21054"

    def setup(self) -> None:
        self.on(
            E.ATTACK_END,
            lambda ev: self.is_my_memo(ev.attack.actor)
            and self.buff(
                self.char, Modifier("The Story's Next Page", stats={S.HEAL_PCT: self.p(1)}, duration=int(self.p(2)))
            ),
        )


@register_lc
class TheFlowerRemembers(_LC):
    lc_id = "21057"

    def setup(self) -> None:
        def before_hit(ev: E.Ev) -> None:
            if self.is_my_memo(ev.hit.attacker):
                ev.hit.add(S.CRIT_DMG, self.p(1))

        self.on(E.BEFORE_HIT, before_hit)


@register_lc
class FlyIntoAPinkTomorrow(_LC):
    lc_id = "22006"

    def setup(self) -> None:
        if not self.char.data.get("name", "").startswith("Trailblazer") or self.char.path != Path.REMEMBRANCE:
            return
        self.passive("Fly Into a Pink Tomorrow", {S.DMG_PCT: self.p(1)}, scope=_ally, key="Fly Into a Pink Tomorrow")
        m = re.search(r'"([^"]+)"', self.data.get("desc") or "")  # the Enhanced Basic ATK's name
        enhanced = m.group(1) if m else ""

        def before_hit(ev: E.Ev) -> None:
            act = ev.hit.action
            if (
                ev.hit.attacker is self.char
                and act is not None
                and enhanced
                and (act.label == enhanced or (act.skill or {}).get("name") == enhanced)
            ):
                ev.hit.add(S.DMG_PCT, self.p(2))

        self.on(E.BEFORE_HIT, before_hit)


@register_lc
class Shadowburn(_LC):
    lc_id = "20021"

    def setup(self) -> None:
        self.done = False

        def summoned(memo: Summon) -> None:
            if not self.done:
                self.done = True
                self.battle.gain_sp(int(self.p(0)), self.char)
                self.battle.gain_energy(self.char, self.p(1))

        _MemoWatch(self, on_summon=summoned)


@register_lc
class Reminiscence(_LC):
    lc_id = "20022"

    def setup(self) -> None:
        def turn_start(ev: E.Ev) -> None:
            if self.is_my_memo(ev.entity):
                # "the wearer and memosprite each gain 1 stack": the memosprite syncs the wearer's DMG%,
                # so one stack on the wearer covers both
                self.buff(
                    self.char,
                    Modifier(
                        "Commemoration",
                        stats={S.DMG_PCT: self.p(0)},
                        stacking=Stacking.STACK,
                        max_stacks=int(self.p(1)),
                        tick=Tick.NONE,
                    ),
                )

        self.on(E.TURN_START, turn_start)
        _MemoWatch(self, on_gone=lambda memo: self.battle.remove_named(self.char, "Commemoration"))


# ========================================================================= Elation
@register_lc
class Sneering(_LC):
    lc_id = "20023"

    def setup(self) -> None:
        # "Aha Instant" comes from the optional Elation system (inert without it)
        self.on(AHA_INSTANT_START, lambda ev: self.passive("Sneering", {ELATION: self.p(0)}))
        self.on(AHA_INSTANT_END, lambda ev: self.battle.remove_named(self.char, "Sneering"))


@register_lc
class LingeringTear(_LC):
    lc_id = "20024"

    def setup(self) -> None:
        # Punchline is the team counter of the optional Elation system (0 without it)
        self.passive(
            "Lingering Tear",
            dyn_keys={S.CRIT_DMG},
            dyn=lambda m, k, e: self.p(1) if _punchline(self.battle) >= self.p(0) - 1e-9 else 0.0,
        )


@register_lc
class MushyShroomysAdventures(_LC):
    lc_id = "21064"

    def setup(self) -> None:
        def on_use(ev: E.Ev) -> None:
            if ev.action.owner is self.char and _is_elation_skill(ev.action):
                for e in self.enemies():
                    self.buff(
                        e,
                        Modifier(
                            "Mushy Shroomy's Adventures",
                            stats={VULN_ELATION: self.p(1)},
                            kind=ModKind.DEBUFF,
                            duration=int(self.p(2)),
                        ),
                    )

        self.on(E.ACTION_START, on_use)


@register_lc
class TodaysGoodLuck(_LC):
    lc_id = "21065"

    def setup(self) -> None:
        self.on(
            E.ACTION_START,
            lambda ev: ev.action.owner is self.char
            and _is_elation_skill(ev.action)
            and self.buff(
                self.char,
                Modifier(
                    "Today's Good Luck",
                    stats={ELATION: self.p(1)},
                    stacking=Stacking.STACK,
                    max_stacks=int(self.p(2)),
                    tick=Tick.NONE,
                ),
            ),
        )


@register_lc
class ALittleGetaway(_LC):
    lc_id = "21066"

    def setup(self) -> None:
        def before_hit(ev: E.Ev) -> None:
            h = ev.hit
            if h.credited is self.char and _is_elation_skill(h.action or self.battle.current_action):
                h.add(S.DEF_IGNORE, self.p(1))

        self.on(E.BEFORE_HIT, before_hit)


@register_lc
class TomorrowTogether(_LC):
    lc_id = "22007"

    def setup(self) -> None:
        def after_ult(ev: E.Ev) -> None:
            if self.mine(ev.action) and ev.action.kind == ActionKind.ULT:
                for c in self.team():
                    self.buff(c, Modifier("Tomorrow, Together", stats={ELATION: self.p(1)}, duration=int(self.p(2))))

        self.on(E.ACTION_END, after_ult)


@register_lc
class DazzledByAFloweryWorld(_LC):
    lc_id = "23053"

    def setup(self) -> None:
        # "Light Cone effects of the same type cannot stack": only the first wearer raises the SP limit
        first = next(c for c in self.battle.team if isinstance(c.light_cone, DazzledByAFloweryWorld))
        if first is self.char:
            n = sum(1 for c in self.battle.team if c.path == Path.ELATION)
            self.battle.max_sp += int(min(n * self.p(1), self.p(2)))
        self.turn, self.spent = -1, 0

        def on_sp(ev: E.Ev) -> None:
            # not modelled: consuming "Thrill" (Elation mechanic) also counts as consuming SP
            if ev.delta >= 0 or ev.entity is not self.char:
                return
            n = -int(ev.delta)
            self.buff(
                self.char,
                Modifier(
                    "Dazzled by a Flowery World",
                    stats={DEF_IGNORE_ELATION: self.p(5)},
                    stacks=min(n, int(self.p(4))),
                    stacking=Stacking.STACK,
                    max_stacks=int(self.p(4)),
                    tick=Tick.NONE,
                ),
            )
            if self.turn != self.battle.turns:
                self.turn, self.spent = self.battle.turns, 0
            self.spent += n
            if self.spent >= self.p(6):
                self.passive("Stream Promo", {ELATION: self.p(3)}, scope=_ally, key="Stream Promo")

        self.on(E.SP_CHANGED, on_sp)


@register_lc
class WhenSheDecidedToSee(_LC):
    lc_id = "23054"

    def setup(self) -> None:
        def great_fortune() -> None:
            self.buff(
                self.char,
                Modifier(
                    "Great Fortune",
                    stats={S.CRIT_RATE: self.p(1), S.CRIT_DMG: self.p(2)},
                    duration=int(self.p(3)),
                    scope=_ally,
                    dyn=lambda m, k, e: self.p(4) if e is self.char else 0.0,
                    dyn_keys={S.ERR},
                ),
            )

        def on_ult(ev: E.Ev) -> None:
            act = ev.action
            kit = self.char.kit
            on_ally = (act.target is not None and act.target.side == Side.ALLY) or getattr(
                kit, "ult_targets_ally", False
            )
            if self.mine(act) and act.kind == ActionKind.ULT and on_ally:
                great_fortune()

        self.on(E.BATTLE_START, lambda ev: great_fortune())
        self.on(E.ACTION_START, on_ult)
        self.on(E.WAVE_START, lambda ev: self.battle.gain_energy(self.char, self.p(5), fixed=True))


@register_lc
class ColorsForTomorrow(_LC):
    lc_id = "23055"

    def setup(self) -> None:
        def after_elation(ev: E.Ev) -> None:
            act = ev.action
            if act.owner is not self.char or not _is_elation_skill(act):
                return
            on_allies = act.target is not None and act.target.side == Side.ALLY
            if not on_allies and (act.target is not None or (act.skill or {}).get("effect") not in _ALLY_EFFECTS):
                return  # only an Elation Skill used on all allies
            for e in self.enemies():
                self.buff(
                    e,
                    Modifier(
                        "Colors for Tomorrow", stats={S.VULN: self.p(3)}, kind=ModKind.DEBUFF, duration=int(self.p(2))
                    ),
                )
            self.battle.gain_energy(self.char, self.p(1), fixed=True)
            for a in self.team(memosprites=True):
                self.heal(a, self.p(4) * self.char.defense)

        self.on(E.ACTION_END, after_elation)


@register_lc
class WelcomeToTheCosmicCity(_LC):
    lc_id = "23057"

    def setup(self) -> None:
        self.passive("Welcome to the Cosmic City", {DEF_IGNORE_ELATION: self.p(1)})
        self.ready, self.basics = True, 0

        def on_end(ev: E.Ev) -> None:
            act = ev.action
            if not self.mine(act):
                return
            if act.kind == ActionKind.BASIC and not self.ready:
                self.basics += 1
                if self.basics >= self.p(3):
                    self.ready, self.basics = True, 0
            on_self = act.target is self.char or (act.target is None and (act.skill or {}).get("effect") == "Enhance")
            elation = getattr(self.battle, "elation", None)
            if act.kind == ActionKind.ULT and on_self and self.ready and elation is not None:
                self.ready = False
                elation.gain(int(self.p(2)), self.char)  # Punchline (optional Elation system)

        self.on(E.ACTION_END, on_end)


@register_lc
class UntilTheFlowersBloomAgain(_LC):
    lc_id = "23058"

    def setup(self) -> None:
        excess = min(max(0.0, self.char.max_energy - self.p(4)), self.p(6))
        self.passive("Until the Flowers Bloom Again", {S.ERR: self.p(3) + math.floor(excess / 10 + 1e-9) * self.p(5)})

        def on_use(ev: E.Ev) -> None:
            if ev.action.owner is self.char and _is_elation_skill(ev.action):
                for e in self.enemies():
                    self.buff(
                        e,
                        Modifier(
                            "Until the Flowers Bloom Again",
                            stats={S.VULN: self.p(1)},
                            kind=ModKind.DEBUFF,
                            duration=int(self.p(2)),
                            key="Until the Flowers Bloom Again",
                        ),
                    )

        self.on(E.ACTION_START, on_use)


@register_lc
class SummerRidesTheSurf(_LC):
    lc_id = "23064"

    def setup(self) -> None:
        self.last: str | None = None
        self.uses = 0

        def on_use(ev: E.Ev) -> None:
            act = ev.action
            if act.owner is not self.char or not _is_elation_skill(act):
                return
            self.buff(self.char, Modifier("Updraft", stats={S.SPD_PCT: self.p(1)}, tick=Tick.NONE))
            sid = str((act.skill or {}).get("id") or act.label)
            if self.last is not None and sid != self.last:
                self.buff(self.char, Modifier("Uptrend", stats={ELATION: self.p(2)}, tick=Tick.NONE))
            self.last = sid
            self.uses += 1
            if self.uses >= self.p(3):
                self.uses = 0
                self.battle.gain_sp(1, self.char)

        self.on(E.ACTION_START, on_use)
        self.on(E.WAVE_START, lambda ev: self.battle.gain_sp(1, self.char))


@register_lc
class ElationBrimmingWithBlessings(_LC):
    lc_id = "24006"

    def setup(self) -> None:
        def after_use(ev: E.Ev) -> None:
            act = ev.action
            t = act.target
            if self.mine(act) and act.kind in (ActionKind.SKILL, ActionKind.ULT) and isinstance(t, Character):
                self.buff(
                    t, Modifier("Elation Brimming With Blessings", stats={ELATION: self.p(1)}, duration=int(self.p(2)))
                )

        self.on(E.ACTION_END, after_use)
