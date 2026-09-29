"""Conditional effects of the Hunt (Rogue), Destruction (Warrior) and Erudition (Mage) light cones.

The always-on stats of a light cone (its "properties") are applied from the data by
the build code; the classes below only add what depends on combat state. Every
number is read with ``self.p(i)`` (``#i+1`` in the description text); the few
module-level constants are numbers written literally in the description.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING, Any

from .. import events as E
from .. import stats as S
from ..entities import Character, Enemy, Entity
from ..enums import ActionKind, DmgTag, Side
from ..equipment import LightCone, register_lc
from ..modifiers import Modifier, ModKind, Stacking, Tick, hidden

if TYPE_CHECKING:
    from ..battle import Action, Hit

# numbers that are written literally in the descriptions (not parameters in the data)
MILKY_WAY_MAX_ENEMIES = 5  # Night on the Milky Way: "up to 5 stacks"
RAITON_BASICS = 2  # Ninjutsu Inscription: "After using 2 Basic ATKs"
VEIL_SP = 1  # Into the Unreachable Veil: "recovers 1 Skill Point"
SAIL_TURNS = 2  # A Star That Lights the Night: "lasting for 2 turns"
ETERNAL_MAX_STACKS = 5  # Eternal Calculus: "can stack up to 5 times"
COSMOS_MIN_WEAK = 2  # The Day The Cosmos Fell: "at least 2 attacked enemies"
IN_THE_NIGHT_SPD = 100  # In the Night: "SPD that exceeds 100"
SILENCE_MAX_ENEMIES = 2  # Only Silence Remains: "2 or fewer enemies"
FIREDANCE_TURNS = 2  # Dance at Sunset: "lasting for 2 turns"

# action tag a kit can put on an Assist Skill action (the engine has no dedicated ActionKind)
ASSIST = "assist"
ATTACK_KINDS = (ActionKind.BASIC, ActionKind.SKILL, ActionKind.ULT)


def _ally(e: Entity) -> bool:
    return e.side == Side.ALLY


def _enemy(e: Entity) -> bool:
    return e.side == Side.ENEMY


def _has(h: Hit, *tags: str) -> bool:
    return not h.tags.isdisjoint(tags)


class _LC(LightCone):
    """Shared helpers (same conventions as ``hsrsim/gear/relics.py``)."""

    def __init__(self, *args: Any, **kw: Any) -> None:
        super().__init__(*args, **kw)
        self._last_turn: dict[str, int] = {}

    def passive(self, name: str, stats: dict[str, float] | None = None, **kw: Any) -> Modifier:
        return self.battle.apply(hidden(name, stats, **kw), self.char, self.char)

    def buff(self, mod: Modifier, target: Entity | None = None) -> Modifier:
        return self.battle.apply(mod, target or self.char, self.char)

    def used(self, act: Action, *kinds: ActionKind) -> bool:
        """``act`` belongs to the wearer (incl. its summons) and is one of ``kinds`` (any kind if empty)."""
        return act.owner is self.char and (not kinds or act.kind in kinds)

    def on_use(self, kinds: tuple[ActionKind, ...], fn: Callable[[Action], Any], *, start: bool = False) -> None:
        """Call ``fn(action)`` when the wearer uses one of ``kinds`` (ACTION_START if ``start`` else ACTION_END)."""
        event = E.ACTION_START if start else E.ACTION_END
        self.on(event, lambda ev: self.used(ev.action, *kinds) and fn(ev.action))

    def on_my_hit(self, fn: Callable[[Hit], Any]) -> None:
        """BEFORE_HIT listener restricted to the wearer's hits (incl. its summons' hits)."""
        self.on(E.BEFORE_HIT, lambda ev: ev.hit.credited is self.char and fn(ev.hit))

    def hit_bonus(self, cond: Callable[[Hit], bool], key: str, value: float | Callable[[Hit], float]) -> None:
        """Hit-local bonus on the wearer's hits for which ``cond(hit)`` holds (counted once per hit)."""

        def before_hit(h: Hit) -> None:
            if cond(h):
                v = value(h) if callable(value) else value
                if v:
                    h.add(key, v)

        self.on_my_hit(before_hit)

    def during(self, act: Action, name: str, stats: dict[str, float]) -> Modifier:
        """Hidden modifier that lasts until ``act`` ends ("DMG dealt by this attack")."""
        mod = self.passive(name, stats)

        def end(ev: E.Ev) -> None:
            if ev.action is act:
                self.battle.remove_modifier(mod)

        mod.listen(E.ACTION_END, end)
        return mod

    def on_kill(self, fn: Callable[[], Any]) -> None:
        self.on(E.KILL, lambda ev: ev.killer is self.char and fn())

    def on_own_turn(self, event: str, fn: Callable[[], Any]) -> None:
        """TURN_START / TURN_END of the wearer."""
        self.on(event, lambda ev: ev.entity is self.char and fn())

    def on_attacked(self, fn: Callable[[], Any]) -> None:
        """The wearer is attacked by an enemy."""
        self.on(E.ALLY_ATTACKED, lambda ev: self.char in ev.targets and fn())

    def after_my_attack(self, fn: Callable[[Action], Any]) -> None:
        self.on(E.ATTACK_END, lambda ev: self.used(ev.attack) and fn(ev.attack))

    def when(self, cond: Callable[[], bool], fn: Callable[[], Any]) -> Callable[..., None]:
        """Event callback running ``fn()`` if ``cond()`` holds."""

        def cb(*_: Any) -> None:
            if cond():
                fn()

        return cb

    def once_per_turn(self, tag: str = "") -> bool:
        """True the first time it is asked (per ``tag``) during the current turn."""
        if self._last_turn.get(tag) == self.battle.turns:
            return False
        self._last_turn[tag] = self.battle.turns
        return True

    def cooling(self, name: str) -> bool:
        return self.char.has_mod(name)

    def start_cooldown(self, name: str, turns: int) -> None:
        # "once every N turns": the turn in which it triggered counts as the first of the N
        self.buff(Modifier(name, duration=turns, kind=ModKind.OTHER, dispellable=False, skip_first_tick=False))

    def crit(self, h: Hit) -> bool:
        """Did ``h`` crit? In expected-crit mode the outcome is rolled with the hit's CRIT Rate."""
        if not h.can_crit:
            return False
        if h.crit is not None:
            return h.crit
        cr = h.crit_override[0] if h.crit_override else h.attacker.stat_q(S.CRIT_RATE, h.quals, h.extra)
        return self.battle.rng.random() < cr

    def ult_energy_consumed(self) -> float:
        # approximation: the engine does not report the Energy an Ultimate consumed (kits zero it)
        return self.char.max_energy

    def remove_stacks(self, name: str, n: int = 1) -> None:
        m = self.char.get_mod(name)
        if m is not None:
            m.stacks -= n
            if m.stacks <= 0:
                self.battle.remove_modifier(m)


