"""Qingque (青雀) — Erudition / Quantum. Jade tiles: Skill draws tiles and stacks DMG%; 4 of a suit enters
"Hidden Hand" (ATK up, Basic ATK becomes the Blast "Cherry on Top!").

Options (``default_opts``):

* ``rotation``: ``"skill"`` (default: use the Skill until Hidden Hand, ``max_skills`` or the SP reserve is
  reached, then Basic ATK) or ``"basic"``.
* ``max_skills``: maximum Skills per turn (default 4).
* ``sp_reserve``: SP kept for the team (default 0).
"""

from __future__ import annotations

from collections import Counter

from .. import events as E
from .. import stats as S
from ..entities import Character, Enemy
from ..enums import ActionKind, DmgTag
from ..modifiers import Modifier, Stacking, Tick
from . import register
from .base import Kit

ENHANCED_BASIC = "120108"  # "Cherry on Top!"
SUITS = 3  # "randomly draws 1 tile from 3 different suits" (literal)
HAND_MAX = 4  # "can hold up to 4 tiles at one time" / "4 tiles of the same suit" (literal)
A2_SP = 1  # Tile Battle: "Restores 1 Skill Point when using the Skill" (literal)
E6_SP = 1  # E6: "Recovers 1 Skill Point after using Enhanced Basic ATK" (literal)
HIDDEN_HAND = "Hidden Hand"


