"""Yunli (云璃) — Destruction / Physical. Counters when attacked; Parry ultimate -> "Intuit: Cull".

Options: ``rotation`` ("skill" default | "basic"); ``ult_timing``: "enemy_next" (default: cast the Ultimate
right before an enemy acts, so Parry catches its attack) | "asap".

The Ultimate consumes 120 of her 240 Energy, grants Parry and Taunts all enemies until the end of the
next unit's turn. Being attacked during Parry launches "Intuit: Cull" (blast + random bounces); if no
Counter happened, "Intuit: Slash" (blast only) is launched on a random enemy when Parry ends.
"""

from __future__ import annotations

from .. import events as E
from .. import stats as S
from ..battle import Action
from ..entities import Character, Enemy, Entity
from ..enums import ActionKind, DmgTag, Element
from ..modifiers import Modifier, Tick
from . import register
from .base import Kit

# approximation: Taunt is modelled as an overwhelming aggro bonus while Parry is active
TAUNT_AGGRO = 1e6
# approximation: Toughness of each random "Intuit: Cull" bounce (not in the skill data; community hit data)
CULL_BOUNCE_TOUGHNESS = 5.0
# "Intuit: Cull" main/adjacent hits are split 7 x 12% + 16% in the ability script
CULL_SPLITS = [0.12] * 7 + [0.16]


