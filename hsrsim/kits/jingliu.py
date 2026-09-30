"""Jingliu (镜流) — Destruction / Ice. Syzygy stacks, Spectral Transmigration (enhanced Skill, CRIT Rate,
ATK from teammates' consumed HP).

The enhanced kit (``JingliuEnhanced``) scales on Max HP, enters Spectral Transmigration at 2 Syzygy, and turns
teammates' HP loss into Moonlight (CRIT DMG) stacks and extra Syzygy.

Options (``default_opts``):
* ``rotation``: ``"skill"`` (default: Transcendent Flash whenever SP allows outside Spectral Transmigration)
  or ``"basic"``. In Spectral Transmigration only Moon On Glacial River can be used.
"""

from __future__ import annotations

from typing import Any

from .. import events as E
from .. import stats as S
from ..control import MenuItem
from ..entities import Enemy
from ..enums import ActionKind, Element
from ..modifiers import Modifier, ModKind, Stacking, Tick, hidden
from . import register, register_enhanced
from .base import Kit
from .misha import CharFreeze

SYZYGY_MAX = 3  # Talent text "Syzygy can stack up to 3 times"
ENHANCED_SKILL_ID = "121209"  # "Moon On Glacial River"
HP_FLOOR = 1.0  # Talent text "this cannot reduce teammates' HP to lower than 1"
TRANSMIGRATION = "Spectral Transmigration"
# Moon On Glacial River: 5 hits on the main and adjacent targets (and the E1 extra DMG) in
# Avatar_Jingliu_00_PassiveAtkReady_Ability / Avatar_Advanced_Jingliu_00_PassiveAtkReady_Ability
MOON_SPLITS = [0.1, 0.1, 0.1, 0.2, 0.5]


