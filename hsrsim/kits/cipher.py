"""Cipher (赛飞儿) — Nihility / Quantum. Tallies the team's DMG on the "Patron" and releases it as True DMG
with her Ultimate; follow-up attack when teammates attack the Patron.

Options (``default_opts``):
  * ``rotation``: ``"skill"`` (Skill whenever SP allows, default) or ``"basic"``.
"""

from __future__ import annotations

from .. import events as E
from .. import stats as S
from ..entities import Enemy
from ..enums import ActionKind, DmgTag, Element, Side
from ..modifiers import Modifier, ModKind, Stacking, Tick
from . import register
from .base import Kit

# A2 "When Cipher's SPD is higher than or equal to 140/170" (literal thresholds, not parameters)
A2_SPD = (140.0, 170.0)


@register
class Cipher(Kit):
    char_id = "1406"

    def setup(self) -> None:
        self.tally = 0.0
        self.patron: Enemy | None = None
        self.fua_left = int(self.p("talent", 2))
        self.tally_bonus_once = 0.0  # Technique: extra tally ratio for the technique's own DMG
        self.on(E.DAMAGE_DEALT, self._on_damage)
        self.on(E.ATTACK_END, self._on_attack_end)
        self.on(E.TURN_START, self._turn_start)
        self.on(E.KILL, lambda ev: self._ensure_patron())
        self.on(E.WAVE_START, lambda ev: self._ensure_patron())
        if self.trace(1):
            self.passive("Empyrean Strides", {}, dyn=self._a2_cr, dyn_keys={S.CRIT_RATE})
        if self.trace(3):
            self.passive("Sleight of Sky", {S.VULN: self.tp(3, 0)}, scope=self.enemy_scope)
        if self.e(2):
            self.on(E.AFTER_HIT, self._e2)

    def on_battle_start(self) -> None:
        self._ensure_patron()

    def technique(self) -> None:
        p = self.sk("technique")["params"][0]
        self.tally_bonus_once = p[1]
        with self.action(ActionKind.EXTRA, None, label="Puss in Boots (Technique)", energy=0, sp=0) as act:
            act.aoe(p[2], toughness=self.toughness("technique"))
        self.tally_bonus_once = 0.0

    # -------------------------------------------------------------- Patron
    def _ensure_patron(self) -> None:
        if self.patron is not None and self.patron.alive:
            return
        t = self.battle.default_target()
        if t is not None:
            self.make_patron(t)

    def make_patron(self, t: Enemy) -> None:
        if self.patron is not None and self.patron is not t:
            self.battle.remove_named(self.patron, "Patron")
        self.patron = t
        self.battle.apply(
            Modifier("Patron", kind=ModKind.OTHER, tick=Tick.NONE, dispellable=False, key="Cipher Patron"), t, self.char
        )

    # --------------------------------------------------------------- tally
    def _a2_level(self) -> int:
        if not self.trace(1):
            return 0
        spd = self.char.spd
        return 2 if spd >= A2_SPD[1] else 1 if spd >= A2_SPD[0] else 0

    def _a2_cr(self, mod: Modifier, key: str, ent: object) -> float:
        lvl = self._a2_level()
        return self.tp(1, lvl - 1) if lvl else 0.0

    def _on_damage(self, ev: E.Ev) -> None:
        rec = ev.record
        credited = ev.credited
        if DmgTag.TRUE in rec.tags or credited is None or credited.side != Side.ALLY:
            return
        target = ev.target
        amount = rec.amount - rec.overkill
        if amount <= 0:
            return
        if target is self.patron:
            ratio = self.p("talent", 1)
        elif self.trace(2):
            ratio = self.tp(2, 0)
        else:
            return
        act = self.battle.current_action
        if self.e(6) and act is not None and act.data.get("cipher_fua"):
            ratio += self.ep(6, 2)
        lvl = self._a2_level()
        mult = 1.0 + (self.tp(1, 1 + lvl) if lvl else 0.0) + self.tally_bonus_once
        if self.e(1):
            mult *= self.ep(1, 2)
        self.tally += amount * ratio * mult

    # ------------------------------------------------------------- actions
    def _turn_start(self, ev: E.Ev) -> None:
        if ev.entity is self.char:
            self.fua_left = int(self.p("talent", 2))

    def basic(self, target: Enemy | None) -> None:
        assert target is not None
        self.simple_basic(target)

    def skill(self, target: Enemy | None) -> None:
        assert target is not None
        self.make_patron(target)
        with self.action(ActionKind.SKILL, "skill", target) as act:
            for t in [target, *self.battle.adjacent(target)]:
                self.battle.try_debuff(
                    Modifier(
                        "Weakened (Cipher)",
                        stats={S.WEAKEN: self.p("skill", 2)},
                        duration=int(self.p("skill", 3)),
                        kind=ModKind.DEBUFF,
                    ),
                    t,
                    self.char,
                    self.p("skill", 5),
                )
            self.buff_self(
                Modifier(
                    "Hey, Jackpot for the Taking",
                    stats={S.ATK_PCT: self.p("skill", 4)},
                    duration=int(self.p("skill", 3)),
                )
            )
            act.blast(
                target,
                self.p("skill", 0),
                self.p("skill", 1),
                toughness=(self.toughness("skill", 0), self.toughness("skill", 2)),
            )

    def ult(self, target: Enemy | None) -> None:
        if target is None:
            return
        self.make_patron(target)
        b = self.battle
        with self.action(ActionKind.ULT, "ult", target) as act:
            tally = self.tally
            act.hit(target, self.p("ult", 0), toughness=self.toughness("ult", 0))
            if target.alive:
                b.true_damage(tally, self.p("ult", 1), target, self.char, "Kitty Phantom Thief (True DMG)")
            targets = [target, *b.adjacent(target)]
            act.blast(
                target,
                self.p("ult", 3),
                self.p("ult", 3),
                toughness=(0.0, self.toughness("ult", 2)),
            )
            share = self.p("ult", 2) / max(1, len(targets))
            for t in targets:
                if t.alive:
                    b.true_damage(tally, share, t, self.char, "Kitty Phantom Thief (True DMG)")
        self.tally = self.ep(6, 0) * tally if self.e(6) else 0.0

    # --------------------------------------------------------------- talent
    def _on_attack_end(self, ev: E.Ev) -> None:
        act = ev.attack
        owner = act.owner
        patron = self.patron
        if owner is None or owner.side != Side.ALLY or patron is None or patron not in act.attacked:
            return
        if self.e(4) and patron.alive:
            self.battle.additional_damage(
                self.char,
                patron,
                self.ep(4, 0),
                element=Element.QUANTUM,
                label="The Jig Is Up (Cipher E4)",
                tags=(DmgTag.ADDITIONAL,),
            )
        if owner is self.char or self.fua_left <= 0:
            return
        self.fua_left -= 1
        self.battle.queue_action(self._fua, self.char, "Cipher follow-up")

    def _fua(self) -> None:
        self._ensure_patron()
        t = self.patron
        if t is None:
            return
        extra: dict[str, float] = {}
        if self.trace(3):
            extra[S.CRIT_DMG] = self.tp(3, 1)
        if self.e(6):
            extra[S.DMG_PCT] = self.ep(6, 1)
        with self.action(ActionKind.FUA, "talent", t) as act:
            act.data["cipher_fua"] = True
            if self.e(1):
                self.buff_self(
                    Modifier(
                        "Read the Room, Seek the Glee", stats={S.ATK_PCT: self.ep(1, 0)}, duration=int(self.ep(1, 1))
                    )
                )
            act.hit(t, self.p("talent", 0), toughness=self.toughness("talent"), extra=extra)

    def _e2(self, ev: E.Ev) -> None:
        h = ev.hit
        if h.attacker is not self.char or h.action is None or not h.target.alive:
            return
        self.battle.try_debuff(
            Modifier(
                "In the Fray, Nab On a Spree",
                stats={S.VULN: self.ep(2, 2)},
                duration=int(self.ep(2, 0)),
                kind=ModKind.DEBUFF,
                stacking=Stacking.REFRESH,
            ),
            h.target,
            self.char,
            self.ep(2, 1),
        )
