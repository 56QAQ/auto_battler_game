"""Conditional effects of relic sets and planar ornaments.

Unconditional stats (e.g. "ATK +12%") are applied from the data by the build
code; the classes below only add what depends on combat state. Parameters are
read from the data (``self.p(pieces, i)``) so they track the game files.
"""

from __future__ import annotations

from typing import Any

from .. import events as E
from .. import stats as S
from ..entities import Character, Enemy, Entity, Summon
from ..enums import ActionKind, DmgTag, Element, Side
from ..equipment import RelicSet, register_relic
from ..modifiers import Modifier, Stacking, Tick, hidden


def _ally(e: Entity) -> bool:
    return e.side == Side.ALLY


def _memosprite_of(c: Character) -> Summon | None:
    for s in c.summons:
        if s.alive and s.is_memosprite:
            return s
    return None


def _def_reduced(e: Entity) -> bool:
    return any(m.is_debuff and (S.DEF_REDUCTION in m.stats or "def_reduction" in m.tags) for m in e.modifiers)


class _Set(RelicSet):
    def passive(self, name: str, stats: dict[str, float] | None = None, target: Entity | None = None,
                **kw: Any) -> Modifier:
        return self.battle.apply(hidden(name, stats, **kw), target or self.char, self.char)

    def buff(self, target: Entity, mod: Modifier) -> Modifier:
        return self.battle.apply(mod, target, self.char)

    def mine(self, act: Any) -> bool:
        return act.owner is self.char


# ----------------------------------------------------------------- 4-piece relics
@register_relic
class Musketeer(_Set):
    set_id = "102"

    def setup(self) -> None:
        if self.pieces >= 4:
            self.passive("Musketeer 4pc", {f"{S.DMG_PCT}:{DmgTag.BASIC}": self.p(4, 1)})


@register_relic
class Hunter(_Set):
    set_id = "104"

    def setup(self) -> None:
        if self.pieces >= 4:
            self.on(E.ACTION_END, lambda ev: self.mine(ev.action) and ev.action.kind == ActionKind.ULT and self.buff(
                self.char, Modifier("Hunter 4pc", stats={S.CRIT_DMG: self.p(4, 0)}, duration=int(self.p(4, 1)))))


@register_relic
class Champion(_Set):
    set_id = "105"

    def setup(self) -> None:
        if self.pieces >= 4:
            def stack(ev: E.Ev) -> None:
                self.buff(self.char, Modifier("Champion 4pc", stats={S.ATK_PCT: self.p(4, 0)}, stacking=Stacking.STACK,
                                              max_stacks=int(self.p(4, 1)), tick=Tick.NONE))

            self.on(E.ATTACK_END, lambda ev: self.mine(ev.attack) and stack(ev))
            self.on(E.ALLY_ATTACKED, lambda ev: self.char in ev.targets and stack(ev))


@register_relic
class GuardOfWutheringSnow(_Set):
    set_id = "106"

    def setup(self) -> None:
        self.passive("Guard 2pc", {S.MITIGATION: self.p(2, 0)})


@register_relic
class Firesmith(_Set):
    set_id = "107"

    def setup(self) -> None:
        if self.pieces >= 4:
            self.passive("Firesmith 4pc", {f"{S.DMG_PCT}:{DmgTag.SKILL}": self.p(4, 0)})

            def after_ult(ev: E.Ev) -> None:
                if self.mine(ev.action) and ev.action.kind == ActionKind.ULT:
                    self.char.data_flags["firesmith"] = True

            def before_hit(ev: E.Ev) -> None:
                h = ev.hit
                if h.attacker is self.char and self.char.data_flags.get("firesmith") and h.action is not None:
                    h.add(f"{S.DMG_PCT}:Fire", self.p(4, 1))

            def attack_end(ev: E.Ev) -> None:
                if self.mine(ev.attack) and ev.attack.kind != ActionKind.ULT:
                    self.char.data_flags.pop("firesmith", None)

            self.on(E.ACTION_END, after_ult)
            self.on(E.BEFORE_HIT, before_hit)
            self.on(E.ATTACK_END, attack_end)