# ====================================================================== Erudition (Mage)
@register_lc
class NightOnTheMilkyWay(_LC):
    lc_id = "23000"

    def setup(self) -> None:
        def atk(m: Modifier, k: str, e: Entity) -> float:
            return self.p(1) * min(MILKY_WAY_MAX_ENEMIES, len(self.battle.alive_enemies()))

        self.passive("Night on the Milky Way", dyn=atk, dyn_keys={S.ATK_PCT})
        self.on(
            E.BREAK,
            lambda ev: self.buff(Modifier("Night on the Milky Way (Break)", stats={S.DMG_PCT: self.p(0)}, duration=1)),
        )


@register_lc
class BeforeDawn(_LC):
    lc_id = "23010"

    def setup(self) -> None:
        self.hit_bonus(lambda h: _has(h, DmgTag.SKILL, DmgTag.ULT), S.DMG_PCT, self.p(1))
        self.on_use((ActionKind.SKILL, ActionKind.ULT), lambda act: self.buff(Modifier("Somnus Corpus")))

        def on_fua(act: Action) -> None:
            m = self.char.get_mod("Somnus Corpus")
            if m is not None:
                self.battle.remove_modifier(m)
                self.during(act, "Somnus Corpus (consumed)", {f"{S.DMG_PCT}:{DmgTag.FUA}": self.p(2)})

        self.on_use((ActionKind.FUA,), on_fua, start=True)


@register_lc
class AnInstantBeforeAGaze(_LC):
    lc_id = "23018"

    def setup(self) -> None:
        # only affects Ultimate DMG, so a permanent Ultimate DMG bonus is equivalent
        bonus = self.p(1) * min(self.char.max_energy, self.p(2))
        self.passive("An Instant Before A Gaze", {f"{S.DMG_PCT}:{DmgTag.ULT}": bonus})


@register_lc
class YetHopeIsPriceless(_LC):
    lc_id = "23028"

    def setup(self) -> None:
        def fua_bonus(m: Modifier, k: str, e: Entity) -> float:
            steps = int((self.char.stat(S.CRIT_DMG) - self.p(1)) / self.p(2) + 1e-9)
            return self.p(3) * max(0, min(int(self.p(4)), steps))

        self.passive("Yet Hope Is Priceless", dyn=fua_bonus, dyn_keys={f"{S.DMG_PCT}:{DmgTag.FUA}"})

        name = "Yet Hope Is Priceless (DEF ignore)"

        def grant(*_: Any) -> None:
            self.buff(Modifier(name, duration=int(self.p(6))))

        self.on(E.BATTLE_START, grant)
        self.on_use((ActionKind.BASIC,), grant)
        self.hit_bonus(lambda h: self.char.has_mod(name) and _has(h, DmgTag.ULT, DmgTag.FUA), S.DEF_IGNORE, self.p(5))


@register_lc
class NinjutsuInscriptionDazzlingEvilbreaker(_LC):
    lc_id = "23033"

    def setup(self) -> None:
        self.on(E.BATTLE_START, lambda ev: self.battle.gain_energy(self.char, self.p(1)))

        def raiton(act: Action) -> None:
            m = self.buff(Modifier("Raiton"))
            m.data["basics"] = 0

        def on_basic(act: Action) -> None:
            m = self.char.get_mod("Raiton")
            if m is None:
                return
            m.data["basics"] = m.data.get("basics", 0) + 1
            if m.data["basics"] >= RAITON_BASICS:
                self.battle.remove_modifier(m)
                self.battle.advance(self.char, self.p(2))

        self.on_use((ActionKind.ULT,), raiton)
        self.on_use((ActionKind.BASIC,), on_basic)


@register_lc
class IntoTheUnreachableVeil(_LC):
    lc_id = "23037"

    def setup(self) -> None:
        name = "Into the Unreachable Veil"
        self.on_use((ActionKind.ULT,), lambda act: self.buff(Modifier(name, duration=int(self.p(4)))), start=True)
        self.hit_bonus(lambda h: self.char.has_mod(name) and _has(h, DmgTag.SKILL, DmgTag.ULT), S.DMG_PCT, self.p(3))
        self.on_use(
            (ActionKind.ULT,),
            self.when(
                lambda: self.ult_energy_consumed() >= self.p(2) - 1e-9, lambda: self.battle.gain_sp(VEIL_SP, self.char)
            ),
        )


