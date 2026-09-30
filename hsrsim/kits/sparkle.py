"""Sparkle (花火) — Harmony / Quantum. SP battery, CRIT DMG buff + 50% advance, DMG% per SP spent."""

from __future__ import annotations

from .. import events as E
from .. import stats as S
from ..entities import Character, Enemy, Entity
from ..enums import ActionKind, Element
from ..modifiers import Modifier, ModKind, Stacking, Tick
from . import register, register_enhanced
from .base import Kit

E1_CIPHER_EXTRA_TURNS = 1  # base E1 text only: "The Cipher effect ... lasts for 1 extra turn"
E4_EXTRA_SP = 1  # E4 text only: "recovers 1 more Skill Point ... increases the Max Skill Points by 1"


@register
class Sparkle(Kit):
    char_id = "1306"
    ult_targets_ally = True
    default_opts = {"target": None}

    def setup(self) -> None:
        extra = int(self.p("talent", 2)) + (E4_EXTRA_SP if self.e(4) else 0)
        self.battle.max_sp += extra
        self.on(E.SP_CHANGED, self._on_sp)
        if self.trace(3):
            self.passive("Nocturne", {S.ATK_PCT: self.tp(3, 3)}, scope=self.ally_scope)
            n_q = sum(1 for c in self.battle.team if c.element == Element.QUANTUM)
            if n_q:
                self.passive(
                    "Nocturne (Quantum)",
                    {S.ATK_PCT: self.tp(3, min(n_q, 3) - 1)},
                    scope=lambda e: self.ally_scope(e) and getattr(e, "element", None) == Element.QUANTUM,
                )

    def technique(self) -> None:
        self.battle.gain_sp(int(self.sk("technique")["params"][0][0]), self.char)

    # ---------------------------------------------------------- talent
    def _on_sp(self, ev: E.Ev) -> None:
        if ev.delta >= 0:
            return
        for _ in range(-ev.delta):
            for c in self.allies():
                stats = {S.DEF_IGNORE: self.ep(2, 0)} if self.e(2) else {}
                self.buff(
                    c,
                    Modifier(
                        "Red Herring",
                        stats=stats,
                        duration=int(self.p("talent", 0)),
                        stacking=Stacking.STACK,
                        max_stacks=int(self.p("talent", 3)),
                        dyn=self._herring_dmg,
                        dyn_keys={S.DMG_PCT},
                    ),
                )

    def _herring_dmg(self, mod: Modifier, key: str, ent: Entity) -> float:
        """DMG% per stack, +Cipher bonus while the holder has Cipher (the game recomputes the value whenever
        Cipher is added or removed: OnListenModifierAdd / OnModifierRemove of Skill03_PowerUp)."""
        per = self.p("talent", 1) + (self.p("ult", 2) if ent.has_mod("Cipher") else 0.0)
        return per * mod.stacks

    # ---------------------------------------------------------- policy
    def take_turn(self) -> None:
        target = self.pick_target()
        if target is None:
            return
        if self.opts.get("rotation", "skill") == "skill" and self.can_skill():
            self.skill(target)
        else:
            self.basic(target)

    # ---------------------------------------------------------- actions
    def basic(self, target: Enemy | None) -> None:
        assert target is not None
        extra = self.tp(1, 0) if self.trace(1) else 0.0
        with self.action(ActionKind.BASIC, "basic", target) as act:
            act.hit(target, self.p("basic", 0), toughness=self.toughness("basic"))
            act.energy += extra

    def _cd_buff_value(self) -> float:
        v = self.p("skill", 0) * self.char.stat(S.CRIT_DMG) + self.p("skill", 1)
        if self.e(6):
            v += self.ep(6, 0) * self.char.stat(S.CRIT_DMG)
        return v

    def _apply_cd_buff(self, ally: Character, value: float) -> None:
        if self.trace(2):
            # extended until the start of the target's next turn (CritDmgAddedRatio02, ModifierPhase1End); this
            # holds whether or not the target is the current turn owner (turn-start ticks never skip)
            mod = Modifier(
                "Dreamdiver",
                stats={S.CRIT_DMG: value},
                duration=int(self.p("skill", 2)) + 1,
                tick=Tick.HOLDER_TURN_START,
            )
        else:
            mod = Modifier("Dreamdiver", stats={S.CRIT_DMG: value}, duration=int(self.p("skill", 2)))
        self.buff(ally, mod)

    def skill(self, target: Enemy | None) -> None:
        ally = self.main_dps()
        with self.action(ActionKind.SKILL, "skill", ally):
            value = self._cd_buff_value()
            self._apply_cd_buff(ally, value)
            if self.e(6):  # "apply to all teammates with Cipher" (AllTeammate: not Sparkle herself)
                for c in self.teammates():
                    if c is not ally and c.has_mod("Cipher"):
                        self._apply_cd_buff(c, value)
        if ally is not self.char:
            self.battle.advance(ally, self.p("skill", 3))

    def ult(self, target: Enemy | None) -> None:
        with self.action(ActionKind.ULT, "ult"):
            self.battle.gain_sp(int(self.p("ult", 1)) + (E4_EXTRA_SP if self.e(4) else 0), self.char)
            dur = int(self.p("ult", 3)) + (E1_CIPHER_EXTRA_TURNS if self.e(1) else 0)
            for c in self.allies():
                stats = {S.ATK_PCT: self.ep(1, 0)} if self.e(1) else {}
                self.buff(c, Modifier("Cipher", stats=stats, duration=dur))
            if self.e(6):
                holders = [c for c in self.allies() if c.has_mod("Dreamdiver")]
                if holders:
                    value = holders[0].get_mod("Dreamdiver").stats[S.CRIT_DMG]  # type: ignore[union-attr]
                    for c in self.teammates():  # spread to teammates with Cipher (AllTeammate)
                        if not c.has_mod("Dreamdiver") and c.has_mod("Cipher"):
                            self._apply_cd_buff(c, value)