@register
class Qingque(Kit):
    char_id = "1201"
    default_opts = {"rotation": "skill", "max_skills": 4, "sp_reserve": 0}

    def setup(self) -> None:
        self.hand: list[int] = []
        self.hidden_hand = False
        self.a2_used = False
        self.self_sufficer = False
        if self.e(1):
            self.passive("Rise Through the Tiles", {f"{S.DMG_PCT}:{DmgTag.ULT}": self.ep(1, 0)})
        self.on(E.TURN_START, self._on_turn_start)
        self.on(E.TURN_END, self._on_turn_end)

    def technique(self) -> None:
        self._draw(int(self.sk("technique")["params"][0][0]))

    # --------------------------------------------------------------- tiles
    def _counts(self) -> Counter[int]:
        return Counter(self.hand)

    def _add_tile(self, suit: int) -> None:
        self.hand.append(suit)
        if len(self.hand) > HAND_MAX:
            # approximation: a full hand discards one tile of the suit with the fewest tiles (random on ties)
            counts = self._counts()
            low = min(counts.values())
            drop = self.battle.rng.choice(sorted(s for s, n in counts.items() if n == low))
            self.hand.remove(drop)

    def _draw(self, n: int) -> None:
        for _ in range(n):
            self._add_tile(self.battle.rng.randrange(SUITS))
            if self.e(2):  # approximation: 1 Energy per tile drawn
                self.battle.gain_energy(self.char, self.ep(2, 0))

    def _toss(self) -> None:
        """Basic ATK: toss 1 tile from the suit with the fewest tiles."""
        if self.hand:
            counts = self._counts()
            self.hand.remove(min(counts, key=lambda s: (counts[s], s)))

    def _check_hidden_hand(self) -> None:
        if not self.hidden_hand and any(n >= HAND_MAX for n in self._counts().values()):
            self._enter_hidden_hand()

    def _enter_hidden_hand(self) -> None:
        """Consume all tiles and enter "Hidden Hand" (no-op on the state when already active)."""
        self.hand.clear()
        if self.hidden_hand:
            return
        self.hidden_hand = True
        self.buff_self(Modifier(HIDDEN_HAND, stats={S.ATK_PCT: self.p("talent", 0)}, tick=Tick.NONE))

    def _on_turn_start(self, ev: E.Ev) -> None:
        if not isinstance(ev.entity, Character):  # approximation: summon/memosprite turns do not draw tiles
            return
        self._draw(1)
        if ev.entity is self.char:
            self._check_hidden_hand()

    def _on_turn_end(self, ev: E.Ev) -> None:
        if ev.entity is self.char:
            self.self_sufficer = False

    # -------------------------------------------------------------- policy
    def take_turn(self) -> None:
        target = self.pick_target()
        if target is None:
            return
        if self.opts.get("rotation", "skill") == "skill":
            used = 0
            reserve = int(self.opts.get("sp_reserve", 0))
            while (
                not self.hidden_hand
                and used < int(self.opts.get("max_skills", 4))
                and self.can_skill()
                and self.battle.sp > reserve
            ):
                self.skill(target)
                used += 1
        target = target if target.alive else self.pick_target()
        if target is not None:
            self.basic(target)

    # ------------------------------------------------------------- actions
    def basic(self, target: Enemy | None) -> None:
        assert target is not None
        if self.hidden_hand:
            self.enhanced_basic(target)
            return
        self._toss()
        self.simple_basic(target)
        self._self_sufficer(target, self.p("basic", 0), self.toughness("basic"))

    def enhanced_basic(self, target: Enemy) -> None:
        rec = self.sk(ENHANCED_BASIC)
        prm = rec["params"][self.level_of(rec) - 1]
        main_t = self.toughness(ENHANCED_BASIC, 0)
        with self.action(ActionKind.BASIC, rec, target, sp=0) as act:  # "cannot recover Skill Points"
            act.blast(target, prm[0], prm[1], toughness=(main_t, self.toughness(ENHANCED_BASIC, 2)), splits="data")
        self._self_sufficer(target, prm[0], main_t, adj=(prm[1], self.toughness(ENHANCED_BASIC, 2)))
        self.hidden_hand = False
        self.battle.remove_named(self.char, HIDDEN_HAND)
        if self.trace(3):
            self.buff_self(Modifier("Winning Hand", stats={S.SPD_PCT: self.tp(3, 0)}, duration=1))
        if self.e(6):
            self.battle.gain_sp(E6_SP, self.char)

    def _self_sufficer(
        self, target: Enemy, mult: float, toughness: float, adj: tuple[float, float] | None = None
    ) -> None:
        """E4: the Basic ATK / Enhanced Basic ATK is followed by a Follow-Up ATK with the same multiplier.

        ``adj`` = (multiplier, Toughness) on adjacent enemies: after "Cherry on Top!" the Follow-Up ATK is a
        Blast as well (the game's Rank04_ATK_Special ability also hits AbilityTargetAdjoinEntity)."""
        if not self.self_sufficer:
            return
        self.self_sufficer = False
        t = target if target.alive and target.hp > 0 else self.pick_target()
        if t is None:
            return
        # approximation: "100% of Basic ATK DMG" = same multipliers/Toughness as the Basic ATK, performed right
        # after the Basic ATK (while Hidden Hand's ATK bonus is still active)
        with self.action(ActionKind.FUA, "basic", t, label="Self-Sufficer", energy=0, sp=0) as act:
            if adj is None:
                act.hit(t, mult, toughness=toughness)
            else:
                act.blast(t, mult, adj[0], toughness=(toughness, adj[1]))

    def skill(self, target: Enemy | None) -> None:
        with self.action(ActionKind.SKILL, "skill", target):
            self._draw(int(self.p("skill", 0)))
            per = self.p("skill", 1) + (self.tp(2, 0) if self.trace(2) else 0.0)
            self.buff_self(
                Modifier(
                    "A Scoop of Moon",
                    stats={S.DMG_PCT: per},
                    duration=1,
                    skip_first_tick=False,  # "until the end of the current turn"
                    stacking=Stacking.STACK,
                    max_stacks=int(self.p("skill", 2)),
                )
            )
            if self.trace(1) and not self.a2_used:
                self.a2_used = True
                self.battle.gain_sp(A2_SP, self.char)
            if self.e(4) and self.battle.rng.random() < self.ep(4, 0):
                self.self_sufficer = True
        self._check_hidden_hand()

    def ult(self, target: Enemy | None) -> None:
        with self.action(ActionKind.ULT, "ult", target) as act:
            act.aoe(self.p("ult", 0), toughness=self.toughness("ult", 1), main_target=target, splits="data")
        # the 4 tiles of one suit are consumed at once and "Hidden Hand" starts immediately, also outside her turn
        # (the game's Ultimate script removes the tiles and adds the Hidden Hand modifier right after the DMG)
        self._enter_hidden_hand()
