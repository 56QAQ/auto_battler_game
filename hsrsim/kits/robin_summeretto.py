"""Robin • Summeretto (知更鸟•晴歌) — Remembrance / Wind. "Vibes" from every ally attack (and the first
healing/Shield of each ally per turn) summon the memosprite band "Summer Songbirds" (Bessie, then Drummie at #6
and Paddie at #7 Vibes). With all three on stage she enters "Fever": the Songbirds and a countdown join the Action
Order, a DEF-ignore Zone is deployed, Robin stops taking turns, and the countdown drains Vibes until the band
leaves. Deviated Chords (A2) buffs whoever makes her gain Vibes.

The three members are one memosprite unit ("Summer Songbirds") with a member count.

Options (``default_opts``):
  * ``rotation``: ``"skill"`` (Skill whenever SP allows, default), ``"auto"`` (Skill only to summon the band)
    or ``"basic"``.
  * ``target``: name of the ally receiving the Ultimate (default: the first other team slot).

# approximation: Robin's Action Gauge is frozen while she is out of the Action Order during "Fever".
# approximation: E6 "store her Ultimate up to 2 times" is an Energy bank that only catches the overflow of
#   Energy from her own effects (E6 regeneration, the band's summon and Memosprite Skill Energy).
# approximation: E2's extra Vibes trigger once per turn (the first Vibe gain caused by an ability).
# not modelled: Crowd Control immunity/dispel, "Special Guest" blocking action advances on other allies.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from .. import events as E
from .. import formulas as F
from .. import stats as S
from ..entities import Character, Enemy, Entity, Summon
from ..enums import ActionKind, DmgTag, Side
from ..modifiers import Modifier, ModKind, Tick
from . import register
from .base import Kit

if TYPE_CHECKING:
    from ..battle import Battle

SONGBIRDS = "Summer Songbirds"
SPECIAL_GUEST = "Special Guest"
SPECIAL_GUEST_TURNS = 2  # Ultimate "This lasts for 2 turn(s)" (literal)
TECHNIQUE_TURNS = 2  # Technique "lasting for 2 turn(s)" (literal)
MEMO_SKILL = "1151201"
MEMO_WARBLE = "1151203"
MEMO_SUMMON = "1151205"
MEMO_LEAVE = "1151206"


@register
class RobinSummeretto(Kit):
    char_id = "1512"
    ult_targets_ally = True
    default_opts = {"rotation": "skill", "target": None}

    def setup(self) -> None:
        self.vibes = 0
        self.members = 0
        self.fever = False
        self.first_fever = True
        self.zone: Modifier | None = None
        self.countdown: Summon | None = None
        self.turn_id = 0
        self.provided: set[int] = set()  # allies that already healed/shielded during this turn
        self.a4_turn = -1
        self.e2_turn = -1
        self.groove = 0
        self.tally = 0.0  # E1
        self.bank = 0.0  # E6 stored Energy
        self.saved_gauge = 0.0
        self.on(E.TURN_START, self._new_turn)
        self.on(E.PRE_TURN, self._skip_turn_in_fever)
        self.on(E.ATTACK_END, self._on_attack)
        self.on(E.HEALED, self._on_healed)
        self.on(E.MOD_APPLIED, self._on_mod_applied)
        self.passive("A Warble of Wings", {}, dyn=self._fever_dmg, dyn_keys={S.DMG_PCT})  # the band syncs it
        if self.trace(3):
            self.passive("Rebuilt Harmony", {S.CRIT_RATE: self.tp(3, 0)})
        if self.e(1):
            self.on(E.DAMAGE_DEALT, self._e1_tally)
        if self.e(2):
            self.passive("A Heart of Still Water", {S.RES_PEN: self.ep(2, 2)}, scope=self.ally_scope)

    def technique(self) -> None:
        p = self.sk("technique")["params"][0]
        self.battle.advance(self.char, p[2])
        self.gain_vibes(int(p[0]))
        for c in self.allies():
            self.buff(c, Modifier("We Are the Melody", stats={S.DMG_PCT: p[1]}, duration=TECHNIQUE_TURNS))

    # ------------------------------------------------------------ helpers
    def _lv(self, sid: str) -> list[Any]:
        rec = self.sk(sid)
        return list(rec["params"][self.level_of(rec) - 1])

    def songbirds(self) -> Summon | None:
        return self.memosprite()

    def vibes_cap(self) -> int:
        return int(self.p("talent", 4)) + (int(self.ep(2, 0)) if self.e(2) else 0)

    def _fever_dmg(self, mod: Modifier, key: str, ent: Entity) -> float:
        if not self.fever:
            return 0.0
        lv = self._lv(MEMO_WARBLE)
        return lv[0] + self.vibes * lv[1]

    def _energy(self, amount: float, fixed: bool = False) -> None:
        """Energy for Robin; with E6 during "Fever" the overflow is banked (Ultimate stored up to 2 times)."""
        c = self.char
        eff = amount if fixed else amount * (1.0 + c.stat(S.ERR))
        overflow = c.energy + eff - c.max_energy
        self.battle.gain_energy(c, amount, fixed=fixed)
        if self.e(6) and self.fever and overflow > 0:
            self.bank = min(c.max_energy, self.bank + overflow)

    def pay_ult_cost(self) -> None:
        if self.bank >= self.char.max_energy - 1e-9:
            self.bank = 0.0  # use the stored Ultimate, Energy stays full
            return
        self.char.energy = self.bank
        self.bank = 0.0

    # ----------------------------------------------------------------- Vibes
    def _new_turn(self, ev: E.Ev) -> None:
        self.turn_id += 1
        self.provided.clear()

    def gain_vibes(self, n: int, cause: Entity | None = None, ability: bool = False) -> None:
        if n <= 0:
            return
        if ability and self.e(2) and self.e2_turn != self.turn_id:
            self.e2_turn = self.turn_id
            n += int(self.ep(2, 1))
        self.vibes = min(self.vibes_cap(), self.vibes + n)
        if self.trace(2) and self.a4_turn != self.turn_id:
            self.a4_turn = self.turn_id
            if self.groove > 0:  # Improvised Blues: consume 1 Groove on the first Vibes gain of the turn
                self.groove -= 1
                self._energy(self.tp(2, 1), fixed=True)
        if cause is not None and self.trace(1):
            self._deviated_chords(cause)
        self._check_members()

    def _deviated_chords(self, cause: Entity) -> None:
        # summons (memosprites included) sync their stats from their owner: buff the owner once
        holder = cause.owner if isinstance(cause, Summon) else cause
        if holder.side != Side.ALLY or not holder.alive:
            return
        if holder is not self.char and holder.atk > self.char.atk:
            stats = {S.ATK_FLAT: (self.tp(1, 0) + self.vibes * self.tp(1, 1)) * self.char.max_hp}
        else:
            stats = {S.CRIT_DMG: self.tp(1, 2) + self.vibes * self.tp(1, 3)}
        self.buff(holder, Modifier("Deviated Chords", stats=stats, duration=int(self.tp(1, 4))))

    def _on_attack(self, ev: E.Ev) -> None:
        act = ev.attack
        actor = act.actor
        if act.owner is None or act.owner.side != Side.ALLY:
            return
        n = 1
        guest = act.owner if isinstance(actor, Summon) else actor
        if guest.has_mod(SPECIAL_GUEST):
            n += int(self.p("ult", 1))
        self.gain_vibes(n, cause=actor, ability=True)

    def _provided(self, source: Entity | None) -> None:
        """First healing/Shield provided by an ally during any target's turn: 1 Vibe."""
        if source is None or source.side != Side.ALLY or source.uid in self.provided:
            return
        self.provided.add(source.uid)
        self.gain_vibes(1, cause=source, ability=self.battle.current_action is not None)

    def _mine(self, ent: Entity) -> bool:
        return ent is self.char or ent is self.songbirds()

    def _groove(self, target: Entity, source: Entity | None) -> None:
        if self.trace(2) and self._mine(target) and source is not None and not self._mine(source):
            self.groove = min(int(self.tp(2, 2)), self.groove + int(self.tp(2, 0)))

    def _on_healed(self, ev: E.Ev) -> None:
        self._groove(ev.entity, ev.source)
        self._provided(ev.source)

    def _on_mod_applied(self, ev: E.Ev) -> None:
        mod = ev.mod
        if "shield" not in mod.tags:
            return
        self._groove(ev.target, mod.source)
        self._provided(mod.source)

    # ------------------------------------------------------------ the band
    def _summon_band(self) -> Summon:
        sb = self.summon_memosprite(SONGBIRDS, on_turn=self._band_turn)
        sb.on_timeline = False  # only on the Action Order during "Fever"
        self.members = 1  # Bessie
        self.battle.apply(
            Modifier(
                "A Warble of Wings (DMG taken)",
                tick=Tick.NONE,
                kind=ModKind.OTHER,
                scope=self.enemy_scope,
                dispellable=False,
                dyn=lambda m, k, e: self._lv(MEMO_WARBLE)[1 + self.members] if self.members else 0.0,
                dyn_keys={S.VULN},
                key="Summer Songbirds DMG taken",
            ),
            sb,
            self.char,
        )
        if self.e(4):
            self.battle.apply(
                Modifier(
                    "Her Variation on the Theme",
                    tick=Tick.NONE,
                    kind=ModKind.OTHER,
                    dispellable=False,
                    dyn=lambda m, k, e: self.ep(4, 1) + self.vibes * self.ep(4, 2) if self.fever else 0.0,
                    dyn_keys={S.SPD_PCT},
                ),
                sb,
                self.char,
            )
        self._energy(self._lv(MEMO_SUMMON)[0])
        self._check_members()
        return sb

    def _check_members(self) -> None:
        if self.fever or self.songbirds() is None:
            return
        if self.members < 2 and self.vibes >= self.p("talent", 5):
            self.members = 2  # Drummie
        if self.members < 3 and self.vibes >= self.p("talent", 6):
            self.members = 3  # Paddie
        if self.members >= 3:
            self._enter_fever()

    def _enter_fever(self) -> None:
        sb = self.songbirds()
        assert sb is not None
        self.fever = True
        # "will not enter her turn until the Fever state ends": out of the Action Order (gauge frozen)
        self.char.on_timeline = False
        self.saved_gauge = self.char.gauge
        sb.on_timeline = True
        sb.gauge = F.AV_BASE
        self.zone = self.buff_self(
            Modifier(
                "Wings Heed No Borders (Zone)",
                tick=Tick.NONE,
                kind=ModKind.OTHER,
                scope=self.ally_scope,
                dispellable=False,
                dyn=lambda m, k, e: self.p("talent", 7) + self.vibes * self.p("talent", 8),
                dyn_keys={S.DEF_IGNORE},
                key="Robin Summeretto Zone",
            )
        )
        self.countdown = self.battle.add_unit(
            Summon("Fever Countdown", self.char, spd=self._lv(MEMO_WARBLE)[8], on_turn=self._countdown_turn)
        )
        if self.e(4):
            self.gain_vibes(int(self.ep(4, 0)))
        if self.e(6) and self.first_fever:
            self._energy(self.ep(6, 1), fixed=True)
        self.first_fever = False

    def _exit_fever(self) -> None:
        self.fever = False
        self.vibes = 0
        if self.zone is not None:
            self.battle.remove_modifier(self.zone)
        self.zone = None
        if self.countdown is not None:
            self.battle.remove_unit(self.countdown)
        self.countdown = None
        sb = self.songbirds()
        if sb is not None:
            self.battle.remove_unit(sb)
        self.members = 0
        self.char.on_timeline = True
        self.char.gauge = self.saved_gauge
        self.battle.advance(self.char, self._lv(MEMO_LEAVE)[0])  # "Astride Summer's Nightwind"

    def _skip_turn_in_fever(self, ev: E.Ev) -> None:
        # the engine's timeline only honours ``on_timeline`` for summons: cancel Robin's turns during "Fever"
        if ev.entity is self.char and self.fever:
            ev.data["cancel"] = True

    def _countdown_turn(self, unit: Summon, battle: Battle) -> None:
        if self.e(6):
            self._energy(self.ep(6, 1), fixed=True)
        lv = self._lv(MEMO_WARBLE)
        self.vibes = max(0, self.vibes - max(int(lv[5]), int(lv[9] * self.vibes)))
        if self.vibes <= 0:
            self._exit_fever()

    def _band_turn(self, sb: Summon, battle: Battle) -> None:
        """Chirrup Quartet: AoE DMG = #2% of the band's Max HP (E6: +100% of the multiplier)."""
        target = self.pick_target()
        if target is None:
            return
        rec = self.sk(MEMO_SKILL)
        lv = rec["params"][self.level_of(rec) - 1]
        mult = lv[1] * (1.0 + (self.ep(6, 0) if self.e(6) else 0.0))
        with self.battle.action(sb, ActionKind.MEMOSPRITE, skill=rec, target=target, energy=0.0) as act:
            act.aoe(mult, stat="hp", toughness=float(rec["toughness"][1]), main_target=target)
            if self.e(1) and self.tally > 0:
                top = max(self.enemies(), key=lambda e: e.hp, default=None)
                if top is not None:
                    ratio = self.ep(1, 0) + self.vibes * self.ep(1, 1)
                    self.battle.true_damage(self.tally, ratio, top, self.char, "Stray Bird of Summer (True DMG)")
                    self.tally -= self.ep(1, 3) * self.tally
        self._energy(float(rec["energy"]))

    def _e1_tally(self, ev: E.Ev) -> None:
        rec = ev.record
        if self.songbirds() is None or DmgTag.TRUE in rec.tags or ev.credited.side != Side.ALLY:
            return
        self.tally += self.ep(1, 2) * rec.amount

    # --------------------------------------------------------------- policy
    def take_turn(self) -> None:
        target = self.pick_target()
        if target is None:
            return
        policy = self.opts.get("rotation", "skill")
        if policy == "basic" or not self.can_skill() or (policy == "auto" and self.songbirds() is not None):
            self.basic(target)
        else:
            self.skill(target)

    def _ult_target(self) -> Character | None:
        ally = self.main_dps()
        return ally if ally is not self.char and ally.alive else None

    # -------------------------------------------------------------- actions
    def basic(self, target: Enemy | None) -> None:
        assert target is not None
        with self.action(ActionKind.BASIC, "basic", target) as act:
            act.hit(target, self.p("basic", 0), stat="hp", toughness=self.toughness("basic"), splits="data")

    def skill(self, target: Enemy | None) -> None:
        sb = self.songbirds()
        with self.action(ActionKind.SKILL, "skill", sb):
            if sb is None:
                self._summon_band()
            else:
                amount = self.p("skill", 0) * sb.max_hp * (1.0 + self.char.stat(S.HEAL_PCT) + sb.stat(S.HEAL_TAKEN))
                self.battle.heal(sb, amount, self.char)
                self.gain_vibes(int(self.p("skill", 1)), cause=self.char, ability=True)

    def ult(self, target: Enemy | None) -> None:
        ally = self._ult_target()
        with self.action(ActionKind.ULT, "ult", ally):
            if ally is not None:
                self.battle.gain_energy(ally, self.p("ult", 2) * ally.max_energy, fixed=True)
                self.buff(
                    ally,
                    Modifier(
                        SPECIAL_GUEST, duration=SPECIAL_GUEST_TURNS, tick=Tick.HOLDER_TURN_START, key=SPECIAL_GUEST
                    ),
                )
        if ally is not None:
            self.battle.advance(ally, self.p("ult", 0))