@register_lc
class LifeShouldBeCastToFlames(_LC):
    lc_id = "23041"

    def setup(self) -> None:
        self.on_own_turn(E.TURN_START, lambda: self.battle.gain_energy(self.char, self.p(4)))

        def implanted(h: Hit) -> bool:
            return any(m.source is self.char and any(t.startswith("weak:") for t in m.tags) for m in h.target.modifiers)

        self.hit_bonus(implanted, S.DMG_PCT, self.p(2))

        def shred(h: Hit) -> None:
            act = h.action
            if act is None or not h.target.alive:
                return
            done: set[int] = act.data.setdefault("lsbctf", set())
            if h.target.uid in done:
                return
            done.add(h.target.uid)
            mod = Modifier(
                "Life Should Be Cast to Flames",
                stats={S.DEF_REDUCTION: self.p(1)},
                duration=int(self.p(3)),
                kind=ModKind.DEBUFF,
                key="Life Should Be Cast to Flames",
            )
            self.battle.apply(mod, h.target, self.char)

        self.on_my_hit(shred)


@register_lc
class AStarThatLightsTheNight(_LC):
    lc_id = "23060"

    def setup(self) -> None:
        self.passive("A Star That Lights the Night", {S.DEF_IGNORE: self.p(6)})

        # the engine has no Assist Skill: kits opt in by tagging the action with ASSIST
        def ult_bonus(m: Modifier, k: str, e: Entity) -> float:
            return self.p(5) * m.stacks if m.stacks >= self.p(4) else 0.0

        def on_action(ev: E.Ev) -> None:
            act = ev.action
            if not self.used(act) or ASSIST not in act.tags:
                return
            self.battle.gain_energy(self.char, self.p(1))
            self.buff(
                Modifier(
                    "Sail",
                    stats={f"{S.DMG_PCT}:{ASSIST}": self.p(3)},
                    duration=SAIL_TURNS,
                    stacking=Stacking.STACK,
                    max_stacks=int(self.p(2)),
                    dyn=ult_bonus,
                    dyn_keys={f"{S.DMG_PCT}:{DmgTag.ULT}"},
                )
            )

        self.on(E.ACTION_START, on_action)


@register_lc
class FlickeringStars(_LC):
    lc_id = "23061"

    def setup(self) -> None:
        self.spent: dict[int, int] = {}

        def on_sp(ev: E.Ev) -> None:
            if ev.delta >= 0 or not isinstance(ev.entity, Character):
                return
            turn = self.battle.turns
            before = self.spent.get(turn, 0)
            self.spent = {turn: before - ev.delta}
            if before < self.p(2) <= self.spent[turn]:
                dur = int(self.p(3))
                self.buff(Modifier("Radiant Crown", stats={f"{S.DMG_PCT}:{DmgTag.SKILL}": self.p(1)}, duration=dur))
                self.buff(
                    Modifier(
                        "Radiant Crown (team)",
                        stats={S.DEF_IGNORE: self.p(4)},
                        duration=dur,
                        scope=_ally,
                        key="Radiant Crown",
                    )
                )

        self.on(E.SP_CHANGED, on_sp)


@register_lc
class EternalCalculus(_LC):
    lc_id = "24004"

    def setup(self) -> None:
        def after_attack(ev: E.Ev) -> None:
            act = ev.attack
            if not self.used(act):
                return
            n = len(act.attacked)
            self.battle.remove_named(self.char, "Eternal Calculus")  # lasts until the next attack
            if n:
                stacks = min(ETERNAL_MAX_STACKS, n)
                self.buff(Modifier("Eternal Calculus", stats={S.ATK_PCT: self.p(1)}, stacks=stacks, tick=Tick.NONE))
            if n >= self.p(2):
                self.buff(Modifier("Eternal Calculus SPD", stats={S.SPD_PCT: self.p(3)}, duration=int(self.p(4))))

        self.on(E.ATTACK_END, after_attack)


@register_lc
class TheBirthOfTheSelf(_LC):
    lc_id = "21006"

    def setup(self) -> None:
        self.passive("The Birth of the Self", {f"{S.DMG_PCT}:{DmgTag.FUA}": self.p(0)})
        self.hit_bonus(lambda h: _has(h, DmgTag.FUA) and h.target.hp_ratio <= self.p(1) + 1e-9, S.DMG_PCT, self.p(2))


@register_lc
class MakeTheWorldClamor(_LC):
    lc_id = "21013"

    def setup(self) -> None:
        self.passive("Make the World Clamor", {f"{S.DMG_PCT}:{DmgTag.ULT}": self.p(0)})
        self.on(E.BATTLE_START, lambda ev: self.battle.gain_energy(self.char, self.p(1)))


@register_lc
class GeniusesRepose(_LC):
    lc_id = "21020"

    def setup(self) -> None:
        self.on_kill(
            lambda: self.buff(Modifier("Geniuses' Repose", stats={S.CRIT_DMG: self.p(1)}, duration=int(self.p(2))))
        )


@register_lc
class TheSeriousnessOfBreakfast(_LC):
    lc_id = "21027"

    def setup(self) -> None:
        self.on_kill(
            lambda: self.buff(
                Modifier(
                    "The Seriousness of Breakfast",
                    stats={S.ATK_PCT: self.p(1)},
                    stacking=Stacking.STACK,
                    max_stacks=int(self.p(2)),
                    tick=Tick.NONE,
                )
            )
        )