@register
class Jingliu(Kit):
    char_id = "1212"
    default_opts = {"rotation": "skill"}

    def setup(self) -> None:
        self.syzygy = 0
        self.state_mod: Modifier | None = None
        self.e2_ready = False

    def technique(self) -> None:
        p = self.sk("technique")["params"][0]
        # SkillMaze_Jingliu_Modifier: ModifySPNew AddValue (scales with ERR)
        self.battle.gain_energy(self.char, p[5])
        for e in self.enemies():
            self.battle.try_debuff(
                CharFreeze(self.char, p[4], int(p[3]), label="Frozen (Jingliu Technique)"),
                e,
                self.char,
                p[1],
                debuff_type="freeze",
            )
        self.gain_syzygy(int(p[0]))

    # ------------------------------------------------------------ Syzygy
    @property
    def in_transmigration(self) -> bool:
        return self.state_mod is not None

    def syzygy_cap(self) -> int:
        return SYZYGY_MAX + (int(self.ep(6, 0)) if self.e(6) and self.in_transmigration else 0)

    def gain_syzygy(self, n: int) -> None:
        self.syzygy = min(self.syzygy_cap(), self.syzygy + n)
        if not self.in_transmigration and self.syzygy >= self.p("talent", 4):
            self._enter()

    def _enter(self) -> None:
        stats = {S.CRIT_RATE: self.p("talent", 6)}
        if self.trace(1):
            stats[S.EFFECT_RES] = self.tp(1, 0)
        if self.trace(3):
            stats[f"{S.DMG_PCT}:ult"] = self.tp(3, 0)
        if self.e(6):
            stats[S.CRIT_DMG] = self.ep(6, 1)
        self.state_mod = self.buff_self(
            Modifier(TRANSMIGRATION, stats=stats, tick=Tick.NONE, kind=ModKind.OTHER, dispellable=False)
        )
        if self.e(6):
            self.syzygy = min(self.syzygy_cap(), self.syzygy + int(self.ep(6, 0)))
        self.battle.advance(self.char, self.p("talent", 5))

    def _exit(self) -> None:
        if self.state_mod is not None:
            self.battle.remove_modifier(self.state_mod)
        self.state_mod = None
        self.syzygy = min(self.syzygy, SYZYGY_MAX)

    def _consume_team(self) -> Modifier | None:
        """Attacks in Spectral Transmigration consume teammates' HP; ATK rises until the attack ends."""
        if not self.in_transmigration:
            return None
        total = 0.0
        for c in self.teammates():
            cost = min(self.p("talent", 1) * c.max_hp, max(0.0, c.hp - HP_FLOOR))
            if cost > 0:
                total += self.battle.lose_hp(c, cost, self.char)
        ratio = self.p("talent", 2) + (self.ep(4, 0) if self.e(4) else 0.0)
        cap = self.p("talent", 3) + (self.ep(4, 1) if self.e(4) else 0.0)
        atk = min(ratio * total, cap * self.char.raw(S.BASE_ATK))
        return self.buff_self(hidden("Moon On Glacial River (ATK)", {S.ATK_FLAT: atk}))

    def _e1_buff(self) -> None:
        if self.e(1):
            self.buff_self(
                Modifier("Moon Crashes Tianguan Gate", stats={S.CRIT_DMG: self.ep(1, 0)}, duration=int(self.ep(1, 1)))
            )

    # ------------------------------------------------------------ policy
    def can_skill(self) -> bool:
        return self.in_transmigration or super().can_skill()

    def take_turn(self) -> None:
        target = self.pick_target()
        if target is None:
            return
        if self.in_transmigration or (self.opts.get("rotation", "skill") == "skill" and self.can_skill()):
            self.skill(target)
        else:
            self.basic(target)

    def menu(self) -> list[MenuItem]:
        """Spectral Transmigration: only the enhanced Skill "Moon On Glacial River" (no SP) can be used."""
        if self.in_transmigration:
            return [
                self.basic_item(enabled=False, note="【转魄】状态下仅能施放【寒川映月】"),
                self.skill_item(self.sk(f"{self.prefix}09"), enabled=True, note=""),
            ]
        return super().menu()

    # ----------------------------------------------------------- actions
    def basic(self, target: Enemy | None) -> None:
        assert target is not None
        if self.in_transmigration:  # only the enhanced Skill is available in Spectral Transmigration
            self.skill(target)
            return
        self.simple_basic(target)

    def skill(self, target: Enemy | None) -> None:
        assert target is not None
        if self.in_transmigration:
            self.enhanced_skill(target)
            return
        with self.action(ActionKind.SKILL, "skill", target) as act:
            act.hit(target, self.p("skill", 0), toughness=self.toughness("skill"))
        if self.trace(2):
            self.battle.advance(self.char, self.tp(2, 0))
        self.gain_syzygy(int(self.p("skill", 1)))

    def _blast_with_e1(
        self, act: Any, target: Enemy, main: float, adj: float, tough: tuple[float, float], **kw: Any
    ) -> None:
        single = not self.battle.adjacent(target)
        act.blast(target, main, adj, toughness=tough, **kw)
        if self.e(1) and single:  # "If only one enemy target is attacked" (part of the same attack)
            act.hit(target, self.ep(1, 2), label="E1 Moon Crashes Tianguan Gate", **kw)

    def enhanced_skill(self, target: Enemy) -> None:
        rec = self.sk(ENHANCED_SKILL_ID)
        lv = rec["params"][self.level_of(rec) - 1]
        extra = {S.DMG_PCT: self.ep(2, 0)} if self.e2_ready else None
        self.e2_ready = False
        with self.action(ActionKind.SKILL, rec, target, sp=0) as act:
            atk = self._consume_team()
            self._e1_buff()
            self._blast_with_e1(
                act,
                target,
                lv[0],
                lv[2],
                (self.toughness(ENHANCED_SKILL_ID, 0), self.toughness(ENHANCED_SKILL_ID, 2)),
                extra=extra,
                splits=MOON_SPLITS,
            )
            self.syzygy = max(0, self.syzygy - int(lv[1]))
        if atk is not None:
            self.battle.remove_modifier(atk)
        if self.syzygy <= 0:
            self._exit()

    def ult(self, target: Enemy | None) -> None:
        if target is None:
            return
        with self.action(ActionKind.ULT, "ult", target) as act:
            atk = self._consume_team()
            self._e1_buff()
            self._blast_with_e1(
                act, target, self.p("ult", 0), self.p("ult", 2), (self.toughness("ult", 0), self.toughness("ult", 2))
            )
        if atk is not None:
            self.battle.remove_modifier(atk)
        if self.e(2):
            self.e2_ready = True
        self.gain_syzygy(int(self.p("ult", 1)))  # "Gains 1 stack of Syzygy after attack ends"


