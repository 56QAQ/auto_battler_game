"""Every implemented light cone and relic set runs through short fights without errors."""

import pytest

from hsrsim.equipment import LIGHT_CONES, RELIC_SETS, load_gear
from hsrsim.scenarios import aoe_dps, boss_dps

from .helpers import generic_build, lc_path, path_char

load_gear()


@pytest.mark.parametrize("lc_id", sorted(LIGHT_CONES))
def test_light_cone_smoke(lc_id):
    wearer = path_char(lc_path(lc_id))
    team = [
        generic_build(wearer, light_cone=lc_id, superimposition=5),
        generic_build("Bronya" if wearer != "Bronya" else "Tingyun"),
    ]
    for sc in (boss_dps(cycles=3), aoe_dps(cycles=2, count=3)):
        rep = sc.run(team)
        assert rep.total > 0


@pytest.mark.parametrize("set_id", sorted(RELIC_SETS))
def test_relic_set_smoke(set_id):
    team = [generic_build("Seele", relics={set_id: 4}), generic_build("Bronya", relics={set_id: 4})]
    for sc in (boss_dps(cycles=3), aoe_dps(cycles=2, count=3)):
        rep = sc.run(team)
        assert rep.total > 0