@register_lc
class TodayIsAnotherPeacefulDay(_LC):
    lc_id = "21034"

    def setup(self) -> None:
        self.passive("Today Is Another Peaceful Day", {S.DMG_PCT: self.p(0) * min(self.char.max_energy, self.p(1))})


@register_lc
class TheDayTheCosmosFell(_LC):
    lc_id = "21040"

    def setup(self) -> None:
        def after_attack(ev: E.Ev) -> None:
            act = ev.attack
            if not self.used(act):
                return
            weak = sum(1 for t in act.attacked if t.is_weak_to(self.char.element))
            if weak >= COSMOS_MIN_WEAK:
                self.buff(Modifier("The Day The Cosmos Fell", stats={S.CRIT_DMG: self.p(1)}, duration=int(self.p(2))))

        self.on(E.ATTACK_END, after_attack)


@register_lc
class AfterTheCharmonyFall(_LC):
    lc_id = "21045"

    def setup(self) -> None:
        self.on_use(
            (ActionKind.ULT,),
            lambda act: self.buff(
                Modifier("After the Charmony Fall", stats={S.SPD_PCT: self.p(1)}, duration=int(self.p(2)))
            ),
        )


@register_lc
class ADreamScentedInWheat(_LC):
    lc_id = "21060"

    def setup(self) -> None:
        self.hit_bonus(lambda h: _has(h, DmgTag.ULT, DmgTag.FUA), S.DMG_PCT, self.p(1))


@register_lc
class TheGreatCosmicEnterprise(_LC):
    lc_id = "22004"

    def setup(self) -> None:
        def weakness_types(h: Hit) -> float:
            t = h.target
            types = {el.value for el in t.weaknesses}
            types |= {tag[5:] for m in t.modifiers if not m.removed for tag in m.tags if tag.startswith("weak:")}
            return self.p(1) * len(types)  # at most 7 = number of elements

        self.hit_bonus(lambda h: True, S.DMG_PCT, weakness_types)


@register_lc
class DataBank(_LC):
    lc_id = "20006"

    def setup(self) -> None:
        self.passive("Data Bank", {f"{S.DMG_PCT}:{DmgTag.ULT}": self.p(0)})


@register_lc
class Passkey(_LC):
    lc_id = "20013"

    def setup(self) -> None:
        self.on_use(
            (ActionKind.SKILL,), self.when(self.once_per_turn, lambda: self.battle.gain_energy(self.char, self.p(0)))
        )


@register_lc
class Sagacity(_LC):
    lc_id = "20020"

    def setup(self) -> None:
        self.on_use(
            (ActionKind.ULT,),
            lambda act: self.buff(Modifier("Sagacity", stats={S.ATK_PCT: self.p(0)}, duration=int(self.p(1)))),
            start=True,
        )


# ========================================================================= Hunt (Rogue)
@register_lc
class InTheNight(_LC):
    lc_id = "23001"

    def setup(self) -> None:
        crit_ult = f"{S.CRIT_DMG}:{DmgTag.ULT}"

        def dyn(m: Modifier, k: str, e: Entity) -> float:
            stacks = int((self.char.spd - IN_THE_NIGHT_SPD) / self.p(1) + 1e-9)
            stacks = max(0, min(int(self.p(4)), stacks))
            return stacks * (self.p(3) if k == crit_ult else self.p(2))

        keys = {f"{S.DMG_PCT}:{DmgTag.BASIC}", f"{S.DMG_PCT}:{DmgTag.SKILL}", crit_ult}
        self.passive("In the Night", dyn=dyn, dyn_keys=keys)


@register_lc
class SleepLikeTheDead(_LC):
    lc_id = "23012"

    def setup(self) -> None:
        cd = "Sleep Like the Dead (cooldown)"

        def after_hit(ev: E.Ev) -> None:
            h = ev.hit
            if h.credited is not self.char or not _has(h, DmgTag.BASIC, DmgTag.SKILL) or self.cooling(cd):
                return
            if not self.crit(h):
                self.buff(Modifier("Sleep Like the Dead", stats={S.CRIT_RATE: self.p(1)}, duration=int(self.p(2))))
                self.start_cooldown(cd, int(self.p(3)))

        self.on(E.AFTER_HIT, after_hit)


@register_lc
class WorrisomeBlissful(_LC):
    lc_id = "23016"

    def setup(self) -> None:
        self.passive("Worrisome, Blissful", {f"{S.DMG_PCT}:{DmgTag.FUA}": self.p(1)})

        def after_fua(act: Action) -> None:
            t = act.target if isinstance(act.target, Enemy) else next(iter(act.attacked), None)
            if t is not None and t.alive:
                tame = Modifier(
                    "Tame",
                    kind=ModKind.OTHER,
                    stacking=Stacking.STACK,
                    max_stacks=int(self.p(3)),
                    dispellable=False,
                )
                self.battle.apply(tame, t, self.char)

        def before_hit(ev: E.Ev) -> None:
            h = ev.hit
            if h.credited.side != Side.ALLY:
                return
            stacks = sum(m.stacks for m in h.target.mods("Tame") if m.source is self.char)
            if stacks:
                h.add(S.CRIT_DMG, self.p(2) * stacks)

        self.on_use((ActionKind.FUA,), after_fua)
        self.on(E.BEFORE_HIT, before_hit)


