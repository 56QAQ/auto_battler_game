"""Acheron (黄泉) — Nihility / Lightning. Slashed Dream instead of Energy; Crimson Knot; Rainblade ultimate."""

from __future__ import annotations

from .. import events as E
from .. import stats as S
from ..entities import Enemy
from ..enums import ActionKind, DmgTag, Path
from ..modifiers import Modifier, ModKind, Stacking, Tick, hidden
from . import register
from .base import Kit

MAX_KNOTS = 9


@register
class Acheron(Kit):
    char_id = "1308"

    def setup(self) -> None:
        self.sd_max = int(self.p("talent", 0))
        self.sd = 0
        self.qa = 0  # Quadrivalent Ascendance stacks
        self.in_ult = False
        self.char.max_energy = 0.0  # Acheron has no Energy; Slashed Dream is tracked here
        self._debuffed: dict[int, list[Enemy]] = {}
        self.on(E.MOD_APPLIED, self._on_mod)
        self.on(E.ACTION_END, self._on_action_end)
        self.on(E.KILL, self._on_kill)
        others = sum(1 for c in self.battle.team if c is not self.char and c.path == Path.NIHILITY)
        if self.e(2):
            others += 1
        if self.trace(2) and others >= 1:
            abyss = (self.tp(2, 1) if others >= 2 else self.tp(2, 0)) - 1.0

            def the_abyss(ev: E.Ev) -> None:  # one multiplicative factor per hit
                h = ev.hit
                if h.attacker is self.char and h.tags & {DmgTag.BASIC, DmgTag.SKILL, DmgTag.ULT}:
                    h.add(S.FINAL_DMG, abyss)

            self.on(E.BEFORE_HIT, the_abyss)
        if self.e(1):
            self.on(
                E.BEFORE_HIT,
                lambda ev: ev.hit.attacker is self.char
                and ev.hit.target.debuffs
                and ev.hit.add(S.CRIT_RATE, self.ep(1, 0)),
            )
        if self.e(2):
            self.on(E.TURN_START, lambda ev: ev.entity is self.char and self._gain(1, knot=True))
        if self.e(4):
            self.on(E.ENEMY_SPAWNED, lambda ev: self._e4(ev.enemy))
        if self.e(6):
            self.passive("Apocalypse, the Emancipator", {f"{S.RES_PEN}:{DmgTag.ULT}": self.ep(6, 0)})

    def on_battle_start(self) -> None:
        if self.e(4):
            for e in self.enemies():
                self._e4(e)
        if self.trace(1):
            n = int(self.tp(1, 0))
            self._gain(n, knot=False)
            enemies = self.enemies()
            if enemies:
                self.add_knots(self.battle.rng.choice(enemies), n)

    def technique(self) -> None:
        self.qa = min(self._qa_max(), self.qa + 1)
        p = self.sk("technique")["params"][0]
        with self.action(ActionKind.EXTRA, None, label="Quadrivalent Ascendance (technique)", energy=0, sp=0) as act:
            act.aoe(p[0], toughness=20, ignore_weakness=True)

    def _e4(self, e: Enemy) -> None:
        self.battle.apply(
            Modifier(
                "Shrined Fire",
                stats={f"{S.VULN}:{DmgTag.ULT}": self.ep(4, 0)},
                kind=ModKind.DEBUFF,
                tick=Tick.NONE,
                dispellable=False,
            ),
            e,
            self.char,
        )

    # ------------------------------------------------ Slashed Dream / Knots
    def _qa_max(self) -> int:
        return int(self.tp(1, 1)) if self.trace(1) else 1

    def _gain(self, n: int, knot: bool = True, target: Enemy | None = None) -> None:
        over = self.sd + n - self.sd_max
        self.sd = min(self.sd_max, self.sd + n)
        if over > 0 and self.trace(1):
            self.qa = min(self._qa_max(), self.qa + over)
        if knot and not self.in_ult:
            t = target or self._most_knotted()
            if t is not None:
                self.add_knots(t, 1)

    def knots(self, e: Enemy) -> int:
        m = e.get_mod("Crimson Knot")
        return m.stacks if m is not None else 0

    def _most_knotted(self, among: list[Enemy] | None = None) -> Enemy | None:
        pool = [e for e in (among or self.enemies()) if e.alive]
        if not pool:
            return None
        return max(pool, key=lambda e: (self.knots(e), e is self.battle.default_target()))

    def add_knots(self, e: Enemy, n: int) -> None:
        if self.in_ult or n <= 0 or not e.alive:
            return
        self.battle.apply(
            Modifier(
                "Crimson Knot",
                kind=ModKind.DEBUFF,
                stacks=n,
                max_stacks=MAX_KNOTS,
                stacking=Stacking.STACK,
                tick=Tick.NONE,
                dispellable=False,
                key="Crimson Knot",
            ),
            e,
            self.char,
        )

    def _on_mod(self, ev: E.Ev) -> None:
        mod, target = ev.mod, ev.target
        act = self.battle.current_action
        if act is None or not mod.is_debuff or not isinstance(target, Enemy) or mod.name == "Crimson Knot":
            return
        if mod.source is None or mod.source.side != self.char.side:
            return
        self._debuffed.setdefault(id(act), [])
        if target not in self._debuffed[id(act)]:
            self._debuffed[id(act)].append(target)

    def _on_action_end(self, ev: E.Ev) -> None:
        targets = self._debuffed.pop(id(ev.action), None)
        if targets:
            self._gain(1, knot=True, target=self._most_knotted(targets))

    def _on_kill(self, ev: E.Ev) -> None:
        n = self.knots(ev.target)
        if n:
            others = [e for e in self.enemies() if e is not ev.target and e.hp > 0]
            t = self._most_knotted(others) if others else None
            if t is not None:
                self.add_knots(t, n)

    # ----------------------------------------------------------- ultimate
    def ult_ready(self) -> bool:
        return self.sd >= self.sd_max

    def pay_ult_cost(self) -> None:
        self.sd -= self.sd_max

    def _tags(self, base: str) -> tuple[str, ...]:
        return (base, DmgTag.ULT) if self.e(6) and base != DmgTag.ULT else (base,)

    def ult(self, target: Enemy | None) -> None:
        if target is None:
            return
        b = self.battle
        self.in_ult = True
        res_down = hidden("Atop Rainleaf (RES down)", {S.RES_REDUCTION: self.p("talent", 1)}, scope=self.enemy_scope)
        b.apply(res_down, self.char, self.char)
        rain = [self.sk("130814"), self.sk("130815"), self.sk("130816")]
        with self.action(ActionKind.ULT, "ult", target, energy=0) as act:
            for rb in rain:
                t = target if target.alive and target.hp > 0 else b.default_target()
                if t is None:
                    break
                lv = rb["params"][self.level_of(rb) - 1]
                had_knot = self.knots(t) > 0
                act.hit(
                    t,
                    lv[0],
                    toughness=rb["toughness"][0],
                    ignore_weakness=True,
                    label="Rainblade",
                    splits=rb.get("splits"),
                )
                if self.trace(3) and had_knot:
                    self.buff_self(
                        Modifier(
                            "Thunder Core",
                            stats={S.DMG_PCT: self.tp(3, 0)},
                            duration=int(self.tp(3, 2)),
                            stacking=Stacking.STACK,
                            max_stacks=int(self.tp(3, 1)),
                        )
                    )
                removed = min(3, self.knots(t))
                if removed:
                    m = t.get_mod("Crimson Knot")
                    assert m is not None
                    m.stacks -= removed
                    if m.stacks <= 0:
                        b.remove_modifier(m)
                    mult = min(self.p("ult", 4), lv[1] * (1 + removed))
                    act.aoe(
                        mult,
                        toughness=rb["toughness"][1],
                        ignore_weakness=True,
                        label="Rainblade (Crimson Knot)",
                        main_target=t,
                    )
            sr = self.sk("130817")
            lv = sr["params"][self.level_of(sr) - 1]
            act.aoe(
                lv[0],
                toughness=sr["toughness"][1],
                ignore_weakness=True,
                label="Stygian Resurge",
                main_target=target,
                splits=sr.get("splits_aoe"),
            )
            for e in b.alive_enemies():
                b.remove_named(e, "Crimson Knot")
            if self.trace(3):
                act.bounce(None, int(self.tp(3, 3)), self.tp(3, 4), label="Thunder Core")
        b.remove_modifier(res_down)
        self.in_ult = False
        if self.qa:
            n = self.qa
            self.qa = 0
            self._gain(n, knot=False)
            enemies = self.enemies()
            if enemies:
                self.add_knots(self.battle.rng.choice(enemies), n)

    # ------------------------------------------------------------ actions
    def basic(self, target: Enemy | None) -> None:
        assert target is not None
        with self.action(ActionKind.BASIC, "basic", target, tags=self._tags(DmgTag.BASIC)) as act:
            act.hit(target, self.p("basic", 0), toughness=self.toughness("basic"), ignore_weakness=self.e(6))

    def skill(self, target: Enemy | None) -> None:
        assert target is not None
        with self.action(ActionKind.SKILL, "skill", target, tags=self._tags(DmgTag.SKILL)) as act:
            self._gain(int(self.p("skill", 2)), knot=False)
            self.add_knots(target, int(self.p("skill", 2)))
            act.blast(
                target,
                self.p("skill", 0),
                self.p("skill", 1),
                toughness=(self.toughness("skill", 0), self.toughness("skill", 2)),
                ignore_weakness=self.e(6),
                splits="data",
            )
