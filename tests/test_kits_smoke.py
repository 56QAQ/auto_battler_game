"""Every implemented kit runs at E0 and E6 in single-target and AoE fights (base and enhanced kits)."""

import pytest

from hsrsim.build import Build
from hsrsim.data import get_data
from hsrsim.kits import ENHANCED_KITS, load_all
from hsrsim.scenarios import aoe_dps, boss_dps, clear_waves

KITS = sorted(load_all())
ENHANCED = sorted(ENHANCED_KITS)
FILLERS = ["Bronya", "Pela", "Huohuo", "Tingyun"]


def team_for(cid: str, eidolon: int, enhanced: bool = False) -> list[Build]:
    name = get_data().character(cid)["name"]
    mates = [f for f in FILLERS if f != name][:3]
    return [Build(cid, eidolon=eidolon, enhanced=enhanced)] + [Build(m) for m in mates]


@pytest.mark.parametrize("cid", KITS)
@pytest.mark.parametrize("eidolon", [0, 6])
def test_kit_runs(cid, eidolon):
    for sc in (boss_dps(cycles=4), aoe_dps(cycles=3, count=3)):
        rep = sc.run(team_for(cid, eidolon))
        assert rep.total > 0
        assert rep.battle.turn_counts.get(rep.battle.team[0].name, 0) > 0


@pytest.mark.parametrize("cid", KITS)
def test_kit_clears_waves(cid):
    rep = clear_waves(max_cycles=40).run(team_for(cid, 0))
    assert rep.total > 0


@pytest.mark.parametrize("cid", ENHANCED)
@pytest.mark.parametrize("eidolon", [0, 6])
def test_enhanced_kit_runs(cid, eidolon):
    for sc in (boss_dps(cycles=4), aoe_dps(cycles=3, count=3)):
        rep = sc.run(team_for(cid, eidolon, enhanced=True))
        assert rep.total > 0
        assert rep.battle.team[0].enhanced
