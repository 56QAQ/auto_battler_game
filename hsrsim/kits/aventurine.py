"""Aventurine (砂金) — Preservation / Imaginary. DEF scaling, stacking Fortified Wager shields, Blind Bet follow-ups.

Options:
  rotation:       "auto" (default) Skill when an ally has no Fortified Wager, "skill" always, "basic" never
  technique_def:  index of the Technique DEF buff kept (0/1/2 = 24%/36%/60%; default 2 — using the
                  Technique repeatedly retains the best roll)
"""

from __future__ import annotations

from .. import events as E
from .. import stats as S
from ..entities import Character, Enemy, Entity
from ..enums import ActionKind, Side
from ..modifiers import Modifier, ModKind, Tick
from . import register
from .base import Kit

WAGER = "Fortified Wager"
BET_THRESHOLD = 7  # "Upon reaching 7 points of Blind Bet" (literal in the Talent text)
BET_CAP = 10  # '"Blind Bet" is capped at 10 points' (literal)
BINGO_SHIELD_TURNS = 3  # A6 extra Fortified Wager "lasting for 3 turns" (literal)
DEF_STEP = 100.0  # A2 "for every 100 of DEF that exceeds ..." (literal)
BET_PER_TRIGGER = 1  # Talent/A6 "gains 1 point of Blind Bet"; Ultimate "Randomly gains 1 to #1 points" (literal)


def _has_wager(e: Entity) -> bool:
    return e.side == Side.ALLY and e.has_mod(WAGER)


