"""Blade (刃) — Destruction / Wind. Hellscape (HP-scaling enhanced Basic ATK), Charge follow-up, HP-loss Ultimate.

Base kit only (the enhanced kit is not implemented yet).

Options (``default_opts``):
* ``rotation``: ``"skill"`` (default) enters Hellscape with the Skill whenever it is not active and SP allows
  (the Skill does not end the turn: Forest of Swords follows immediately); ``"basic"`` never uses the Skill.
"""

from __future__ import annotations

from .. import events as E
from .. import stats as S
from ..entities import Enemy, Entity
from ..enums import ActionKind
from ..modifiers import Modifier, ModKind, Stacking, Tick
from . import register
from .base import Kit

MAX_CHARGE = 5  # Talent text "stacking up to 5 times" (ability config MWRen_Qi_MaxLayer = 5)
E6_MAX_CHARGE = 4  # E6 text "The maximum number of Charge stacks is reduced to 4"
ULT_HP_SET = 0.5  # Ultimate text "Sets Blade's current HP to 50% of his Max HP"
LOW_HP = 0.5  # A2 / E4 text: "at 50% of Max HP or lower"
FOREST_ID = "120508"  # enhanced Basic ATK "Forest of Swords"


@register
class Blade(Kit):
    char_id = "1205"
    default_opts = {"rotation": "skill"}

    def setup(self) -> None:
        if self.char.enhanced:
            raise NotImplementedError("Blade enhanced kit is not implemented yet")
        self.charge = 0
        self.tally = 0.0  # HP lost in this battle since the last Ultimate (the cap is applied on use)
        self.fua_pending = False
        self.on(E.ALLY_ATTACKED, self._on_attacked)
        self.on(E.HP_CHANGED, self._on_hp_changed)
        self.on(E.WAVE_START, self._on_wave)
        if self.trace(1):
            # not modelled: battle.heal ignores heal_taken% (the stat is still exposed on Blade)
            self.passive("Vita Infinita", {}, dyn=self._a2, dyn_keys={S.HEAL_TAKEN})

    def technique(self) -> None:
        p = self.sk("technique")["params"][0]
        with self.action(ActionKind.EXTRA, None, label="Karma Wind", energy=0, sp=0) as act:
            self.consume_hp(p[1])
            act.aoe(p[0], stat="hp", toughness=self.toughness("technique"))

    def _a2(self, mod: Modifier, key: str, ent: Entity) -> float:
        return self.tp(1, 0) if self.char.hp_ratio <= LOW_HP else 0.0

    # ------------------------------------------------------------- HP / Charge
    def consume_hp(self, ratio: float) -> float:
        """Consume ``ratio`` x Max HP; with insufficient HP, HP drops to 1."""
        amount = min(ratio * self.char.max_hp, max(0.0, self.char.hp - 1.0))
        return self.battle.lose_hp(self.char, amount, self.char) if amount > 0 else 0.0

    def max_charge(self) -> int:
        return E6_MAX_CHARGE if self.e(6) else MAX_CHARGE

    def _on_hp_changed(self, ev: E.Ev) -> None:
        if ev.entity is not self.char or ev.delta >= 0:
            return
        self.tally += -ev.delta
        if not isinstance(ev.source, Enemy):  # enemy attacks are counted once per attack (ALLY_ATTACKED)
            self.add_charge()
        if self.e(4):
            mh = self.char.max_hp
            before = (self.char.hp - ev.delta) / mh
            mod = self.char.get_mod("Rejected by Death, Infected With Life")
            stacks = mod.stacks if mod is not None else 0
            if before > LOW_HP >= self.char.hp_ratio and stacks < int(self.ep(4, 1)):
                self.buff_self(
                    Modifier(
                        "Rejected by Death, Infected With Life",
                        stats={S.HP_PCT: self.ep(4, 0)},
                        kind=ModKind.OTHER,
                        tick=Tick.NONE,
                        stacking=Stacking.STACK,
                        max_stacks=int(self.ep(4, 1)),
                        dispellable=False,
                    )
                )

    def _on_attacked(self, ev: E.Ev) -> None:
        if self.char in ev.targets:
            self.add_charge()  # "A max of 1 Charge stack can be gained every time he is attacked"

    def add_charge(self) -> None:
        if self.fua_pending:
            return  # all Charges are consumed after the pending follow-up anyway
        self.charge = min(self.max_charge(), self.charge + 1)
        if self.charge >= self.max_charge():
            self.fua_pending = True
            self.battle.queue_action(self._fua, self.char, "Blade Talent")

    def _on_wave(self, ev: E.Ev) -> None:
        # a follow-up queued when the previous wave died is dropped by the engine: re-launch it on the new wave
        if self.fua_pending:
            self.battle.queue_action(self._fua, self.char, "Blade Talent")

    def _fua(self) -> None:
        target = self.battle.default_target()
        if target is None:
            return
        hp_mult = self.p("talent", 3) + (self.ep(6, 0) if self.e(6) else 0.0)
        extra = {S.DMG_PCT: self.tp(3, 0)} if self.trace(3) else None
        with self.action(ActionKind.FUA, "talent", target) as act:
            act.aoe(
                {"atk": self.p("talent", 1), "hp": hp_mult},
                toughness=self.toughness("talent", 1),
                main_target=target,
                extra=extra,
            )
            self.battle.heal(self.char, self.p("talent", 2) * self.char.max_hp, self.char)
        self.charge = 0
        self.fua_pending = False

    # ------------------------------------------------------------ policy
    @property
    def in_hellscape(self) -> bool:
        return self.char.has_mod("Hellscape")

    def take_turn(self) -> None:
        target = self.pick_target()
        if target is None:
            return
        if not self.in_hellscape and self.opts.get("rotation", "skill") == "skill" and self.can_skill():
            self.skill(target)
        else:
            self.basic(target)

    # ----------------------------------------------------------- actions
    def basic(self, target: Enemy | None) -> None:
        assert target is not None
        if self.in_hellscape:
            self.forest(target)
        else:
            self.simple_basic(target)

    def forest(self, target: Enemy) -> None:
        rec = self.sk(FOREST_ID)
        lv = rec["params"][self.level_of(rec) - 1]
        with self.action(ActionKind.BASIC, rec, target) as act:
            self.consume_hp(lv[0])
            hits = act.blast(
                target,
                {"atk": lv[1], "hp": lv[3]},
                {"atk": lv[2], "hp": lv[4]},
                toughness=(self.toughness(FOREST_ID, 0), self.toughness(FOREST_ID, 2)),
            )
        if self.trace(2) and any(h.target.broken for h in hits):
            self.battle.heal(self.char, self.tp(2, 0) * self.char.max_hp + self.tp(2, 1), self.char)

    def skill(self, target: Enemy | None) -> None:
        assert target is not None
        with self.action(ActionKind.SKILL, "skill", target):
            self.consume_hp(self.p("skill", 0))
            stats = {S.DMG_PCT: self.p("skill", 3)}
            if self.e(2):
                stats[S.CRIT_RATE] = self.ep(2, 0)
            # approximation: the Skill's own turn counts (3 Forest of Swords per Skill, community consensus);
            # the game implements the extra action with TurnInsertAction, which the engine has no notion of
            self.buff_self(Modifier("Hellscape", stats=stats, duration=int(self.p("skill", 1)), skip_first_tick=False))
        # "Using this Skill does not end the current turn" (Ultimates may be inserted before Forest of Swords)
        self.battle.ult_window()
        t = target if target.alive and target.hp > 0 else self.pick_target()
        if t is not None:
            self.forest(t)

    def ult(self, target: Enemy | None) -> None:
        if target is None:
            return
        with self.action(ActionKind.ULT, "ult", target) as act:
            mh = self.char.max_hp
            goal = ULT_HP_SET * mh
            if self.char.hp > goal:
                self.battle.lose_hp(self.char, self.char.hp - goal, self.char)  # counts towards the tally
            elif self.char.hp < goal:
                self.battle.heal(self.char, goal - self.char.hp, self.char)
            lost = min(self.tally, self.p("ult", 6) * mh)
            main_flat = self.p("ult", 4) * lost
            if self.e(1):
                main_flat += self.ep(1, 0) * min(self.tally, self.ep(1, 1) * mh)
            act.hit(
                target,
                {"atk": self.p("ult", 0), "hp": self.p("ult", 1)},
                flat=main_flat,
                toughness=self.toughness("ult", 0),
            )
            for adj in self.battle.adjacent(target):
                act.hit(
                    adj,
                    {"atk": self.p("ult", 2), "hp": self.p("ult", 3)},
                    flat=self.p("ult", 5) * lost,
                    toughness=self.toughness("ult", 2),
                    primary=False,
                )
        self.tally = 0.0