@register_lc
class BaptismOfPureThought(_LC):
    lc_id = "23020"

    def setup(self) -> None:
        self.hit_bonus(lambda h: True, S.CRIT_DMG, lambda h: self.p(1) * min(len(h.target.debuffs), int(self.p(2))))
        self.on_use(
            (ActionKind.ULT,),
            lambda act: self.buff(
                Modifier(
                    "Disputation",
                    stats={S.DMG_PCT: self.p(3), f"{S.DEF_IGNORE}:{DmgTag.FUA}": self.p(4)},
                    duration=int(self.p(5)),
                )
            ),
            start=True,
        )


@register_lc
class SailingTowardsASecondLife(_LC):
    lc_id = "23027"

    def setup(self) -> None:
        self.passive("Sailing Towards a Second Life", {f"{S.DEF_IGNORE}:{DmgTag.BREAK}": self.p(2)})
        self.passive(
            "Sailing Towards a Second Life (SPD)",
            dyn=lambda m, k, e: self.p(3) if self.char.stat(S.BREAK_EFFECT) >= self.p(1) - 1e-9 else 0.0,
            dyn_keys={S.SPD_PCT},
        )


@register_lc
class IVentureForthToHunt(_LC):
    lc_id = "23031"

    def setup(self) -> None:
        self.on_use(
            (ActionKind.FUA,),
            lambda act: self.buff(
                Modifier(
                    "Luminflux",
                    stats={f"{S.DEF_IGNORE}:{DmgTag.ULT}": self.p(1)},
                    stacking=Stacking.STACK,
                    max_stacks=int(self.p(2)),
                    tick=Tick.NONE,
                )
            ),
            start=True,
        )
        self.on_own_turn(E.TURN_END, lambda: self.remove_stacks("Luminflux"))


@register_lc
class TheHellWhereIdealsBurn(_LC):
    lc_id = "23046"

    def setup(self) -> None:
        self.on(
            E.BATTLE_START,
            lambda ev: self.battle.max_sp >= self.p(1)
            and self.passive("The Hell Where Ideals Burn", {S.ATK_PCT: self.p(2)}),
        )
        self.on_use(
            (ActionKind.SKILL,),
            lambda act: self.buff(
                Modifier(
                    "The Hell Where Ideals Burn (Skill)",
                    stats={S.ATK_PCT: self.p(3)},
                    stacking=Stacking.STACK,
                    max_stacks=int(self.p(4)),
                    tick=Tick.NONE,
                )
            ),
        )


@register_lc
class TheFinaleOfALie(_LC):
    lc_id = "23056"

    def setup(self) -> None:
        self.fuas = 0

        def umbra(*_: Any) -> None:
            dur = int(self.p(2))
            self.buff(Modifier("Umbra Devourer", stats={S.ATK_PCT: self.p(3)}, duration=dur))
            self.buff(
                Modifier(
                    "Umbra Devourer (enemies)",
                    stats={S.VULN: self.p(4)},
                    duration=dur,
                    scope=_enemy,
                    key="Umbra Devourer",
                )
            )

        def after_fua(act: Action) -> None:
            self.fuas += 1
            if self.fuas >= self.p(1):
                self.fuas = 0
                umbra()

        self.on(E.BATTLE_START, umbra)
        self.on_use((ActionKind.FUA,), after_fua)


@register_lc
class CruisingInTheStellarSea(_LC):
    lc_id = "24001"

    def setup(self) -> None:
        self.hit_bonus(lambda h: h.target.hp_ratio <= self.p(1) + 1e-9, S.CRIT_RATE, self.p(2))
        self.on_kill(
            lambda: self.buff(
                Modifier("Cruising in the Stellar Sea", stats={S.ATK_PCT: self.p(3)}, duration=int(self.p(4)))
            )
        )


@register_lc
class OnlySilenceRemains(_LC):
    lc_id = "21003"

    def setup(self) -> None:
        self.passive(
            "Only Silence Remains",
            dyn=lambda m, k, e: self.p(1) if len(self.battle.alive_enemies()) <= SILENCE_MAX_ENEMIES else 0.0,
            dyn_keys={S.CRIT_RATE},
        )


@register_lc
class Swordplay(_LC):
    lc_id = "21010"

    def setup(self) -> None:
        self.last_target: Enemy | None = None

        def before_hit(h: Hit) -> None:
            act = h.action
            if act is None or act.hits[0] is not h:  # decide once, on the first hit of an attack
                return
            main = act.target if isinstance(act.target, Enemy) else h.target
            if main is not self.last_target:
                self.battle.remove_named(self.char, "Swordplay")
                self.last_target = main

        def after_attack(ev: E.Ev) -> None:
            if self.used(ev.attack) and self.last_target is not None:
                self.buff(
                    Modifier(
                        "Swordplay",
                        stats={S.DMG_PCT: self.p(0)},
                        stacking=Stacking.STACK,
                        max_stacks=int(self.p(1)),
                        tick=Tick.NONE,
                    )
                )

        self.on_my_hit(before_hit)
        self.on(E.ATTACK_END, after_attack)


@register_lc
class SubscribeForMore(_LC):
    lc_id = "21017"

    def setup(self) -> None:
        def bonus(h: Hit) -> float:
            full = self.char.max_energy > 0 and self.char.energy >= self.char.max_energy - 1e-9
            return self.p(0) + (self.p(1) if full else 0.0)

        self.hit_bonus(lambda h: _has(h, DmgTag.BASIC, DmgTag.SKILL), S.DMG_PCT, bonus)