@register_relic
class Genius(_Set):
    set_id = "108"

    def setup(self) -> None:
        if self.pieces >= 4:
            def before_hit(ev: E.Ev) -> None:
                h = ev.hit
                if h.attacker is self.char:
                    ign = self.p(4, 0) + (self.p(4, 1) if h.target.is_weak_to(Element.QUANTUM) else 0.0)
                    h.add(S.DEF_IGNORE, ign)

            self.on(E.BEFORE_HIT, before_hit)


@register_relic
class BandOfSizzlingThunder(_Set):
    set_id = "109"

    def setup(self) -> None:
        if self.pieces >= 4:
            self.on(E.ACTION_START, lambda ev: self.mine(ev.action) and ev.action.kind == ActionKind.SKILL and self.buff(
                self.char, Modifier("Band 4pc", stats={S.ATK_PCT: self.p(4, 0)}, duration=int(self.p(4, 1)))))


@register_relic
class Eagle(_Set):
    set_id = "110"

    def setup(self) -> None:
        if self.pieces >= 4:
            self.on(E.ACTION_END, lambda ev: self.mine(ev.action) and ev.action.kind == ActionKind.ULT
                    and self.battle.advance(self.char, self.p(4, 0)))


@register_relic
class Thief(_Set):
    set_id = "111"

    def setup(self) -> None:
        if self.pieces >= 4:
            self.on(E.BREAK, lambda ev: ev.credited is self.char and self.battle.gain_energy(self.char, self.p(4, 1)))


@register_relic
class Wastelander(_Set):
    set_id = "112"

    def setup(self) -> None:
        if self.pieces >= 4:
            def before_hit(ev: E.Ev) -> None:
                h = ev.hit
                if h.attacker is self.char and h.target.debuffs:
                    h.add(S.CRIT_RATE, self.p(4, 0))
                    if h.target.has_tag("imprisonment"):
                        h.add(S.CRIT_DMG, self.p(4, 1))

            self.on(E.BEFORE_HIT, before_hit)


@register_relic
class Longevous(_Set):
    set_id = "113"

    def setup(self) -> None:
        if self.pieces >= 4:
            def on_hp(ev: E.Ev) -> None:
                if ev.entity is self.char and ev.delta < 0:
                    self.buff(self.char, Modifier("Longevous 4pc", stats={S.CRIT_RATE: self.p(4, 0)},
                                                  duration=int(self.p(4, 1)), stacking=Stacking.STACK,
                                                  max_stacks=int(self.p(4, 2))))

            self.on(E.HP_CHANGED, on_hp)


@register_relic
class Messenger(_Set):
    set_id = "114"

    def setup(self) -> None:
        if self.pieces >= 4:
            def after_ult(ev: E.Ev) -> None:
                act = ev.action
                kit = getattr(self.char, "kit", None)
                if self.mine(act) and act.kind == ActionKind.ULT and getattr(kit, "ult_targets_ally", False):
                    for c in self.battle.allies():
                        self.battle.apply(Modifier("Messenger 4pc", stats={S.SPD_PCT: self.p(4, 0)},
                                                   duration=int(self.p(4, 1)), key="Messenger 4pc"), c, self.char)

            self.on(E.ACTION_END, after_ult)


@register_relic
class Ashblazing(_Set):
    set_id = "115"

    def setup(self) -> None:
        self.passive("Ashblazing 2pc", {f"{S.DMG_PCT}:{DmgTag.FUA}": self.p(2, 0)})
        if self.pieces >= 4:
            def start(ev: E.Ev) -> None:
                if self.mine(ev.action) and ev.action.kind == ActionKind.FUA:
                    self.battle.remove_named(self.char, "Ashblazing 4pc")

            def after_hit(ev: E.Ev) -> None:
                h = ev.hit
                if h.action is not None and self.mine(h.action) and h.action.kind == ActionKind.FUA and h.primary:
                    self.buff(self.char, Modifier("Ashblazing 4pc", stats={S.ATK_PCT: self.p(4, 0)},
                                                  duration=int(self.p(4, 2)), stacking=Stacking.STACK,
                                                  max_stacks=int(self.p(4, 1))))

            self.on(E.ACTION_START, start)
            self.on(E.AFTER_HIT, after_hit)


