"""Yao Guang (爻光) — Elation / Physical. Elation zone, Aha extra turns, Great Boon Elation DMG."""

from __future__ import annotations

from .. import events as E
from .. import stats as S
from ..entities import Character, Enemy, Entity
from ..enums import ActionKind, DmgTag, Side
from ..modifiers import Modifier, ModKind, Tick
from . import register
from .base import Kit


@register
class YaoGuang(Kit):
    char_id = "1502"
    has_elation_skill = True
    elation_skill_id = "150220"

    def setup(self) -> None:
        self.zone: Modifier | None = None
        self.e4_turn = False
        if self.trace(1):
            self.passive("Amaze-In Grace", {}, dyn=self._a2, dyn_keys={S.ELATION_DMG_PCT})
        if self.trace(2):
            self.passive("Poised and Sated", {S.CRIT_DMG: self.tp(2, 3)})
        if self.e(1):
            self.passive("Chuckle Chimes", {f"{S.DEF_IGNORE}:{DmgTag.ELATION}": self.ep(1, 0)}, scope=self.ally_scope)
        if self.e(6):
            self.passive("Ferried Along", {S.MERRYMAKE_PCT: self.ep(6, 0)}, scope=self.ally_scope)
        self.on(E.ATTACK_END, self._great_boon)

    def technique(self) -> None:
        # MAvatar_YaoGuang_00_MazeSkill: an inserted Skill at battle start that consumes no Skill Points
        self.skill(None, sp=0)

    def banger_extra_turns(self) -> int:
        return int(self.tp(3, 1)) if self.trace(3) else 0

    def _a2(self, mod: Modifier, key: str, ent: Entity) -> float:
        spd = self.char.spd
        lo = self.tp(1, 0)
        if spd < lo:
            return 0.0
        excess = min(spd - lo, self.tp(1, 4))
        return self.tp(1, 1) + int(excess / self.tp(1, 2)) * self.tp(1, 3)

    # ------------------------------------------------------------ zone
    def _zone_elation(self, mod: Modifier, key: str, ent: Entity) -> float:
        """Every ally, Yao Guang included, gains #2 of Yao Guang's Elation (Skill02_ToSelf / _ToMember convert her
        ElationDamageAddedRatioBase, i.e. her Elation without the conversion itself); E2 adds a flat bonus to the
        same allies (on the Base property, so it is part of the converted amount)."""
        e2 = self.ep(2, 0) if self.e(2) else 0.0
        return self.p("skill", 1) * (self._elation_before_zone(mod) + e2) + e2

    def _elation_before_zone(self, zone: Modifier) -> float:
        """Yao Guang's Elation without the Zone (no recursion into the Zone's own conversion)."""
        ch = self.char
        total = ch.base.get(S.ELATION_DMG_PCT, 0.0)
        for m in ch._stat_mods():
            if m is not zone and m.touches(S.ELATION_DMG_PCT):
                total += m.value(S.ELATION_DMG_PCT, ch)
        return total

    def _zone(self) -> None:
        stats = {S.SPD_PCT: self.ep(2, 1)} if self.e(2) else {}
        self.zone = self.buff_self(
            Modifier(
                "Decalight Zone",
                stats=stats,
                duration=int(self.p("skill", 0)),
                tick=Tick.SOURCE_TURN_START,
                scope=self.ally_scope,
                dyn=self._zone_elation,
                dyn_keys={S.ELATION_DMG_PCT},
                key="Decalight Zone",
            )
        )

    # ---------------------------------------------------------- policy
    def take_turn(self) -> None:
        target = self.pick_target()
        if target is None:
            return
        zone = self.zone if self.zone is not None and not self.zone.removed else None
        if self.can_skill() and (zone is None or (zone.duration or 0) <= 1):
            self.skill(target)
        else:
            self.basic(target)

    # --------------------------------------------------------- actions
    def basic(self, target: Enemy | None) -> None:
        assert target is not None
        with self.action(ActionKind.BASIC, "basic", target) as act:
            act.blast(
                target,
                self.p("basic", 0),
                self.p("basic", 1),
                toughness=(self.toughness("basic", 0), self.toughness("basic", 2)),
            )
        self.gain_punchline(int(self.p("skill", 2)))

    def skill(self, target: Enemy | None, sp: int | None = None) -> None:
        with self.action(ActionKind.SKILL, "skill", sp=sp):
            self._zone()
        self.gain_punchline(int(self.p("skill", 2)))

    def ult(self, target: Enemy | None) -> None:
        with self.action(ActionKind.ULT, "ult"):
            self.gain_punchline(int(self.p("ult", 0)))
            for c in self.allies():
                self.buff(
                    c, Modifier("Hexagram RES PEN", stats={S.RES_PEN: self.p("ult", 1)}, duration=int(self.p("ult", 2)))
                )
        fixed = int(self.ep(1, 1)) if self.e(1) else int(self.p("ult", 3))
        if self.e(4):
            self.battle.queue_action(self._flag_e4, self.char, "Yao Guang E4 flag", priority=4)
        self.battle.elation.extra_turn(fixed, self.char)
        if self.e(4):
            # needs_enemies=False: the flag must be cleared even if the Aha turn ends the wave
            self.battle.queue_action(
                self._unflag_e4, self.char, "Yao Guang E4 unflag", priority=6, needs_enemies=False
            )

    def _flag_e4(self) -> None:
        self.e4_turn = True
        self.passive(
            "Threads of Fate (E4)",
            {f"{S.FINAL_DMG}:elation_skill": self.ep(4, 0) - 1.0},
            scope=lambda e: e.side == Side.ALLY,
        )

    def _unflag_e4(self) -> None:
        self.e4_turn = False
        self.battle.remove_named(self.char, "Threads of Fate (E4)")

    # -------------------------------------------------- elation skill
    def elation_skill(self, punchline: float) -> None:
        rec = self.sk(self.elation_skill_id)
        lv = rec["params"][self.level_of(rec) - 1]
        mult = 1.0 + (self.ep(6, 1) if self.e(6) else 0.0)
        tough = rec["toughness"]
        with self.action(ActionKind.ELATION, rec, label=rec["name"]) as act:
            for e in self.enemies():  # "Inflicts" without a base chance: guaranteed
                self.battle.apply(
                    Modifier(
                        "Woe's Whisper",
                        stats={S.VULN: lv[2]},
                        duration=int(lv[3]),
                        kind=ModKind.DEBUFF,
                        key="Woe's Whisper",
                    ),
                    e,
                    self.char,
                )
            for e in self.enemies():
                self.elation_hit(
                    e,
                    lv[1] * mult,
                    punchline,
                    label="Let Thy Fortune Burst (AoE)",
                    action=act,
                    tags=("elation_skill",),
                    toughness=tough[1],
                )
            for _ in range(int(lv[4])):
                pool = [e for e in self.enemies() if e.hp > 0] or self.enemies()
                if not pool:
                    break
                t = self.battle.rng.choice(pool)
                self.elation_hit(
                    t,
                    lv[5] * mult,
                    punchline,
                    label="Let Thy Fortune Burst (bounce)",
                    action=act,
                    tags=("elation_skill",),
                    toughness=tough[0],
                )
        if self.trace(2):
            self.battle.gain_sp(int(self.tp(2, 0)), self.char)

    # ----------------------------------------------------------- talent
    def _great_boon(self, ev: E.Ev) -> None:
        act = ev.attack
        owner = act.owner
        if not isinstance(owner, Character) or owner.side != Side.ALLY or not act.attacked:
            return
        p = self.banger()
        if p <= 0:
            return
        times = 2 if act.sp < 0 else 1
        min_el = self.char.stat(S.ELATION_DMG_PCT)
        for _ in range(times):
            pool = [t for t in act.attacked if t.alive and t.hp > 0] or [t for t in act.attacked if t.alive]
            if not pool:
                return
            t = self.battle.rng.choice(pool)
            self.battle.elation.damage(
                owner,
                t,
                self.p("talent", 0),
                punchline=p,
                label="Great Boon (Yao Guang)",
                credited=owner,
                min_elation=min_el,
            )
