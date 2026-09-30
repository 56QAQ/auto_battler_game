"""Conditional effects of Harmony (Shaman), Nihility (Warlock) and Preservation (Knight) light cones.

Always-on stats (the data's "static props") are applied by the build code; the classes below
only add what depends on combat state. Every number comes from the data: ``self.p(i)`` is the
``#(i+1)`` placeholder of the description at the equipped superimposition. Values written out
literally in the description text (e.g. "1 Skill Point", "for 1 turn", "a 100% base chance")
have no parameter and are kept as named constants.

Not modelled by the engine (see the per-class comments): shield HP absorption / Shield Effect,
healing boosts, characters being knocked down.
"""

from __future__ import annotations

from collections import Counter
from typing import TYPE_CHECKING, Any

from .. import events as E
from .. import stats as S
from ..entities import Character, Enemy, Entity, Summon
from ..enums import ActionKind, DmgTag, Element, Side
from ..equipment import LightCone, register_lc
from ..modifiers import DotModifier, Modifier, ModKind, Stacking, Tick, hidden

if TYPE_CHECKING:
    from ..battle import Action, Battle, Hit

DOT_TYPES = ("wind_shear", "burn", "shock", "bleed")
ABILITY_TAG = {ActionKind.BASIC: DmgTag.BASIC, ActionKind.SKILL: DmgTag.SKILL, ActionKind.ULT: DmgTag.ULT}
ONE_SP = 1  # "recovers 1 Skill Point" (fixed in the description text)
TEXT_CERTAIN = 1.0  # "a 100% base chance" written in the text (no parameter)
ONE_TURN = 1  # "for 1 turn" / "until the end of the wearer's turn" written in the text


# ------------------------------------------------------------------------------ helpers
def _ally(e: Entity) -> bool:
    return e.side == Side.ALLY


def _acting_ally(e: Entity) -> bool:
    """Ally targets that take actions of their own: characters and memosprites."""
    return isinstance(e, Character) or (isinstance(e, Summon) and e.is_memosprite)


def _def_reduced(e: Entity) -> bool:
    return any(m.is_debuff and (S.DEF_REDUCTION in m.stats or "def_reduction" in m.tags) for m in e.modifiers)


def _slowed(e: Entity) -> bool:
    return any(
        m.is_debuff and ("slow" in m.tags or m.stats.get(S.SPD_PCT, 0.0) < 0 or m.stats.get(S.SPD_FLAT, 0.0) < 0)
        for m in e.modifiers
        if not m.removed
    )


def _dot_from(e: Entity, source: Entity) -> bool:
    return any("dot" in m.tags and m.source is source for m in e.modifiers if not m.removed)


def _has_summon(e: Entity) -> bool:
    return any(s.alive for s in getattr(e, "summons", ()))


def _shielded(e: Entity) -> bool:
    return e.has_tag("shield")


class _LC(LightCone):
    def passive(
        self, name: str, stats: dict[str, float] | None = None, target: Entity | None = None, **kw: Any
    ) -> Modifier:
        return self.battle.apply(hidden(name, stats, **kw), target or self.char, self.char)

    def buff(self, target: Entity, mod: Modifier) -> Modifier:
        return self.battle.apply(mod, target, self.char)

    def used(self, act: Action, *kinds: ActionKind) -> bool:
        return act.owner is self.char and act.kind in kinds

    def by_me(self, hit: Hit) -> bool:
        """DMG credited to the wearer (own hits, DoTs, and hits of owner-stat summons)."""
        return hit.credited is self.char

    def on_ally(self, act: Action) -> bool:
        """Ability used on an ally: single-target ally ability or a team-wide ally Ultimate."""
        if isinstance(act.target, Character):
            return True
        return (
            act.target is None
            and act.kind == ActionKind.ULT
            and bool(getattr(self.char.kit, "ult_targets_ally", False))
        )

    def first_on(self, act: Action | None, target: Entity) -> bool:
        """True the first time this light cone asks about ``target`` during ``act``."""
        if act is None:
            return True
        seen: set[int] = act.data.setdefault(f"lc{id(self)}", set())
        if target.uid in seen:
            return False
        seen.add(target.uid)
        return True

    def once_per_turn(self) -> bool:
        turn = self.battle.turns
        if getattr(self, "_last_turn", None) == turn:
            return False
        self._last_turn = turn
        return True

    def next_ally_buff(self, name: str, value: float, duration: int) -> None:
        """Skill buff for "the next ally taking action (except the wearer)": granted when that
        ally's (character or memosprite) turn starts and lasts ``duration`` of its turns."""
        self.pending = False

        def on_skill(ev: E.Ev) -> None:
            if self.used(ev.action, ActionKind.SKILL):
                self.pending = True

        def on_turn(ev: E.Ev) -> None:
            e = ev.entity
            if self.pending and e is not self.char and _ally(e) and _acting_ally(e):
                self.pending = False
                # the current turn counts: "1 turn" covers exactly this action
                self.buff(e, Modifier(name, stats={S.DMG_PCT: value}, duration=duration, skip_first_tick=False))

        self.on(E.ACTION_END, on_skill)
        self.on(E.TURN_START, on_turn)


# =================================================================== Preservation (Knight)
@register_lc
class MomentOfVictory(_LC):
    lc_id = "23005"

    def setup(self) -> None:
        self.passive("Moment of Victory (aggro)", {S.AGGRO_PCT: self.p(0)})

        def attacked(ev: E.Ev) -> None:
            if self.char in ev.targets:
                self.buff(
                    self.char,
                    Modifier(
                        "Moment of Victory", stats={S.DEF_PCT: self.p(2)}, duration=ONE_TURN, skip_first_tick=False
                    ),
                )

        self.on(E.ALLY_ATTACKED, attacked)