@register_relic
class Prisoner(_Set):
    set_id = "116"

    def setup(self) -> None:
        if self.pieces >= 4:
            def before_hit(ev: E.Ev) -> None:
                h = ev.hit
                if h.attacker is self.char:
                    n = len(h.target.mods(tag="dot"))
                    h.add(S.DEF_IGNORE, self.p(4, 0) * min(n, int(self.p(4, 1))))

            self.on(E.BEFORE_HIT, before_hit)


@register_relic
class PioneerDiver(_Set):
    set_id = "117"

    def setup(self) -> None:
        def before_hit(ev: E.Ev) -> None:
            h = ev.hit
            if h.attacker is not self.char:
                return
            n = len(h.target.debuffs)
            if n:
                h.add(S.DMG_PCT, self.p(2, 0))
            if self.pieces >= 4:
                mult = 2.0 if self.char.has_mod("Pioneer 4pc boost") else 1.0
                if n >= self.p(4, 4):
                    h.add(S.CRIT_DMG, self.p(4, 2) * mult)
                elif n >= self.p(4, 3):
                    h.add(S.CRIT_DMG, self.p(4, 1) * mult)

        def on_debuff(ev: E.Ev) -> None:
            m = ev.mod
            if m.is_debuff and m.source is self.char and isinstance(ev.target, Enemy):
                self.buff(self.char, Modifier("Pioneer 4pc boost", duration=int(self.p(4, 5))))

        self.on(E.BEFORE_HIT, before_hit)
        if self.pieces >= 4:
            self.on(E.MOD_APPLIED, on_debuff)


@register_relic
class Watchmaker(_Set):
    set_id = "118"

    def setup(self) -> None:
        if self.pieces >= 4:
            def after_ult(ev: E.Ev) -> None:
                act = ev.action
                kit = getattr(self.char, "kit", None)
                if self.mine(act) and act.kind == ActionKind.ULT and getattr(kit, "ult_targets_ally", False):
                    for c in self.battle.allies():
                        self.battle.apply(Modifier("Watchmaker 4pc", stats={S.BREAK_EFFECT: self.p(4, 0)},
                                                   duration=int(self.p(4, 1)), key="Watchmaker 4pc"), c, self.char)

            self.on(E.ACTION_END, after_ult)


@register_relic
class IronCavalry(_Set):
    set_id = "119"

    def setup(self) -> None:
        if self.pieces >= 4:
            def dyn(mod: Modifier, key: str, ent: Entity) -> float:
                be = self.char.stat(S.BREAK_EFFECT)
                if key == f"{S.DEF_IGNORE}:{DmgTag.BREAK}":
                    return self.p(4, 2) if be >= self.p(4, 0) else 0.0
                return self.p(4, 3) if be >= self.p(4, 1) else 0.0

            self.passive("Iron Cavalry 4pc", {}, dyn=dyn,
                         dyn_keys={f"{S.DEF_IGNORE}:{DmgTag.BREAK}", f"{S.DEF_IGNORE}:{DmgTag.SUPER_BREAK}"})


@register_relic
class WindSoaring(_Set):
    set_id = "120"

    def setup(self) -> None:
        if self.pieces >= 4:
            self.on(E.ACTION_END, lambda ev: self.mine(ev.action) and ev.action.kind == ActionKind.FUA and self.buff(
                self.char, Modifier("Wind-Soaring 4pc", stats={f"{S.DMG_PCT}:{DmgTag.ULT}": self.p(4, 1)},
                                    duration=int(self.p(4, 2)))))


