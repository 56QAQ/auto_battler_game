"""Jiaoqiu (椒丘) — Nihility / Fire. Ashen Roast: stacking vulnerability + Burn-like DoT; Ultimate DMG zone.

Options: ``rotation`` ("skill" default | "basic").

Ashen Roast is a stacking debuff (1 stack: +15% DMG taken, +5% per further stack) that also counts as
Burn and deals a Fire DoT at the start of the holder's turn. Jiaoqiu's Basic ATK / Skill / Ultimate
apply a Talent stack to every enemy they hit; the Skill adds one more stack on the primary target.
"""

from __future__ import annotations

from .. import events as E
from .. import stats as S
from ..battle import Battle
from ..entities import Enemy, Entity
from ..enums import ActionKind, DmgTag, Element, Side
from ..modifiers import DotModifier, Modifier, ModKind, Stacking, Tick
from . import register
from .base import Kit

ASHEN_ROAST = "Ashen Roast"
ZONE = "Pyrograph Arcanum (Zone)"


@register
class Jiaoqiu(Kit):
    char_id = "1218"

    def setup(self) -> None:
        self.zone: Modifier | None = None
        self.zone_triggers = 0
        self.zone_peak = 0  # highest Ashen Roast stack count seen while the Zone exists (A6)
        self.zone_seen: set[tuple[int, int]] = set()  # (enemy uid, turn) pairs that already triggered
        self.on(E.ACTION_START, self._zone_trigger)
        if self.trace(2):
            self.passive("Hearth Kindle", {}, dyn=self._a4, dyn_keys={S.ATK_PCT})
        if self.trace(3):
            self.on(E.ENEMY_SPAWNED, self._a6)
        if self.e(1):
            self.on(E.BEFORE_HIT, self._e1)
        if self.e(6):
            self.on(E.KILL, self._e6_transfer)

    def on_battle_start(self) -> None:
        if self.trace(1):
            # MAvatar_Jiaoqiu_00_Tree01_recoverSP: ModifySPNew AddValue (scales with ERR)
            self.battle.gain_energy(self.char, self.tp(1, 0))

    def technique(self) -> None:
        p = self.sk("technique")["params"][0]
        with self.action(ActionKind.EXTRA, None, label="Jiaoqiu Technique", energy=0, sp=0) as act:
            act.aoe(p[0])
            for e in self.enemies():
                self.add_roast(e, 1, p[2])

    # ------------------------------------------------------------ passives
    def _a4(self, mod: Modifier, key: str, ent: Entity) -> float:
        over = self.char.stat(S.EHR) - self.tp(2, 0)
        if over <= 0:
            return 0.0
        return min(self.tp(2, 3), int(over / self.tp(2, 1) + 1e-9) * self.tp(2, 2))

    def _e1(self, ev: E.Ev) -> None:
        hit = ev.hit
        if hit.attacker.side == Side.ALLY and hit.target.has_mod(ASHEN_ROAST):
            hit.add(S.DMG_PCT, self.ep(1, 0))

    # --------------------------------------------------------- Ashen Roast
    def max_roast(self) -> int:
        return int(self.ep(6, 1)) if self.e(6) else int(self.p("talent", 3))

    def roast(self, e: Enemy) -> int:
        m = e.get_mod(ASHEN_ROAST)
        return m.stacks if m is not None else 0

    def _roast_vuln(self, mod: Modifier, key: str, ent: Entity) -> float:
        return self.p("talent", 1) + self.p("talent", 2) * max(0, mod.stacks - 1)

    def _roast_mod(self, target: Enemy, stacks: int) -> DotModifier:
        jq = self.char

        def dmg(mod: DotModifier, b: Battle, ratio: float) -> float:
            mult = self.p("talent", 5) + (self.ep(2, 0) if self.e(2) else 0.0)
            return b.dot_damage(
                jq, target, Element.FIRE, mult, label=ASHEN_ROAST, tags=(DmgTag.DOT, "burn", "ashen_roast"), ratio=ratio
            )

        stats = {S.RES_REDUCTION: self.ep(6, 2)} if self.e(6) else {}
        return DotModifier(
            ASHEN_ROAST,
            dot_type="burn",  # "considered as being Burned"
            damage_fn=dmg,
            duration=int(self.p("talent", 4)),
            stacks=min(stacks, self.max_roast()),
            max_stacks=self.max_roast(),
            stacking=Stacking.STACK,
            stats=stats,
            dyn=self._roast_vuln,
            dyn_keys={S.VULN},
            key=ASHEN_ROAST,
            tags={"ashen_roast"},
        )

    def add_roast(self, target: Enemy, n: int, chance: float | None = None) -> None:
        """Inflict ``n`` Ashen Roast stacks (``chance`` None = no hit roll)."""
        if n <= 0 or not target.alive:
            return
        mod = self._roast_mod(target, n)
        if chance is None:
            self.battle.apply(mod, target, self.char)
        else:
            self.battle.try_debuff(mod, target, self.char, chance)
        self._track_peak()

    def set_roast(self, target: Enemy, n: int) -> None:
        """Set the stack count (Ultimate): keeps the remaining duration of an existing Ashen Roast."""
        n = min(n, self.max_roast())
        m = target.get_mod(ASHEN_ROAST)
        if m is not None:
            m.stacks = max(m.stacks, n)
        elif n > 0 and target.alive:
            self.battle.apply(self._roast_mod(target, n), target, self.char)
        self._track_peak()

    def _talent_stacks(self) -> int:
        return 1 + (int(self.ep(1, 1)) if self.e(1) else 0)

    def _talent_roast(self, target: Enemy) -> None:
        self.add_roast(target, self._talent_stacks(), self.p("talent", 0))

    def _track_peak(self) -> None:
        if self.zone_active:
            self.zone_peak = max([self.zone_peak] + [self.roast(e) for e in self.enemies()])

    def _e6_transfer(self, ev: E.Ev) -> None:
        n = self.roast(ev.target)
        others = [e for e in self.enemies() if e is not ev.target and e.hp > 0]
        if n <= 0 or not others:
            return
        dest = min(others, key=self.roast)
        self.add_roast(dest, n)

    # --------------------------------------------------------------- zone
    @property
    def zone_active(self) -> bool:
        return self.zone is not None and not self.zone.removed

    def _zone_trigger(self, ev: E.Ev) -> None:
        act = ev.action
        e = act.actor
        if not self.zone_active or act.kind != ActionKind.ENEMY or not isinstance(e, Enemy):
            return
        key = (e.uid, self.battle.turns)
        if key in self.zone_seen or self.zone_triggers >= int(self.p("ult", 4)):
            return
        self.zone_seen.add(key)
        self.zone_triggers += 1
        self.add_roast(e, 1, self.p("ult", 1))

    def _a6(self, ev: E.Ev) -> None:
        if self.zone_active:
            self.add_roast(ev.enemy, max(self.zone_peak, int(self.tp(3, 0))))

    # ------------------------------------------------------------ actions
    def basic(self, target: Enemy | None) -> None:
        assert target is not None
        with self.action(ActionKind.BASIC, "basic", target) as act:
            self._talent_roast(target)  # the game applies the Talent stack before the hit
            act.hit(target, self.p("basic", 0), toughness=self.toughness("basic"))

    def skill(self, target: Enemy | None) -> None:
        assert target is not None
        with self.action(ActionKind.SKILL, "skill", target) as act:
            # ability script order: Talent stack on every target hit -> DMG -> the Skill's own stack on the primary
            for e in [target, *self.battle.adjacent(target)]:
                self._talent_roast(e)
            act.blast(
                target,
                self.p("skill", 0),
                self.p("skill", 1),
                toughness=(self.toughness("skill", 0), self.toughness("skill", 2)),
            )
            self.add_roast(target, 1, self.p("skill", 2))

    def ult(self, target: Enemy | None) -> None:
        with self.action(ActionKind.ULT, "ult", target) as act:
            highest = max([self.roast(e) for e in self.enemies()] + [0])
            for e in self.enemies():
                self.set_roast(e, highest)
            stats = {f"{S.VULN}:{DmgTag.ULT}": self.p("ult", 2)}
            if self.e(4):
                stats[S.ATK_PCT] = -self.ep(4, 0)  # enemy ATK -15% while the Zone exists
            self.zone = self.buff_self(
                Modifier(
                    ZONE,
                    stats=stats,
                    duration=int(self.p("ult", 3)),
                    tick=Tick.SOURCE_TURN_START,
                    kind=ModKind.OTHER,
                    scope=self.enemy_scope,
                    key=ZONE,
                )
            )
            self.zone_triggers = 0
            self.zone_seen.clear()
            self.zone_peak = highest
            for e in self.enemies():
                self._talent_roast(e)
            act.aoe(self.p("ult", 0), toughness=self.toughness("ult", 1), main_target=target)
