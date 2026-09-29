"""The bundled datamine snapshot and build pipeline produce exact in-game stat values."""

import pytest

from hsrsim import stats as S
from hsrsim.build import Build, make_character
from hsrsim.data import get_data


def test_lookup_by_name_and_id():
    gd = get_data()
    assert gd.character("Seele")["id"] == "1102"
    assert gd.character("希儿")["id"] == "1102"
    assert gd.character("1102")["name"] == "Seele"
    assert gd.character("Trailblazer (Harmony)")["id"] == "8005"
    assert gd.character("March 7th (Hunt)")["id"] == "1224"
    with pytest.raises(KeyError):
        gd.character("March 7th")  # ambiguous
    assert gd.light_cone("In the Night")["id"] == "23001"


def test_level_multiplier_table():
    gd = get_data()
    assert gd.break_base(80) == pytest.approx(3767.5535)
    assert gd.break_base(1) == pytest.approx(54)


def test_relic_values():
    gd = get_data()
    assert gd.relic_main_value("body", "CriticalDamageBase") == pytest.approx(0.648)
    assert gd.relic_main_value("feet", "SpeedDelta") == pytest.approx(25.032)
    assert gd.relic_main_value("head", "HPDelta") == pytest.approx(705.6)
    assert gd.relic_sub_roll("CriticalChanceBase", "low") == pytest.approx(0.02592)
    assert gd.relic_sub_roll("CriticalChanceBase", "high") == pytest.approx(0.0324)
    assert gd.relic_sub_roll("CriticalChanceBase") == pytest.approx(0.02916)


def test_character_sheet_seele():
    # Seele Lv80 + In the Night Lv80, no relics except the fixed head/hands main stats
    c = make_character(Build("Seele", light_cone="In the Night"))
    base_atk = (296.208 + 4.356 * 79) + (269.28 + 3.96 * 79)
    atk_pct = 0.04 + 0.04 + 0.06 + 0.06 + 0.08  # minor traces
    assert c.raw(S.BASE_ATK) == pytest.approx(base_atk)
    assert c.atk == pytest.approx(base_atk * (1 + atk_pct) + 352.8)
    assert c.stat(S.CRIT_RATE) == pytest.approx(0.05 + 0.18)  # base + LC
    assert c.stat(S.CRIT_DMG) == pytest.approx(0.5 + 0.053 + 0.08 + 0.107)
    assert c.spd == pytest.approx(115)
    assert c.max_energy == 120
    assert c.skill_levels["110202"] == 10 and c.skill_levels["110201"] == 6


def test_eidolon_skill_levels_and_enhanced_variant():
    c = make_character(Build("Seele", eidolon=5))
    assert c.skill_levels["110202"] == 12  # E3 Skill +2
    assert c.skill_levels["110201"] == 7  # E5 Basic +1
    e = make_character(Build("Seele", enhanced=True))
    assert e.enhanced
    assert e.stat(S.CRIT_DMG) == pytest.approx(0.5 + 0.053 + 0.08 + 0.107)  # traces counted once


def test_substat_rolls():
    c = make_character(Build("Seele", substats={"crit_rate": "10r", "spd": 6.0}))
    assert c.stat(S.CRIT_RATE) == pytest.approx(0.05 + 10 * 0.02916)
    assert c.spd == pytest.approx(121)
