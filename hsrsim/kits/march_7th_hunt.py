"""March 7th (三月七, The Hunt / Imaginary). Shifu: path-based bonus effects; Charge -> Enhanced Basic ATK.

Options: ``target``: name of the ally designated as "Shifu" (default: the first teammate);
``rotation``: "skill" (default: Skill only while there is no Shifu) | "basic".

Charge comes from her Basic ATK and from Shifu's attacks/Ultimates. At 7 Charge she immediately takes an
inserted action and uses the Enhanced Basic ATK (3 hits + random extra hits), which consumes 7 Charge.
"""

from __future__ import annotations

from .. import events as E
from .. import stats as S
from ..battle import Action
from ..control import MenuItem
from ..entities import Character, Enemy, Entity
from ..enums import ActionKind, Path
from ..modifiers import Modifier, Tick, hidden
from . import register
from .base import Kit

ENHANCED_BASIC_ID = "122408"
SHIFU = "Shifu"
# Shifu Paths whose effect is Additional DMG; the other Paths boost Toughness Reduction instead
DMG_PATHS = frozenset({Path.ERUDITION, Path.DESTRUCTION, Path.HUNT, Path.REMEMBRANCE, Path.ELATION})
E2_SPLITS = [0.4, 0.6]  # E2 follow-up hit splits from the ability script (not in the data)
# approximation: Toughness Reduction of the E2 Follow-Up ATK (not in the eidolon parameters)
E2_FUA_TOUGHNESS = 10.0