@register_relic
class Sacerdos(_Set):
    set_id = "121"

    def setup(self) -> None:
        if self.pieces >= 4:
            def on_action(ev: E.Ev) -> None:
                act = ev.action
                t = act.target
                if self.mine(act) and act.kind in (ActionKind.SKILL, ActionKind.ULT) and isinstance(t, Character):
                    self.battle.apply(Modifier("Sacerdos 4pc", stats={S.CRIT_DMG: self.p(4, 0)},
                                               duration=int(self.p(4, 1)), stacking=Stacking.STACK,
                                               max_stacks=int(self.p(4, 2)), key="Sacerdos 4pc"), t, self.char)

            self.on(E.ACTION_START, on_action)


@register_relic
class Scholar(_Set):
    set_id = "122"

    def setup(self) -> None:
        if self.pieces >= 4:
            self.passive("Scholar 4pc", {f"{S.DMG_PCT}:{DmgTag.SKILL}": self.p(4, 0),
                                         f"{S.DMG_PCT}:{DmgTag.ULT}": self.p(4, 0)})

            def on_end(ev: E.Ev) -> None:
                act = ev.action
                if not self.mine(act):
                    return
                if act.kind == ActionKind.ULT:
                    self.buff(self.char, hidden("Scholar next Skill", {f"{S.DMG_PCT}:{DmgTag.SKILL}": self.p(4, 1)}))
                elif act.kind == ActionKind.SKILL:
                    self.battle.remove_named(self.char, "Scholar next Skill")

            self.on(E.ACTION_END, on_end)


@register_relic
class HeroOfTriumphantSong(_Set):
    set_id = "123"

    def setup(self) -> None:
        if self.pieces >= 4:
            self.passive("Hero 4pc SPD", {}, dyn=lambda m, k, e: self.p(4, 0) if _memosprite_of(self.char) else 0.0,
                         dyn_keys={S.SPD_PCT})

            def on_attack(ev: E.Ev) -> None:
                act = ev.attack
                if isinstance(act.actor, Summon) and act.actor.owner is self.char and act.actor.is_memosprite:
                    self.buff(self.char, Modifier("Hero 4pc CRIT DMG", stats={S.CRIT_DMG: self.p(4, 1)},
                                                  duration=int(self.p(4, 2))))

            self.on(E.ATTACK_END, on_attack)


@register_relic
class Poet(_Set):
    set_id = "124"

    def setup(self) -> None:
        if self.pieces >= 4:
            spd = self.char.spd
            cr = self.p(4, 4) if spd < self.p(4, 2) else (self.p(4, 3) if spd < self.p(4, 1) else 0.0)
            if cr:
                self.passive("Poet 4pc", {S.CRIT_RATE: cr})


@register_relic
class WarriorGoddess(_Set):
    set_id = "125"

    def setup(self) -> None:
        if self.pieces >= 4:
            def on_heal(ev: E.Ev) -> None:
                src = ev.source
                owner = src.owner if isinstance(src, Summon) else src
                if owner is self.char and ev.delta > 0 and ev.entity is not src:
                    self.buff(self.char, Modifier("Gentle Rain", stats={S.SPD_PCT: self.p(4, 0)},
                                                  duration=int(self.p(4, 2))))
                    self.battle.apply(Modifier("Gentle Rain (team)", stats={S.CRIT_DMG: self.p(4, 1)},
                                               duration=int(self.p(4, 2)), scope=_ally, key="Gentle Rain team"),
                                      self.char, self.char)

            self.on(E.HP_CHANGED, on_heal)


@register_relic
class Wavestrider(_Set):
    set_id = "126"

    def setup(self) -> None:
        if self.pieces >= 4:
            self.help = 0

            def on_action(ev: E.Ev) -> None:
                act = ev.action
                if act.target is self.char and act.owner is not self.char and act.owner.side == Side.ALLY:
                    self.help = min(int(self.p(4, 0)), self.help + 1)
                if self.mine(act) and act.kind == ActionKind.ULT and self.help >= self.p(4, 0):
                    self.help = 0
                    self.buff(self.char, Modifier("Wavestrider 4pc", stats={S.ATK_PCT: self.p(4, 1)},
                                                  duration=int(self.p(4, 2))))

            self.on(E.ACTION_START, on_action)


