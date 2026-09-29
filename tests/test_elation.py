"""Elation path: Punchline curve, Aha SPD, Aha Instant flow."""

import pytest

from hsrsim.build import Build
from hsrsim.elation import aha_speed, punchline_multiplier
from hsrsim.scenarios import boss_dps


def test_punchline_curve():
    assert punchline_multiplier(0) == 1.0
    assert punchline_multiplier(240) == pytest.approx(1 + 5 * 240 / 480)
    assert punchline_multiplier(20) == pytest.approx(1 + 100 / 260)


def test_aha_speed_weights():
    # 80 + 150/5 + 120/10 + 100/20 + 90/40 + 80/40
    assert aha_speed([100, 150, 120, 90, 80]) == pytest.approx(80 + 30 + 12 + 5 + 2.25 + 2)


def test_aha_instant_consumes_punchline_and_grants_banger():
    team = [Build("Sparxie"), Build("Yao Guang"), Build("Robin"), Build("Huohuo")]
    rep = boss_dps(cycles=4).run(team)
    b = rep.battle
    assert b.elation.instants >= 1
    assert b.turn_counts.get("Aha", 0) >= 1
    assert any(r.tags and "elation" in r.tags for r in b.records)
