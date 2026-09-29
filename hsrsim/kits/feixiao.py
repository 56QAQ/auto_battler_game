"""Feixiao (飞霄) — The Hunt / Wind. Flying Aureus instead of Energy; follow-ups after teammates' attacks.

Options:
* ``rotation``: "skill" (default) | "basic".
* ``technique_pulled``: enemies pulled in by the Technique (default: number of enemies in wave 1).

Feixiao has no Energy (``max_energy`` is 0): every 2 attacks by allies grant 1 Flying Aureus
(her Ultimate attacks do not count) and the Ultimate costs 6 of the 12 points she can hold.
"""

from __future__ import annotations

from typing import Any

from .. import events as E
from .. import stats as S
from ..battle import Action
from ..entities import Character, Enemy
from ..enums import ActionKind, DmgTag, Side
from ..modifiers import Modifier
from . import register
from .base import Kit

BASIC_SPLITS = [0.2, 0.2, 0.6]  # hit splits from the ability script (not parameters)
SKILL_SPLITS = [0.34, 0.33, 0.33]
BLITZ_ID = "122008"  # "Boltsunder Blitz" (bonus vs Weakness Broken targets)
WARAXE_ID = "122009"  # "Waraxe Skyward" (bonus vs targets that are not Weakness Broken)
FINISH_ID = "122014"  # the Ultimate's final hit


def _tough(rec: dict[str, Any], which: int = 0) -> float:
    t = rec["toughness"]
    if isinstance(t, list):
        return float(t[which]) if len(t) > which else 0.0
    return float(t or 0.0)