@register_relic
class WorldRemaking(_Set):
    set_id = "127"

    def setup(self) -> None:
        if self.pieces >= 4:
            def on_end(ev: E.Ev) -> None:
                act = ev.action
                if not self.mine(act) or act.kind not in (ActionKind.BASIC, ActionKind.SKILL):
                    return
                self.battle.remove_named(self.char, "World-Remaking 4pc")
                if _memosprite_of(self.char):
                    self.battle.apply(hidden("World-Remaking 4pc", {S.DMG_PCT: self.p(4, 1)}, scope=_ally),
                                      self.char, self.char)
                    self.buff(self.char, hidden("World-Remaking 4pc HP", {S.HP_PCT: self.p(4, 0)}))

            self.on(E.ACTION_END, on_end)


@register_relic
class SelfEnshroudedRecluse(_Set):
    set_id = "128"

    def setup(self) -> None:
        if self.pieces >= 4:
            def dyn(mod: Modifier, key: str, ent: Entity) -> float:
                shielded = any("shield" in m.tags and m.source is self.char for m in ent.modifiers)
                return self.p(4, 1) if shielded else 0.0

            self.passive("Recluse 4pc", {}, scope=_ally, dyn=dyn, dyn_keys={S.CRIT_DMG})


@register_relic
class MagicalGirl(_Set):
    set_id = "129"

    def setup(self) -> None:
        if self.pieces >= 4:
            self.passive("Magical Girl 4pc", {f"{S.DEF_IGNORE}:{DmgTag.ELATION}": self.p(4, 0)})


@register_relic
class Diviner(_Set):
    set_id = "130"

    def setup(self) -> None:
        if self.pieces >= 4:
            spd = self.char.spd
            cr = self.p(4, 3) if spd >= self.p(4, 1) else (self.p(4, 2) if spd >= self.p(4, 0) else 0.0)
            if cr:
                self.passive("Diviner 4pc", {S.CRIT_RATE: cr})


@register_relic
class Isee(_Set):
    set_id = "131"

    def setup(self) -> None:
        if self.pieces >= 4:
            def add() -> None:
                self.buff(self.char, Modifier(
                    "Isee 4pc", stats={f"{S.DMG_PCT}:{DmgTag.SKILL}": self.p(4, 0), f"{S.DMG_PCT}:{DmgTag.ULT}": self.p(4, 0)},
                    stacking=Stacking.STACK, max_stacks=int(self.p(4, 1)), tick=Tick.NONE))

            def remove_one() -> None:
                m = self.char.get_mod("Isee 4pc")
                if m is not None:
                    m.stacks -= int(self.p(4, 2))
                    if m.stacks <= 0:
                        self.battle.remove_modifier(m)

            self.on(E.BATTLE_START, lambda ev: add())
            self.on(E.ACTION_START, lambda ev: self.mine(ev.action) and ev.action.kind == ActionKind.SKILL and add())
            self.on(E.ACTION_END, lambda ev: self.mine(ev.action) and ev.action.kind == ActionKind.ULT and remove_one())
            self.on(E.TURN_START, lambda ev: ev.entity is self.char and remove_one())


@register_relic
class MasterSmith(_Set):
    set_id = "132"

    def setup(self) -> None:
        if self.pieces >= 4:
            self.comburent_ready = True

            def before_hit(ev: E.Ev) -> None:
                h = ev.hit
                if h.attacker is self.char and _def_reduced(h.target):
                    h.add(S.CRIT_DMG, self.p(4, 0))

            def on_debuff(ev: E.Ev) -> None:
                m = ev.mod
                if (self.comburent_ready and m.source is self.char and m.is_debuff and isinstance(ev.target, Enemy)
                        and (S.DEF_REDUCTION in m.stats)):
                    self.comburent_ready = False
                    self.battle.apply(Modifier("Comburent", stats={S.DMG_PCT: self.p(4, 2)},
                                               duration=int(self.p(4, 1)), tick=Tick.SOURCE_TURN_END,
                                               scope=_ally, key="Comburent"), self.char, self.char)

            def after_attack(ev: E.Ev) -> None:
                if self.mine(ev.attack):
                    self.comburent_ready = True

            self.on(E.BEFORE_HIT, before_hit)
            self.on(E.MOD_APPLIED, on_debuff)
            self.on(E.ATTACK_END, after_attack)


