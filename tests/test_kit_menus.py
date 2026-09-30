"""Manual-control action menus (``Kit.menu`` / ``perform`` / ``menu_for`` / ``perform_for``) of every kit."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import pytest

from hsrsim.battle import Battle, BattleConfig
from hsrsim.build import Build, make_character
from hsrsim.control import ALLIES, ALLY, CONTINUE, ENEMIES, ENEMY, SELF, Controller, Decision, MenuItem
from hsrsim.data import get_data
from hsrsim.entities import Character, Entity
from hsrsim.kits import ENHANCED_KITS, load_all
from hsrsim.scenarios import aoe_dps
from hsrsim.session import Session

KITS = sorted(load_all())
ENHANCED = sorted(ENHANCED_KITS)
FILLERS = ["Bronya", "Pela", "Huohuo", "Tingyun"]
TARGET_KINDS = {ENEMY, ENEMIES, ALLY, ALLIES, SELF}
ITEM_KINDS = {"basic", "skill", "other"}


def team_for(cid: str, eidolon: int = 0, enhanced: bool = False, mates: list[str] | None = None) -> list[Build]:
    name = get_data().character(cid)["name"]
    others = mates if mates is not None else [f for f in FILLERS if f != name][:3]
    return [Build(cid, eidolon=eidolon, enhanced=enhanced)] + [Build(m) for m in others]


def _pick_target(state: dict[str, Any], kind: str, n: int) -> str:
    if kind in (ENEMY, ENEMIES):
        refs = [e["ref"] for e in state["enemies"] if e["alive"] and e["targetable"]]
    elif kind == ALLY:
        refs = [a["ref"] for a in state["allies"] if a["alive"]]
    else:
        return ""
    return refs[n % len(refs)] if refs else ""


def _check_menu(menu: list[dict[str, Any]]) -> None:
    ids = [m["id"] for m in menu]
    assert len(ids) == len(set(ids)), ids
    for m in menu:
        assert m["target"] in TARGET_KINDS, m
        assert m["kind"] in ITEM_KINDS, m
        assert m["label"], m
        assert m["enabled"] or m["note"], f"disabled item without a reason: {m}"


# ================================================================================ generic session test
@pytest.mark.parametrize(
    "cid,enhanced,eidolon,pick",
    [(c, False, 0, "first") for c in KITS]
    + [(c, False, 6, "last") for c in KITS]
    + [(c, True, 0, "first") for c in ENHANCED]
    + [(c, True, 6, "last") for c in ENHANCED],
)
def test_menus_drive_a_session(cid: str, enhanced: bool, eidolon: int, pick: str) -> None:
    """Scripted player: at a turn the first (or last) enabled item on alternating targets, at a window any ready
    Ultimate, else continue. No crash, every turn point offers an enabled item and the battle advances."""
    session = Session(aoe_dps(cycles=3, count=3), team_for(cid, eidolon, enhanced), seed=1)
    try:
        state = session.start()
        own_turns = 0
        points = 0
        for n in range(400):
            assert not state.get("fatal"), state.get("fatal")
            assert not state.get("error"), state.get("error")
            point = state.get("point")
            if state.get("finished") or point is None:
                break
            points += 1
            if point["kind"] == "turn":
                menu = point["menu"]
                _check_menu(menu)
                enabled = [m for m in menu if m["enabled"]]
                assert enabled, f"{point['actor_name']}: no enabled action in {menu}"
                item = enabled[0] if pick == "first" else enabled[-1]
                own_turns += point["actor"] == "a0"
                decision = {"kind": "act", "item": item["id"], "target": _pick_target(state, item["target"], n)}
                state = session.decide(decision)
            else:
                ready = [a["ref"] for a in state["allies"] if a["alive"] and a.get("ult_ready")]
                state = session.decide({"kind": "ult", "who": ready[0]} if ready else {"kind": "continue"})
        assert not state.get("fatal"), state.get("fatal")
        assert state.get("finished"), "the battle did not reach its end"
        assert points > 0 and own_turns > 0
        assert state["time"] > 0 and state["total"] > 0
    finally:
        session.close()


# =================================================================================== direct battles
class Script(Controller):
    """Controller answering turns with ``policy(battle, actor, menu)``; Ultimate windows continue. Every turn
    decision point is logged as (battle turn, actor name, menu)."""

    def __init__(self, policy: Callable[[Battle, Entity, list[MenuItem]], Decision]) -> None:
        self.policy = policy
        self.log: list[tuple[int, str, list[MenuItem]]] = []

    def turn(self, battle: Battle, actor: Entity, extra_turn: bool) -> Decision:
        menu = battle._menu_of(actor) or []
        self.log.append((battle.turns, actor.name, menu))
        return self.policy(battle, actor, menu)

    def window(self, battle: Battle, where: str, subject: Entity | None) -> Decision:
        return CONTINUE


def make_battle(cid: str, eidolon: int = 0, mates: list[str] | None = None, count: int = 3) -> Battle:
    sc = aoe_dps(cycles=3, count=count)
    chars = [make_character(b) for b in team_for(cid, eidolon, mates=mates)]
    battle = Battle(chars, sc.make_waves(), BattleConfig(**sc.config))
    battle.start()
    return battle


def items(menu: list[MenuItem]) -> dict[str, MenuItem]:
    return {m.id: m for m in menu}


def auto(battle: Battle, actor: Entity, menu: list[MenuItem]) -> Decision:
    return Decision("auto")


def labels_of(battle: Battle, owner: str) -> set[str]:
    return {r.label for r in battle.records if r.owner == owner}


def test_imbibitor_lunae_enhancement_levels() -> None:
    b = make_battle("1213")
    kit = b.team[0].kit
    assert kit is not None
    b.sp, kit.squama = 1, 1
    menu = items(kit.menu())
    assert list(menu) == ["basic", "enhanced_basic:1", "enhanced_basic:2", "enhanced_basic:3"]
    assert [menu[f"enhanced_basic:{n}"].label for n in (1, 2, 3)] == ["Transcendence", "Divine Spear", "Fulgurant Leap"]
    assert menu["enhanced_basic:1"].enabled and menu["enhanced_basic:1"].sp == 0  # paid with Squama
    assert menu["enhanced_basic:2"].enabled and menu["enhanced_basic:2"].sp == -1
    assert not menu["enhanced_basic:3"].enabled and menu["enhanced_basic:3"].note
    kit.perform("enhanced_basic:2", b.enemies[1])
    assert (b.sp, kit.squama) == (0, 0)
    assert "Divine Spear" in labels_of(b, b.team[0].name)
    assert not items(kit.menu())["enhanced_basic:1"].enabled


def test_qingque_skill_does_not_end_the_turn() -> None:
    b = make_battle("1201")
    qq = b.team[0]
    kit = qq.kit
    assert kit is not None
    used: dict[int, int] = {}

    def policy(battle: Battle, actor: Entity, menu: list[MenuItem]) -> Decision:
        if actor is not qq:
            return Decision("auto")
        m = items(menu)
        assert not m["skill"].ends_turn
        if m["skill"].enabled and used.get(battle.turns, 0) < 2:
            used[battle.turns] = used.get(battle.turns, 0) + 1
            return Decision("act", "skill")
        return Decision("act", "basic", target=battle.enemies[0].ref)

    ctrl = Script(policy)
    b.controller = ctrl
    b.sp = b.max_sp
    b.run(max_cycles=2)
    assert any(n == 2 for n in used.values()), "two Skills within one turn"
    turns = [t for t, name, _ in ctrl.log if name == qq.name]
    assert any(turns.count(t) >= 2 for t in turns)  # several decisions in the same turn
    kit._enter_hidden_hand()  # type: ignore[attr-defined]
    m = items(kit.menu())
    assert m["basic"].label == "Cherry on Top!" and m["basic"].shape == "Blast"
    assert not m["skill"].enabled and m["skill"].note


def test_blade_hellscape_then_forest_of_swords() -> None:
    b = make_battle("1205")
    blade = b.team[0]
    seen: list[dict[str, MenuItem]] = []

    def policy(battle: Battle, actor: Entity, menu: list[MenuItem]) -> Decision:
        if actor is not blade:
            return Decision("auto")
        m = items(menu)
        seen.append(m)
        if m["skill"].enabled:
            return Decision("act", "skill")
        return Decision("act", "basic", target=battle.enemies[2].ref)

    b.controller = Script(policy)
    b.run(max_cycles=1)
    first, second = seen[0], seen[1]
    assert first["skill"].label == "Hellscape" and first["skill"].target == SELF and not first["skill"].ends_turn
    assert second["basic"].label == "Forest of Swords" and second["basic"].enabled
    assert not second["skill"].enabled and second["skill"].note
    assert "Forest of Swords" in labels_of(b, blade.name)


def test_jingliu_spectral_transmigration_menu() -> None:
    for enhanced in (False, True):
        sc = aoe_dps(cycles=1, count=3)
        chars = [make_character(x) for x in team_for("1212", enhanced=enhanced)]
        b = Battle(chars, sc.make_waves(), BattleConfig(**sc.config))
        b.start()
        kit = b.team[0].kit
        assert kit is not None
        kit._enter()  # type: ignore[attr-defined]
        b.sp = 0
        m = items(kit.menu())
        assert not m["basic"].enabled and m["basic"].note
        assert m["skill"].label == "Moon On Glacial River" and m["skill"].enabled and m["skill"].sp == 0


def test_phainon_khaslana_extra_turns_offer_three_abilities() -> None:
    b = make_battle("1408")
    ph = b.team[0]
    kit = ph.kit
    assert kit is not None
    menus: list[dict[str, MenuItem]] = []
    choices = ["calamity", "creation", "foundation"]

    def policy(battle: Battle, actor: Entity, menu: list[MenuItem]) -> Decision:
        if actor is not ph:
            return Decision("auto")
        m = items(menu)
        if "pass" in m:  # transformed during his own turn: the turn ends
            return Decision("act", "pass")
        if "creation" not in m:
            if kit.ult_ready():
                return Decision("ult", who=ph.ref)
            return Decision("act", "basic", target=battle.enemies[0].ref)
        menus.append(m)
        want = choices[min(len(menus) - 1, 2)]
        return Decision("act", want if m[want].enabled else "creation", target=battle.enemies[1].ref)

    b.controller = Script(policy)
    kit.coreflame = kit.p("talent", 3)  # type: ignore[attr-defined]
    b.run(max_cycles=3)
    assert menus, "no Khaslana extra turn reached the controller"
    assert set(menus[0]) == {"creation", "calamity", "foundation"}
    assert menus[0]["creation"].shape == "Blast" and menus[0]["foundation"].target == ENEMIES
    done = labels_of(b, ph.name)
    assert {"Creation: Bloodthorn Ferry", "Foundation: Stardeath Verdict"} <= done


def test_archer_circuit_connection_chain() -> None:
    b = make_battle("1015")
    archer = b.team[0]
    kit = archer.kit
    assert kit is not None
    seen: list[tuple[int, dict[str, MenuItem]]] = []

    def policy(battle: Battle, actor: Entity, menu: list[MenuItem]) -> Decision:
        if actor is not archer:
            return Decision("auto")
        m = items(menu)
        seen.append((battle.turns, m))
        if "end" in m and kit.cc_count >= 2:  # type: ignore[attr-defined]
            return Decision("act", "end")
        if m.get("skill") is not None and m["skill"].enabled:
            return Decision("act", "skill", target=battle.enemies[0].ref)
        return Decision("act", "end" if "end" in m else "basic", target=battle.enemies[0].ref)

    b.controller = Script(policy)
    b.sp = b.max_sp
    b.run(max_cycles=1)
    turn, first = seen[0]
    assert set(first) == {"basic", "skill"} and not first["skill"].ends_turn
    same = [m for t, m in seen if t == turn]
    assert len(same) >= 3  # Skill, Skill, End in one turn
    assert "end" in same[1] and same[1]["end"].target == SELF
    assert not kit.cc and not kit.in_chain  # type: ignore[attr-defined]


def test_castorice_netherwing_turns() -> None:
    b = make_battle("1407")
    kit = b.team[0].kit
    assert kit is not None
    nw_menus: list[tuple[int, dict[str, MenuItem]]] = []

    def policy(battle: Battle, actor: Entity, menu: list[MenuItem]) -> Decision:
        if actor.name != "Netherwing":
            return Decision("auto")
        m = items(menu)
        nw_menus.append((battle.turns, m))
        return Decision("act", "breath")

    b.controller = Script(policy)
    kit.newbud = kit.max_newbud()  # type: ignore[attr-defined]
    assert b.cast_ult(b.team[0])
    nw = kit.nw()  # type: ignore[attr-defined]
    assert nw is not None
    first = items(kit.menu_for(nw))
    assert set(first) == {"claw", "breath"} and first["claw"].enabled and not first["breath"].ends_turn
    assert items(kit.menu())["skill"].label == "Boneclaw, Doomdrake's Embrace"
    b.run(max_cycles=2)
    assert nw_menus
    turn = nw_menus[0][0]
    same = [m for t, m in nw_menus if t == turn]
    assert len(same) >= 2 and not same[1]["claw"].enabled  # only Breath can follow a Breath
    assert same[-1]["breath"].label == "Wings Sweep the Ruins"
    assert kit.nw() is None  # type: ignore[attr-defined]


def test_himeko_nova_assist_in_every_menu() -> None:
    b = make_battle("1510", mates=["Seele", "Bronya", "Huohuo"])
    hn, seele = b.team[0], b.team[1]
    hkit, skit = hn.kit, seele.kit
    assert hkit is not None and skit is not None
    assert items(hkit.menu())["assist"].enabled
    m = items(skit.menu())
    assert {"basic", "skill", "assist"} <= set(m) and m["assist"].enabled and m["assist"].sp == 0
    skit.perform("assist", b.enemies[0])
    assert hkit.uses[seele.uid] == 0  # type: ignore[attr-defined]
    assert "Trailblaze, By Your Side" in labels_of(b, hn.name)
    assert not items(skit.menu())["assist"].enabled
    skit.perform("basic", b.enemies[0])  # the teammate's own actions still work


def test_sparxie_livestream_steps() -> None:
    b = make_battle("1501")
    sx = b.team[0]
    seen: list[dict[str, MenuItem]] = []

    def policy(battle: Battle, actor: Entity, menu: list[MenuItem]) -> Decision:
        if actor is not sx:
            return Decision("auto")
        m = items(menu)
        seen.append(m)
        if len(seen) <= 2:
            return Decision("act", "skill")
        return Decision("act", "basic", target=battle.enemies[0].ref)

    b.controller = Script(policy)
    b.sp = b.max_sp
    b.run(max_cycles=1)
    assert seen[0]["skill"].label == "Boom! Sparxicle's Poppin'" and not seen[0]["skill"].ends_turn
    assert seen[1]["skill"].label == "Engagement Farming" and seen[1]["basic"].label == "Bloom! Winner Takes All"
    assert seen[2]["basic"].label == "Bloom! Winner Takes All"
    assert "Bloom! Winner Takes All" in labels_of(b, sx.name)
    assert items(sx.kit.menu())["basic"].label == "Cat Got Your Flametongue?"  # type: ignore[union-attr]


def test_trailblazer_remembrance_mem_menu() -> None:
    b = make_battle("8007")
    tb = b.team[0]
    kit = tb.kit
    assert kit is not None
    kit.summon_mem()  # type: ignore[attr-defined]
    mem = kit.mem()  # type: ignore[attr-defined]
    kit.charge = 0.5  # type: ignore[attr-defined]
    assert kit.menu_for(mem) == []  # below 100% Charge Mem acts on its own
    kit.charge = 1.0  # type: ignore[attr-defined]
    m = items(kit.menu_for(mem))
    assert set(m) == {"baddies", "lemme"} and m["lemme"].target == ALLY
    ally = b.team[2]
    kit.perform_for(mem, "lemme", ally)
    assert ally.has_mod("Mem's Support") and kit.charge < 0.5  # type: ignore[attr-defined]


def test_boothill_standoff_keeps_the_turn() -> None:
    b = make_battle("1315")
    bh = b.team[0]
    kit = bh.kit
    assert kit is not None
    assert not items(kit.menu())["skill"].ends_turn
    kit.perform("skill", b.enemies[1])
    m = items(kit.menu())
    assert m["basic"].label == "Fanning the Hammer" and not m["skill"].enabled
    kit.perform("basic", b.enemies[0])  # the Enhanced Basic ATK always hits the Standoff target
    assert any(r.label == "Fanning the Hammer" and r.target == b.enemies[1].name for r in b.records)


def test_luocha_skill_heals_the_chosen_ally() -> None:
    b = make_battle("1203")
    ally = b.team[3]
    ally.hp = ally.max_hp * 0.5
    b.team[1].hp = b.team[1].max_hp * 0.1  # the policy would pick this one
    assert b.team[0].kit is not None
    b.team[0].kit.perform("skill", ally)
    assert ally.hp > ally.max_hp * 0.5


def test_special_ultimate_resources() -> None:
    labels = {"1308": "闪裂", "1220": "飞黄", "1408": "余烬", "1407": "新蕊", "1415": "追忆", "1506": "MMR"}
    for cid, label in labels.items():
        kit = make_battle(cid).team[0].kit
        assert kit is not None
        cur, need, name = kit.ult_resource()
        assert name == label and need > 0 and cur >= 0
    for cid in ("1302", "1221"):  # Energy, but not the full bar
        kit = make_battle(cid).team[0].kit
        assert kit is not None
        cur, need, name = kit.ult_resource()
        assert name == "能量" and need > 0 and (need < kit.char.max_energy or cid == "1302")


@pytest.mark.parametrize(
    "cid,basic,skill,skill_enabled",
    [
        ("1310", "Fyrefly Type-IV: Pyrogenic Decimation", "Fyrefly Type-IV: Deathstar Overload", True),
        ("1317", "Ningu: Demonbane Petalblade", "Ninja Strike: Rooted Resolute", False),
        ("1402", "Slash by a Thousandfold Kiss", "Rise, Exalted Renown", False),
        ("1415", "To Love and Tomorrow ♪", "Bloom, Elysium of Beyond", False),
        ("1014", "Release, the Golden Scepter", "Strike Air: Hammer of the Wind King", False),
        ("1109", "Hehe! Don't Get Burned!", "Hey! Remember Hook?", True),
        ("1301", "Nectar Blitz", "Special Brew", True),
    ],
)
def test_ultimate_enhanced_forms(cid: str, basic: str, skill: str, skill_enabled: bool) -> None:
    """States entered by the Ultimate relabel the Basic ATK / Skill and lock what the game locks."""
    b = make_battle(cid)
    c = b.team[0]
    kit = c.kit
    assert kit is not None
    before = items(kit.menu())
    assert before["basic"].label == kit.sk("basic")["name"]
    c.energy = c.max_energy
    if cid == "1415":
        kit.recollection = kit._ult_cost()  # type: ignore[attr-defined]
    assert b.cast_ult(c)
    m = items(kit.menu())
    assert (m["basic"].label, m["skill"].label, m["skill"].enabled) == (basic, skill, skill_enabled)
    assert m["skill"].enabled or m["skill"].note
    if cid == "1109":
        assert m["skill"].shape == "Blast" and before["skill"].shape == "SingleAttack"


def test_state_locked_menus() -> None:
    m7 = make_battle("1224").team[0].kit
    assert m7 is not None
    m7.charge = m7.threshold  # type: ignore[attr-defined]
    m = items(m7.menu())
    assert m["basic"].label == "Brows Be Smitten, Heart Be Bitten" and not m["skill"].enabled
    gil = make_battle("1509").team[0].kit
    assert gil is not None
    m = items(gil.menu())
    assert m["basic"].enabled and not m["skill"].enabled
    gil.piqued = True  # type: ignore[attr-defined]
    m = items(gil.menu())
    assert not m["basic"].enabled and m["skill"].enabled
    for cid in ("1208", "1403", "1503"):  # team-wide Skills
        kit = make_battle(cid).team[0].kit
        assert kit is not None and items(kit.menu())["skill"].target == ALLIES
    assert isinstance(gil.char, Character)
