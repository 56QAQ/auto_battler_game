"""Hysilens (海瑟音) — Nihility / Physical. Wind Shear/Bleed/Burn/Shock on every ally attack, a DoT-echo Zone.

Options:
  rotation: "skill" (default, Skill whenever SP allows) or "basic".
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from .. import events as E
from .. import stats as S
from ..entities import Enemy, Entity
from ..enums import ActionKind, DmgTag, Element, Side
from ..modifiers import DotModifier, Modifier, ModKind, Tick
from . import register
from .base import Kit

if TYPE_CHECKING:
    from ..battle import Action, Battle

# Talent states in priority order (the game gives priority to a state the enemy does not have yet)
STATES = ("wind_shear", "bleed", "burn", "shock")
STATE_ELEMENT = {
    "wind_shear": Element.WIND,
    "bleed": Element.PHYSICAL,
    "burn": Element.FIRE,
    "shock": Element.LIGHTNING,
}
STATE_NAME = {"wind_shear": "Wind Shear", "bleed": "Bleed", "burn": "Burn", "shock": "Shock"}


@register
class Hysilens(Kit):
    char_id = "1410"
    default_opts = {"rotation": "skill"}

    def setup(self) -> None:
        self.zone: Modifier | None = None
        self.zone_allies: Modifier | None = None
        self.window = 0  # Zone DoT trigger window ("at the start of each turn or after one attack")
        self.window_counts: dict[tuple[int, int], int] = {}
        self.ode: list[float] | None = None  # Cyrene's "Ode to Ocean" parameters once received
        self.flowing_warmth = False
        self.on(E.ATTACK_END, self._talent)
        self.on(E.DOT_TRIGGERED, self._zone_echo)
        self.on(E.PRE_TURN, self._new_window)
        self.on(E.TURN_END, self._new_window)
        self.on(E.ATTACK_START, lambda ev: ev.attack.owner.side == Side.ALLY and self._new_window(ev))
        if self.trace(3):
            self.passive("The Fiddle of Pearls", {}, dyn=self._a6, dyn_keys={S.DMG_PCT})
        if self.e(1):
            # "the DoT dealt by ally targets is equal to 116% of their original value" (a multiplicative layer)
            self.passive(
                "You Ask Why Hearts Cry", {f"{S.FINAL_DMG}:{DmgTag.DOT}": self.ep(1, 0) - 1.0}, scope=self.ally_scope
            )

    def on_battle_start(self) -> None:
        if self.trace(1):
            self._deploy_zone(int(self.tp(1, 0)))

    def technique(self) -> None:
        p = self.sk("technique")["params"][0]
        for e in self.enemies():
            for _ in range(int(p[2])):
                self.inflict(e, p[1])

    # ------------------------------------------------------------ traces
    def _a6(self, mod: Modifier, key: str, ent: Entity) -> float:
        over = self.char.stat(S.EHR) - self.tp(3, 0)
        if over <= 0:
            return 0.0
        return min(self.tp(3, 3), int(over / self.tp(3, 1) + 1e-9) * self.tp(3, 2))

    # ------------------------------------------------------------ talent
    def _state_dot(self, target: Enemy, state: str, extra: bool) -> DotModifier:
        hys = self.char
        el = STATE_ELEMENT[state]
        label = f"{STATE_NAME[state]} (Hysilens)"

        def dmg(mod: DotModifier, b: Battle, ratio: float) -> float:
            if state == "bleed":
                # "DoT equal to 20% of their Max HP, up to 25% of Hysilens's ATK"
                mult = min(self.p("talent", 2) * target.max_hp / max(1.0, hys.atk), self.p("talent", 3))
            else:
                mult = self.p("talent", 1)
            return b.dot_damage(hys, target, el, mult, label=label, tags=(DmgTag.DOT, state), ratio=ratio)

        return DotModifier(
            label,
            dot_type=state,
            damage_fn=dmg,
            duration=int(self.p("talent", 4)),
            key=f"Hysilens {state}{' E1' if extra else ''}",
        )

    def _has_state(self, e: Enemy, state: str) -> bool:
        return any(m.key == f"Hysilens {state}" for m in e.modifiers if not m.removed)

    def inflict(self, target: Enemy, chance: float) -> None:
        """Talent: one of Wind Shear/Bleed/Burn/Shock, preferring a state the target does not have yet."""
        if not target.alive:
            return
        missing = [s for s in STATES if not self._has_state(target, s)]
        state = self.battle.rng.choice(missing or list(STATES))
        got = self.battle.try_debuff(self._state_dot(target, state, False), target, self.char, chance, debuff_type=state)
        if got is not None and self.e(1):
            self.battle.try_debuff(
                self._state_dot(target, state, True), target, self.char, self.ep(1, 1), debuff_type=state
            )

    def _talent(self, ev: E.Ev) -> None:
        act = ev.attack
        if act.owner is None or act.owner.side != Side.ALLY:
            return
        for t in list(act.attacked):
            self.inflict(t, self.p("talent", 0))
        if act.owner is self.char and self.ode is not None:
            self._ode_after_attack(act)

    # -------------------------------------------------------------- zone
    def zone_active(self) -> bool:
        return self.zone is not None and not self.zone.removed

    def _deploy_zone(self, turns: int) -> None:
        stats = {S.DEF_REDUCTION: self.p("ult", 2), S.ATK_PCT: -self.p("ult", 5)}
        if self.e(4):
            stats[S.RES_REDUCTION] = self.ep(4, 0)
        self.zone = self.buff_self(
            Modifier(
                "Maelstrom Rhapsody Zone",
                stats=stats,
                duration=turns,
                tick=Tick.SOURCE_TURN_START,
                kind=ModKind.OTHER,
                scope=self.enemy_scope,
            )
        )
        if self.e(2) and self.trace(3):
            # E2: the A6 DMG Boost applies to all allies while the Zone is active
            self.zone_allies = self.buff_self(
                Modifier(
                    "Maelstrom Rhapsody Zone (E2)",
                    duration=turns,
                    tick=Tick.SOURCE_TURN_START,
                    kind=ModKind.OTHER,
                    scope=self.teammate_scope,
                    dyn=self._a6,
                    dyn_keys={S.DMG_PCT},
                )
            )
        if self.trace(1):
            self.battle.gain_sp(int(self.tp(1, 1)), self.char)

    def _new_window(self, ev: E.Ev) -> bool:
        self.window += 1
        self.window_counts.clear()
        return True

    def _zone_echo(self, ev: E.Ev) -> None:
        """Every DoT instance an enemy takes inside the Zone echoes as a Physical DoT from Hysilens."""
        if not self.zone_active():
            return
        mod, target = ev.mod, ev.target
        if "dot" not in mod.tags or not target.alive:
            return
        cap = int(self.ep(6, 0)) if self.e(6) else int(self.p("ult", 4))
        k = (self.window, target.uid)
        if self.window_counts.get(k, 0) >= cap:
            return
        self.window_counts[k] = self.window_counts.get(k, 0) + 1
        mult = self.p("ult", 3) + (self.ep(6, 1) if self.e(6) else 0.0)
        # approximation: the echo fires immediately per DoT instance (the game batches it at the same moments)
        self.battle.dot_damage(
            self.char, target, Element.PHYSICAL, mult, label="Maelstrom Rhapsody DoT", tags=(DmgTag.DOT, "zone")
        )

    # ----------------------------------------------------------- actions
    def basic(self, target: Enemy | None) -> None:
        assert target is not None
        self.simple_basic(target)

    def skill(self, target: Enemy | None) -> None:
        with self.action(ActionKind.SKILL, "skill", target) as act:
            for e in self.enemies():
                self.battle.try_debuff(
                    Modifier(
                        "Overtone Hum",
                        stats={S.VULN: self.p("skill", 2)},
                        duration=int(self.p("skill", 3)),
                        kind=ModKind.DEBUFF,
                    ),
                    e,
                    self.char,
                    self.p("skill", 1),
                )
            act.aoe(self.p("skill", 0), toughness=self.toughness("skill", 1), main_target=target)

    def ult(self, target: Enemy | None) -> None:
        with self.action(ActionKind.ULT, "ult", target) as act:
            self._deploy_zone(int(self.p("ult", 1)))
            act.aoe(self.p("ult", 0), toughness=self.toughness("ult", 1), main_target=target)
            if self.trace(2):
                for e in self.enemies():
                    if e.alive and e.has_tag("dot"):
                        self.battle.detonate(e, self.tp(2, 0))

    # ------------------------------------------------ Cyrene: Ode to Ocean
    def on_cyrene_ode(self, cyrene: Kit) -> None:
        """Chrysos Heir special effect from Cyrene's Demiurge (one-time effect)."""
        if self.ode is not None:
            return
        params = cyrene.ode_params("1141522")  # type: ignore[attr-defined]
        self.ode = params
        self.flowing_warmth = True
        self.passive("Ode to Ocean", {S.DMG_PCT: params[0]})

    def _ode_after_attack(self, act: Action) -> None:
        assert self.ode is not None
        if self.flowing_warmth:
            self.flowing_warmth = False
            self.battle.gain_energy(self.char, self.ode[3])
        ratio = {ActionKind.BASIC: self.ode[1], ActionKind.SKILL: self.ode[2]}.get(act.kind)
        if ratio:
            for e in list(act.attacked):
                if e.alive and e.has_tag("dot"):
                    self.battle.detonate(e, ratio)