@register_relic
class EdaciousHeretic(_Set):
    set_id = "134"

    def setup(self) -> None:
        if self.pieces >= 4:
            self.passive("Heretic 4pc", {f"{S.DMG_PCT}:{DmgTag.BASIC}": self.p(4, 0)})
            self.on(E.ACTION_START, lambda ev: self.mine(ev.action) and ev.action.kind == ActionKind.BASIC and self.buff(
                self.char, Modifier("Heretic 4pc ATK", stats={S.ATK_PCT: self.p(4, 1)}, duration=int(self.p(4, 2)))))


# ------------------------------------------------------------------ planar ornaments
def _threshold(stat: str, value: float, bonus: dict[str, float], char: Character) -> Any:
    def dyn(mod: Modifier, key: str, ent: Entity) -> float:
        cur = char.spd if stat == "spd" else char.max_hp if stat == "hp" else char.stat(stat)
        return bonus.get(key, 0.0) if cur >= value - 1e-9 else 0.0

    return dyn


@register_relic
class SpaceSealingStation(_Set):
    set_id = "301"

    def setup(self) -> None:
        self.passive("Space Sealing 2pc", {}, dyn=_threshold("spd", self.p(2, 1), {S.ATK_PCT: self.p(2, 2)}, self.char),
                     dyn_keys={S.ATK_PCT})


@register_relic
class FleetOfTheAgeless(_Set):
    set_id = "302"

    def setup(self) -> None:
        self.passive("Fleet 2pc", {}, scope=_ally, key="Fleet 2pc",
                     dyn=_threshold("spd", self.p(2, 1), {S.ATK_PCT: self.p(2, 2)}, self.char), dyn_keys={S.ATK_PCT})


@register_relic
class PanCosmic(_Set):
    set_id = "303"

    def setup(self) -> None:
        self.passive("Pan-Cosmic 2pc", {}, dyn=lambda m, k, e: min(self.p(2, 2), self.p(2, 1) * self.char.stat(S.EHR)),
                     dyn_keys={S.ATK_PCT})


@register_relic
class Belobog(_Set):
    set_id = "304"

    def setup(self) -> None:
        self.passive("Belobog 2pc", {}, dyn=_threshold(S.EHR, self.p(2, 1), {S.DEF_PCT: self.p(2, 2)}, self.char),
                     dyn_keys={S.DEF_PCT})


@register_relic
class CelestialDifferentiator(_Set):
    set_id = "305"

    def setup(self) -> None:
        if self.char.stat(S.CRIT_DMG) >= self.p(2, 1) - 1e-9:
            mod = self.passive("Celestial Differentiator", {S.CRIT_RATE: self.p(2, 2)})
            self.on(E.ATTACK_END, lambda ev: self.mine(ev.attack) and self.battle.remove_modifier(mod))


@register_relic
class InertSalsotto(_Set):
    set_id = "306"

    def setup(self) -> None:
        bonus = {f"{S.DMG_PCT}:{DmgTag.ULT}": self.p(2, 2), f"{S.DMG_PCT}:{DmgTag.FUA}": self.p(2, 2)}
        self.passive("Inert Salsotto 2pc", {}, dyn=_threshold(S.CRIT_RATE, self.p(2, 1), bonus, self.char),
                     dyn_keys=set(bonus))


@register_relic
class Talia(_Set):
    set_id = "307"

    def setup(self) -> None:
        self.passive("Talia 2pc", {}, dyn=_threshold("spd", self.p(2, 1), {S.BREAK_EFFECT: self.p(2, 2)}, self.char),
                     dyn_keys={S.BREAK_EFFECT})