@register_lc
class SheAlreadyShutHerEyes(_LC):
    lc_id = "23011"

    def setup(self) -> None:
        def hp_lost(ev: E.Ev) -> None:
            if ev.entity is self.char and ev.delta < 0:
                for c in self.battle.allies():
                    self.buff(
                        c, Modifier("She Already Shut Her Eyes", stats={S.DMG_PCT: self.p(1)}, duration=int(self.p(4)))
                    )

        def wave(ev: E.Ev) -> None:
            for c in self.battle.allies():
                self.battle.heal(c, self.p(2) * max(0.0, c.max_hp - c.hp), self.char)

        self.on(E.HP_CHANGED, hp_lost)
        self.on(E.WAVE_START, wave)


@register_lc
class InherentlyUnjustDestiny(_LC):
    lc_id = "23023"

    def setup(self) -> None:
        # not modelled: shields themselves; reacts to any "shield"-tagged modifier the wearer applies
        def shield(ev: E.Ev) -> None:
            m = ev.mod
            if "shield" in m.tags and m.source is self.char and _ally(ev.target):
                self.buff(
                    self.char,
                    Modifier("Inherently Unjust Destiny", stats={S.CRIT_DMG: self.p(1)}, duration=int(self.p(2))),
                )

        def after_hit(ev: E.Ev) -> None:
            h = ev.hit
            act = h.action
            if act is None or not self.used(act, ActionKind.FUA) or not h.target.alive:
                return
            if self.first_on(act, h.target):
                self.battle.try_debuff(
                    Modifier(
                        "Unjust Destiny (DMG taken)",
                        stats={S.VULN: self.p(4)},
                        duration=int(self.p(5)),
                        kind=ModKind.DEBUFF,
                    ),
                    h.target,
                    self.char,
                    self.p(3),
                )

        self.on(E.MOD_APPLIED, shield)
        self.on(E.AFTER_HIT, after_hit)


@register_lc
class ThoughWorldsApart(_LC):
    lc_id = "23051"

    def setup(self) -> None:
        def redoubt_dyn(mod: Modifier, key: str, ent: Entity) -> float:
            return self.p(2) if _has_summon(ent) else 0.0

        def on_ult(ev: E.Ev) -> None:
            if not self.used(ev.action, ActionKind.ULT):
                return
            allies = self.battle.allies()
            atk = self.char.atk
            for c in allies:
                self.battle.heal(c, self.p(4) * atk, self.char)
            if allies:
                self.battle.heal(min(allies, key=lambda c: c.hp), self.p(5) * atk, self.char)
            for c in allies:
                self.buff(
                    c,
                    Modifier(
                        "Redoubt",
                        stats={S.DMG_PCT: self.p(1)},
                        duration=int(self.p(3)),
                        dyn=redoubt_dyn,
                        dyn_keys={S.DMG_PCT},
                    ),
                )

        self.on(E.ACTION_START, on_ult)


@register_lc
class TextureOfMemories(_LC):
    lc_id = "24002"

    def setup(self) -> None:
        # not modelled: the Shield's HP absorption (the shield is a "shield"-tagged marker lasting its duration)
        self.cooldown = 0
        self.passive(
            "Texture of Memories",
            {},
            dyn=lambda m, k, e: self.p(4) if _shielded(self.char) else 0.0,
            dyn_keys={S.MITIGATION},
        )

        def attacked(ev: E.Ev) -> None:
            if self.char in ev.targets and not _shielded(self.char) and self.cooldown <= 0:
                self.cooldown = int(self.p(3))
                self.buff(self.char, Modifier("Texture of Memories (Shield)", duration=int(self.p(2)), tags={"shield"}))

        def turn_end(ev: E.Ev) -> None:
            if ev.entity is self.char and self.cooldown > 0:
                self.cooldown -= 1

        self.on(E.ALLY_ATTACKED, attacked)
        self.on(E.TURN_END, turn_end)


@register_lc
class DayOneOfMyNewLife(_LC):
    lc_id = "21002"

    def setup(self) -> None:
        res = {f"{S.RES}:{el.value}": self.p(1) for el in Element}
        self.passive("Day One of My New Life", res, scope=_ally, key="Day One of My New Life")


@register_lc
class LandausChoice(_LC):
    lc_id = "21009"

    def setup(self) -> None:
        self.passive("Landau's Choice", {S.AGGRO_PCT: self.p(0), S.MITIGATION: self.p(1)})


@register_lc
class TrendOfTheUniversalMarket(_LC):
    lc_id = "21016"

    def setup(self) -> None:
        name = "Burn (Trend of the Universal Market)"

        def attacked(ev: E.Ev) -> None:
            enemy = ev.attacker
            if self.char not in ev.targets or not isinstance(enemy, Enemy) or not enemy.alive:
                return
            me, mult = self.char, self.p(2)

            def dmg(mod: DotModifier, b: Battle, ratio: float) -> float:
                return b.dot_damage(
                    me, enemy, Element.FIRE, mult, stat="def", label=name, tags=(DmgTag.DOT, "burn"), ratio=ratio
                )

            self.battle.try_debuff(
                DotModifier(name, dot_type="burn", damage_fn=dmg, duration=int(self.p(3))), enemy, me, self.p(1)
            )

        self.on(E.ALLY_ATTACKED, attacked)


