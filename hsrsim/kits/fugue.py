"""Fugue (忘归人) — Nihility / Fire. Foxian Prayer (Break Effect, toughness vs any Weakness), DEF shred,
Cloudflame Luster (a second Toughness bar), team Super Break on Weakness Broken enemies.

Options: ``target``: name of the ally receiving Foxian Prayer (default: the first teammate);
``rotation``: "skill" (default: Skill whenever Torrid Scorch is not active) | "basic".
"""

from __future__ import annotations

from .. import events as E
from .. import stats as S
from ..entities import Character, Enemy, Entity
from ..enums import ActionKind, Side
from ..modifiers import Modifier, ModKind, Stacking, Tick
from . import register
from .base import Kit

ENHANCED_BASIC_ID = "122508"
PRAYER = "Foxian Prayer"
SCORCH = "Torrid Scorch"
DEF_DOWN = "Virtue Beckons Bliss (DEF Reduction)"
ULT_SPLITS = [0.6, 0.1, 0.1, 0.1, 0.1]  # hit splits from the ability script (not parameters)


@register
class Fugue(Kit):
    char_id = "1225"
    default_opts = {"target": None}

    def setup(self) -> None:
        self.scorch: Modifier | None = None
        self.first_skill = True
        self.luster: dict[int, float] = {}  # Cloudflame Luster left per enemy uid
        self.on(E.ENEMY_SPAWNED, lambda ev: self._init_luster(ev.enemy))
        self.on(E.BEFORE_HIT, self._before_hit)
        self.on(E.AFTER_HIT, self._after_hit)
        self.on(E.ATTACK_END, self._super_break)
        self.on(E.BREAK, self._on_break)
        if self.trace(2):
            self.passive("Sylvan Enigma", {S.BREAK_EFFECT: self.tp(2, 0)})
        if self.e(6):
            self.passive("Clairvoyance of Boom and Doom", {S.BREAK_EFF: self.ep(6, 0)})

    def technique(self) -> None:
        p = self.sk("technique")["params"][0]
        self.battle.advance(self.char, p[3])
        for e in self.enemies():
            self._def_down(e, p[1], int(p[2]))

    # --------------------------------------------------- Cloudflame Luster
    def _init_luster(self, e: Enemy) -> None:
        # approximation: each enemy receives Cloudflame Luster once (not restored on Toughness recovery)
        self.luster[e.uid] = self.p("talent", 1) * e.max_toughness

    def _after_hit(self, ev: E.Ev) -> None:
        hit = ev.hit
        t = hit.target
        if hit.credited.side != Side.ALLY or not hit.was_broken or hit.toughness_potential <= 0:
            return
        left = self.luster.get(t.uid, 0.0)
        if left <= 0 or not t.alive:
            return
        left -= hit.toughness_potential
        self.luster[t.uid] = max(0.0, left)
        if left <= 1e-9:
            # "When Cloudflame Luster is reduced to 0, the enemy will receive Weakness Break DMG again"
            self.battle.break_damage(
                hit.attacker, t, hit.element, credited=hit.credited, label="Break (Cloudflame Luster)"
            )

    def _super_break(self, ev: E.Ev) -> None:
        act = ev.attack
        if act.owner is None or act.owner.side != Side.ALLY or act.kind == ActionKind.ENEMY:
            return
        for t in act.attacked:
            tough = self.battle.super_break_toughness(act, t)
            if tough > 0:
                self.battle.super_break(
                    act.actor, t, tough, self.p("talent", 0), credited=act.owner, label="Super Break (Fugue)"
                )

    def _on_break(self, ev: E.Ev) -> None:
        credited = ev.credited
        if credited is None or credited.side != Side.ALLY:
            return
        if self.trace(1) and ev.target.alive:
            self.battle.delay(ev.target, self.tp(1, 0))
        if self.trace(3):
            value = self.tp(3, 0)
            if self.char.stat(S.BREAK_EFFECT) >= self.tp(3, 3):
                value += self.tp(3, 4)
            for c in self.teammates():
                self.buff(
                    c,
                    Modifier(
                        "Phecda Primordia",
                        stats={S.BREAK_EFFECT: value},
                        duration=int(self.tp(3, 1)),
                        stacking=Stacking.STACK,
                        max_stacks=int(self.tp(3, 2)),
                    ),
                )
        if self.e(2):
            self.battle.gain_energy(self.char, self.ep(2, 0))

    # ------------------------------------------------------ Foxian Prayer
    @property
    def in_scorch(self) -> bool:
        return self.scorch is not None and not self.scorch.removed

    def _has_prayer(self, e: Entity) -> bool:
        return self.in_scorch and any(m.source is self.char for m in e.mods(PRAYER))

    def _def_down(self, e: Enemy, chance: float, turns: int | None = None) -> None:
        self.battle.try_debuff(
            Modifier(
                DEF_DOWN,
                stats={S.DEF_REDUCTION: self.p("skill", 3)},
                duration=turns if turns is not None else int(self.p("skill", 4)),
                kind=ModKind.DEBUFF,
            ),
            e,
            self.char,
            chance,
        )

    def _before_hit(self, ev: E.Ev) -> None:
        hit = ev.hit
        act = hit.action
        if act is None or not self._has_prayer(hit.credited):
            return
        if hit.toughness > 0 and not hit.ignore_weakness and not hit.target.is_weak_to(hit.element):
            hit.ignore_weakness = True
            hit.toughness *= self.p("skill", 5)
        # approximation: the DEF Reduction is rolled before the first hit on each target of the attack
        done: set[int] = act.data.setdefault("fugue_def_down", set())
        if hit.target.uid not in done:
            done.add(hit.target.uid)
            self._def_down(hit.target, self.p("skill", 2))

    # ------------------------------------------------------------- policy
    def take_turn(self) -> None:
        target = self.pick_target()
        if target is None:
            return
        if self.opts.get("rotation", "skill") == "skill" and not self.in_scorch and self.can_skill():
            self.skill(target)
        else:
            self.basic(target)

    # ------------------------------------------------------------ actions
    def basic(self, target: Enemy | None) -> None:
        assert target is not None
        if not self.in_scorch:
            self.simple_basic(target)
            return
        rec = self.sk(ENHANCED_BASIC_ID)
        lv = rec["params"][self.level_of(rec) - 1]
        with self.action(ActionKind.BASIC, rec, target) as act:
            act.blast(target, lv[0], lv[1], toughness=(float(rec["toughness"][0]), float(rec["toughness"][2])))

    def skill(self, target: Enemy | None) -> None:
        ally = self.main_dps()
        dur = int(self.p("skill", 0))
        with self.action(ActionKind.SKILL, "skill", ally):
            self.scorch = self.buff_self(Modifier(SCORCH, duration=dur, tick=Tick.SOURCE_TURN_START, key=SCORCH))
            for c in self.battle.team:
                self.battle.remove_named(c, PRAYER)
            stats = {S.BREAK_EFFECT: self.p("skill", 1)}
            if self.e(1):
                stats[S.BREAK_EFF] = self.ep(1, 0)
            if self.e(4):
                stats[S.BREAK_DMG_PCT] = self.ep(4, 0)
            holders: list[Character] = self.allies() if self.e(6) else [ally]
            for c in holders:
                # lasts as long as Torrid Scorch (counts down at the start of Fugue's turns)
                self.buff(c, Modifier(PRAYER, stats=stats, duration=dur, tick=Tick.SOURCE_TURN_START))
        if self.trace(2) and self.first_skill:
            self.battle.gain_sp(int(self.tp(2, 1)), self.char)
        self.first_skill = False

    def ult(self, target: Enemy | None) -> None:
        with self.action(ActionKind.ULT, "ult", target) as act:
            act.aoe(
                self.p("ult", 0),
                toughness=self.toughness("ult", 1),
                main_target=target,
                ignore_weakness=True,
                splits=ULT_SPLITS,
            )
        if self.e(2):
            for c in self.allies():
                self.battle.advance(c, self.ep(2, 1))
