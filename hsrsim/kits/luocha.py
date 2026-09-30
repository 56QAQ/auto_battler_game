"""Luocha (罗刹) — Abundance / Imaginary. Auto-triggered Skill heal at low HP, Abyss Flower stacks deploy a
Zone that heals attackers; AoE Ultimate that removes enemy buffs.

Healing is modelled with ``battle.heal`` (outgoing healing bonus and E2 applied).

Options (``default_opts``):

* ``rotation``: ``"auto"`` (default: Skill on the lowest-HP ally when one is below ``heal_threshold``,
  else Basic ATK), ``"skill"`` (Skill whenever SP allows, e.g. for Zone uptime) or ``"basic"``.
* ``heal_threshold``: HP ratio below which ``"auto"`` uses the Skill (default 0.5).
"""

from __future__ import annotations

from .. import events as E
from .. import stats as S
from ..entities import Character, Enemy, Entity, Summon
from ..enums import ActionKind
from ..modifiers import Modifier, ModKind, Tick
from . import register
from .base import Kit

E2_HP_THRESHOLD = 0.5  # E2: "if the target ally's HP percentage is lower than 50%" (literal)
ZONE = "Cycle of Life"


@register
class Luocha(Kit):
    char_id = "1203"
    default_opts = {"rotation": "auto", "heal_threshold": 0.5}

    def setup(self) -> None:
        self.flowers = 0
        self.zone: Modifier | None = None
        self.auto_cd = 0
        self.auto_pending = False
        if self.trace(3):
            self.passive("Through the Valley", {f"{S.DEBUFF_RES}:cc": self.tp(3, 0)})
        self.on(E.HP_CHANGED, self._on_hp_changed)
        self.on(E.ATTACK_END, self._on_attack_end)
        self.on(E.TURN_END, self._on_turn_end)

    def technique(self) -> None:
        self._deploy_zone()

    # --------------------------------------------------------------- Zone
    def _zone_active(self) -> bool:
        return self.zone is not None and not self.zone.removed

    def _gain_flower(self) -> None:
        # approximation: Abyss Flower cannot be gained while the Zone is active
        if self._zone_active():
            return
        self.flowers += 1
        if self.flowers >= int(self.p("talent", 0)):
            self.flowers = 0
            self._deploy_zone()

    def _deploy_zone(self) -> None:
        turns = int(self.p("talent", 2))
        # approximation: the Zone counts down at the end of Luocha's turns
        self.zone = self.buff_self(
            Modifier(
                ZONE,
                stats={S.ATK_PCT: self.ep(1, 0)} if self.e(1) else {},
                duration=turns,
                scope=self.ally_scope,
            )
        )
        if self.e(4):
            # Weakened enemies deal less DMG to allies (``S.WEAKEN`` is applied by the engine's enemy attacks)
            self.buff_self(
                Modifier(
                    "Heavy Lies the Crown",
                    stats={S.WEAKEN: self.ep(4, 0)},
                    duration=turns,
                    kind=ModKind.DEBUFF,
                    scope=self.enemy_scope,
                )
            )

    def _on_attack_end(self, ev: E.Ev) -> None:
        act = ev.attack
        owner = act.owner
        if not self._zone_active() or not act.attacked or not isinstance(owner, Character):
            return
        atk = self.char.atk
        self._heal(owner, self.p("talent", 1) * atk + self.p("talent", 3))
        if self.trace(2):
            for c in self.allies():
                if c is not owner:
                    self._heal(c, self.tp(2, 0) * atk + self.tp(2, 1))

    # ------------------------------------------------------------ healing
    def _heal(self, ally: Character, amount: float, bonus: float = 0.0) -> None:
        self.battle.heal(ally, amount, self.char, bonus=bonus)

    def _skill_effect(self, ally: Character, auto: bool) -> None:
        # approximation: the low-HP trigger is an inserted Skill action without SP cost (it grants the Skill's Energy)
        kw = {"sp": 0, "label": "Prayer of Abyss Flower (auto)"} if auto else {}
        with self.action(ActionKind.SKILL, "skill", ally, **kw):
            if self.trace(1):
                for m in [m for m in ally.debuffs if m.dispellable][: int(self.tp(1, 0))]:
                    self.battle.remove_modifier(m)
            bonus = 0.0
            if self.e(2):
                if ally.hp_ratio < E2_HP_THRESHOLD:
                    bonus = self.ep(2, 0)
                else:
                    shield = self.ep(2, 1) * self.char.atk + self.ep(2, 2)
                    # MAvatar_Luocha_00_Skill02_Shield: LifeStepMoment default (turn end)
                    self.battle.add_shield(
                        ally, shield, self.char, duration=int(self.ep(2, 3)), name="Bestowal", tick=Tick.HOLDER_TURN_END
                    )
            self._heal(ally, self.p("skill", 0) * self.char.atk + self.p("skill", 1), bonus)
            self._gain_flower()

    def _on_hp_changed(self, ev: E.Ev) -> None:
        ally = ev.entity
        if ev.delta >= 0 or not isinstance(ally, Character) or self.auto_cd > 0 or self.auto_pending:
            return
        if ally.hp_ratio > self.p("skill", 2):
            return
        self.auto_pending = True
        self.auto_cd = int(self.p("skill", 3))

        def trigger() -> None:
            self.auto_pending = False
            self._skill_effect(ally, auto=True)

        self.battle.queue_action(trigger, self.char, "Luocha auto Skill", needs_enemies=False)

    def _on_turn_end(self, ev: E.Ev) -> None:
        if ev.entity is self.char and self.auto_cd > 0:
            self.auto_cd -= 1

    # ------------------------------------------------------------- policy
    def _lowest(self) -> Character:
        return min(self.allies(), key=lambda c: (c.hp_ratio, c.slot))

    def take_turn(self) -> None:
        target = self.pick_target()
        if target is None:
            return
        policy = self.opts.get("rotation", "auto")
        low = self._lowest().hp_ratio < float(self.opts.get("heal_threshold", 0.5))
        if self.can_skill() and (policy == "skill" or (policy == "auto" and low)):
            self.skill(target)
        else:
            self.basic(target)

    # ------------------------------------------------------------ actions
    def basic(self, target: Enemy | None) -> None:
        assert target is not None
        self.simple_basic(target)

    def skill(self, target: Enemy | None) -> None:
        self._skill_effect(self._lowest(), auto=False)

    def perform(self, item: str, target: Entity | None) -> None:
        """Manual control: the Skill heals the chosen ally (the policy heals the lowest-HP ally)."""
        ally = target.owner if isinstance(target, Summon) else target
        if item == "skill" and isinstance(ally, Character) and ally.side == self.char.side and ally.alive:
            self._skill_effect(ally, auto=False)
            return
        super().perform(item, target)

    def ult(self, target: Enemy | None) -> None:
        with self.action(ActionKind.ULT, "ult", target) as act:
            for e in self.enemies():
                for m in [m for m in e.buffs if m.dispellable][: int(self.p("ult", 1))]:
                    self.battle.remove_modifier(m)
            if self.e(6):
                for e in self.enemies():
                    self.battle.try_debuff(
                        Modifier(
                            "Reunion With the Dust",
                            stats={S.RES_REDUCTION: self.ep(6, 1)},
                            duration=int(self.ep(6, 2)),
                            kind=ModKind.DEBUFF,
                        ),
                        e,
                        self.char,
                        self.ep(6, 0),
                        fixed=True,
                    )
            act.aoe(self.p("ult", 0), toughness=self.toughness("ult", 1), main_target=target, splits="data")
        self._gain_flower()
