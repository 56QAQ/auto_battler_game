"""Ultimate insertion inside turns: an Ultimate's inserted actions (Aha's extra turn from Yao Guang's Ultimate,
the Aesthetic Archetype's extra turn from Pearl's) interrupt the current turn, which resumes afterwards; no
Ultimate can be inserted into those extra turns (attempts are cast when they end); an Ultimate may be cast after
the action has resolved but before the turn ends."""

from hsrsim import events as E
from hsrsim.battle import Battle
from hsrsim.build import Build, make_character
from hsrsim.control import CONTINUE, Controller, Decision
from hsrsim.entities import Enemy
from hsrsim.scenarios import boss_dps
from hsrsim.session import Session

ELATION_TEAM = ("Yao Guang", "Silver Wolf LV.999", "Pearl", "8009")


def _battle(names=ELATION_TEAM, controller=None):
    chars = [make_character(Build(n)) for n in names]
    b = Battle(chars, [[Enemy("Dummy", hp=1e12, spd=1)]])
    b.controller = controller
    b.start()
    trace = []
    b.events.on(E.TURN_START, lambda ev: trace.append(("turn_start", ev.entity.name, bool(ev.extra))))
    b.events.on(E.TURN_END, lambda ev: trace.append(("turn_end", ev.entity.name, bool(ev.extra))))
    b.events.on(E.ACTION_START, lambda ev: trace.append((ev.action.kind.name, ev.action.owner.name, False)))
    return b, chars, trace


def _kinds(trace):
    return [(k, who) for k, who, _ in trace]


class YaoGuang(Controller):
    """Yao Guang casts her Ultimate before choosing ("pre") or after her Skill ("post"), then continues."""

    def __init__(self, mode):
        self.mode, self.cast, self.windows = mode, False, []

    def turn(self, b, actor, extra):
        if self.mode == "pre" and not self.cast and actor.kit.ult_ready():
            self.cast = True
            return Decision("ult", who=actor.ref)
        return Decision("act", item="skill")

    def window(self, b, where, subject):
        self.windows.append((where, subject.name if subject else ""))
        if self.mode == "post" and where == "after_action" and not self.cast and subject.kit.ult_ready():
            self.cast = True
            return Decision("ult", who=subject.ref)
        return CONTINUE


def test_ult_before_choosing_runs_aha_extra_turn_then_the_turn_resumes():
    b, (yg, *_), trace = _battle(controller=YaoGuang("pre"))
    yg.energy = yg.max_energy
    b.take_turn(yg)
    k = _kinds(trace)
    ult, skill, end = k.index(("ULT", "Yao Guang")), k.index(("SKILL", "Yao Guang")), k.index(("turn_end", "Yao Guang"))
    elation = [i for i, (kind, _) in enumerate(k) if kind == "ELATION"]
    assert len(elation) == 4  # the Aha Instant: every Elation character's Elation Skill
    assert ult < min(elation) and max(elation) < skill < end  # interrupts the turn, which then resumes


def test_ult_after_the_action_is_inside_the_turn():
    ctrl = YaoGuang("post")
    b, (yg, *_), trace = _battle(controller=ctrl)
    yg.energy = yg.max_energy - 10  # the Skill's Energy fills it
    b.take_turn(yg)
    assert ("after_action", "Yao Guang") in ctrl.windows
    k = _kinds(trace)
    skill, ult, end = k.index(("SKILL", "Yao Guang")), k.index(("ULT", "Yao Guang")), k.index(("turn_end", "Yao Guang"))
    elation = [i for i, (kind, _) in enumerate(k) if kind == "ELATION"]
    assert skill < ult < min(elation) and max(elation) < end  # Ultimate + Aha extra turn before her turn ends


def test_auto_policy_casts_in_the_after_action_window():
    b, (yg, *_), trace = _battle()  # no controller: kit policies
    yg.energy = yg.max_energy - 10
    yg.kit.want_ult = lambda: True
    b.take_turn(yg)
    k = _kinds(trace)
    assert k.index(("ULT", "Yao Guang")) < k.index(("turn_end", "Yao Guang"))