@register_lc
class RiverFlowsInSpring(_LC):
    lc_id = "21024"

    def setup(self) -> None:
        self.lost_at: int | None = None

        def grant(*_: Any) -> None:
            self.buff(Modifier("Cherry Blossom", stats={S.SPD_PCT: self.p(0), S.DMG_PCT: self.p(1)}, tick=Tick.NONE))

        def on_hp(ev: E.Ev) -> None:
            src = ev.source
            if ev.entity is self.char and ev.delta < 0 and src is not None and src.side == Side.ENEMY:
                if self.char.has_mod("Cherry Blossom"):
                    self.battle.remove_named(self.char, "Cherry Blossom")
                self.lost_at = self.battle.turns

        def turn_end(ev: E.Ev) -> None:
            if ev.entity is self.char and self.lost_at is not None and self.battle.turns > self.lost_at:
                self.lost_at = None
                grant()

        self.on(E.BATTLE_START, grant)
        self.on(E.HP_CHANGED, on_hp)
        self.on(E.TURN_END, turn_end)


@register_lc
class ReturnToDarkness(_LC):
    lc_id = "21031"

    def setup(self) -> None:
        def after_hit(ev: E.Ev) -> None:
            h = ev.hit
            act = h.action
            if h.credited is not self.char or act is None or act.data.get("return_to_darkness"):
                return
            if self.crit(h):
                act.data["return_to_darkness"] = True
                buffs = [m for m in h.target.buffs if m.dispellable]
                if buffs and self.battle.rng.random() < self.p(1):  # fixed chance
                    self.battle.remove_modifier(buffs[-1])

        self.on(E.AFTER_HIT, after_hit)


@register_lc
class FinalVictor(_LC):
    lc_id = "21037"

    def setup(self) -> None:
        def after_hit(ev: E.Ev) -> None:
            h = ev.hit
            if h.credited is self.char and self.crit(h):
                self.buff(
                    Modifier(
                        "Good Fortune",
                        stats={S.CRIT_DMG: self.p(1)},
                        stacking=Stacking.STACK,
                        max_stacks=int(self.p(2)),
                        tick=Tick.NONE,
                    )
                )

        self.on(E.AFTER_HIT, after_hit)
        self.on_own_turn(E.TURN_END, lambda: self.battle.remove_named(self.char, "Good Fortune"))


@register_lc
class ShadowedByNight(_LC):
    lc_id = "21047"

    def setup(self) -> None:
        def grant(*_: Any) -> None:
            if self.once_per_turn():
                self.buff(Modifier("Shadowed by Night", stats={S.SPD_PCT: self.p(1)}, duration=int(self.p(2))))

        self.on(E.BATTLE_START, grant)

        def on_damage(ev: E.Ev) -> None:
            if ev.credited is self.char and DmgTag.BREAK in ev.record.tags:
                grant()

        self.on(E.DAMAGE_DEALT, on_damage)


@register_lc
class SeeYouAtTheEnd(_LC):
    lc_id = "21062"

    def setup(self) -> None:
        self.hit_bonus(lambda h: _has(h, DmgTag.SKILL, DmgTag.FUA), S.DMG_PCT, self.p(1))


@register_lc
class RaceToTheHorizon(_LC):
    lc_id = "22008"

    def setup(self) -> None:
        self.on_use(
            (ActionKind.FUA,),
            lambda act: self.buff(
                Modifier(
                    "Race to the Horizon",
                    stats={S.CRIT_DMG: self.p(1)},
                    duration=int(self.p(2)),
                    stacking=Stacking.STACK,
                    max_stacks=int(self.p(3)),
                )
            ),
        )


@register_lc
class Arrows(_LC):
    lc_id = "20000"

    def setup(self) -> None:
        self.on(
            E.BATTLE_START,
            lambda ev: self.buff(Modifier("Arrows", stats={S.CRIT_RATE: self.p(0)}, duration=int(self.p(1)))),
        )


@register_lc
class DartingArrow(_LC):
    lc_id = "20007"

    def setup(self) -> None:
        self.on_kill(
            lambda: self.buff(Modifier("Darting Arrow", stats={S.ATK_PCT: self.p(0)}, duration=int(self.p(1))))
        )


@register_lc
class Adversarial(_LC):
    lc_id = "20014"

    def setup(self) -> None:
        self.on_kill(lambda: self.buff(Modifier("Adversarial", stats={S.SPD_PCT: self.p(0)}, duration=int(self.p(1)))))


# ================================================================== Destruction (Warrior)
@register_lc
class SomethingIrreplaceable(_LC):
    lc_id = "23002"

    def setup(self) -> None:
        def trigger(*_: Any) -> None:
            if not self.once_per_turn():
                return
            self.battle.heal(self.char, self.p(1) * self.char.atk, self.char)
            self.buff(Modifier("Something Irreplaceable", stats={S.DMG_PCT: self.p(2)}, duration=1))

        self.on_kill(trigger)
        self.on_attacked(trigger)


@register_lc
class TheUnreachableSide(_LC):
    lc_id = "23009"

    def setup(self) -> None:
        name = "The Unreachable Side"

        def grant() -> None:
            self.buff(Modifier(name, stats={S.DMG_PCT: self.p(2)}, tick=Tick.NONE))

        def hp_consumed(ev: E.Ev) -> None:
            if ev.entity is self.char and ev.delta < 0 and ev.source is self.char:
                grant()

        self.on_attacked(grant)
        self.on(E.HP_CHANGED, hp_consumed)
        self.after_my_attack(lambda act: self.battle.remove_named(self.char, name))