@register_relic
class Vonwacq(_Set):
    set_id = "308"

    def setup(self) -> None:
        if self.char.spd >= self.p(2, 1) - 1e-9:
            self.on(E.BATTLE_START, lambda ev: self.battle.advance(self.char, self.p(2, 2)))


@register_relic
class RutilantArena(_Set):
    set_id = "309"

    def setup(self) -> None:
        bonus = {f"{S.DMG_PCT}:{DmgTag.BASIC}": self.p(2, 2), f"{S.DMG_PCT}:{DmgTag.SKILL}": self.p(2, 2)}
        self.passive("Rutilant Arena 2pc", {}, dyn=_threshold(S.CRIT_RATE, self.p(2, 1), bonus, self.char),
                     dyn_keys=set(bonus))


@register_relic
class BrokenKeel(_Set):
    set_id = "310"

    def setup(self) -> None:
        self.passive("Broken Keel 2pc", {}, scope=_ally, key="Broken Keel 2pc",
                     dyn=_threshold(S.EFFECT_RES, self.p(2, 1), {S.CRIT_DMG: self.p(2, 2)}, self.char),
                     dyn_keys={S.CRIT_DMG})


@register_relic
class Glamoth(_Set):
    set_id = "311"

    def setup(self) -> None:
        def dyn(mod: Modifier, key: str, ent: Entity) -> float:
            spd = self.char.spd
            if spd >= self.p(2, 2) - 1e-9:
                return self.p(2, 4)
            return self.p(2, 3) if spd >= self.p(2, 1) - 1e-9 else 0.0

        self.passive("Glamoth 2pc", {}, dyn=dyn, dyn_keys={S.DMG_PCT})


@register_relic
class Penacony(_Set):
    set_id = "312"

    def setup(self) -> None:
        el = self.char.element
        self.passive("Penacony 2pc", {S.DMG_PCT: self.p(2, 1)}, key=f"Penacony 2pc {el.value}",
                     scope=lambda e: e.side == Side.ALLY and e is not self.char and getattr(e, "element", None) == el)


@register_relic
class Sigonia(_Set):
    set_id = "313"

    def setup(self) -> None:
        self.on(E.KILL, lambda ev: self.buff(self.char, Modifier(
            "Sigonia 2pc", stats={S.CRIT_DMG: self.p(2, 2)}, stacking=Stacking.STACK, max_stacks=int(self.p(2, 1)),
            tick=Tick.NONE)))


@register_relic
class Izumo(_Set):
    set_id = "314"

    def setup(self) -> None:
        if any(c is not self.char and c.path == self.char.path for c in self.battle.team):
            self.passive("Izumo 2pc", {S.CRIT_RATE: self.p(2, 1)})


@register_relic
class Duran(_Set):
    set_id = "315"

    def setup(self) -> None:
        def on_fua(ev: E.Ev) -> None:
            act = ev.action
            if act.kind != ActionKind.FUA or not isinstance(act.owner, Character):
                return
            m = self.buff(self.char, Modifier("Merit", stats={f"{S.DMG_PCT}:{DmgTag.FUA}": self.p(2, 1)},
                                              stacking=Stacking.STACK, max_stacks=int(self.p(2, 0)), tick=Tick.NONE))
            if m.stacks >= self.p(2, 0):
                self.buff(self.char, hidden("Merit (max)", {S.CRIT_DMG: self.p(2, 2)}))

        self.on(E.ACTION_START, on_fua)


@register_relic
class Kalpagni(_Set):
    set_id = "316"

    def setup(self) -> None:
        def on_hit(ev: E.Ev) -> None:
            h = ev.hit
            if h.attacker is self.char and h.action is not None and h.target.is_weak_to(Element.FIRE):
                self.buff(self.char, Modifier("Kalpagni 2pc", stats={S.BREAK_EFFECT: self.p(2, 1)},
                                              duration=int(self.p(2, 2))))

        self.on(E.AFTER_HIT, on_hit)