@register
class Feixiao(Kit):
    char_id = "1220"
    default_opts = {"technique_pulled": None}

    def setup(self) -> None:
        self.char.max_energy = 0.0  # Flying Aureus replaces Energy
        self.aureus = 0
        self.tally = 0  # attacks counted towards the next Flying Aureus point
        self.fua_ready = True  # Talent follow-up available (once per turn, resets at Feixiao's turn start)
        self.e2_used: dict[int, int] = {}
        self.no_count: Action | None = None  # the Technique's action does not count as an attack
        self.on(E.ATTACK_END, self._on_attack_end)
        self.on(E.TURN_START, self._on_turn_start)
        if self.trace(2):
            self.passive("Formshift", {f"{S.CRIT_DMG}:{DmgTag.FUA}": self.tp(2, 0)})
        if self.e(6):
            self.passive("Homeward I Near", {f"{S.RES_PEN}:{DmgTag.ULT}": self.ep(6, 0)})

    def on_battle_start(self) -> None:
        if self.trace(1):
            self.gain_aureus(int(self.tp(1, 0)))

    def technique(self) -> None:
        p = self.sk("technique")["params"][0]
        self.gain_aureus(int(p[3]))
        pulled = self.opts.get("technique_pulled")
        n = int(pulled) if pulled is not None else len(self.enemies())
        mult = p[2] + min(p[5], p[4] * max(0, n - 1))

        def blast() -> None:
            with self.action(ActionKind.EXTRA, None, label="Feixiao Technique", energy=0, sp=0) as act:
                self.no_count = act
                act.aoe(mult, extra={S.CRIT_RATE: 1.0})  # guaranteed CRIT
            self.no_count = None

        blast()
        self.on(E.WAVE_START, lambda ev: self.battle.queue_action(blast, self.char, "Feixiao Technique"))

    # ------------------------------------------------------- Flying Aureus
    def gain_aureus(self, n: int) -> None:
        self.aureus = min(int(self.p("talent", 3)), self.aureus + n)

    def ult_ready(self) -> bool:
        return self.aureus >= int(self.p("talent", 2))

    def pay_ult_cost(self) -> None:
        self.aureus -= int(self.p("talent", 2))

    def _count_attack(self, n: int = 1) -> None:
        self.tally += n
        need = int(self.p("talent", 1))
        while self.tally >= need:
            self.tally -= need
            self.gain_aureus(1)

    def _on_turn_start(self, ev: E.Ev) -> None:
        if ev.entity is not self.char or ev.extra:
            return
        if self.trace(1) and self.fua_ready:  # no Talent follow-up since the last turn
            self._count_attack()
        self.fua_ready = True

    def _on_attack_end(self, ev: E.Ev) -> None:
        act = ev.attack
        owner = act.owner
        if owner is None or owner.side != Side.ALLY or act.kind == ActionKind.ENEMY or not act.attacked:
            return
        if act is self.no_count:
            return
        if not (owner is self.char and act.kind == ActionKind.ULT):
            self._count_attack()
        if self.e(2) and act.kind == ActionKind.FUA:
            used = self.e2_used.get(self.battle.turns, 0)
            if used < int(self.ep(2, 0)):
                self.e2_used = {self.battle.turns: used + 1}
                self.gain_aureus(1)
        if owner is not self.char and isinstance(owner, Character) and self.fua_ready:
            self.fua_ready = False
            primary = act.target if isinstance(act.target, Enemy) else act.attacked[0]
            self.battle.queue_action(lambda: self._fua(primary), self.char, "Feixiao follow-up")

    # ------------------------------------------------------------ actions
    def _fua_tags(self) -> tuple[str, ...]:
        return (DmgTag.FUA, DmgTag.ULT) if self.e(6) else (DmgTag.FUA,)

    def _fua(self, target: Enemy | None) -> None:
        t = target if target is not None and target.alive and target.hp > 0 else self._random_enemy()
        if t is None:
            return
        with self.action(ActionKind.FUA, "talent", t, tags=self._fua_tags()) as act:
            self.buff_self(
                Modifier("Thunderhunt", stats={S.DMG_PCT: self.p("talent", 4)}, duration=int(self.p("talent", 5)))
            )
            if self.e(4):
                self.buff_self(
                    Modifier("Stormward I Hear", stats={S.SPD_PCT: self.ep(4, 1)}, duration=int(self.ep(4, 2)))
                )
            mult = self.p("talent", 0) + (self.ep(6, 1) if self.e(6) else 0.0)
            tough = self.toughness("talent") * (1.0 + (self.ep(4, 0) if self.e(4) else 0.0))
            act.hit(t, mult, toughness=tough)

    def _random_enemy(self) -> Enemy | None:
        pool = [e for e in self.enemies() if e.hp > 0] or self.enemies()
        return self.battle.rng.choice(pool) if pool else None

    def basic(self, target: Enemy | None) -> None:
        assert target is not None
        self.simple_basic(target, splits=BASIC_SPLITS)

    def skill(self, target: Enemy | None) -> None:
        assert target is not None
        with self.action(ActionKind.SKILL, "skill", target) as act:
            if self.trace(3):
                self.buff_self(
                    Modifier("Boltcatch", stats={S.ATK_PCT: self.tp(3, 0)}, duration=int(self.tp(3, 1)))
                )
            act.hit(target, self.p("skill", 0), toughness=self.toughness("skill"), splits=SKILL_SPLITS)
        self._fua(target)  # "immediately launches 1 extra instance of Talent's Follow-Up ATK"

    def ult(self, target: Enemy | None) -> None:
        t = target if target is not None and target.alive else self._random_enemy()
        if t is None:
            return
        tags = (DmgTag.ULT, DmgTag.FUA) if self.trace(2) else (DmgTag.ULT,)
        blitz, waraxe, finish = self.sk(BLITZ_ID), self.sk(WARAXE_ID), self.sk(FINISH_ID)
        e1_stacks = 0
        with self.action(ActionKind.ULT, "ult", t, tags=tags) as act:
            for _ in range(int(self.p("ult", 2))):
                if not (t.alive and t.hp > 0):
                    nt = self._random_enemy()
                    if nt is None:
                        break
                    t = nt
                # Boltsunder Blitz on a broken target, Waraxe Skyward otherwise: both get their bonus
                rec = blitz if t.broken else waraxe
                lv = rec["params"][self.level_of(rec) - 1]
                act.hit(
                    t,
                    lv[0] + lv[1],
                    toughness=_tough(rec),
                    ignore_weakness=True,
                    extra=self._ult_extra(t, e1_stacks),
                    label=rec["name"],
                )
                if self.e(1):
                    e1_stacks = min(int(self.ep(1, 1)), e1_stacks + 1)
            if not (t.alive and t.hp > 0):
                t = self._random_enemy() or t
            lv = finish["params"][self.level_of(finish) - 1]
            act.hit(
                t,
                lv[0],
                toughness=_tough(finish),
                ignore_weakness=True,
                extra=self._ult_extra(t, e1_stacks),
                label="Terrasplit",
            )

    def _ult_extra(self, t: Enemy, e1_stacks: int) -> dict[str, float]:
        extra: dict[str, float] = {}
        if not t.broken:
            extra[S.BREAK_EFF] = self.p("ult", 1)
        if e1_stacks:
            # "increases the Ultimate DMG dealt by an amount equal to 10% of the original DMG" per stack
            extra[S.FINAL_DMG] = self.ep(1, 0) * e1_stacks
        return extra