@register_lc
class WeAreWildfire(_LC):
    lc_id = "21023"

    def setup(self) -> None:
        def start(ev: E.Ev) -> None:
            for c in self.battle.allies():
                self.buff(c, Modifier("We Are Wildfire", stats={S.MITIGATION: self.p(1)}, duration=int(self.p(2))))
                self.battle.heal(c, self.p(0) * max(0.0, c.max_hp - c.hp), self.char)

        self.on(E.BATTLE_START, start)


@register_lc
class ThisIsMe(_LC):
    lc_id = "21030"

    def setup(self) -> None:
        def before_hit(ev: E.Ev) -> None:
            h = ev.hit
            if h.action is not None and self.used(h.action, ActionKind.ULT) and self.first_on(h.action, h.target):
                h.flat += self.p(1) * self.char.scaling("def", h.extra)

        self.on(E.BEFORE_HIT, before_hit)


@register_lc
class DestinysThreadsForewoven(_LC):
    lc_id = "21039"

    def setup(self) -> None:
        def dyn(mod: Modifier, key: str, ent: Entity) -> float:
            return min(self.p(3), (self.char.defense // self.p(1)) * self.p(2))

        self.passive("Destiny's Threads Forewoven", {}, dyn=dyn, dyn_keys={S.DMG_PCT})


@register_lc
class ConcertForTwo(_LC):
    lc_id = "21043"

    def setup(self) -> None:
        # shields are detected through "shield"-tagged modifiers (none unless a kit adds them)
        self.passive(
            "Concert for Two",
            {},
            dyn_keys={S.DMG_PCT},
            dyn=lambda m, k, e: self.p(1) * sum(1 for c in self.battle.allies() if _shielded(c)),
        )


@register_lc
class JourneyForeverPeaceful(_LC):
    lc_id = "21053"

    def setup(self) -> None:
        # not modelled: "provided Shield Effect +X%" (shield values are not simulated)
        self.passive(
            "Journey, Forever Peaceful",
            {},
            scope=_ally,
            dyn_keys={S.DMG_PCT},
            dyn=lambda m, k, e: self.p(1) if _shielded(e) else 0.0,
        )


@register_lc
class Amber(_LC):
    lc_id = "20003"

    def setup(self) -> None:
        self.passive(
            "Amber", {}, dyn=lambda m, k, e: self.p(2) if self.char.hp_ratio < self.p(1) else 0.0, dyn_keys={S.DEF_PCT}
        )


@register_lc
class Defense(_LC):
    lc_id = "20010"

    def setup(self) -> None:
        def on_ult(ev: E.Ev) -> None:
            if self.used(ev.action, ActionKind.ULT):
                self.battle.heal(self.char, self.p(0) * self.char.max_hp, self.char)

        self.on(E.ACTION_END, on_ult)


@register_lc
class Pioneering(_LC):
    lc_id = "20017"

    def setup(self) -> None:
        def on_break(ev: E.Ev) -> None:
            if ev.credited is self.char:
                self.battle.heal(self.char, self.p(0) * self.char.max_hp, self.char)

        self.on(E.BREAK, on_break)


# ======================================================================== Harmony (Shaman)
@register_lc
class ButTheBattleIsntOver(_LC):
    lc_id = "23003"
    ULT_PERIOD = 2  # "can be triggered once after every 2 uses of the wearer's Ultimate" (text)

    def setup(self) -> None:
        self.cooldown = 0

        def on_ult(ev: E.Ev) -> None:
            act = ev.action
            if not self.used(act, ActionKind.ULT):
                return
            if self.cooldown <= 0 and self.on_ally(act):
                self.battle.gain_sp(ONE_SP, self.char)
                self.cooldown = self.ULT_PERIOD
            self.cooldown -= 1

        self.on(E.ACTION_START, on_ult)
        self.next_ally_buff("But the Battle Isn't Over", self.p(1), int(self.p(2)))


@register_lc
class PastSelfInMirror(_LC):
    lc_id = "23019"

    def setup(self) -> None:
        def on_ult(ev: E.Ev) -> None:
            if not self.used(ev.action, ActionKind.ULT):
                return
            for c in self.battle.allies():
                self.buff(
                    c,
                    Modifier(
                        "Past Self in Mirror",
                        stats={S.DMG_PCT: self.p(1)},
                        duration=int(self.p(2)),
                        key="Past Self in Mirror",
                    ),
                )
            if self.char.stat(S.BREAK_EFFECT) >= self.p(3) - 1e-9:
                self.battle.gain_sp(ONE_SP, self.char)

        def wave(ev: E.Ev) -> None:
            for c in self.battle.allies():
                if isinstance(c, Character):
                    self.battle.gain_energy(c, self.p(4))

        self.on(E.ACTION_START, on_ult)
        self.on(E.WAVE_START, wave)


@register_lc
class EarthlyEscapade(_LC):
    lc_id = "23021"

    def setup(self) -> None:
        me = self.char

        def mask(duration: int) -> None:
            self.buff(
                me,
                Modifier(
                    "Mask",
                    stats={S.CRIT_RATE: self.p(4), S.CRIT_DMG: self.p(1)},
                    duration=duration,
                    scope=lambda e: _ally(e) and e is not me,
                ),
            )

        def flame() -> None:
            m = self.buff(
                me,
                Modifier(
                    "Radiant Flame",
                    kind=ModKind.OTHER,
                    stacking=Stacking.STACK,
                    max_stacks=int(self.p(3)),
                    tick=Tick.NONE,
                ),
            )
            if m.stacks >= self.p(3):
                self.battle.remove_modifier(m)
                mask(int(self.p(2)))

        # Radiant Flame counts SP recovered *including overflow*
        def on_recover(ev: E.Ev) -> None:
            if ev.entity is me:
                for _ in range(max(0, int(ev.amount))):
                    flame()

        self.on(E.SP_RECOVERED, on_recover)
        self.on(E.BATTLE_START, lambda ev: mask(int(self.p(5))))


@register_lc
class FlowingNightglow(_LC):
    lc_id = "23026"

    def setup(self) -> None:
        def on_attack(ev: E.Ev) -> None:
            if _ally(ev.attack.owner):
                self.buff(
                    self.char,
                    Modifier(
                        "Cantillation",
                        stats={S.ERR: self.p(0)},
                        stacking=Stacking.STACK,
                        max_stacks=int(self.p(1)),
                        tick=Tick.NONE,
                    ),
                )

        def on_ult(ev: E.Ev) -> None:
            if not self.used(ev.action, ActionKind.ULT):
                return
            self.battle.remove_named(self.char, "Cantillation")
            dur = int(self.p(4))
            self.buff(self.char, Modifier("Cadenza", stats={S.ATK_PCT: self.p(3)}, duration=dur))
            self.buff(self.char, Modifier("Cadenza (allies)", stats={S.DMG_PCT: self.p(2)}, duration=dur, scope=_ally))

        self.on(E.ATTACK_END, on_attack)
        self.on(E.ACTION_START, on_ult)


@register_lc
class AGroundedAscent(_LC):
    lc_id = "23034"

    def setup(self) -> None:
        self.count = 0

        def on_end(ev: E.Ev) -> None:
            act = ev.action
            target = act.target
            if not self.used(act, ActionKind.SKILL, ActionKind.ULT) or not isinstance(target, Character):
                return
            self.battle.gain_energy(self.char, self.p(0))
            self.buff(
                target,
                Modifier(
                    "Hymn",
                    stats={S.DMG_PCT: self.p(1)},
                    duration=int(self.p(3)),
                    stacking=Stacking.STACK,
                    max_stacks=int(self.p(2)),
                ),
            )
            self.count += 1
            if self.count >= self.p(4):
                self.count = 0
                self.battle.gain_sp(ONE_SP, self.char)

        self.on(E.ACTION_END, on_end)


@register_lc
class IfTimeWereAFlower(_LC):
    lc_id = "23038"

    def setup(self) -> None:
        def presage(duration: int) -> None:
            self.buff(self.char, Modifier("Presage", stats={S.CRIT_DMG: self.p(3)}, duration=duration, scope=_ally))

        def on_fua(ev: E.Ev) -> None:
            if self.used(ev.action, ActionKind.FUA) and ev.action.is_attack:
                self.battle.gain_energy(self.char, self.p(1))
                presage(int(self.p(2)))

        def start(ev: E.Ev) -> None:
            self.battle.gain_energy(self.char, self.p(4))
            presage(int(self.p(5)))

        self.on(E.ACTION_END, on_fua)
        self.on(E.BATTLE_START, start)


@register_lc
class EpochEtchedInGoldenBlood(_LC):
    lc_id = "23048"

    def setup(self) -> None:
        def on_end(ev: E.Ev) -> None:
            act = ev.action
            if self.used(act, ActionKind.ULT) and act.is_attack:
                self.battle.gain_sp(int(self.p(2)), self.char)
            if self.used(act, ActionKind.SKILL) and isinstance(act.target, Character):
                self.buff(
                    act.target,
                    Modifier(
                        "Etched in Golden Blood",
                        stats={f"{S.DMG_PCT}:{DmgTag.SKILL}": self.p(3)},
                        duration=int(self.p(4)),
                    ),
                )

        self.on(E.ACTION_END, on_end)


@register_lc
class MemoriesOfThePast(_LC):
    lc_id = "21004"

    def setup(self) -> None:
        def on_attack(ev: E.Ev) -> None:
            if ev.attack.owner is self.char and self.once_per_turn():
                self.battle.gain_energy(self.char, self.p(1))

        self.on(E.ATTACK_END, on_attack)


@register_lc
class PlanetaryRendezvous(_LC):
    lc_id = "21011"

    def setup(self) -> None:
        el = self.char.element
        self.passive(
            "Planetary Rendezvous",
            {f"{S.DMG_PCT}:{el.value}": self.p(0)},
            scope=lambda e: _ally(e) and getattr(e, "element", None) == el,
        )


@register_lc
class DanceDanceDance(_LC):
    lc_id = "21018"

    def setup(self) -> None:
        def on_ult(ev: E.Ev) -> None:
            if self.used(ev.action, ActionKind.ULT):
                for e in self.battle.allies(include_summons=True):
                    self.battle.advance(e, self.p(0))

        self.on(E.ACTION_END, on_ult)


@register_lc
class PastAndFuture(_LC):
    lc_id = "21025"

    def setup(self) -> None:
        self.next_ally_buff("Past and Future", self.p(0), int(self.p(1)))


@register_lc
class CarveTheMoonWeaveTheClouds(_LC):
    lc_id = "21032"

    def setup(self) -> None:
        # not modelled: removal when the wearer is knocked down (allies do not die in the simulator)
        effects = [("ATK", S.ATK_PCT, self.p(0)), ("CRIT DMG", S.CRIT_DMG, self.p(1)), ("ERR", S.ERR, self.p(2))]
        self.last = -1
        self.current: Modifier | None = None

        def roll() -> None:
            i = self.battle.rng.choice([j for j in range(len(effects)) if j != self.last])
            self.last = i
            if self.current is not None:
                self.battle.remove_modifier(self.current)
            label, key, value = effects[i]
            self.current = self.passive(
                f"Carve the Moon, Weave the Clouds ({label})",
                {key: value},
                scope=_ally,
                key=f"Carve the Moon, Weave the Clouds ({label})",
            )

        def turn_start(ev: E.Ev) -> None:
            if ev.entity is self.char:
                roll()

        self.on(E.BATTLE_START, lambda ev: roll())
        self.on(E.TURN_START, turn_start)


@register_lc
class DreamvilleAdventure(_LC):
    lc_id = "21036"

    def setup(self) -> None:
        def on_end(ev: E.Ev) -> None:
            act = ev.action
            if self.used(act, *ABILITY_TAG):
                # explicit key: re-applying replaces the previous ability type ("most recent type only")
                self.passive(
                    "Childishness", {f"{S.DMG_PCT}:{ABILITY_TAG[act.kind]}": self.p(0)}, scope=_ally, key="Childishness"
                )

        self.on(E.ACTION_END, on_end)


@register_lc
class PoisedToBloom(_LC):
    lc_id = "21046"

    def setup(self) -> None:
        paths = Counter(c.path for c in self.battle.team)
        self.passive(
            "Poised to Bloom",
            {S.CRIT_DMG: self.p(1)},
            key="Poised to Bloom",
            scope=lambda e: isinstance(e, Character) and paths[e.path] >= 2,
        )


@register_lc
class InPursuitOfTheWind(_LC):
    lc_id = "21056"

    def setup(self) -> None:
        self.passive("In Pursuit of the Wind", {S.BREAK_DMG_PCT: self.p(0)}, scope=_ally, key="In Pursuit of the Wind")


@register_lc
class ForTomorrowsJourney(_LC):
    lc_id = "22002"

    def setup(self) -> None:
        self.on(
            E.ACTION_END,
            lambda ev: self.used(ev.action, ActionKind.ULT)
            and self.buff(
                self.char, Modifier("For Tomorrow's Journey", stats={S.DMG_PCT: self.p(1)}, duration=int(self.p(2)))
            ),
        )


@register_lc
class TheForeverVictual(_LC):
    lc_id = "22005"

    def setup(self) -> None:
        self.on(
            E.ACTION_END,
            lambda ev: self.used(ev.action, ActionKind.SKILL)
            and self.buff(
                self.char,
                Modifier(
                    "The Forever Victual",
                    stats={S.ATK_PCT: self.p(1)},
                    stacking=Stacking.STACK,
                    max_stacks=int(self.p(2)),
                    tick=Tick.NONE,
                ),
            ),
        )


@register_lc
class Chorus(_LC):
    lc_id = "20005"

    def setup(self) -> None:
        self.passive("Chorus", {S.ATK_PCT: self.p(0)}, scope=_ally, key="Chorus")


@register_lc
class MeshingCogs(_LC):
    lc_id = "20012"

    def setup(self) -> None:
        def trigger(ok: bool) -> None:
            if ok and self.once_per_turn():
                self.battle.gain_energy(self.char, self.p(0))

        self.on(E.ATTACK_END, lambda ev: trigger(ev.attack.owner is self.char))
        self.on(E.ALLY_ATTACKED, lambda ev: trigger(self.char in ev.targets))


@register_lc
class Mediation(_LC):
    lc_id = "20019"

    def setup(self) -> None:
        def start(ev: E.Ev) -> None:
            for c in self.battle.allies():
                self.buff(c, Modifier("Mediation", stats={S.SPD_FLAT: self.p(0)}, duration=int(self.p(1))))

        self.on(E.BATTLE_START, start)


# ======================================================================= Nihility (Warlock)
@register_lc
class InTheNameOfTheWorld(_LC):
    lc_id = "23004"

    def setup(self) -> None:
        name = "In the Name of the World (Skill)"

        def before_hit(ev: E.Ev) -> None:
            h = ev.hit
            if self.by_me(h) and h.target.debuffs:
                h.add(S.DMG_PCT, self.p(0))

        def start(ev: E.Ev) -> None:
            if self.used(ev.action, ActionKind.SKILL):
                self.passive(name, {S.EHR: self.p(1), S.ATK_PCT: self.p(2)})

        def end(ev: E.Ev) -> None:
            if self.used(ev.action, ActionKind.SKILL):
                self.battle.remove_named(self.char, name)

        self.on(E.BEFORE_HIT, before_hit)
        self.on(E.ACTION_START, start)
        self.on(E.ACTION_END, end)


@register_lc
class PatienceIsAllYouNeed(_LC):
    lc_id = "23006"

    def setup(self) -> None:
        me = self.char

        def on_attack(ev: E.Ev) -> None:
            if ev.attack.owner is me:
                self.buff(
                    me,
                    Modifier(
                        "Patience Is All You Need",
                        stats={S.SPD_PCT: self.p(2)},
                        stacking=Stacking.STACK,
                        max_stacks=int(self.p(3)),
                        tick=Tick.NONE,
                    ),
                )

        def after_hit(ev: E.Ev) -> None:
            h = ev.hit
            target = h.target
            if h.action is None or h.action.owner is not me or not target.alive or target.has_mod("Erode"):
                return
            mult = self.p(0)

            def dmg(mod: DotModifier, b: Battle, ratio: float) -> float:
                return b.dot_damage(
                    me, target, Element.LIGHTNING, mult, label="Erode", tags=(DmgTag.DOT, "shock"), ratio=ratio
                )

            # Erode counts as Shock (dot_type "shock")
            self.battle.try_debuff(
                DotModifier("Erode", dot_type="shock", damage_fn=dmg, duration=int(self.p(4))), target, me, TEXT_CERTAIN
            )

        self.on(E.ATTACK_END, on_attack)
        self.on(E.AFTER_HIT, after_hit)


@register_lc
class IncessantRain(_LC):
    lc_id = "23007"

    def setup(self) -> None:
        def before_hit(ev: E.Ev) -> None:
            h = ev.hit
            if self.by_me(h) and len(h.target.debuffs) >= self.p(3):
                h.add(S.CRIT_RATE, self.p(4))

        def on_end(ev: E.Ev) -> None:
            act = ev.action
            if not self.used(act, *ABILITY_TAG):
                return
            cands = [t for t in act.attacked if t.alive and not t.has_mod("Aether Code")]
            if cands:
                target = self.battle.rng.choice(cands)
                self.battle.try_debuff(
                    Modifier("Aether Code", stats={S.VULN: self.p(2)}, duration=ONE_TURN, kind=ModKind.DEBUFF),
                    target,
                    self.char,
                    self.p(1),
                )

        self.on(E.BEFORE_HIT, before_hit)
        self.on(E.ACTION_END, on_end)


@register_lc
class ReforgedRemembrance(_LC):
    lc_id = "23022"

    def setup(self) -> None:
        self.granted: set[str] = set()  # one Prophet stack per DoT type per battle

        def after_hit(ev: E.Ev) -> None:
            h = ev.hit
            if not self.by_me(h):
                return
            for kind in DOT_TYPES:
                if kind not in self.granted and h.target.has_tag(kind):
                    self.granted.add(kind)
                    self.buff(
                        self.char,
                        Modifier(
                            "Prophet",
                            stats={S.ATK_PCT: self.p(1), f"{S.DEF_IGNORE}:{DmgTag.DOT}": self.p(2)},
                            stacking=Stacking.STACK,
                            max_stacks=int(self.p(3)),
                            tick=Tick.NONE,
                        ),
                    )

        self.on(E.AFTER_HIT, after_hit)


@register_lc
class AlongThePassingShore(_LC):
    lc_id = "23024"

    def setup(self) -> None:
        def before_hit(ev: E.Ev) -> None:
            h = ev.hit
            if not self.by_me(h):
                return
            t = h.target
            # Mirage Fizzle lands on hit (once per target per attack) and already counts for that hit
            if h.action is not None and h.action.owner is self.char and t.alive and self.first_on(h.action, t):
                self.buff(t, Modifier("Mirage Fizzle", duration=ONE_TURN, kind=ModKind.DEBUFF))
            if t.has_mod("Mirage Fizzle"):
                h.add(S.DMG_PCT, self.p(1))
                h.add(f"{S.DMG_PCT}:{DmgTag.ULT}", self.p(2))

        self.on(E.BEFORE_HIT, before_hit)


@register_lc
class ThoseManySprings(_LC):
    lc_id = "23029"

    def setup(self) -> None:
        me = self.char

        def mine(t: Entity, name: str) -> Modifier | None:
            return next((m for m in t.mods(name) if m.source is me), None)

        def on_end(ev: E.Ev) -> None:
            act = ev.action
            if not self.used(act, *ABILITY_TAG) or not act.is_attack:
                return
            dur = int(self.p(3))
            for t in act.attacked:
                if not t.alive or mine(t, "Cornered") is not None:
                    continue  # "during this period, the wearer cannot inflict Unarmored"
                self.battle.try_debuff(
                    Modifier("Unarmored", stats={S.VULN: self.p(2)}, duration=dur, kind=ModKind.DEBUFF),
                    t,
                    me,
                    self.p(1),
                )
                unarmored = mine(t, "Unarmored")
                if unarmored is not None and _dot_from(t, me):
                    cornered = Modifier(
                        "Cornered", stats={S.VULN: self.p(2) + self.p(5)}, duration=dur, kind=ModKind.DEBUFF
                    )
                    if self.battle.try_debuff(cornered, t, me, self.p(4)) is not None:
                        self.battle.remove_modifier(unarmored)

        self.on(E.ACTION_END, on_end)


@register_lc
class LongRoadLeadsHome(_LC):
    lc_id = "23035"

    def setup(self) -> None:
        def on_break(ev: E.Ev) -> None:
            t = ev.target
            if t.alive:
                self.battle.try_debuff(
                    Modifier(
                        "Charring",
                        stats={f"{S.VULN}:{DmgTag.BREAK}": self.p(2)},
                        duration=int(self.p(3)),
                        kind=ModKind.DEBUFF,
                        stacking=Stacking.STACK,
                        max_stacks=int(self.p(4)),
                    ),
                    t,
                    self.char,
                    self.p(1),
                )

        self.on(E.BREAK, on_break)


@register_lc
class LiesDanceOnTheBreeze(_LC):
    lc_id = "23043"

    def setup(self) -> None:
        def on_attack(ev: E.Ev) -> None:
            if ev.attack.owner is not self.char:
                return
            dur = int(self.p(3))
            theft = self.char.spd >= self.p(6) - 1e-9
            for t in self.battle.alive_enemies():
                # "only the most recently inflicted instance takes effect": one shared key per state
                self.battle.try_debuff(
                    Modifier(
                        "Bamboozle",
                        stats={S.DEF_REDUCTION: self.p(2)},
                        duration=dur,
                        kind=ModKind.DEBUFF,
                        key="Bamboozle",
                    ),
                    t,
                    self.char,
                    self.p(1),
                )
                if theft:
                    self.battle.try_debuff(
                        Modifier(
                            "Theft", stats={S.DEF_REDUCTION: self.p(5)}, duration=dur, kind=ModKind.DEBUFF, key="Theft"
                        ),
                        t,
                        self.char,
                        self.p(4),
                    )

        self.on(E.ATTACK_END, on_attack)


@register_lc
class WhyDoesTheOceanSing(_LC):
    lc_id = "23047"

    def setup(self) -> None:
        # not modelled: "removes all Enthrallment when the wearer is knocked down" (allies do not die)
        me = self.char
        name = "Enthrallment"

        def dot_taken(mod: Modifier, key: str, ent: Entity) -> float:
            n = sum(1 for m in ent.debuffs if m.source is me and m is not mod)
            return self.p(3) * min(n, int(self.p(4)))

        def on_debuff(ev: E.Ev) -> None:
            m, t = ev.mod, ev.target
            if not m.is_debuff or m.source is not me or m.name == name or not isinstance(t, Enemy) or not t.alive:
                return
            self.battle.try_debuff(
                Modifier(
                    name,
                    duration=int(self.p(2)),
                    kind=ModKind.DEBUFF,
                    key=name,
                    dyn=dot_taken,
                    dyn_keys={f"{S.VULN}:{DmgTag.DOT}"},
                ),
                t,
                me,
                self.p(1),
            )

        def on_attack(ev: E.Ev) -> None:
            act = ev.attack
            if _ally(act.owner) and any(t.has_mod(name) for t in act.attacked):
                self.battle.apply(
                    Modifier("Enthrallment (SPD)", stats={S.SPD_PCT: self.p(5)}, duration=int(self.p(6))), act.actor, me
                )

        self.on(E.MOD_APPLIED, on_debuff)
        self.on(E.ATTACK_END, on_attack)


@register_lc
class NeverForgetHerFlame(_LC):
    lc_id = "23050"

    def setup(self) -> None:
        self.sp_ready = True

        def start(ev: E.Ev) -> None:
            # the teammate who triggered combat is unknown: lc_options {"partner": name}, else highest Break Effect
            mates = [c for c in self.battle.allies() if c is not self.char and isinstance(c, Character)]
            partner = next((c for c in mates if c.name == self.opts.get("partner")), None)
            if partner is None and mates:
                partner = max(mates, key=lambda c: c.stat(S.BREAK_EFFECT))
            for c in [self.char] + ([partner] if partner is not None else []):
                self.passive(
                    "Never Forget Her Flame", {S.BREAK_DMG_PCT: self.p(1)}, target=c, key="Never Forget Her Flame"
                )

        def on_mod(ev: E.Ev) -> None:
            m = ev.mod
            if self.sp_ready and m.source is self.char and any(tag.startswith("weak:") for tag in m.tags):
                self.sp_ready = False
                self.battle.gain_sp(ONE_SP, self.char)

        def on_ult(ev: E.Ev) -> None:
            if self.used(ev.action, ActionKind.ULT):
                self.sp_ready = True

        self.on(E.BATTLE_START, start)
        self.on(E.MOD_APPLIED, on_mod)
        self.on(E.ACTION_START, on_ult)


class _Purgatory(Modifier):
    """Hits on the holder get +CRIT DMG, more when they come from the source (the wearer)."""

    def on_apply(self, battle: Battle) -> None:
        def before_hit(ev: E.Ev) -> None:
            h = ev.hit
            if h.target is self.holder:
                h.add(S.CRIT_DMG, self.data["all"] + (self.data["own"] if h.credited is self.source else 0.0))

        self.listen(E.BEFORE_HIT, before_hit)


@register_lc
class ReforgedInHellfire(_LC):
    lc_id = "23059"

    def setup(self) -> None:
        self.energy_wave = -1

        def turn_start(ev: E.Ev) -> None:
            if ev.entity is self.char and self.energy_wave != self.battle.wave_index:
                self.energy_wave = self.battle.wave_index
                self.battle.gain_energy(self.char, self.p(1), fixed=True)

        def on_skill(ev: E.Ev) -> None:
            act = ev.action
            if not self.used(act, ActionKind.SKILL) or not act.is_attack:
                return
            target = act.target if isinstance(act.target, Enemy) and act.target in act.attacked else None
            target = target or next(iter(act.attacked), None)
            if target is not None and target.alive:
                mod = _Purgatory("Purgatory", duration=int(self.p(2)), kind=ModKind.DEBUFF)
                mod.data.update({"all": self.p(3), "own": self.p(4)})
                self.buff(target, mod)

        self.on(E.TURN_START, turn_start)
        self.on(E.ACTION_END, on_skill)


@register_lc
class SolitaryHealing(_LC):
    lc_id = "24003"

    def setup(self) -> None:
        self.on(
            E.ACTION_START,
            lambda ev: self.used(ev.action, ActionKind.ULT)
            and self.buff(
                self.char,
                Modifier("Solitary Healing", stats={f"{S.DMG_PCT}:{DmgTag.DOT}": self.p(1)}, duration=int(self.p(2))),
            ),
        )

        def on_kill(ev: E.Ev) -> None:
            if _dot_from(ev.target, self.char):
                self.battle.gain_energy(self.char, self.p(3))

        self.on(E.KILL, on_kill)


@register_lc
class GoodNightAndSleepWell(_LC):
    lc_id = "21001"

    def setup(self) -> None:
        def before_hit(ev: E.Ev) -> None:
            h = ev.hit
            if self.by_me(h):
                h.add(S.DMG_PCT, self.p(0) * min(len(h.target.debuffs), int(self.p(1))))

        self.on(E.BEFORE_HIT, before_hit)


@register_lc
class EyesOfThePrey(_LC):
    lc_id = "21008"

    def setup(self) -> None:
        self.passive("Eyes of the Prey", {f"{S.DMG_PCT}:{DmgTag.DOT}": self.p(1)})


@register_lc
class ResolutionShinesAsPearlsOfSweat(_LC):
    lc_id = "21015"

    def setup(self) -> None:
        def after_hit(ev: E.Ev) -> None:
            h = ev.hit
            t = h.target
            if h.action is None or h.action.owner is not self.char or not t.alive or t.has_mod("Ensnared"):
                return
            if self.first_on(h.action, t):
                self.battle.try_debuff(
                    Modifier(
                        "Ensnared", stats={S.DEF_REDUCTION: self.p(1)}, duration=int(self.p(2)), kind=ModKind.DEBUFF
                    ),
                    t,
                    self.char,
                    self.p(0),
                )

        self.on(E.AFTER_HIT, after_hit)


@register_lc
class Fermata(_LC):
    lc_id = "21022"

    def setup(self) -> None:
        def before_hit(ev: E.Ev) -> None:
            h = ev.hit
            if self.by_me(h) and (h.target.has_tag("shock") or h.target.has_tag("wind_shear")):
                h.add(S.DMG_PCT, self.p(1))

        self.on(E.BEFORE_HIT, before_hit)


@register_lc
class WeWillMeetAgain(_LC):
    lc_id = "21029"

    def setup(self) -> None:
        def on_end(ev: E.Ev) -> None:
            act = ev.action
            if not self.used(act, ActionKind.BASIC, ActionKind.SKILL):
                return
            cands = [t for t in act.attacked if t.alive and t.hp > 0]
            if cands:
                t = self.battle.rng.choice(cands)
                self.battle.additional_damage(self.char, t, self.p(0), label="We Will Meet Again")

        self.on(E.ACTION_END, on_end)


@register_lc
class ItsShowtime(_LC):
    lc_id = "21041"

    def setup(self) -> None:
        self.passive(
            "It's Showtime (ATK)",
            {},
            dyn_keys={S.ATK_PCT},
            dyn=lambda m, k, e: self.p(4) if self.char.stat(S.EHR) >= self.p(3) - 1e-9 else 0.0,
        )

        def on_debuff(ev: E.Ev) -> None:
            m = ev.mod
            if m.is_debuff and m.source is self.char and isinstance(ev.target, Enemy):
                self.buff(
                    self.char,
                    Modifier(
                        "Trick",
                        stats={S.DMG_PCT: self.p(0)},
                        duration=int(self.p(2)),
                        stacking=Stacking.STACK,
                        max_stacks=int(self.p(1)),
                    ),
                )

        self.on(E.MOD_APPLIED, on_debuff)


@register_lc
class BoundlessChoreo(_LC):
    lc_id = "21044"

    def setup(self) -> None:
        def before_hit(ev: E.Ev) -> None:
            h = ev.hit
            if self.by_me(h) and (_slowed(h.target) or _def_reduced(h.target)):
                h.add(S.CRIT_DMG, self.p(1))

        self.on(E.BEFORE_HIT, before_hit)


@register_lc
class HolidayThermaeEscapade(_LC):
    lc_id = "21061"

    def setup(self) -> None:
        def on_attack(ev: E.Ev) -> None:
            if ev.attack.owner is not self.char:
                return
            for t in ev.attack.attacked:
                if t.alive:
                    self.battle.try_debuff(
                        Modifier(
                            "Vulnerability (Holiday Thermae Escapade)",
                            stats={S.VULN: self.p(2)},
                            duration=int(self.p(3)),
                            kind=ModKind.DEBUFF,
                            key="Holiday Thermae Escapade",
                        ),
                        t,
                        self.char,
                        self.p(1),
                    )

        self.on(E.ATTACK_END, on_attack)


@register_lc
class BeforeTheTutorialMissionStarts(_LC):
    lc_id = "22000"

    def setup(self) -> None:
        def on_attack(ev: E.Ev) -> None:
            if ev.attack.owner is self.char and any(_def_reduced(t) for t in ev.attack.attacked):
                self.battle.gain_energy(self.char, self.p(1))

        self.on(E.ATTACK_END, on_attack)


@register_lc
class Void(_LC):
    lc_id = "20004"

    def setup(self) -> None:
        self.on(
            E.BATTLE_START,
            lambda ev: self.buff(self.char, Modifier("Void", stats={S.EHR: self.p(0)}, duration=int(self.p(1)))),
        )


@register_lc
class Loop(_LC):
    lc_id = "20011"

    def setup(self) -> None:
        def before_hit(ev: E.Ev) -> None:
            h = ev.hit
            if self.by_me(h) and _slowed(h.target):
                h.add(S.DMG_PCT, self.p(0))

        self.on(E.BEFORE_HIT, before_hit)


@register_lc
class HiddenShadow(_LC):
    lc_id = "20018"

    def setup(self) -> None:
        self.armed = False

        def on_end(ev: E.Ev) -> None:
            act = ev.action
            if self.used(act, ActionKind.SKILL):
                self.armed = True
            elif self.used(act, ActionKind.BASIC) and self.armed:
                target = act.target if isinstance(act.target, Enemy) and act.target.alive else None
                target = target or next((t for t in act.attacked if t.alive), None)
                if target is not None:
                    self.armed = False
                    self.battle.additional_damage(self.char, target, self.p(0), label="Hidden Shadow")

        self.on(E.ACTION_END, on_end)
