"""Dan Heng (丹恒) — Hunt / Wind. Slow on CRIT Skill, stronger Ultimate vs Slowed enemies,
Wind RES PEN on his next attack after an ally targets him (Talent).

Options: ``rotation`` (``"skill"`` default / ``"basic"``).
"""

from __future__ import annotations

from .. import events as E
from .. import stats as S
from ..battle import Hit
from ..entities import Character, Enemy, Entity
from ..enums import ActionKind, DmgTag
from ..modifiers import Modifier, ModKind
from . import register
from .base import Kit

TALENT_BUFF = "Superiority of Reach"
# E2: "Reduces Talent cooldown by 1 turn" (literal in the text)
E2_COOLDOWN_REDUCTION = 1


def is_slowed(e: Entity) -> bool:
    """approximation: any active debuff that lowers SPD counts as Slowed (Slow, Imprisonment, SPD Bugs ...)."""
    for m in e.modifiers:
        if m.removed or not m.is_debuff:
            continue
        if "slow" in m.tags or m.value(S.SPD_PCT, e) < 0 or m.value(S.SPD_FLAT, e) < 0:
            return True
    return False


@register
class DanHeng(Kit):
    char_id = "1002"

    def setup(self) -> None:
        self.talent_cd = 0
        self.on(E.ACTION_START, self._targeted)
        self.on(E.MOD_APPLIED, self._buffed)
        self.on(E.HEALED, self._healed)
        self.on(E.TURN_END, self._turn_end)
        self.on(E.ATTACK_END, self._after_attack)
        self.on(E.BEFORE_HIT, self._before_hit)
        if self.trace(1):
            self.passive("Hidden Dragon", {}, dyn=self._a2, dyn_keys={S.AGGRO_PCT})

    def technique(self) -> None:
        p = self.sk("technique")["params"][0]
        self.buff_self(Modifier("Splitting Spearhead", stats={S.ATK_PCT: p[0]}, duration=int(p[1])))

    def _a2(self, mod: Modifier, key: str, ent: Entity) -> float:
        return -self.tp(1, 1) if self.char.hp_ratio <= self.tp(1, 0) else 0.0

    # ------------------------------------------------------------ talent
    def _cooldown(self) -> int:
        return int(self.p("talent", 1)) - (E2_COOLDOWN_REDUCTION if self.e(2) else 0)

    def _trigger_talent(self) -> None:
        if self.talent_cd > 0:
            return
        self.talent_cd = self._cooldown()
        self.buff_self(Modifier(TALENT_BUFF, stats={f"{S.RES_PEN}:Wind": self.p("talent", 0)}))

    def _by_ally(self, source: object) -> bool:
        act = self.battle.current_action
        return (
            isinstance(source, Character)
            and source is not self.char
            and act is not None
            and act.owner is source
            and act.kind != ActionKind.ENEMY
        )

    def _targeted(self, ev: E.Ev) -> None:
        act = ev.action
        if act.target is self.char and isinstance(act.owner, Character) and act.owner is not self.char:
            self._trigger_talent()

    def _buffed(self, ev: E.Ev) -> None:
        # approximation: team-wide ally abilities (buffs / shields) count as "targeting" Dan Heng
        if ev.target is self.char and ev.mod.kind == ModKind.BUFF and self._by_ally(ev.mod.source):
            self._trigger_talent()

    def _healed(self, ev: E.Ev) -> None:
        if ev.entity is self.char and self._by_ally(ev.source):
            self._trigger_talent()

    def _turn_end(self, ev: E.Ev) -> None:
        if ev.entity is self.char and self.talent_cd > 0:
            self.talent_cd -= 1

    def _after_attack(self, ev: E.Ev) -> None:
        act = ev.attack
        if act.owner is not self.char:
            return
        self.battle.remove_named(self.char, TALENT_BUFF)  # consumed by the attack
        if self.trace(2) and self.battle.rng.random() < self.tp(2, 0):  # fixed chance
            self.buff_self(Modifier("Faster Than Light", stats={S.SPD_PCT: self.tp(2, 1)}, duration=int(self.tp(2, 2))))

    def _before_hit(self, ev: E.Ev) -> None:
        hit = ev.hit
        if hit.attacker is not self.char:
            return
        if self.trace(3) and DmgTag.BASIC in hit.tags and is_slowed(hit.target):
            hit.add(S.DMG_PCT, self.tp(3, 0))
        if self.e(1) and hit.target.hp_ratio >= self.ep(1, 0):
            hit.add(S.CRIT_RATE, self.ep(1, 1))

    # ----------------------------------------------------------- actions
    def _crit(self, hit: Hit) -> bool:
        if hit.crit is not None:  # crit_mode "random"
            return hit.crit
        # approximation: in "expected" crit mode roll the hit's CRIT Rate for the Slow trigger
        cr = self.char.stat_q(S.CRIT_RATE, hit.quals, hit.extra)
        return self.battle.rng.random() < cr

    def basic(self, target: Enemy | None) -> None:
        assert target is not None
        self.simple_basic(target)

    def skill(self, target: Enemy | None) -> None:
        assert target is not None
        with self.action(ActionKind.SKILL, "skill", target) as act:
            hits = act.hit(target, self.p("skill", 0), toughness=self.toughness("skill"), splits="data")
            if target.hp > 0 and any(self._crit(h) for h in hits):
                slow = self.p("skill", 1) + (self.ep(6, 0) if self.e(6) else 0.0)
                self.battle.try_debuff(
                    Modifier(
                        "Slow (Dan Heng)",
                        stats={S.SPD_PCT: -slow},
                        duration=int(self.p("skill", 2)),
                        kind=ModKind.DEBUFF,
                        tags={"slow"},
                    ),
                    target,
                    self.char,
                    self.p("skill", 3),
                )

    def ult(self, target: Enemy | None) -> None:
        assert target is not None
        mult = self.p("ult", 0) + (self.p("ult", 1) if is_slowed(target) else 0.0)
        with self.action(ActionKind.ULT, "ult", target) as act:
            act.hit(target, mult, toughness=self.toughness("ult"), splits="data")
            killed = target.hp <= 0
        if self.e(4) and killed:
            self.battle.queue_extra_turn(self.char)
