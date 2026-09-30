"""Dan Heng • Permansor Terrae (丹恒•腾荒) — Preservation / Physical. "Bondmate" ally, stacking team Shields and
the summon "Souldragon" (own SPD) whose enhanced actions deal Additional DMG of the Bondmate's Type.

Options:
  target:   name of the ally that becomes the "Bondmate" (default: first teammate).
  rotation: "auto" (default: Skill when there is no Bondmate / the Bondmate has no Shield / SP is plentiful),
            "skill" (Skill whenever SP allows) or "basic".

# not modelled: Souldragon disappearing when DHPT or the Bondmate is knocked down (allies cannot die with
#   ``allies_immortal``); the Technique's Daze (only the free Skill at battle start is applied).
"""

from __future__ import annotations

from typing import Any

from .. import events as E
from .. import stats as S
from ..entities import Character, Enemy, Entity, Summon
from ..enums import ActionKind
from ..modifiers import Modifier, ModKind, Tick
from . import register
from .base import Kit

SHIELD_NAME = "Terra Omnibus Shield"
SP_PLENTY = 4  # "auto" rotation: also use the Skill while the team has at least this many Skill Points


@register
class DanHengPermansorTerrae(Kit):
    char_id = "1414"
    default_opts = {"target": None, "rotation": "auto"}

    def setup(self) -> None:
        self.bondmate: Character | None = None
        self.bond_mod: Modifier | None = None
        self.dragon: Summon | None = None
        self.enhanced_left = 0
        self.a2_active = False
        self.ode_next = False  # Cyrene "Ode to Earth" used on DHPT: next Souldragon action is enhanced
        self.ode_earth_left = 0  # Cyrene "Ode to Earth": Souldragon attacks with the extra Additional DMG
        self.ode: list[float] | None = None
        self.on(E.ATTACK_END, self._on_attack_end)
        if self.e(6):
            self.passive(
                "One Dream to Enfold All Wilds",
                {},
                scope=self.enemy_scope,
                dyn=lambda m, k, e: self.ep(6, 0) if self._bond_alive() else 0.0,
                dyn_keys={S.VULN},
            )

    def on_battle_start(self) -> None:
        if self.trace(2):
            self.battle.advance(self.char, self.tp(2, 0))

    def technique(self) -> None:
        # "automatically uses Skill 1 time on the character with Bondmate without consuming any Skill Points"
        self._skill(self.main_dps(), free=True)

    # ------------------------------------------------------------- shields
    def _skill_shield(self) -> float:
        return self.p("skill", 0) * self.char.atk + self.p("skill", 1)

    def shield(self, ally: Entity, base: float, turns: int) -> None:
        """DHPT's Shields stack up to 300% of the current Skill Shield (one shared instance per ally)."""
        scale = 1.0 + self.char.stat(S.SHIELD_PCT)
        cap = self._skill_shield() * self.p("skill", 3)
        cur = 0.0
        old = next((m for m in ally.modifiers if m.name == SHIELD_NAME and not m.removed), None)
        if old is not None:
            cur = old.data.get("value", 0.0) / scale
        total = min(cap, cur + base)
        self.battle.add_shield(ally, total, self.char, duration=turns, name=SHIELD_NAME, key="DHPT Shield")

    def _shield_value(self, ally: Entity) -> float:
        return sum(m.data.get("value", 0.0) for m in ally.modifiers if "shield" in m.tags and not m.removed)

    def _shield_team(self, base: float, turns: int) -> None:
        for c in self.battle.allies(include_summons=True):
            self.shield(c, base, turns)

    # ------------------------------------------------------------ bondmate
    def _bond_alive(self) -> bool:
        return self.bondmate is not None and self.bondmate.alive

    def _bond_atk(self, mod: Modifier, key: str, ent: Entity) -> float:
        return self.tp(1, 0) * self.char.atk if self.a2_active and ent is not self.char else 0.0

    def _bond_dmg(self, mod: Modifier, key: str, ent: Entity) -> float:
        return self.ode[0] if self.ode is not None and self.ode_earth_left > 0 else 0.0

    def set_bondmate(self, ally: Character) -> None:
        if self.bondmate is not ally:
            if self.bond_mod is not None:
                self.battle.remove_modifier(self.bond_mod)
            self.bondmate = ally
            stats: dict[str, float] = {}
            if self.e(4):
                stats[S.MITIGATION] = self.ep(4, 0)
            if self.e(6):
                stats[S.DEF_IGNORE] = self.ep(6, 2)
            self.bond_mod = self.buff(
                ally,
                Modifier(
                    "Bondmate",
                    stats=stats,
                    tick=Tick.NONE,
                    kind=ModKind.BUFF,
                    dispellable=False,
                    dyn=lambda m, k, e: self._bond_atk(m, k, e) if k == S.ATK_FLAT else self._bond_dmg(m, k, e),
                    dyn_keys={S.ATK_FLAT, S.DMG_PCT},
                ),
            )
        if self.dragon is None or not self.dragon.alive:
            # approximation: an existing Souldragon keeps its place on the Action Order when the Bondmate changes
            self.dragon = self.battle.add_unit(
                Summon("Souldragon", self.char, spd=self.p("talent", 4), on_turn=self._dragon_turn)
            )

    # ------------------------------------------------------------ souldragon
    def _bond_additional(self, target: Enemy, mult: float, label: str, flat: float = 0.0) -> None:
        bond = self.bondmate
        if bond is None or not target.alive:
            return
        self.battle.additional_damage(
            bond,
            target,
            mult if not flat else {},
            element=bond.element,
            label=label,
            credited=bond,
            flat=flat,
        )

    def _dragon_turn(self, unit: Summon, battle: Any) -> None:
        b = self.battle
        enhanced = self.enhanced_left > 0 or self.ode_next
        e2 = self.e(2) and enhanced
        shield_mult = (self.ep(2, 2) if e2 else 1.0) * (self.ode[4] if self.ode_next and self.ode is not None else 1.0)
        kind = ActionKind.FUA if enhanced else ActionKind.EXTRA
        with b.action(unit, kind, skill=self.sk("talent"), label="Souldragon", energy=0, sp=0) as act:
            for c in b.allies(include_summons=True):
                for m in [m for m in c.debuffs if m.dispellable][: int(self.p("talent", 5))]:
                    b.remove_modifier(m)
            self._shield_team(
                (self.p("talent", 0) * self.char.atk + self.p("talent", 1)) * shield_mult, int(self.p("talent", 2))
            )
            if self.trace(3):
                allies = b.allies(include_summons=True)
                low = min(allies, key=self._shield_value) if allies else None
                if low is not None:
                    self.shield(
                        low, (self.tp(3, 1) * self.char.atk + self.tp(3, 2)) * shield_mult, int(self.p("talent", 2))
                    )
            if enhanced and b.alive_enemies():
                act.aoe(self.p("ult", 1), toughness=self.toughness("talent", 1))
                add_mult = self.p("ult", 7) * (self.ep(2, 1) if e2 else 1.0)
                for e in b.alive_enemies():
                    self._bond_additional(e, add_mult, "Souldragon (Bondmate Additional DMG)")
                if self.trace(3) and b.alive_enemies():
                    # E2 doubles every Additional DMG the Bondmate deals in this action (the ability script sets
                    # both the Ultimate's and Sublimity's owner-DMG percentages)
                    top = max(b.alive_enemies(), key=lambda x: x.hp)
                    self._bond_additional(top, self.tp(3, 0) * (self.ep(2, 1) if e2 else 1.0), "Sublimity")
                if self.ode is not None and self.ode_earth_left > 0 and self.bondmate is not None:
                    self.ode_earth_left -= 1
                    flat = self.ode[3] * self._shield_value(self.bondmate)
                    for e in b.alive_enemies():
                        self._bond_additional(e, 0.0, "Ode to Earth", flat=flat)
        if self.ode_next:
            self.ode_next = False  # "Does not consume the enhancement number of DHPT's Ultimate"
        elif enhanced:
            self.enhanced_left -= 1

    # ------------------------------------------------------------- listeners
    def _on_attack_end(self, ev: E.Ev) -> None:
        act = ev.attack
        if self.bondmate is None or act.actor is not self.bondmate or not self.trace(2):
            return
        self.battle.gain_energy(self.char, self.tp(2, 1))
        if self.dragon is not None and self.dragon.alive:
            self.battle.advance(self.dragon, self.tp(2, 2))

    # --------------------------------------------------------------- actions
    def take_turn(self) -> None:
        target = self.pick_target()
        if target is None:
            return
        policy = self.opts.get("rotation", "auto")
        if policy == "basic" or not self.can_skill():
            self.basic(target)
        elif policy == "skill":
            self.skill(target)
        else:
            bond = self.bondmate
            need = bond is None or not bond.alive or not bond.has_mod(SHIELD_NAME)
            if need or self.battle.sp >= SP_PLENTY:
                self.skill(target)
            else:
                self.basic(target)

    def basic(self, target: Enemy | None) -> None:
        assert target is not None
        self.simple_basic(target)

    def skill(self, target: Enemy | None) -> None:
        self._skill(self.main_dps())

    def _skill(self, ally: Character, free: bool = False) -> None:
        kw: dict[str, Any] = {"sp": 0} if free else {}
        with self.action(ActionKind.SKILL, "skill", ally, **kw):
            self.set_bondmate(ally)
            self.a2_active = self.a2_active or self.trace(1)
            self._shield_team(self._skill_shield(), int(self.p("skill", 2)))

    def ult(self, target: Enemy | None) -> None:
        with self.action(ActionKind.ULT, "ult", target) as act:
            act.aoe(self.p("ult", 0), toughness=self.toughness("ult", 1), main_target=target)
            self._shield_team(self.p("ult", 3) * self.char.atk + self.p("ult", 4), int(self.p("ult", 5)))
            self.enhanced_left = int(self.p("ult", 2)) + (int(self.ep(2, 0)) if self.e(2) else 0)
            if self.e(6) and self._bond_alive():
                for e in self.enemies():
                    self._bond_additional(e, self.ep(6, 1), "One Dream to Enfold All Wilds")
        if self.e(1):
            self.battle.gain_sp(int(self.ep(1, 0)), self.char)
            if self._bond_alive():
                assert self.bondmate is not None
                self.buff(
                    self.bondmate,
                    Modifier("Shed Scales of Old", stats={S.RES_PEN: self.ep(1, 1)}, duration=int(self.ep(1, 2))),
                )
        if self.e(2) and self.dragon is not None and self.dragon.alive:
            self.battle.advance(self.dragon, 1.0)

    # ------------------------------------------------- Cyrene: Ode to Earth
    def on_cyrene_ode(self, cyrene: Kit) -> None:
        """Used on DHPT: Souldragon advances 100% and its next action is enhanced (Shield x150%)."""
        self.ode = cyrene.ode_params("1141525")  # type: ignore[attr-defined]
        self.ode_next = True
        if self.dragon is not None and self.dragon.alive:
            self.battle.advance(self.dragon, 1.0)

    def on_demiurge_skill(self, cyrene: Kit) -> None:
        """Whenever Demiurge uses a Memosprite Skill, DHPT gains "Ode to Earth"."""
        self.ode = self.ode or cyrene.ode_params("1141525")  # type: ignore[attr-defined]
        self.ode_earth_left = int(self.ode[2])