@register
class March7thHunt(Kit):
    char_id = "1224"
    default_opts = {"target": None}

    def setup(self) -> None:
        self.shifu: Character | None = None
        self.charge = 0
        self.ascended: Modifier | None = None  # Talent DMG boost until the Enhanced Basic ATK
        self.insert_turn = -1  # turn index of the last inserted "immediately takes action"
        self.bonus_hits = 0  # Ultimate: extra initial hits of the next Enhanced Basic ATK
        self.bonus_chance = 0.0
        self.e6_ready = False
        self.e2_turn = -1
        self.on(E.ACTION_END, self._on_action_end)
        if self.e(1):
            self.passive(
                "My Sword Stirs Starlight",
                {},
                dyn=lambda m, k, e: self.ep(1, 0) if self._shifu() is not None else 0.0,
                dyn_keys={S.SPD_PCT},
            )
        if self.e(4):
            self.on(
                E.TURN_START,
                lambda ev: ev.entity is self.char and self.battle.gain_energy(self.char, self.ep(4, 0)),
            )

    def on_battle_start(self) -> None:
        if self.trace(1):
            self.battle.advance(self.char, self.tp(1, 0))

    def technique(self) -> None:
        p = self.sk("technique")["params"][0]
        # approximation: every teammate is assumed to have used their Technique
        self.gain_charge(min(int(p[0]), len(self.teammates())))
        self.battle.gain_energy(self.char, p[1])  # MazeInLevel ModifySPNew AddValue: scales with ERR

    # ----------------------------------------------------------------- Shifu
    def _shifu(self) -> Character | None:
        s = self.shifu
        return s if s is not None and s.alive and s.has_mod(SHIFU) else None

    def _shifu_hit(
        self,
        act: Action,
        target: Enemy,
        mult: float,
        tough: float,
        splits: list[float] | str | None = None,
        extra: dict[str, float] | None = None,
    ) -> None:
        """One hit of Basic ATK / Enhanced Basic ATK / E2 follow-up with Shifu's Path effect."""
        shifu = self._shifu()
        ign = False
        if shifu is not None:
            if shifu.path not in DMG_PATHS:
                tough *= 1.0 + self.p("skill", 2)
            if self.trace(2) and target.is_weak_to(shifu.element) and not target.is_weak_to(self.char.element):
                ign = True  # A4: Shifu's Weakness type counts; breaking triggers the Imaginary effect
        act.hit(target, mult, toughness=tough, ignore_weakness=ign, splits=splits, extra=extra)
        if shifu is not None and shifu.path in DMG_PATHS and target.alive:
            self.battle.additional_damage(
                self.char, target, self.p("skill", 1), element=shifu.element, label="Shifu (Additional DMG)"
            )

    # ---------------------------------------------------------------- Charge
    @property
    def threshold(self) -> int:
        return int(self.p("talent", 0))

    def gain_charge(self, n: int) -> None:
        self.charge = min(int(self.p("talent", 2)), self.charge + n)
        if self.charge < self.threshold:
            return
        if self.ascended is None:
            self.ascended = self.buff_self(hidden("Master, I've Ascended!", {S.DMG_PCT: self.p("talent", 1)}))
        if self.insert_turn != self.battle.turns and self.battle.alive_enemies():
            # "immediately takes action": an inserted action (once per turn in the ability script)
            self.insert_turn = self.battle.turns
            self.battle.queue_extra_turn(self.char)

    def _on_action_end(self, ev: E.Ev) -> None:
        act = ev.action
        shifu = self._shifu()
        if shifu is None or act.actor is not shifu:
            return
        if act.is_attack or act.kind == ActionKind.ULT:
            self.gain_charge(1)
        if (
            self.e(2)
            and act.kind in (ActionKind.BASIC, ActionKind.SKILL)
            and act.is_attack
            and self.e2_turn != self.battle.turns
        ):
            self.e2_turn = self.battle.turns
            primary = act.target if isinstance(act.target, Enemy) else act.attacked[0]
            self.battle.queue_action(lambda: self._e2_fua(primary), self.char, "March 7th E2")

    def _random_enemy(self) -> Enemy | None:
        pool = [e for e in self.enemies() if e.hp > 0] or self.enemies()
        return self.battle.rng.choice(pool) if pool else None

    def _e2_fua(self, target: Enemy) -> None:
        t = target if target.alive and target.hp > 0 else self._random_enemy()
        if t is None:
            return
        # not modelled: Energy of the E2 Follow-Up ATK (unknown eidolon parameters)
        with self.action(ActionKind.FUA, None, t, label="Blade Dances on Waves' Fight", energy=0, sp=0) as act:
            self._shifu_hit(act, t, self.ep(2, 0), E2_FUA_TOUGHNESS, splits=E2_SPLITS)
        self.gain_charge(int(self.ep(2, 2)))

    # ---------------------------------------------------------------- policy
    def take_turn(self) -> None:
        target = self.pick_target()
        if target is None:
            return
        if self.charge >= self.threshold:
            self._enhanced_basic(target)
        elif (
            self.opts.get("rotation", "skill") == "skill"
            and self._shifu() is None
            and self.teammates()
            and self.can_skill()
        ):
            self.skill(target)
        else:
            self.basic(target)

    def menu(self) -> list[MenuItem]:
        """At the Charge threshold the Basic ATK is enhanced and the Skill cannot be used."""
        if self.charge >= self.threshold:
            return [
                self.basic_item(self.sk(ENHANCED_BASIC_ID)),
                self.skill_item(enabled=False, note="充能已满：仅能施放强化普攻"),
            ]
        if not self.teammates():
            return [self.basic_item(), self.skill_item(enabled=False, note="没有可指定为【师父】的队友")]
        return super().menu()

    def perform(self, item: str, target: Entity | None) -> None:
        if item == "skill" and target is self.char:
            target = None  # "one ally (excluding this unit)": the default Shifu
        super().perform(item, target)

    # --------------------------------------------------------------- actions
    def basic(self, target: Enemy | None) -> None:
        assert target is not None
        if self.charge >= self.threshold:
            self._enhanced_basic(target)
            return
        with self.action(ActionKind.BASIC, "basic", target) as act:
            self._shifu_hit(act, target, self.p("basic", 0), self.toughness("basic"), splits="data")
        self.gain_charge(int(self.p("basic", 1)))

    def _enhanced_basic(self, target: Enemy) -> None:
        rec = self.sk(ENHANCED_BASIC_ID)
        lv = rec["params"][self.level_of(rec) - 1]
        tough = float(rec["toughness"][0])
        hits = int(lv[3]) + self.bonus_hits
        chance = lv[1] + self.bonus_chance
        extra = {S.CRIT_DMG: self.ep(6, 0)} if self.e6_ready else None
        with self.action(ActionKind.BASIC, rec, target) as act:  # SP +0, Energy fixed (not per hit)
            t: Enemy | None = target
            for i in range(hits + int(lv[2])):
                if i >= hits and self.battle.rng.random() >= chance:
                    break  # extra hits: fixed chance each, up to 3
                if t is None or not (t.alive and t.hp > 0):
                    t = self._random_enemy()
                if t is None:
                    break
                self._shifu_hit(act, t, lv[0], tough, extra=extra)
        self.charge -= self.threshold
        if self.ascended is not None:
            self.battle.remove_modifier(self.ascended)
            self.ascended = None
        self.bonus_hits, self.bonus_chance, self.e6_ready = 0, 0.0, False
        shifu = self._shifu()
        if self.trace(3) and shifu is not None:
            self.buff(
                shifu,
                Modifier(
                    "Tide Tamer",
                    stats={S.CRIT_DMG: self.tp(3, 0), S.BREAK_EFFECT: self.tp(3, 1)},
                    duration=int(self.tp(3, 2)),
                ),
            )

    def skill(self, target: Enemy | None) -> None:
        ally: Entity = self.main_dps()
        if ally is self.char:
            self.basic(target)
            return
        assert isinstance(ally, Character)
        with self.action(ActionKind.SKILL, "skill", ally):
            for c in self.battle.team:
                if c is not ally:
                    self.battle.remove_named(c, SHIFU)
            self.buff(ally, Modifier(SHIFU, stats={S.SPD_PCT: self.p("skill", 0)}, tick=Tick.NONE, key=SHIFU))
            self.shifu = ally

    def ult(self, target: Enemy | None) -> None:
        assert target is not None
        with self.action(ActionKind.ULT, "ult", target) as act:
            act.hit(target, self.p("ult", 0), toughness=self.toughness("ult"))
        self.bonus_hits = int(self.p("ult", 1))
        self.bonus_chance = self.p("ult", 2)
        if self.e(6):
            self.e6_ready = True
