"""Castorice (遐蝶) — Remembrance / Quantum. No Energy: "Newbud" fills from the team's HP loss; the
Ultimate summons the memosprite Netherwing (HP = max Newbud) and deploys a RES-down Territory.
Max HP scaling; the Skill costs the team's HP instead of SP.

Options (``default_opts``):
  * ``rotation``: ``"skill"`` (Skill / Enhanced Skill every turn, default) or ``"basic"``.
  * ``breath``: Netherwing's policy: ``"last_turn"`` (Claw Splits the Veil, then "Breath Scorches the Shadow"
    repeatedly on its last turn until "Wings Sweep the Ruins", default), ``"always"`` (Breath from the first
    turn) or ``"never"`` (Claw only; Wings Sweep when it leaves).

Manual control: Netherwing's turns are the player's: "Claw Splits the Veil" (ends the turn) or "Breath Scorches the
Shadow" (the turn continues; once used, only Breath can follow; at 25% HP or less it becomes "Wings Sweep the Ruins").

# not modelled: Netherwing bearing the team's lethal HP loss (allies cannot die with ``allies_immortal``);
#   A4's Netherwing SPD boost after killing every enemy with Breath; healing amounts ignore E4's bonus.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from .. import events as E
from .. import stats as S
from ..control import MenuItem
from ..entities import Enemy, Entity, Summon
from ..enums import ActionKind, DmgTag, Side
from ..modifiers import Modifier, Stacking, Tick
from . import register
from .aglaea import memo_hit
from .base import Kit

if TYPE_CHECKING:
    from ..battle import Action, Battle

# Max "Newbud" = (highest team level)^2 x 5.3125, at least 2000 (Castorice_RefreshMaxSpecialSP in the
# ability config; not part of the skill data). 34000 at level 80.
NEWBUD_LEVEL_COEF = 5.3125
NEWBUD_MIN = 2000.0
MAX_BREATHS_PER_TURN = 20  # safety cap for the repeated Breath loop


@register
class Castorice(Kit):
    char_id = "1407"
    default_opts = {"rotation": "skill", "breath": "last_turn"}

    def setup(self) -> None:
        self.char.max_energy = 0.0  # Castorice has no Energy: Newbud is tracked here
        self.newbud = 0.0
        self.nw_turns = 0
        self.breaths = 0
        self.ardent = 0
        self.e2_bonus = False
        self.heal_conv: dict[int, float] = {}
        self._nw_turn_counted = -1  # battle turn whose Netherwing turn was counted
        self._breath_turn = -1  # manual control: battle turn in which Netherwing used Breath
        self.on(E.HP_CHANGED, self._on_hp)
        self.on(E.TURN_END, self._nw_turn_end)
        if self.trace(1):
            self.on(E.HEALED, self._a2)
            self.on(E.ACTION_END, lambda ev: self.heal_conv.clear())
        if self.trace(2):
            self.passive(
                "Inverted Torch",
                {},
                dyn=lambda m, k, e: self.tp(2, 1) if self.char.hp_ratio >= self.tp(2, 0) else 0.0,
                dyn_keys={S.SPD_PCT},
            )
        if self.e(1):
            self.on(E.BEFORE_HIT, self._e1)
        if self.e(4):
            self.passive("Rest in Songs of Gloom", {S.HEAL_TAKEN: self.ep(4, 0)}, scope=self.ally_scope)
        if self.e(6):
            self.passive("Await for Years to Loom", {f"{S.RES_PEN}:{self.char.element.value}": self.ep(6, 0)})

    def technique(self) -> None:
        p = self.sk("technique")["params"][0]
        self._summon_nw(hp_ratio=p[1])
        self._drain(p[0])

    # ------------------------------------------------------------ Newbud
    def max_newbud(self) -> float:
        lvl = max(c.level for c in self.battle.team)
        return max(NEWBUD_MIN, lvl * lvl * NEWBUD_LEVEL_COEF)

    def nw(self) -> Summon | None:
        return self.memosprite()

    def _gain(self, amount: float) -> None:
        nw = self.nw()
        if nw is not None:
            if nw.hp < nw.max_hp:
                self.battle.heal(nw, amount, self.char)
        else:
            self.newbud = min(self.max_newbud(), self.newbud + amount)

    def _on_hp(self, ev: E.Ev) -> None:
        ent = ev.entity
        if ev.delta >= 0 or ent.side != Side.ALLY or ent is self.nw():
            return
        self.buff_self(
            Modifier(
                "Desolation Across Palms",
                stats={S.DMG_PCT: self.p("talent", 1)},
                duration=int(self.p("talent", 3)),
                stacking=Stacking.STACK,
                max_stacks=int(self.p("talent", 2)),
            )
        )
        self._gain(-ev.delta)

    def _a2(self, ev: E.Ev) -> None:
        ent = ev.entity
        if ent.side != Side.ALLY or ent is self.nw() or ev.effective <= 0:
            return
        cap = self.tp(1, 1) * self.max_newbud()
        done = self.heal_conv.get(ent.uid, 0.0)
        amount = min(cap - done, ev.effective * self.tp(1, 0))
        if amount > 0:
            self.heal_conv[ent.uid] = done + amount
            self._gain(amount)

    def ult_ready(self) -> bool:
        return self.nw() is None and self.newbud >= self.max_newbud() - 1e-6

    def ult_resource(self) -> tuple[float, float, str]:
        return self.newbud, self.max_newbud(), "新蕊"

    def pay_ult_cost(self) -> None:
        self.newbud = 0.0

    def _drain(self, ratio: float) -> None:
        """Consume ``ratio`` of the current HP of all allies except Netherwing (down to 1)."""
        nw = self.nw()
        for a in self.battle.allies(include_summons=True):
            if a is not nw and a.hp > 1.0:
                self.battle.lose_hp(a, ratio * a.hp, self.char)

    # -------------------------------------------------------- Netherwing
    def _memo_lv(self, sid: str) -> tuple[dict[str, Any], list[Any]]:
        rec = self.sk(sid)
        return rec, list(rec["params"][self.level_of(rec) - 1])

    def _summon_nw(self, hp_ratio: float = 1.0) -> Summon:
        nw = self.summon_memosprite("Netherwing", on_turn=self._nw_turn)
        nw.base[S.BASE_HP] = self.p("ult", 2) * self.max_newbud()
        nw.hp = hp_ratio * nw.max_hp
        self.nw_turns = 0
        self.breaths = 0
        self.battle.advance(nw, 1.0)
        # Territory "Lost Netherland" (held by Netherwing: removed when it disappears)
        self.battle.apply(
            Modifier(
                "Lost Netherland",
                stats={S.RES_REDUCTION: self.p("ult", 3)},
                tick=Tick.NONE,
                scope=self.enemy_scope,
                key="Lost Netherland",
            ),
            nw,
            self.char,
        )
        _, roar = self._memo_lv("1140705")
        for c in self.allies():
            self.buff(c, Modifier("Roar Rumbles the Realm", stats={S.DMG_PCT: roar[0]}, duration=int(roar[1])))
        if self.e(2):
            self.ardent = int(self.ep(2, 1))
            self.e2_bonus = True
        return nw

    def _nw_action(self, nw: Summon, rec: dict[str, Any], target: Enemy | None) -> Any:
        return self.battle.action(nw, ActionKind.MEMOSPRITE, skill=rec, target=target)

    def _nw_hit(self, act: Action, target: Enemy, ratio: float, toughness: float, primary: bool = True) -> None:
        """Netherwing's DMG scales with Castorice's Max HP."""
        act.hit(
            target,
            0.0,
            flat=ratio * self.char.max_hp,
            toughness=toughness,
            primary=primary,
            ignore_weakness=self.e(6),
        )

    def _claw(self, nw: Summon) -> None:
        rec, lv = self._memo_lv("1140701")
        with self._nw_action(nw, rec, self.pick_target()) as act:
            act.data["castorice_e1"] = True
            for e in self.enemies():
                self._nw_hit(act, e, lv[0], float(rec["toughness"][1]))

    def _breath(self, nw: Summon) -> None:
        rec, lv = self._memo_lv("1140702")
        mult = lv[1] if self.breaths == 0 else lv[2] if self.breaths == 1 else lv[3]
        self.breaths += 1
        if self.ardent > 0:
            self.ardent -= 1
            self.battle.advance(self.char, 1.0)
        else:
            self.battle.lose_hp(nw, lv[0] * nw.max_hp, nw)
        if self.trace(3):
            self.battle.apply(
                Modifier(
                    "Where the West Wind Dwells",
                    stats={S.DMG_PCT: self.tp(3, 0)},
                    stacking=Stacking.STACK,
                    max_stacks=int(self.tp(3, 1)),
                    tick=Tick.NONE,
                ),
                nw,
                self.char,
            )
        with self._nw_action(nw, rec, self.pick_target()) as act:
            act.data["castorice_e1"] = True
            for e in self.enemies():
                self._nw_hit(act, e, mult, float(rec["toughness"][1]))

    def _wings(self, nw: Summon, sid: str) -> None:
        """Wings Sweep the Ruins (1140712 when triggered by Breath, 1140706 when Netherwing leaves), then leave."""
        rec, lv = self._memo_lv(sid)
        count = int(lv[1]) + (int(self.ep(6, 1)) if self.e(6) else 0)
        nw.hp = 0.0
        if self.enemies():
            with self._nw_action(nw, rec, None) as act:
                act.data["castorice_e1"] = True
                for _ in range(count):
                    alive = [e for e in self.battle.alive_enemies() if e.hp > 0] or self.battle.alive_enemies()
                    if not alive:
                        break
                    t = self.battle.rng.choice(alive)
                    self._nw_hit(act, t, lv[0], float(rec["toughness"][0]))
        for c in self.allies():
            self.battle.heal(c, lv[2] * self.char.max_hp + lv[3], self.char)
        self._dismiss(nw)

    def _dismiss(self, nw: Summon) -> None:
        self.battle.remove_unit(nw)
        self.nw_turns = 0
        self.breaths = 0
        self.ardent = 0

    def _count_nw_turn(self) -> None:
        """Count Netherwing's turn once (its policy and the manual menu may both act in the same turn)."""
        if self._nw_turn_counted != self.battle.turns:
            self._nw_turn_counted = self.battle.turns
            self.nw_turns += 1

    def _nw_turn(self, nw: Summon, battle: Battle) -> None:
        self._count_nw_turn()
        policy = self.opts.get("breath", "last_turn")
        final = self.nw_turns >= int(self.p("ult", 1))
        breathed = self._breath_turn == self.battle.turns  # manual control: only Breath can follow a Breath
        if policy == "always" or (policy == "last_turn" and final) or breathed:
            _, lv = self._memo_lv("1140702")
            for _ in range(MAX_BREATHS_PER_TURN):
                if not nw.alive or not self.enemies():
                    return
                if nw.hp <= lv[4] * nw.max_hp and self.ardent <= 0:
                    self._wings(nw, "1140712")
                    return
                self._breath(nw)
        else:
            self._claw(nw)

    def _wings_now(self, nw: Summon) -> bool:
        """Breath at or below #5 of Netherwing's Max HP (without E2's Ardent) turns into Wings Sweep the Ruins."""
        _, lv = self._memo_lv("1140702")
        return nw.hp <= lv[4] * nw.max_hp and self.ardent <= 0

    def menu_for(self, unit: Entity) -> list[MenuItem]:
        nw = self.nw()
        if nw is None or unit is not nw:
            return []
        breathed = self._breath_turn == self.battle.turns
        claw = self.basic_item(self.sk("1140701"), id="claw", enabled=not breathed)
        if breathed:
            claw.note = "已发动【燎尽黯泽的焰息】，只能继续发动"
        if self._wings_now(nw):
            breath = self.skill_item(self.sk("1140712"), id="breath", enabled=True, note="生命值过低：发动后死龙消失")
        else:
            rec = self.sk("1140702" if self.breaths == 0 else "1140710")
            note = "不消耗生命值（E2）" if self.ardent > 0 else "消耗死龙生命值，回合不结束"
            breath = self.skill_item(rec, id="breath", ends_turn=False, enabled=True, note=note)
        return [claw, breath]

    def perform_for(self, unit: Entity, item: str, target: Entity | None) -> None:
        nw = self.nw()
        if nw is None or unit is not nw or item not in ("claw", "breath"):
            super().perform_for(unit, item, target)
            return
        self._count_nw_turn()
        if item == "claw":
            self._claw(nw)
        elif self._wings_now(nw):
            self._wings(nw, "1140712")
        else:
            self._breath_turn = self.battle.turns
            self._breath(nw)

    def _nw_turn_end(self, ev: E.Ev) -> None:
        nw = self.nw()
        if nw is None or ev.entity is not nw:
            return
        self.battle.remove_named(nw, "Where the West Wind Dwells")
        if self.nw_turns >= int(self.p("ult", 1)):
            self._wings(nw, "1140706")

    # ---------------------------------------------------------- eidolons
    def _e1(self, ev: E.Ev) -> None:
        h = ev.hit
        if h.action is None or not h.action.data.get("castorice_e1"):
            return
        r = h.target.hp_ratio
        if r <= self.ep(1, 1):
            h.add(S.FINAL_DMG, self.ep(1, 3) - 1.0)
        elif r <= self.ep(1, 0):
            h.add(S.FINAL_DMG, self.ep(1, 2) - 1.0)

    # ------------------------------------------------------------ policy
    def take_turn(self) -> None:
        target = self.pick_target()
        if target is None:
            return
        if self.opts.get("rotation", "skill") == "skill":
            self.skill(target)
        else:
            self.basic(target)

    # ----------------------------------------------------------- actions
    def basic(self, target: Enemy | None) -> None:
        assert target is not None
        with self.action(ActionKind.BASIC, "basic", target) as act:
            act.hit(target, self.p("basic", 0), stat="hp", toughness=self.toughness("basic"), splits="data")

    def skill(self, target: Enemy | None) -> None:
        assert target is not None
        nw = self.nw()
        if nw is None:
            self._drain(self.p("skill", 0))
            with self.action(ActionKind.SKILL, "skill", target) as act:
                act.blast(
                    target,
                    self.p("skill", 1),
                    self.p("skill", 2),
                    stat="hp",
                    toughness=(self.toughness("skill", 0), self.toughness("skill", 2)),
                )
            return
        rec = self.sk("140709")
        lv = rec["params"][self.level_of(rec) - 1]
        self._drain(lv[0])
        if self.e2_bonus:
            self.e2_bonus = False
            self.newbud = min(self.max_newbud(), self.newbud + self.ep(2, 2) * self.max_newbud())
        with self.action(ActionKind.SKILL, rec, target) as act:
            act.data["castorice_e1"] = True
            act.aoe(lv[1], stat="hp", toughness=float(rec["toughness"][1]), main_target=target)
            memo_tags = (DmgTag.SKILL, DmgTag.MEMOSPRITE)
            for e in self.enemies():
                memo_hit(act, nw, e, 0.0, flat=lv[2] * self.char.max_hp, tags=memo_tags, primary=e is target)

    def menu(self) -> list[MenuItem]:
        """The Skill costs the team's HP (no SP); it becomes "Boneclaw, Doomdrake's Embrace" with Netherwing."""
        rec = self.sk("140709") if self.nw() is not None else self.sk("skill")
        return [self.basic_item(), self.skill_item(rec, note="消耗我方全体当前生命值")]

    def ult(self, target: Enemy | None) -> None:
        with self.action(ActionKind.ULT, "ult"):
            self._summon_nw()