@register_lc
class IShallBeMyOwnSword(_LC):
    lc_id = "23014"

    def setup(self) -> None:
        full = int(self.p(1))

        def def_ignore(m: Modifier, k: str, e: Entity) -> float:
            return self.p(3) if m.stacks >= full else 0.0

        def eclipse() -> None:
            self.buff(
                Modifier(
                    "Eclipse",
                    stats={S.DMG_PCT: self.p(2)},
                    stacking=Stacking.STACK,
                    max_stacks=full,
                    tick=Tick.NONE,
                    dyn=def_ignore,
                    dyn_keys={S.DEF_IGNORE},
                )
            )

        def teammate(e: Entity) -> bool:
            return isinstance(e, Character) and e is not self.char

        def attacked(ev: E.Ev) -> None:
            for _ in filter(teammate, ev.targets):
                eclipse()

        def hp_lost(ev: E.Ev) -> None:
            # HP lost to an enemy attack is already counted by ALLY_ATTACKED
            if teammate(ev.entity) and ev.delta < 0 and not isinstance(ev.source, Enemy):
                eclipse()

        self.on(E.ALLY_ATTACKED, attacked)
        self.on(E.HP_CHANGED, hp_lost)
        self.after_my_attack(lambda act: self.battle.remove_named(self.char, "Eclipse"))


@register_lc
class BrighterThanTheSun(_LC):
    lc_id = "23015"

    def setup(self) -> None:
        self.on_use(
            (ActionKind.BASIC,),
            lambda act: self.buff(
                Modifier(
                    "Dragon's Call",
                    stats={S.ATK_PCT: self.p(3), S.ERR: self.p(4)},
                    duration=int(self.p(1)),
                    stacking=Stacking.STACK,
                    max_stacks=int(self.p(2)),
                )
            ),
            start=True,
        )


@register_lc
class WhereaboutsShouldDreamsRest(_LC):
    lc_id = "23025"

    def setup(self) -> None:
        def on_damage(ev: E.Ev) -> None:
            t = ev.target
            if ev.credited is not self.char or DmgTag.BREAK not in ev.record.tags or not t.alive:
                return
            # approximation: the engine's target-side stats cannot tell attackers apart, so Routed
            # raises Break DMG taken from every attacker (the game: only from the wearer)
            routed = Modifier(
                "Routed",
                stats={f"{S.VULN}:{DmgTag.BREAK}": self.p(1), S.SPD_PCT: -self.p(2)},
                duration=int(self.p(3)),
                kind=ModKind.DEBUFF,
                key="Routed",
            )
            self.battle.apply(routed, t, self.char)

        self.on(E.DAMAGE_DEALT, on_damage)


@register_lc
class DanceAtSunset(_LC):
    lc_id = "23030"

    def setup(self) -> None:
        self.passive("Dance at Sunset (aggro)", {S.AGGRO_PCT: self.p(3)})
        self.on_use(
            (ActionKind.ULT,),
            lambda act: self.buff(
                Modifier(
                    "Firedance",
                    stats={f"{S.DMG_PCT}:{DmgTag.FUA}": self.p(2)},
                    duration=FIREDANCE_TURNS,
                    stacking=Stacking.STACK,
                    max_stacks=int(self.p(1)),
                )
            ),
        )


@register_lc
class FlameOfBloodBlazeMyPath(_LC):
    lc_id = "23039"

    def setup(self) -> None:
        def on_use(act: Action) -> None:
            c = self.char
            cost = min(self.p(1) * c.max_hp, max(0.0, c.hp - 1.0))  # never below 1 HP
            consumed = self.battle.lose_hp(c, cost, c) if cost > 0 else 0.0
            bonus = self.p(2) + (self.p(4) if consumed > self.p(3) else 0.0)
            self.during(act, "Flame of Blood, Blaze My Path", {S.DMG_PCT: bonus})

        self.on_use((ActionKind.SKILL, ActionKind.ULT), on_use, start=True)


@register_lc
class ThusBurnsTheDawn(_LC):
    lc_id = "23044"

    def setup(self) -> None:
        self.passive("Thus Burns the Dawn", {S.DEF_IGNORE: self.p(1)})
        self.on_use(
            (ActionKind.ULT,),
            lambda act: self.buff(
                Modifier("Blazing Sun", stats={S.DMG_PCT: self.p(2)}, duration=1, tick=Tick.HOLDER_TURN_START)
            ),
        )


@register_lc
class AThanklessCoronation(_LC):
    lc_id = "23045"

    def setup(self) -> None:
        def on_ult(act: Action) -> None:
            atk = self.p(5)
            if self.char.max_energy >= self.p(2) - 1e-9:
                self.battle.gain_energy(self.char, self.p(4) * self.char.max_energy, fixed=True)
                atk += self.p(1)
            self.buff(Modifier("A Thankless Coronation", stats={S.ATK_PCT: atk}, duration=int(self.p(3))))

        self.on_use((ActionKind.ULT,), on_ult, start=True)


@register_lc
class IAmAsYouBehold(_LC):
    lc_id = "23062"

    def setup(self) -> None:
        def kings_entertainment(*_: Any) -> None:
            mod = Modifier(
                "King's Entertainment",
                stats={S.CRIT_DMG: self.p(4)},
                duration=int(self.p(3)),
                scope=_ally,
                key="King's Entertainment",
            )
            self.buff(mod)

        def on_ult(act: Action) -> None:
            bonus = min(self.p(5), self.p(2) * self.ult_energy_consumed())
            self.during(act, "I Am As You Behold (Ultimate)", {f"{S.DMG_PCT}:{DmgTag.ULT}": bonus})
            kings_entertainment()

        self.on(E.BATTLE_START, kings_entertainment)
        self.on_use((ActionKind.ULT,), on_ult, start=True)