class BeforeEnemy(Controller):
    def turn(self, b, actor, extra):
        return Decision("act", item="basic")

    def window(self, b, where, subject):
        yg = b.team[0]
        if where == "before_turn" and subject.side.value == "enemy" and yg.kit.ult_ready():
            return Decision("ult", who=yg.ref)
        return CONTINUE


def test_ult_between_turns_resolves_before_the_next_turn():
    b, (yg, *_), trace = _battle(controller=BeforeEnemy())
    yg.energy = yg.max_energy
    enemy = b.enemies[0]
    for c in b.team:
        c.gauge = 1e9  # the enemy acts next
    enemy.gauge = 0
    b.run(max_av=b.time + 1)
    k = _kinds(trace)
    elation = [i for i, (kind, _) in enumerate(k) if kind == "ELATION"]
    assert elation and max(elation) < k.index(("turn_start", "Dummy"))


class PearlExtraTurn(Controller):
    """Pearl's Ultimate (4 Elation characters) gives Yao Guang an extra turn; Silver Wolf's Ultimate is tried
    inside that extra turn."""

    def __init__(self):
        self.step, self.windows_in_extra = 0, 0

    def turn(self, b, actor, extra):
        pearl, sw, yg = b.team[2], b.team[1], b.team[0]
        if actor is pearl and not extra and self.step == 0:
            self.step = 1
            return Decision("ult", who=pearl.ref, target=yg.ref)
        if extra and self.step == 1:
            self.step = 2
            assert b.ults_locked
            return Decision("ult", who=sw.ref)  # deferred
        return Decision("act", item="basic")

    def window(self, b, where, subject):
        if b.ults_locked:
            self.windows_in_extra += 1
        return CONTINUE


def test_ult_tried_inside_an_ult_extra_turn_is_cast_when_it_ends():
    ctrl = PearlExtraTurn()
    b, (yg, sw, pearl, _), trace = _battle(controller=ctrl)
    pearl.energy = pearl.max_energy
    sw.kit.mmr = sw.kit.p("talent", 0)
    b.take_turn(pearl)
    assert trace == [
        ("turn_start", "Pearl", False),
        ("ULT", "Pearl", False),
        ("turn_start", "Yao Guang", True),  # the extra turn interrupts Pearl's turn
        ("BASIC", "Yao Guang", False),
        ("turn_end", "Yao Guang", True),
        ("ULT", "Silver Wolf LV.999", False),  # tried during the extra turn, cast when it ended
        ("BASIC", "Pearl", False),  # Pearl's turn resumes
        ("turn_end", "Pearl", False),
    ]
    assert ctrl.windows_in_extra == 0 and not b.deferred_ults and not b.ults_locked


def _to_turn(s, st):
    while st["point"] is not None and st["point"]["kind"] != "turn":
        st = s.decide({"kind": "continue"})
    return st


def test_session_after_action_pause_point():
    sc = boss_dps(cycles=2)
    sc.config["start_energy"] = 1.0
    team = [Build(n) for n in ELATION_TEAM]
    s = Session(sc, team, seed=1)
    try:
        st = _to_turn(s, s.start())
        actor = st["point"]["actor"]
        st = s.decide({"kind": "act", "item": "basic"})
        p = st["point"]
        assert p["kind"] == "window" and p["where"] == "after_action" and p["subject"] == actor
        assert st["ult_locked"] is False and st["deferred_ults"] == []
        yg = next(a["ref"] for a in st["allies"] if a["name"] == "Yao Guang")
        n = len(s.log_since(0))
        st = s.decide({"kind": "ult", "who": yg})
        new = s.log_since(n)
        kinds = [e["t"] if e["t"] != "action" else e["kind"] for e in new if e["t"] in ("ult", "action", "turn")]
        assert kinds[0] == "ult" and "elation" in kinds  # the Aha extra turn resolved right away
    finally:
        s.close()
    s = Session(sc, team, seed=1, settings={"pause": {"after_action": False}})
    try:
        st = _to_turn(s, s.start())
        st = s.decide({"kind": "act", "item": "basic"})
        assert st["point"]["where"] != "after_action"
    finally:
        s.close()