@register_relic
class Lushaka(_Set):
    set_id = "317"

    def setup(self) -> None:
        first = self.battle.team[0]
        if first is not self.char:
            self.battle.apply(hidden("Lushaka 2pc", {S.ATK_PCT: self.p(2, 1)}, key="Lushaka 2pc"), first, self.char)


@register_relic
class BananAmusementPark(_Set):
    set_id = "318"

    def setup(self) -> None:
        self.passive("Banana 2pc", {}, dyn=lambda m, k, e: self.p(2, 1) if any(s.alive for s in self.char.summons) else 0.0,
                     dyn_keys={S.CRIT_DMG})


@register_relic
class BoneCollection(_Set):
    set_id = "319"

    def setup(self) -> None:
        self.passive("Bone Collection 2pc", {}, dyn=_threshold("hp", self.p(2, 1), {S.CRIT_DMG: self.p(2, 2)}, self.char),
                     dyn_keys={S.CRIT_DMG})


@register_relic
class Arcadia(_Set):
    set_id = "321"

    def setup(self) -> None:
        def dyn(mod: Modifier, key: str, ent: Entity) -> float:
            n = len(self.battle.allies(include_summons=True))
            if n > 4:
                return self.p(2, 0) * min(n - 4, int(self.p(2, 2)))
            if n < 4:
                return self.p(2, 1) * min(4 - n, int(self.p(2, 3)))
            return 0.0

        self.passive("Arcadia 2pc", {}, dyn=dyn, dyn_keys={S.DMG_PCT})


@register_relic
class Revelry(_Set):
    set_id = "322"

    def setup(self) -> None:
        def dyn(mod: Modifier, key: str, ent: Entity) -> float:
            atk = self.char.atk
            if atk >= self.p(2, 2):
                return self.p(2, 4)
            return self.p(2, 3) if atk >= self.p(2, 1) else 0.0

        self.passive("Revelry 2pc", {}, dyn=dyn, dyn_keys={f"{S.DMG_PCT}:{DmgTag.DOT}"})


@register_relic
class Amphoreus(_Set):
    set_id = "323"

    def setup(self) -> None:
        self.passive("Amphoreus 2pc", {}, scope=_ally, key="Amphoreus 2pc",
                     dyn=lambda m, k, e: self.p(2, 1) if _memosprite_of(self.char) else 0.0, dyn_keys={S.SPD_PCT})


@register_relic
class Tengoku(_Set):
    set_id = "324"

    def setup(self) -> None:
        self.spent: dict[int, int] = {}

        def on_sp(ev: E.Ev) -> None:
            if ev.delta >= 0:
                return
            turn = self.battle.turns
            self.spent[turn] = self.spent.get(turn, 0) - ev.delta
            if self.spent[turn] >= self.p(2, 1):
                self.buff(self.char, Modifier("Tengoku 2pc", stats={S.CRIT_DMG: self.p(2, 2)}, duration=int(self.p(2, 3))))

        self.on(E.SP_CHANGED, on_sp)


@register_relic
class CityOfConvergingStars(_Set):
    set_id = "326"

    def setup(self) -> None:
        self.on(E.ACTION_START, lambda ev: self.mine(ev.action) and ev.action.kind == ActionKind.FUA and self.buff(
            self.char, Modifier("City 2pc ATK", stats={S.ATK_PCT: self.p(2, 0)}, duration=int(self.p(2, 1)))))
        self.on(E.KILL, lambda ev: self.battle.apply(hidden("City 2pc CRIT DMG", {S.CRIT_DMG: self.p(2, 2)}, scope=_ally,
                                                            key="City 2pc CRIT DMG"), self.char, self.char))


@register_relic
class CosmicLifeSciences(_Set):
    set_id = "328"

    def setup(self) -> None:
        excess = self.char.max_energy - self.p(2, 0)
        if excess >= 0:
            self.passive("Cosmic Life Sciences 2pc", {S.DMG_PCT: min(self.p(2, 2), excess * self.p(2, 1))})