ENH_SYZYGY_MAX = 4  # enhanced Talent text "Syzygy can stack up to 4 times"
ENH_ENTRY_BONUS = 1  # enhanced Talent text "enters the Spectral Transmigration state with 1 extra stack of Syzygy"
E6_LIMIT_BONUS = 1  # E6 text "the Syzygy stack limit increases by 1"
MOONLIGHT = "Moonlight"


@register_enhanced
class JingliuEnhanced(Jingliu):
    """Enhanced Jingliu: Max HP scaling, Moonlight CRIT DMG stacks, Syzygy from allies losing HP (A6: DEF ignore)."""

    def setup(self) -> None:
        super().setup()
        self.hp_events = 0  # "ally targets receive DMG or consume HP" counter towards 1 Syzygy
        self.a6_ready = False
        self.on(E.ALLY_ATTACKED, self._on_ally_attacked)
        self.on(E.HP_CHANGED, self._on_hp_changed)

    def technique(self) -> None:
        p = self.sk("technique")["params"][0]
        # SkillMaze_Jingliu_Modifier: ModifySPNew AddValue (scales with ERR)
        self.battle.gain_energy(self.char, p[5])
        for e in self.enemies():
            self.battle.try_debuff(
                CharFreeze(self.char, p[4], int(p[3]), label="Frozen (Jingliu Technique)", stat="hp"),
                e,
                self.char,
                p[1],
                debuff_type="freeze",
            )
        self.gain_syzygy(int(p[0]))

    # ---------------------------------------------------- Moonlight / Syzygy
    def _on_ally_attacked(self, ev: E.Ev) -> None:
        # "Each attack received by each target is only counted once" (enemy hits on HP_CHANGED are skipped)
        for t in ev.targets:
            if t.side == self.char.side:
                self._ally_lost_hp()

    def _on_hp_changed(self, ev: E.Ev) -> None:
        if ev.delta < 0 and ev.entity.side == self.char.side and not isinstance(ev.source, Enemy):
            self._ally_lost_hp()

    def _ally_lost_hp(self) -> None:
        if self.in_transmigration:
            crit_dmg = self.p("talent", 2) + (self.ep(4, 0) if self.e(4) else 0.0)
            self.buff_self(
                Modifier(
                    MOONLIGHT,
                    stats={S.CRIT_DMG: crit_dmg},
                    tick=Tick.NONE,
                    stacking=Stacking.STACK,
                    max_stacks=int(self.p("talent", 3)),
                    dispellable=False,
                )
            )
        self.hp_events += 1
        if self.hp_events >= self.p("talent", 7):
            self.hp_events = 0
            self.gain_syzygy(1)

    def syzygy_cap(self) -> int:
        return ENH_SYZYGY_MAX + (E6_LIMIT_BONUS if self.e(6) and self.in_transmigration else 0)

    def gain_syzygy(self, n: int) -> None:
        self.syzygy = min(self.syzygy_cap(), self.syzygy + n)
        if self.trace(3) and self.syzygy >= self.syzygy_cap():
            self.a6_ready = True
        if not self.in_transmigration and self.syzygy >= self.p("talent", 4):
            self._enter()

    def _enter(self) -> None:
        stats = {S.CRIT_RATE: self.p("talent", 6)}
        if self.trace(1):
            stats[S.EFFECT_RES] = self.tp(1, 0)
            stats[f"{S.DMG_PCT}:ult"] = self.tp(1, 1)
        if self.e(6):
            stats[f"{S.RES_PEN}:{Element.ICE.value}"] = self.ep(6, 1)
        self.state_mod = self.buff_self(
            Modifier(TRANSMIGRATION, stats=stats, tick=Tick.NONE, kind=ModKind.OTHER, dispellable=False)
        )
        self.gain_syzygy(ENH_ENTRY_BONUS + (int(self.ep(6, 0)) if self.e(6) else 0))
        self.battle.advance(self.char, self.p("talent", 5))

    def _exit(self) -> None:
        super()._exit()
        moon = self.char.get_mod(MOONLIGHT)
        if moon is not None:
            self.battle.remove_modifier(moon)

    def _consume_team(self) -> Modifier | None:
        """Attacks in Spectral Transmigration consume teammates' HP (no ATK conversion in the enhanced kit)."""
        if self.in_transmigration:
            for c in self.teammates():
                cost = min(self.p("talent", 1) * c.max_hp, max(0.0, c.hp - HP_FLOOR))
                if cost > 0:
                    self.battle.lose_hp(c, cost, self.char)
        return None

    def _attack_extra(self, base: dict[str, float] | None = None) -> dict[str, float] | None:
        """Hit-local stats for the next attack; consumes the A6 DEF ignore."""
        extra = dict(base or {})
        if self.a6_ready:
            self.a6_ready = False
            extra[S.DEF_IGNORE] = self.tp(3, 0)
        return extra or None

    def _e1_buff(self) -> None:
        if self.e(1):
            self.buff_self(
                Modifier("Moon Crashes Tianguan Gate", stats={S.CRIT_DMG: self.ep(1, 0)}, duration=int(self.ep(1, 2)))
            )

    def _e1_hit(self, act: Any, target: Enemy, extra: dict[str, float] | None) -> None:
        if self.e(1) and target.alive:
            act.hit(target, self.ep(1, 1), stat="hp", label="E1 Moon Crashes Tianguan Gate", extra=extra)

    # ----------------------------------------------------------- actions
    def basic(self, target: Enemy | None) -> None:
        assert target is not None
        if self.in_transmigration:
            self.skill(target)
            return
        with self.action(ActionKind.BASIC, "basic", target) as act:
            act.hit(
                target,
                self.p("basic", 0),
                stat="hp",
                toughness=self.toughness("basic"),
                splits="data",
                extra=self._attack_extra(),
            )

    def skill(self, target: Enemy | None) -> None:
        assert target is not None
        if self.in_transmigration:
            self.enhanced_skill(target)
            return
        with self.action(ActionKind.SKILL, "skill", target) as act:
            act.hit(
                target, self.p("skill", 0), stat="hp", toughness=self.toughness("skill"), extra=self._attack_extra()
            )
            if self.trace(2):
                self.battle.gain_energy(self.char, self.tp(2, 0))
        self.gain_syzygy(int(self.p("skill", 1)))

    def enhanced_skill(self, target: Enemy) -> None:
        sid = f"{self.prefix}09"
        rec = self.sk(sid)
        lv = rec["params"][self.level_of(rec) - 1]
        extra = self._attack_extra({S.DMG_PCT: self.ep(2, 0)} if self.e2_ready else None)
        self.e2_ready = False
        with self.action(ActionKind.SKILL, rec, target, sp=0) as act:
            self._consume_team()
            self._e1_buff()
            act.blast(
                target,
                lv[0],
                lv[2],
                stat="hp",
                toughness=(self.toughness(sid, 0), self.toughness(sid, 2)),
                splits=MOON_SPLITS,
                extra=extra,
            )
            self._e1_hit(act, target, extra)
            self.syzygy = max(0, self.syzygy - int(lv[1]))
            if self.trace(2):
                self.battle.gain_energy(self.char, self.tp(2, 1))
        if self.syzygy <= 0:
            self._exit()

    def ult(self, target: Enemy | None) -> None:
        if target is None:
            return
        extra = self._attack_extra()
        with self.action(ActionKind.ULT, "ult", target) as act:
            self._consume_team()
            self._e1_buff()
            act.blast(
                target,
                self.p("ult", 0),
                self.p("ult", 2),
                stat="hp",
                toughness=(self.toughness("ult", 0), self.toughness("ult", 2)),
                extra=extra,
            )
            self._e1_hit(act, target, extra)
        if self.e(2):
            self.e2_ready = True
        self.gain_syzygy(int(self.p("ult", 1)))  # "Gains 1 stack of Syzygy after the attack ends"
