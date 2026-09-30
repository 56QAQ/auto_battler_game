"""Cerydra (刻律德菈) — Harmony / Wind. "Military Merit" on one ally (ATK from Cerydra's ATK, Additional DMG),
Charge upgrades it to "Peerage": Skill CRIT DMG / RES PEN and Coup de Main (the ally's Skill is used twice).

Coup de Main (glossary: "Copy and immediately use the ability about to be used, then use the original ability")
is implemented by wrapping the Peerage holder's ``skill()`` while they hold Military Merit.

Options:
  target:   name of the ally that receives Military Merit (default: first teammate).
  rotation: "skill" (default, Skill whenever SP allows) or "basic".
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from .. import events as E
from .. import stats as S
from ..entities import Character, Enemy, Entity
from ..enums import ActionKind, DmgTag
from ..modifiers import Modifier, ModKind, Tick
from . import register
from .base import Kit

if TYPE_CHECKING:
    from ..battle import Action

# Skill record "effect" values of Skills that attack enemies (Coup de Main triggers "when using their Skill on
# enemy targets")
ATTACK_EFFECTS = frozenset({"SingleAttack", "Blast", "AoEAttack", "Bounce"})


@register
class Cerydra(Kit):
    char_id = "1412"
    default_opts = {"target": None, "rotation": "skill"}

    def setup(self) -> None:
        self.charge = 0
        self.merit: Character | None = None
        self.merit_mod: Modifier | None = None
        self.peerage_mod: Modifier | None = None
        self.in_coup = False
        self.add_left = int(self.p("talent", 3))
        self.a4_used = False
        self.ode: list[float] | None = None  # Cyrene's "Ode to Law"
        self._patched: tuple[Kit, Any] | None = None
        self.on(E.ACTION_END, self._on_action_end)
        self.on(E.ATTACK_END, self._on_attack_end)
        if self.trace(1):
            self.passive("Veni", {}, dyn=self._a2, dyn_keys={S.CRIT_DMG})
        if self.trace(2):
            self.passive("Vidi", {S.CRIT_RATE: self.tp(2, 0)})
            self.on(E.ULT_USED, self._a4)
        if self.e(2) or self.e(6):
            self.passive("Merit Holder Bonus", {}, dyn=self._e2_e6, dyn_keys={S.DMG_PCT, S.RES_PEN})

    def technique(self) -> None:
        # "automatically uses Skill 1 time on the character with Military Merit without consuming any SP"
        self._skill(self._skill_target(), free=True)

    # ------------------------------------------------------------ passives
    def _a2(self, mod: Modifier, key: str, ent: Entity) -> float:
        over = self.char.atk - self.tp(1, 0)
        if over <= 0:
            return 0.0
        return min(self.tp(1, 3), int(over / self.tp(1, 1) + 1e-9) * self.tp(1, 2))

    def _teammate_has_merit(self) -> bool:
        return self.merit is not None and self.merit is not self.char and self.merit.alive

    def _e2_e6(self, mod: Modifier, key: str, ent: Entity) -> float:
        if not self._teammate_has_merit():
            return 0.0
        if key == S.DMG_PCT:
            return self.ep(2, 1) if self.e(2) else 0.0
        return self.ep(6, 0) if self.e(6) else 0.0

    # --------------------------------------------------------------- charge
    @property
    def peerage(self) -> bool:
        return self.peerage_mod is not None

    def gain_charge(self, n: int) -> None:
        if self.in_coup or n <= 0:
            return  # "During Coup de Main, Cerydra cannot gain Charge"
        self.charge = min(int(self.p("skill", 2)), self.charge + n)
        if self.charge >= int(self.p("skill", 3)) and self.merit is not None and not self.peerage:
            self._upgrade()

    def _upgrade(self) -> None:
        assert self.merit is not None
        stats = {f"{S.CRIT_DMG}:{DmgTag.SKILL}": self.p("skill", 0), f"{S.RES_PEN}:{DmgTag.SKILL}": self.p("skill", 4)}
        if self.e(1):
            stats[f"{S.DEF_IGNORE}:{DmgTag.SKILL}"] = self.ep(1, 1)
        self.peerage_mod = self.buff(
            self.merit, Modifier("Peerage", stats=stats, tick=Tick.NONE, kind=ModKind.BUFF, dispellable=False)
        )

    def _revert(self) -> None:
        if self.peerage_mod is not None:
            self.battle.remove_modifier(self.peerage_mod)
        self.peerage_mod = None

    # ------------------------------------------------------- military merit
    def _merit_atk(self, mod: Modifier, key: str, ent: Entity) -> float:
        return self.p("talent", 1) * self.char.atk if ent is not self.char else 0.0

    def grant_merit(self, ally: Character) -> None:
        if self.merit is ally:
            return
        if self.merit is not None:
            self._clear_merit()
            self.charge = 0  # "When the target changes, Cerydra's Charge is reset to 0"
        self.merit = ally
        stats: dict[str, float] = {}
        if self.e(1):
            stats[S.DEF_IGNORE] = self.ep(1, 0)
        if self.e(2):
            stats[S.DMG_PCT] = self.ep(2, 0)
        if self.e(6):
            stats[S.RES_PEN] = self.ep(6, 0)
        if self.ode is not None:
            stats[S.CRIT_DMG] = self.ode[0]
        self.merit_mod = self.buff(
            ally,
            Modifier(
                "Military Merit",
                stats=stats,
                tick=Tick.NONE,
                kind=ModKind.BUFF,
                dispellable=False,
                dyn=self._merit_atk,
                dyn_keys={S.ATK_FLAT},
            ),
        )
        self._patch(ally)
        if self.charge >= int(self.p("skill", 3)):
            self._upgrade()

    def _clear_merit(self) -> None:
        self._unpatch()
        self._revert()
        if self.merit_mod is not None:
            self.battle.remove_modifier(self.merit_mod)
        self.merit_mod = None
        self.merit = None

    # ---------------------------------------------------------- coup de main
    def _patch(self, ally: Character) -> None:
        kit = ally.kit
        if kit is None or ally is self.char:
            return
        original = kit.skill

        def skill_with_coup(target: Enemy | None) -> None:
            if (
                self.merit is ally
                and self.peerage
                and not self.in_coup
                and isinstance(target, Enemy)
                and kit.sk("skill").get("effect") in ATTACK_EFFECTS
            ):
                self._coup_de_main(original, target)
            else:
                original(target)

        kit.skill = skill_with_coup  # type: ignore[method-assign]
        self._patched = (kit, skill_with_coup)

    def _unpatch(self) -> None:
        if self._patched is not None:
            kit, fn = self._patched
            if kit.__dict__.get("skill") is fn:
                del kit.skill
        self._patched = None

    def _coup_de_main(self, original: Any, target: Enemy) -> None:
        b = self.battle
        assert self.merit is not None and self.merit.kit is not None
        need = self.merit.kit.sk("skill").get("sp_need", 0)
        need = need[0] if isinstance(need, list) else need
        self.in_coup = True
        try:
            # approximation: the copied Skill costs no Skill Points (SP is pre-paid and consumed by the copy)
            b.sp += max(0, int(need))
            original(target if target.alive else b.default_target())
            t = target if target.alive else b.default_target()
            if t is not None:
                original(t)
        finally:
            self.in_coup = False
        self.charge = max(0, self.charge - int(self.p("skill", 3)))
        self._revert()
        if self.ode is not None:
            self.gain_charge(int(self.ode[1]))
        elif self.charge >= int(self.p("skill", 3)):
            self._upgrade()

    # ------------------------------------------------------------- listeners
    def _on_action_end(self, ev: E.Ev) -> None:
        act: Action = ev.action
        if self.merit is None or act.actor is not self.merit or act.kind not in (ActionKind.BASIC, ActionKind.SKILL):
            return
        self.gain_charge(int(self.p("talent", 0)))
        if self.trace(3):
            self.battle.gain_energy(self.char, self.tp(3, 0))

    def _on_attack_end(self, ev: E.Ev) -> None:
        act: Action = ev.attack
        if self.merit is None or act.actor is not self.merit or self.add_left <= 0:
            return
        target = next((t for t in act.attacked if t.alive), None) or self.battle.default_target()
        if target is None:
            return
        self.add_left -= 1
        mult = self.p("talent", 2) + (self.ep(6, 1) if self.e(6) else 0.0)
        self.battle.additional_damage(self.char, target, mult, label="Ave Imperator", credited=self.char)

    def _a4(self, ev: E.Ev) -> None:
        if ev.entity is self.merit and not self.a4_used and self.charge < int(self.p("skill", 2)):
            self.a4_used = True
            self.gain_charge(int(self.tp(2, 1)))

    # --------------------------------------------------------------- actions
    def _skill_target(self) -> Character:
        return (
            self.merit
            if self.merit is not None and self.merit.alive and not self.opts.get("target")
            else (self.main_dps())
        )

    def basic(self, target: Enemy | None) -> None:
        assert target is not None
        self.simple_basic(target)

    def skill(self, target: Enemy | None) -> None:
        self._skill(self._skill_target())

    def _skill(self, ally: Character, free: bool = False) -> None:
        kw: dict[str, Any] = {"sp": 0} if free else {}
        with self.action(ActionKind.SKILL, "skill", ally, **kw):
            self.grant_merit(ally)
            self.gain_charge(int(self.p("skill", 1)))
            if self.trace(3):
                for c in {self.char, ally}:
                    self.buff(
                        c,
                        Modifier(
                            "Vici", stats={S.SPD_FLAT: self.tp(3, 1)}, duration=int(self.tp(3, 2)), key="Cerydra Vici"
                        ),
                    )
            if self.e(1):
                self.battle.gain_energy(ally, self.ep(1, 2))

    def ult(self, target: Enemy | None) -> None:
        with self.action(ActionKind.ULT, "ult", target) as act:
            if self.merit is None or not self.merit.alive:
                self.grant_merit(self.battle.team[0])
            self.gain_charge(int(self.p("ult", 1)))
            mult = self.p("ult", 0) + (self.ep(4, 0) if self.e(4) else 0.0)
            act.aoe(mult, toughness=self.toughness("ult", 1), main_target=target)
        self.add_left = int(self.p("talent", 3))

    # --------------------------------------------------- Cyrene: Ode to Law
    def on_cyrene_ode(self, cyrene: Kit) -> None:
        """Chrysos Heir special effect from Cyrene's Demiurge (for the entire battle)."""
        self.ode = cyrene.ode_params("1141523")  # type: ignore[attr-defined]
        if self.merit_mod is not None and not self.merit_mod.removed:
            self.merit_mod.stats[S.CRIT_DMG] = self.merit_mod.stats.get(S.CRIT_DMG, 0.0) + self.ode[0]