@register_enhanced
class SparkleEnhanced(Sparkle):
    """Enhanced Sparkle: "Figment" stacks raise enemies' DMG taken, SP overflow bank, free Skill (A4)."""

    def setup(self) -> None:
        extra = int(self.p("talent", 2)) + (E4_EXTRA_SP if self.e(4) else 0)
        self.battle.max_sp += extra
        self.bank = 0
        self.free_skill = False
        self.spent_in_turn: dict[tuple[int, int], int] = {}
        self.on(E.SP_CHANGED, self._on_sp_enh)
        self.on(E.SP_RECOVERED, self._on_recover)
        self.on(E.TURN_END, self._refill)
        self.on(E.BEFORE_HIT, self._figment_hit)
        if self.trace(3):
            self.passive("Nocturne", {S.ATK_PCT: self.tp(3, 0)}, scope=self.ally_scope)
            self.passive(
                "Nocturne (PEN)",
                {},
                scope=self.ally_scope,
                key="Sparkle A6 PEN",
                dyn=lambda m, k, e: self.tp(3, 1) if e.has_mod("Dreamdiver") else 0.0,
                dyn_keys={S.RES_PEN},
            )

    def on_battle_start(self) -> None:
        if self.e(1):
            self._e1_spd()

    def technique(self) -> None:
        p = self.sk("technique")["params"][0]
        self.battle.gain_sp(int(p[0]), self.char)
        self.battle.gain_energy(self.char, p[1])  # Maze_Modifier: ModifySPNew AddValue (scaled by ERR)

    def _e1_spd(self) -> None:
        self.buff_self(
            Modifier("Suspension of Disbelief", stats={S.SPD_PCT: self.ep(1, 1)}, duration=int(self.ep(1, 2)))
        )

    # ---------------------------------------------------------------- Figment
    def _on_sp_enh(self, ev: E.Ev) -> None:
        if ev.delta >= 0:
            return
        who = ev.entity
        n = -ev.delta
        for _ in range(n):
            self.buff_self(
                Modifier(
                    "Figment",
                    duration=int(self.p("talent", 0)),
                    stacking=Stacking.STACK,
                    max_stacks=int(self.p("talent", 3)),
                    kind=ModKind.BUFF,
                )
            )
        if isinstance(who, Character):
            if self.trace(1) and who.has_mod("Dreamdiver"):
                self.battle.gain_energy(self.char, self.tp(1, 1) * n)
            key = (self.battle.turns, who.uid)
            self.spent_in_turn[key] = self.spent_in_turn.get(key, 0) + n
            if self.trace(2) and self.spent_in_turn[key] >= self.tp(2, 0):
                self.free_skill = True

    def _figment_hit(self, ev: E.Ev) -> None:
        fig = self.char.get_mod("Figment")
        if fig is None:
            return
        hit = ev.hit
        if hit.attacker.side != self.char.side:
            return
        per = self.p("talent", 1)
        src = hit.credited
        if src.has_mod("Cipher"):
            per += self.p("ult", 2)
        hit.add(S.VULN, per * fig.stacks)
        if self.e(2):
            hit.add(S.DEF_REDUCTION, self.ep(2, 0) * fig.stacks)

    # ------------------------------------------------------------- SP bank
    def _on_recover(self, ev: E.Ev) -> None:
        if (
            ev.entity is self.char
            and self.battle.current_action is not None
            and self.battle.current_action.kind == ActionKind.ULT
            and ev.overflow > 0
        ):
            self.bank = min(int(self.p("ult", 4)), self.bank + int(ev.overflow))

    def _refill(self, ev: E.Ev) -> None:
        if self.bank > 0 and isinstance(ev.entity, Character) and self.battle.sp < self.battle.max_sp:
            n = min(self.bank, self.battle.max_sp - self.battle.sp)
            self.bank -= n
            self.battle.gain_sp(n, self.char)

    # -------------------------------------------------------------- actions
    def can_skill(self) -> bool:
        return self.free_skill or super().can_skill()

    def _cd_buff(self, ally: Character, value: float) -> None:
        self.buff(ally, Modifier("Dreamdiver", stats={S.CRIT_DMG: value}, duration=int(self.p("skill", 2))))

    def skill(self, target: Enemy | None) -> None:
        ally = self.main_dps()
        sp = 0 if self.free_skill else None
        self.free_skill = False
        with self.action(ActionKind.SKILL, "skill", ally, sp=sp):
            value = self._cd_buff_value()
            self._cd_buff(ally, value)
            if self.e(6):  # "apply to all teammates with Cipher" (AllTeammate: not Sparkle herself)
                for c in self.teammates():
                    if c is not ally and c.has_mod("Cipher"):
                        self._cd_buff(c, value)
            if self.e(1):
                self._e1_spd()
        if ally is not self.char:
            self.battle.advance(ally, self.p("skill", 3))

    def ult(self, target: Enemy | None) -> None:
        with self.action(ActionKind.ULT, "ult"):
            self.battle.gain_sp(int(self.p("ult", 1)) + (E4_EXTRA_SP if self.e(4) else 0), self.char)
            for c in self.allies():
                stats = {S.ATK_PCT: self.ep(1, 0)} if self.e(1) else {}
                self.buff(c, Modifier("Cipher", stats=stats, duration=int(self.p("ult", 3))))
            if self.e(6):
                holders = [c for c in self.allies() if c.has_mod("Dreamdiver")]
                if holders:
                    value = holders[0].get_mod("Dreamdiver").stats[S.CRIT_DMG]  # type: ignore[union-attr]
                    for c in self.teammates():  # spread to teammates with Cipher (AllTeammate)
                        if not c.has_mod("Dreamdiver") and c.has_mod("Cipher"):
                            self._cd_buff(c, value)
