"""Targeted checks for the relic sets whose conditional parts were added last (101/103/133/320/325/327)."""

import pytest

from hsrsim import stats as S
from hsrsim.battle import Battle
from hsrsim.build import Build, make_character
from hsrsim.data import get_data
from hsrsim.elation import ElationSystem
from hsrsim.entities import Enemy
from hsrsim.equipment import RELIC_SETS, load_gear
from hsrsim.modifiers import Modifier
from hsrsim.ui.server import preview

from .helpers import generic_build

load_gear()


def _battle(builds):
    chars = [make_character(b) for b in builds]
    battle = Battle(chars, [[Enemy("Dummy", effect_res=0.0, hp=1e12)]])
    battle.start()
    return battle, chars


def _p(set_id, pieces, i):
    return get_data().relic_set(set_id)["pieces"][str(pieces)]["params"][i]


@pytest.mark.parametrize("set_id", ["101", "103", "133", "320", "325", "327"])
def test_sets_are_registered(set_id):
    assert set_id in RELIC_SETS


def test_passerby_4pc_battle_start_sp():
    b0, _ = _battle([generic_build("Seele"), generic_build("Bronya")])
    b1, _ = _battle([generic_build("Seele", relics={"101": 4}), generic_build("Bronya")])
    assert b1.sp == min(b0.sp + 1, b1.max_sp)


def test_knight_4pc_shield_bonus():
    _, (march, _) = _battle([generic_build("1001", relics={"103": 4}), generic_build("Seele")])
    assert march.stat(S.SHIELD_PCT) == pytest.approx(_p("103", 4, 0))


def test_dreamlit_actor_elation_and_banger_crit_dmg():
    b, (bronya, seele, pela) = _battle(
        [Build("Bronya", relics={"133": 4}), generic_build("Seele"), generic_build("Pela")]
    )
    el0, cd0 = seele.stat(S.ELATION_DMG_PCT), pela.stat(S.CRIT_DMG)
    bronya.kit.skill(seele)
    assert seele.stat(S.ELATION_DMG_PCT) - el0 == pytest.approx(_p("133", 4, 0))
    assert pela.stat(S.CRIT_DMG) == pytest.approx(cd0)  # no Certified Banger yet
    banger = Modifier("Certified Banger", duration=2)
    banger.data["punchline"] = int(_p("133", 4, 2))
    b.apply(banger, bronya, bronya)
    assert ElationSystem.certified_banger(bronya) >= _p("133", 4, 2)
    bronya.kit.skill(seele)
    assert seele.stat(S.ELATION_DMG_PCT) - el0 == pytest.approx(_p("133", 4, 0))  # refreshed, not stacked
    assert pela.stat(S.CRIT_DMG) - cd0 == pytest.approx(_p("133", 4, 3))


def _huohuo(set_on, extra_spd):
    relics = {"320": 2} if set_on else {}
    _, (h, _) = _battle(
        [generic_build("Huohuo", relics=relics, extra_stats={"spd": extra_spd}), generic_build("Seele")]
    )
    return h


def test_giant_tree_heal_tiers_follow_spd():
    spd0 = _huohuo(True, 0).spd
    assert spd0 < _p("320", 2, 1)
    for target, bonus in ((spd0, 0.0), (_p("320", 2, 1), _p("320", 2, 3)), (_p("320", 2, 2), _p("320", 2, 4))):
        extra = target - spd0 + 0.5 if target > spd0 else 0.0
        with_set, without = _huohuo(True, extra), _huohuo(False, extra)
        assert with_set.stat(S.HEAL_PCT) - without.stat(S.HEAL_PCT) == pytest.approx(bonus)


def test_punklorde_tier_latches():
    b, (seele, _) = _battle([generic_build("Seele", relics={"325": 2}), generic_build("Bronya")])
    cd0 = seele.stat(S.CRIT_DMG)
    el = seele.stat(S.ELATION_DMG_PCT)
    boost = b.apply(
        Modifier("test elation", stats={S.ELATION_DMG_PCT: _p("325", 2, 2) - el + 0.01}, duration=1), seele, seele
    )
    assert seele.stat(S.CRIT_DMG) - cd0 == pytest.approx(_p("325", 2, 4))
    b.remove_modifier(boost)
    assert seele.stat(S.ELATION_DMG_PCT) == pytest.approx(el)
    assert seele.stat(S.CRIT_DMG) - cd0 == pytest.approx(_p("325", 2, 4))  # "for the first time": kept


def test_fallen_star_anchorage_needs_two_companions():
    group = get_data().character_group("AstralExpress")
    assert {"1001", "1002", "1003"} <= group
    _, (march, _) = _battle([generic_build("1001", relics={"327": 2}), generic_build("Dan Heng")])
    _, (lone, _) = _battle([generic_build("1001", relics={"327": 2}), generic_build("Seele")])
    assert march.stat(S.CRIT_DMG) - lone.stat(S.CRIT_DMG) == pytest.approx(_p("327", 2, 1))


def test_himeko_nova_companions_from_data():
    from hsrsim.kits.himeko_nova import COMPANIONS

    # March 7th, Dan Heng, Himeko, Welt, Imbibitor Lunae, March 7th (Hunt), Sunday, Evernight, Permansor Terrae,
    # Himeko • Nova and every Trailblazer
    known = {"1001", "1002", "1003", "1004", "1213", "1224", "1313", "1413", "1414", "1510"}
    assert known | {str(8001 + i) for i in range(10)} <= COMPANIONS
    assert "1102" not in COMPANIONS  # Seele


@pytest.mark.parametrize("set_id", ["101", "103", "133", "320", "325", "327"])
def test_preview_has_no_static_only_note(set_id):
    planar = get_data().relic_set(set_id)["planar"]
    out = preview({"character": "Seele", "relics": {set_id: 2 if planar else 4}})
    assert "error" not in out
    assert "only static stats modelled" not in str(out)


def test_every_conditional_set_and_light_cone_is_implemented():
    """Nothing in the data snapshot falls back to the "only static stats modelled" build note."""
    from hsrsim.equipment import LIGHT_CONES

    gd = get_data()
    missing = [
        rs["name"]
        for rs in gd.relic_sets.values()
        if rs["id"] not in RELIC_SETS and any(p["params"] != [v for _, v in p["props"]] for p in rs["pieces"].values())
    ]
    missing += [lc["name"] for lc in gd.light_cones.values() if lc["id"] not in LIGHT_CONES and lc["desc"]]
    assert missing == []