@register
class Aventurine(Kit):
    char_id = "1304"
    default_opts = {"rotation": "auto", "technique_def": 2}

    def setup(self) -> None:
        self.bet = 0
        self.fua_queued = False
        self.wager_at_hit: set[int] = set()  # allies holding a Wager when an enemy hit landed on them
        self.bingo_left = int(self.tp(3, 2)) if self.trace(3) else 0
        self.passive("Shot Loaded Right", {S.EFFECT_RES: self.p("talent", 3)}, scope=_has_wager)
        self.on(E.BEFORE_ALLY_HIT, lambda ev: _has_wager(ev.target) and self.wager_at_hit.add(ev.target.uid))
        self.on(E.ALLY_ATTACKED, self._on_attacked)
        self.on(E.BEFORE_HIT, self._unnerved)
        self.on(E.TURN_START, self._turn_start)
        if self.trace(1):
            self.passive("Leverage", {}, dyn=self._a2, dyn_keys={S.CRIT_RATE})
        if self.trace(3):
            self.on(E.ACTION_END, self._bingo)
        if self.e(1):
            self.passive("Prisoner's Dilemma", {S.CRIT_DMG: self.ep(1, 0)}, scope=_has_wager)
        if self.e(6):
            self.passive("Stag Hunt Game", {}, dyn=self._e6, dyn_keys={S.DMG_PCT})

    def on_battle_start(self) -> None:
        if self.trace(2):
            for c in self.allies():
                self.wager(c, self.tp(2, 1) * self.skill_shield(), int(self.tp(2, 0)))

    def technique(self) -> None:
        p = self.sk("technique")["params"][0]
        idx = max(0, min(2, int(self.opts.get("technique_def", 2))))
        for c in self.allies():
            self.buff(c, Modifier("The Red or the Black", stats={S.DEF_PCT: p[idx]}, duration=int(p[3])))

    # ------------------------------------------------------------ passives
    def _a2(self, mod: Modifier, key: str, ent: Entity) -> float:
        over = self.char.defense - self.tp(1, 2)
        return min(self.tp(1, 1), int(over / DEF_STEP) * self.tp(1, 0)) if over > 0 else 0.0

    def _e6(self, mod: Modifier, key: str, ent: Entity) -> float:
        n = sum(1 for c in self.teammates() if self.battle.shield_value(c) > 0)
        return min(self.ep(6, 1), self.ep(6, 0) * n)

    def _turn_start(self, ev: E.Ev) -> None:
        if ev.entity is self.char and self.trace(3):
            self.bingo_left = int(self.tp(3, 2))

    # ------------------------------------------------------------ shields
    def skill_shield(self) -> float:
        return self.p("skill", 0) * self.char.defense + self.p("skill", 1)

    def wager(self, ally: Entity, value: float, turns: int) -> None:
        """Fortified Wager: re-applying stacks the Shield up to 200% of the Skill's Shield (param)."""
        mult = 1.0 + self.char.stat(S.SHIELD_PCT)
        cap = self.p("skill", 3) * self.skill_shield() * mult
        m = ally.get_mod(WAGER)
        if m is not None:
            m.data["value"] = min(cap, m.data.get("value", 0.0) + value * mult)
            m.duration = max(m.duration or 0, turns)
            return
        new = self.battle.add_shield(ally, value, self.char, duration=turns, name=WAGER, tick=Tick.HOLDER_TURN_END)
        new.data["value"] = min(cap, new.data["value"])

    def _shield_all(self, value: float, turns: int) -> None:
        for c in self.allies():
            self.wager(c, value, turns)

    # --------------------------------------------------------- Blind Bet
    def add_bet(self, n: int) -> None:
        self.bet = min(BET_CAP, self.bet + n)
        if self.bet >= BET_THRESHOLD and not self.fua_queued:
            self.fua_queued = True
            self.battle.queue_action(self._fua, self.char, "Aventurine follow-up")

    def _on_attacked(self, ev: E.Ev) -> None:
        # not modelled: CC resistance while holding a Wager, the Wager's "no HP loss" clause
        held, self.wager_at_hit = self.wager_at_hit, set()
        for t in ev.targets:
            if t.uid in held or _has_wager(t):
                self.add_bet(BET_PER_TRIGGER)
            if t is self.char:
                self.add_bet(int(self.p("talent", 0)))

    def _bingo(self, ev: E.Ev) -> None:
        act = ev.action
        owner = act.owner
        if act.kind != ActionKind.FUA or owner is self.char or not isinstance(owner, Character):
            return
        if not act.attacked or not owner.has_mod(WAGER) or self.bingo_left <= 0:
            return
        self.bingo_left -= 1
        self.add_bet(BET_PER_TRIGGER)

    def _fua(self) -> None:
        self.fua_queued = False
        if self.bet < BET_THRESHOLD:
            return
        self.bet -= BET_THRESHOLD
        if self.e(4):
            self.buff_self(
                Modifier("Unexpected Hanging Paradox", stats={S.DEF_PCT: self.ep(4, 0)}, duration=int(self.ep(4, 1)))
            )
        hits = int(self.p("talent", 1)) + (int(self.ep(4, 2)) if self.e(4) else 0)
        rec = self.sk("talent")
        with self.action(ActionKind.FUA, "talent", None, energy=float(rec["energy"]) * hits) as act:
            act.bounce(None, hits, self.p("talent", 2), stat="def", toughness=self.toughness("talent"))
        if self.trace(3):
            d = self.char.defense
            self._shield_all(self.tp(3, 0) * d + self.tp(3, 1), BINGO_SHIELD_TURNS)
            lowest = min(self.allies(), key=lambda c: self.battle.shield_value(c))
            self.wager(lowest, self.tp(3, 3) * d + self.tp(3, 4), BINGO_SHIELD_TURNS)
        if self.bet >= BET_THRESHOLD:
            self.add_bet(0)

    # ----------------------------------------------------------- Unnerved
    def _unnerved(self, ev: E.Ev) -> None:
        h = ev.hit
        if h.attacker.side == Side.ALLY and h.target.has_mod("Unnerved"):
            h.add(S.CRIT_DMG, self.p("ult", 2))

    # ------------------------------------------------------------- policy
    def take_turn(self) -> None:
        target = self.pick_target()
        if target is None:
            return
        rot = self.opts.get("rotation", "auto")
        need = rot == "skill" or (rot == "auto" and any(not c.has_mod(WAGER) for c in self.allies()))
        if need and self.can_skill():
            self.skill(target)
        else:
            self.basic(target)

    # ------------------------------------------------------------ actions
    def basic(self, target: Enemy | None) -> None:
        assert target is not None
        with self.action(ActionKind.BASIC, "basic", target) as act:
            act.hit(target, self.p("basic", 0), stat="def", toughness=self.toughness("basic"))
            if self.e(2) and target.alive:
                self.battle.try_debuff(
                    Modifier(
                        "Bounded Rationality",
                        stats={S.RES_REDUCTION: self.ep(2, 1)},
                        duration=int(self.ep(2, 2)),
                        kind=ModKind.DEBUFF,
                    ),
                    target,
                    self.char,
                    self.ep(2, 0),  # base chance (parameter, not shown in the text)
                )

    def skill(self, target: Enemy | None) -> None:
        with self.action(ActionKind.SKILL, "skill"):
            self._shield_all(self.skill_shield(), int(self.p("skill", 2)))

    def ult(self, target: Enemy | None) -> None:
        assert target is not None
        with self.action(ActionKind.ULT, "ult", target) as act:
            self.add_bet(self.battle.rng.randint(BET_PER_TRIGGER, int(self.p("ult", 0))))
            self.battle.apply(
                Modifier("Unnerved", duration=int(self.p("ult", 3)), kind=ModKind.DEBUFF, key="Unnerved"),
                target,
                self.char,
            )
            act.hit(target, self.p("ult", 1), stat="def", toughness=self.toughness("ult"))
        if self.e(1):
            self._shield_all(self.ep(1, 1) * self.skill_shield(), int(self.ep(1, 2)))