@register_lc
class OnTheFallOfAnAeon(_LC):
    lc_id = "24000"

    def setup(self) -> None:
        self.on(
            E.ATTACK_START,
            lambda ev: self.used(ev.attack)
            and self.buff(
                Modifier(
                    "On the Fall of an Aeon",
                    stats={S.ATK_PCT: self.p(0)},
                    stacking=Stacking.STACK,
                    max_stacks=int(self.p(1)),
                    tick=Tick.NONE,
                )
            ),
        )
        self.on(
            E.BREAK,
            lambda ev: ev.credited is self.char
            and self.buff(
                Modifier("On the Fall of an Aeon (Break)", stats={S.DMG_PCT: self.p(2)}, duration=int(self.p(3)))
            ),
        )


@register_lc
class TheMolesWelcomeYou(_LC):
    lc_id = "21005"

    def setup(self) -> None:
        # one stack per attack type (Basic ATK / Skill / Ultimate): at most 3 stacks, as in the game
        self.on(
            E.ATTACK_START,
            lambda ev: self.used(ev.attack, *ATTACK_KINDS)
            and self.buff(Modifier(f"Mischievous ({ev.attack.kind.value})", stats={S.ATK_PCT: self.p(0)})),
        )


@register_lc
class ASecretVow(_LC):
    lc_id = "21012"

    def setup(self) -> None:
        self.hit_bonus(lambda h: h.target.hp_ratio >= self.char.hp_ratio - 1e-9, S.DMG_PCT, self.p(1))


@register_lc
class UnderTheBlueSky(_LC):
    lc_id = "21019"

    def setup(self) -> None:
        self.on_kill(
            lambda: self.buff(Modifier("Under the Blue Sky", stats={S.CRIT_RATE: self.p(1)}, duration=int(self.p(2))))
        )


@register_lc
class WoofWalkTime(_LC):
    lc_id = "21026"

    def setup(self) -> None:
        # also applies to DoT: character DoTs go through BEFORE_HIT too
        self.hit_bonus(lambda h: h.target.has_tag("burn") or h.target.has_tag("bleed"), S.DMG_PCT, self.p(1))


@register_lc
class NowhereToRun(_LC):
    lc_id = "21033"

    def setup(self) -> None:
        self.on_kill(lambda: self.battle.heal(self.char, self.p(1) * self.char.atk, self.char))


@register_lc
class FlamesAfar(_LC):
    lc_id = "21038"

    def setup(self) -> None:
        cd = "Flames Afar (cooldown)"
        self.lost: tuple[int, float] = (0, 0.0)  # (id of the enemy action, HP lost during it)

        def trigger() -> None:
            c = self.char
            self.start_cooldown(cd, int(self.p(4)))
            self.battle.heal(c, self.p(2) * c.max_hp, c)
            self.buff(Modifier("Flames Afar", stats={S.DMG_PCT: self.p(1)}, duration=int(self.p(3))))

        def on_hp(ev: E.Ev) -> None:
            c = self.char
            if ev.entity is not c or ev.delta >= 0 or self.cooling(cd):
                return
            limit = self.p(0) * c.max_hp
            if ev.source is c:  # own HP consumed at one time
                if -ev.delta > limit:
                    trigger()
                return
            act = self.battle.current_action
            key = id(act) if act is not None else 0
            total = (self.lost[1] if self.lost[0] == key else 0.0) - ev.delta
            self.lost = (key, total)
            if act is not None and total > limit:
                self.lost = (key, float("-inf"))
                trigger()

        self.on(E.HP_CHANGED, on_hp)


@register_lc
class IndeliblePromise(_LC):
    lc_id = "21042"

    def setup(self) -> None:
        self.on_use(
            (ActionKind.ULT,),
            lambda act: self.buff(
                Modifier("Indelible Promise", stats={S.CRIT_RATE: self.p(1)}, duration=int(self.p(2)))
            ),
            start=True,
        )


@register_lc
class ATrailOfBygoneBlood(_LC):
    lc_id = "21058"

    def setup(self) -> None:
        self.hit_bonus(lambda h: _has(h, DmgTag.SKILL, DmgTag.ULT), S.DMG_PCT, self.p(1))


@register_lc
class NinjaRecordSoundHunt(_LC):
    lc_id = "22003"

    def setup(self) -> None:
        self.on(
            E.HP_CHANGED,
            lambda ev: ev.entity is self.char
            and ev.delta != 0
            and self.once_per_turn()
            and self.buff(Modifier("Ninja Record: Sound Hunt", stats={S.CRIT_DMG: self.p(1)}, duration=int(self.p(2)))),
        )


@register_lc
class CollapsingSky(_LC):
    lc_id = "20002"

    def setup(self) -> None:
        self.hit_bonus(lambda h: _has(h, DmgTag.BASIC, DmgTag.SKILL), S.DMG_PCT, self.p(0))


@register_lc
class ShatteredHome(_LC):
    lc_id = "20009"

    def setup(self) -> None:
        self.hit_bonus(lambda h: h.target.hp_ratio > self.p(0), S.DMG_PCT, self.p(1))


@register_lc
class MutualDemise(_LC):
    lc_id = "20016"

    def setup(self) -> None:
        self.passive(
            "Mutual Demise",
            dyn=lambda m, k, e: self.p(1) if self.char.hp_ratio < self.p(0) else 0.0,
            dyn_keys={S.CRIT_RATE},
        )