@register
class Yunli(Kit):
    char_id = "1221"
    default_opts = {"ult_timing": "enemy_next"}

    def setup(self) -> None:
        self.parry: Modifier | None = None
        self.parry_pending = False  # Parry cast; waiting for the next turn to start
        self.parry_turn: Entity | None = None  # Parry ends at the end of this unit's turn
        self.next_counter_cd = 0.0  # Ultimate: CRIT DMG of the next Counter
        self.slash_to_cull = False  # A2: the next "Intuit: Slash" becomes "Intuit: Cull"
        self.e6_action: Action | None = None
        self.on(E.ALLY_ATTACKED, self._on_attacked)
        self.on(E.TURN_START, self._on_turn_start)
        self.on(E.TURN_END, self._on_turn_end)
        if self.e(6):
            self.on(E.ACTION_START, self._e6)

    def technique(self) -> None:
        p = self.sk("technique")["params"][0]
        t = self._random_enemy()
        if t is not None:
            self._intuit(t, cull=True, dmg_bonus=p[0], label="Intuit: Cull (Technique)")

    # ------------------------------------------------------------ parry
    @property
    def in_parry(self) -> bool:
        return self.parry is not None and not self.parry.removed

    def _end_parry(self) -> None:
        if self.parry is not None:
            self.battle.remove_modifier(self.parry)
        self.parry = None
        self.parry_pending = False
        self.parry_turn = None

    def ult_ready(self) -> bool:
        return not self.in_parry and self.char.energy >= self.p("ult", 7) - 1e-9

    def pay_ult_cost(self) -> None:
        self.char.energy -= self.p("ult", 7)

    def want_ult(self) -> bool:
        if not super().want_ult():
            return False
        if self.opts.get("ult_timing", "enemy_next") == "asap":
            return True
        # hold while one of her Counters is still queued (it would consume the Ultimate's CRIT DMG bonus)
        if any(q.owner is self.char for q in self.battle.queue):
            return False
        # Parry lasts until the end of the next unit's turn: only an enemy acting next turns it into "Intuit: Cull"
        return isinstance(self.battle.next_actor(), Enemy)

    def _on_turn_start(self, ev: E.Ev) -> None:
        # approximation: only character and enemy turns count as "the next ally's or enemy's turn"
        if self.parry_pending and isinstance(ev.entity, (Character, Enemy)):
            self.parry_pending = False
            self.parry_turn = ev.entity

    def _on_turn_end(self, ev: E.Ev) -> None:
        if self.parry_turn is None or ev.entity is not self.parry_turn:
            return
        if self.in_parry:
            self._end_parry()
            self.battle.queue_action(self._slash, self.char, "Intuit: Slash")
        self.parry_turn = None

    def _on_attacked(self, ev: E.Ev) -> None:
        if self.char not in ev.targets or not self.char.alive:
            return
        self.battle.gain_energy(self.char, self.p("talent", 2))
        if self.e6_action is not None and ev.action is self.e6_action:
            return  # E6 already answered this enemy action with "Intuit: Cull"
        attacker = ev.attacker
        if self.in_parry:
            self._end_parry()
            self.battle.queue_action(lambda: self._intuit(attacker, cull=True), self.char, "Intuit: Cull")
        else:
            self.battle.queue_action(lambda: self._counter(attacker), self.char, "Yunli Counter")

    def _e6(self, ev: E.Ev) -> None:
        act = ev.action
        if self.in_parry and act.kind == ActionKind.ENEMY and isinstance(act.actor, Enemy):
            self.e6_action = act
            self._end_parry()
            attacker = act.actor
            self.battle.queue_action(lambda: self._intuit(attacker, cull=True), self.char, "Intuit: Cull (E6)")

    # ---------------------------------------------------------- counters
    def _random_enemy(self) -> Enemy | None:
        pool = [e for e in self.enemies() if e.hp > 0] or self.enemies()
        return self.battle.rng.choice(pool) if pool else None

    def _counter_extra(self) -> dict[str, float]:
        extra: dict[str, float] = {}
        if self.next_counter_cd:
            extra[S.CRIT_DMG] = self.next_counter_cd
            self.next_counter_cd = 0.0
        if self.e(2):
            extra[S.DEF_IGNORE] = self.ep(2, 0)
        return extra

    def _a6(self) -> None:
        if self.trace(3):
            self.buff_self(Modifier("True Sunder", stats={S.ATK_PCT: self.tp(3, 0)}, duration=1))

    def _counter(self, target: Enemy) -> None:
        t = target if target.alive and target.hp > 0 else self._random_enemy()
        if t is None:
            return
        self._a6()
        extra = self._counter_extra()
        with self.action(ActionKind.FUA, "talent", t, label="Counter (Flashforge)") as act:
            act.blast(
                t,
                self.p("talent", 0),
                self.p("talent", 1),
                toughness=(self.toughness("talent", 0), self.toughness("talent", 2)),
                extra=extra,
            )

    def _slash(self) -> None:
        t = self._random_enemy()
        if t is None:
            return
        if self.slash_to_cull:
            self.slash_to_cull = False
            self._intuit(t, cull=True)
        else:
            self._intuit(t, cull=False)
            if self.trace(1):
                self.slash_to_cull = True

    def _intuit(self, target: Enemy, cull: bool, dmg_bonus: float = 0.0, label: str | None = None) -> None:
        t = target if target.alive and target.hp > 0 else self._random_enemy()
        if t is None:
            return
        self._a6()
        extra = self._counter_extra()
        dmg = dmg_bonus + (self.ep(1, 0) if self.e(1) else 0.0)
        if dmg:
            extra[S.DMG_PCT] = dmg
        if self.e(6):
            extra[S.CRIT_RATE] = self.ep(6, 0)
            extra[f"{S.RES_PEN}:{Element.PHYSICAL.value}"] = self.ep(6, 1)
        name = label or ("Intuit: Cull" if cull else "Intuit: Slash")
        # "When Yunli deals DMG via this ability, it's considered as dealing Ultimate DMG"
        # approximation: the Counter itself generates no Energy (only the +15 for being attacked)
        with self.action(ActionKind.FUA, "ult", t, label=name, tags=(DmgTag.ULT, DmgTag.FUA), energy=0, sp=0) as act:
            act.blast(
                t,
                self.p("ult", 0),
                self.p("ult", 5),
                toughness=(self.toughness("ult", 0), self.toughness("ult", 2)),
                splits=CULL_SPLITS if cull else None,
                extra=extra,
            )
            if cull:
                n = int(self.p("ult", 3)) + (int(self.ep(1, 1)) if self.e(1) else 0)
                act.bounce(None, n, self.p("ult", 6), toughness=CULL_BOUNCE_TOUGHNESS, extra=extra)
        if self.e(4):
            self.buff_self(
                Modifier("Artisan's Ironsong", stats={S.EFFECT_RES: self.ep(4, 0)}, duration=int(self.ep(4, 1)))
            )

    # ------------------------------------------------------------ actions
    def basic(self, target: Enemy | None) -> None:
        assert target is not None
        self.simple_basic(target)

    def skill(self, target: Enemy | None) -> None:
        assert target is not None
        with self.action(ActionKind.SKILL, "skill", target) as act:
            self.battle.heal(self.char, self.p("skill", 2) * self.char.atk + self.p("skill", 3), self.char)
            act.blast(
                target,
                self.p("skill", 0),
                self.p("skill", 1),
                toughness=(self.toughness("skill", 0), self.toughness("skill", 2)),
            )

    def ult(self, target: Enemy | None) -> None:
        with self.action(ActionKind.ULT, "ult"):
            stats = {S.AGGRO: TAUNT_AGGRO}
            if self.trace(2):
                stats[S.MITIGATION] = self.tp(2, 0)  # not modelled: Crowd Control resistance
            self.parry = self.buff_self(Modifier("Parry", stats=stats, tick=Tick.NONE, key="Yunli Parry"))
            self.next_counter_cd = self.p("ult", 1)
            self.parry_pending = True
            self.parry_turn = None
