"""Pearl (真珠) — Elation / Ice. DEF-scaling healer: permanent Certified Banger (cap 50) used as Repellency,
"Deep Learning" Aesthetic Archetype (enhanced Basic ATK with Elation DMG), team Elation DMG procs.

Options:
  ``target``: name of the "Aesthetic Archetype" (default: the first Elation teammate, else the first teammate).
  ``repellency``: model Repellency (consume Certified Banger to offset 60% of DMG taken by allies; default on).
  ``rotation``: "skill" (default: Skill when Skill Points allow and the Certified Banger it grants would not
      be capped), or "basic".
"""

from __future__ import annotations

from .. import events as E
from .. import stats as S
from ..elation import PUNCHLINE_CHANGED
from ..entities import Character, Enemy, Entity
from ..enums import ActionKind, Element, Path, Side
from ..modifiers import Modifier, ModKind, Tick
from . import register
from ._batch8_util import BANGER, elation_count, grant_banger
from .base import Kit

DISSOLVE = "Dissolve Reason into Elation"
RENDER_ID = "150310"  # enhanced Basic ATK (non-Elation Archetype)
IMAGENATE_ID = "150308"  # enhanced Basic ATK (Elation Archetype)


@register
class Pearl(Kit):
    char_id = "1503"
    has_elation_skill = True
    elation_skill_id = "150320"
    ult_targets_ally = True
    default_opts = {"target": None, "repellency": True, "rotation": "skill"}

    def setup(self) -> None:
        self.archetype: Character | None = None
        self.charges = 0
        self.a4_gained = 0.0
        self.a6_armed = False
        self.extra_for: Character | None = None
        self.extra_state: tuple[Modifier, int] | None = None
        self.cap = self.p("talent", 2)
        self.on(E.MOD_APPLIED, self._on_banger, priority=-10)
        self.on(E.ATTACK_END, self._dissolve_proc)
        self.on(E.TURN_START, self._turn_start)
        self.on(E.TURN_END, self._turn_end)
        self.on(E.ULT_USED, self._a6)
        if self.opts.get("repellency", True):
            self.on(E.HP_CHANGED, self._repellency)
        self.passive(
            "Grow Grace from Grit",
            {},
            scope=self.ally_scope,
            dyn=lambda m, k, e: self.p("talent", 3) if e.hp_ratio <= self.p("talent", 0) else 0.0,
            dyn_keys={S.MITIGATION},
        )
        if self.trace(1):
            self.passive("Panoptic Vision", {}, dyn=self._a2, dyn_keys={S.ELATION_DMG_PCT})
            self.passive(
                "Panoptic Vision (healing)",
                {},
                dyn=lambda m, k, e: self.tp(1, 5) * self.char.stat(S.ELATION_DMG_PCT),
                dyn_keys={S.HEAL_PCT},
            )
        if self.trace(2):
            self.passive(
                "Sensory Latitude",
                {},
                scope=self.ally_scope,
                dyn=lambda m, k, e: self.tp(2, 2) if self.banger() > 0 else 0.0,
                dyn_keys={S.EFFECT_RES},
            )
        if self.e(1):
            n = elation_count(self.battle)
            if n >= 2:
                self.passive("Nestle That Pearl", {S.ELATION_DMG_PCT: self.ep(1, min(n, 4) - 2)}, scope=self.ally_scope)
            # not modelled: the fatal-DMG revive (allies cannot be knocked down in the simulator)
        if self.e(2):
            self.passive("Crop That Dappled Dawn", {S.MERRYMAKE_PCT: self.ep(2, 0)}, scope=self.ally_scope)
        if self.e(6):
            self.passive(
                "Compute Life From One Shell",
                {},
                scope=self.ally_scope,
                dyn=lambda m, k, e: self.ep(6, 0) if self.deep_learning else 0.0,
                dyn_keys={S.RES_PEN},
            )

    def technique(self) -> None:
        p = self.sk("technique")["params"][0]
        self.gain_banger(p[1])
        ally = self.pick_archetype()
        if ally is not None:
            self.archetype = ally
            self.charges = int(p[0])
            if self.trace(3) and ally.path == Path.ELATION:
                self.a6_armed = True

    def _a2(self, mod: Modifier, key: str, ent: Entity) -> float:
        d = self.char.defense
        if d < self.tp(1, 0):
            return 0.0
        excess = min(d - self.tp(1, 0), self.tp(1, 4))
        return self.tp(1, 1) + int(excess / self.tp(1, 2)) * self.tp(1, 3)

    # ------------------------------------------------------ Certified Banger
    def _pearl_bangers(self) -> list[Modifier]:
        return [m for m in self.char.modifiers if m.name == BANGER and not m.removed]

    def banger_points(self) -> float:
        return sum(float(m.data.get("punchline", 0)) for m in self._pearl_bangers())

    def gain_banger(self, n: float) -> None:
        grant_banger(self.battle, self.char, n, self.char)

    def _on_banger(self, ev: E.Ev) -> None:
        """Pearl's Certified Banger lasts indefinitely and is capped (Talent)."""
        mod = ev.mod
        if ev.target is not self.char or mod.name != BANGER or ev.refreshed:
            return
        mod.duration = None
        mod.tick = Tick.NONE
        others = self.banger_points() - float(mod.data.get("punchline", 0))
        allowed = max(0.0, self.cap - others)
        mod.data["punchline"] = min(float(mod.data.get("punchline", 0)), allowed)
        if mod.data["punchline"] <= 0:
            self.battle.remove_modifier(mod)

    def consume_banger(self, n: float) -> float:
        used = 0.0
        for m in self._pearl_bangers():
            if n - used <= 1e-9:
                break
            take = min(float(m.data.get("punchline", 0)), n - used)
            m.data["punchline"] = float(m.data.get("punchline", 0)) - take
            used += take
            if m.data["punchline"] <= 1e-9:
                self.battle.remove_modifier(m)
        return used

    def _repellency(self, ev: E.Ev) -> None:
        ent = ev.entity
        if ev.delta >= 0 or not isinstance(ev.source, Enemy) or getattr(ent, "side", None) != Side.ALLY:
            return
        # approximation: applied after the hit (the engine has no "before ally takes DMG" hook): the offset DMG
        # is restored as HP and the matching Repellency (Certified Banger x 200) is consumed
        per = self.p("talent", 4)
        need = self.p("talent", 1) * -ev.delta / per
        used = self.consume_banger(min(need, self.banger_points()))
        if used > 0:
            self.battle.heal(ent, used * per, self.char)

    # ---------------------------------------------------------------- traces
    def _turn_start(self, ev: E.Ev) -> None:
        ent = ev.entity
        if ent is self.char:
            self.a4_gained = 0.0
        if ent is self.extra_for and ev.extra:
            self._start_extra(ent)
        if not self.trace(2):
            return
        if isinstance(ent, Character) or (getattr(ent, "is_memosprite", False) and ent.side == Side.ALLY):
            gain = min(self.tp(2, 0), self.tp(2, 1) - self.a4_gained)
            if gain > 0:
                self.a4_gained += gain
                self.gain_banger(gain)

    def _a6(self, ev: E.Ev) -> None:
        if self.a6_armed and ev.entity is self.archetype and ev.entity is not self.char:
            self.a6_armed = False
            self.battle.gain_energy(self.char, self.tp(3, 0), fixed=True)

    def _cleanse(self) -> None:
        if not self.trace(2):
            return
        for c in self.allies():
            for m in [m for m in c.debuffs if m.dispellable][: int(self.tp(2, 3))]:
                self.battle.remove_modifier(m)

    def _heal_all(self, ratio: float, flat: float) -> None:
        amount = ratio * self.char.defense + flat
        allies = self.allies()
        for c in allies:
            self.battle.heal(c, amount, self.char)
        if allies:
            self.battle.heal(min(allies, key=lambda c: c.hp_ratio), amount, self.char)

    # --------------------------------------------------------- Deep Learning
    @property
    def deep_learning(self) -> bool:
        return self.archetype is not None and self.archetype.alive and self.charges > 0

    def pick_archetype(self) -> Character | None:
        mates = self.teammates()
        if self.opts.get("target"):
            c = self.main_dps()
            return c if c is not self.char else None
        for c in mates:
            if c.path == Path.ELATION:
                return c
        return mates[0] if mates else None

    def _start_extra(self, ally: Character) -> None:
        mult = 1.0 + (self.ep(2, 1) if self.e(2) else 0.0)
        mod = grant_banger(self.battle, ally, self.p("ult", 7) * mult, self.char)
        pl = int(self.p("ult", 6) * mult)
        self.gain_punchline(pl)
        if mod is not None:
            mod.duration = None
            mod.tick = Tick.NONE
            self.extra_state = (mod, pl)

    def _turn_end(self, ev: E.Ev) -> None:
        if ev.entity is self.extra_for and ev.extra and self.extra_state is not None:
            mod, pl = self.extra_state
            self.battle.remove_modifier(mod)
            el = self.battle.elation
            removed = min(pl, el.punchline)
            if removed > 0:
                el.punchline -= removed
                self.battle.events.emit(PUNCHLINE_CHANGED, delta=-removed, total=el.punchline, source=self.char)
            self.extra_state = None
            self.extra_for = None

    # --------------------------------------------------------------- policy
    def take_turn(self) -> None:
        target = self.pick_target()
        if target is None:
            return
        if self.deep_learning:
            self.enhanced_basic(target)
            return
        room = self.cap - self.banger_points()
        if self.opts.get("rotation", "skill") == "skill" and self.can_skill() and room >= self.p("skill", 0):
            self.skill(target)
        else:
            self.basic(target)

    # -------------------------------------------------------------- actions
    def basic(self, target: Enemy | None) -> None:
        assert target is not None
        with self.action(ActionKind.BASIC, "basic", target) as act:
            act.hit(target, self.p("basic", 0), stat="def", toughness=self.toughness("basic"))

    def enhanced_basic(self, target: Enemy) -> None:
        arch = self.archetype
        assert arch is not None
        elation_arch = arch.path == Path.ELATION
        rec = self.sk(IMAGENATE_ID if elation_arch else RENDER_ID)
        lv = rec["params"][self.level_of(rec) - 1]
        with self.action(ActionKind.BASIC, rec, target) as act:
            act.aoe(lv[0], stat="def", toughness=rec["toughness"][1], main_target=target)
            self._heal_all(lv[1], lv[3])
            p = self.banger()
            if elation_arch and p > 0:
                for e in self.enemies():
                    self.elation_hit(e, lv[4], p, label="Imagenate the Starry Night (Elation)", action=act)
            # Elation DMG "calculated based on the Aesthetic Archetype's stats", credited to Pearl.
            # approximation: the Ultimate's "after attacking, additionally deals #2% Ice Elation DMG" is read as part
            # of Pearl's "Imagenate the Starry Night" (Elation Archetype only; fribbels instead adds it to the
            # Archetype's own attacks), and it counts Pearl's Certified Banger as its Punchline.
            extra = (self.p("ult", 1) if elation_arch else 0.0) + (self.ep(6, 1) if self.e(6) else 0.0)
            if extra > 0:
                for e in self.enemies():
                    self.battle.elation.damage(
                        arch,
                        e,
                        extra,
                        punchline=p,
                        element=Element.ICE,
                        label="Deep Learning (Archetype Elation)",
                        credited=self.char,
                        action=act,
                    )
        self._cleanse()
        self.charges -= 1

    def skill(self, target: Enemy | None) -> None:
        with self.action(ActionKind.SKILL, "skill"):
            self.gain_banger(self.p("skill", 0))
            self._heal_all(self.p("skill", 1), self.p("skill", 2))
        self._cleanse()

    def ult(self, target: Enemy | None) -> None:
        ally = self.pick_archetype()
        with self.action(ActionKind.ULT, "ult", ally):
            self.gain_banger(self.p("ult", 2))
            if ally is None:
                return
            self.archetype = ally
            self.charges = int(self.p("ult", 0))
            n = elation_count(self.battle)
            adv = self.p("ult", 2 + min(max(n, 1), 3))  # 1/2/(3+) Elation characters
            movers = [ally]
            if self.e(2):
                movers += [c for c in self.allies() if c.path == Path.ELATION and c not in (self.char, ally)]
            for c in movers:
                self.battle.advance(c, adv)
            if n >= 4:
                self.extra_for = ally
                self.battle.queue_extra_turn(ally)
            if self.trace(3) and ally.path == Path.ELATION:
                self.a6_armed = True

    # -------------------------------------------------------- elation skill
    def elation_skill(self, punchline: float) -> None:
        rec = self.sk(self.elation_skill_id)
        lv = rec["params"][self.level_of(rec) - 1]
        scale = float(lv[min(max(elation_count(self.battle), 1), 4) - 1])
        if self.e(4):
            scale *= 1.0 + self.ep(4, 0)
        with self.action(ActionKind.ELATION, rec, label=rec["name"]):
            for c in self.allies():
                mod = Modifier(DISSOLVE, duration=None, tick=Tick.NONE, kind=ModKind.BUFF, dispellable=False)
                mod.data.update(punchline=punchline, scale=scale)
                self.buff(c, mod)

    def _dissolve_proc(self, ev: E.Ev) -> None:
        act = ev.attack
        owner = act.owner
        if not isinstance(owner, Character) or not act.attacked:
            return
        mod = owner.get_mod(DISSOLVE)
        if mod is None:
            return
        self.battle.remove_modifier(mod)
        for t in act.attacked:
            if t.alive:
                self.battle.elation.damage(
                    owner,
                    t,
                    float(mod.data["scale"]),
                    punchline=float(mod.data["punchline"]),
                    element=owner.element,
                    label="Dissolve Reason into Elation (Pearl)",
                    credited=owner,
                )
