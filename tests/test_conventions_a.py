"""Script conventions (first half of the roster): ERR-scaled vs fixed Energy, modifier tick timing.

* ``ModifySPNew AddValue=`` scales with the receiver's Energy Regeneration Rate, ``FixedAddValue=`` does not.
* ``LifeStepMoment=ModifierPhase1End`` counts down at the holder's turn start, the default at its turn end.
"""

import pytest

from hsrsim import stats as S
from hsrsim.battle import Battle, BattleConfig
from hsrsim.build import Build, make_character
from hsrsim.entities import Enemy
from hsrsim.enums import Element
from hsrsim.modifiers import Tick

ERR = 0.2


def _battle(builds, n_enemies=1, **cfg):
    chars = [make_character(b) for b in builds]
    enemies = [
        Enemy(f"Dummy {i}", hp=1e12, toughness=1e6, effect_res=0.0, weaknesses=list(Element)) for i in range(n_enemies)
    ]
    b = Battle(chars, [enemies], BattleConfig(**cfg))
    b.start()
    return b, chars, b.enemies


def _always_succeed(b):
    b.rng.random = lambda: 0.0  # every chance roll succeeds


# ----------------------------------------------------------------- Rule 1: Energy
def test_1402_aglaea_technique_energy_scales_with_err():
    b, (ag,), _ = _battle([Build("Aglaea", extra_stats={S.ERR: ERR})])
    before = ag.energy
    ag.kit.technique()  # StageAbility_Maze_Aglaea_Modifier: ModifySPNew AddValue
    assert ag.energy - before == pytest.approx(ag.kit.sk("technique")["params"][0][1] * (1 + ERR))


def test_1211_bailu_e1_energy_is_fixed():
    b, (bailu, seele), _ = _battle([Build("Bailu", eidolon=1), Build("Seele", extra_stats={S.ERR: ERR})])
    bailu.kit.invigorate(seele, 2)
    mod = seele.get_mod("Invigoration")
    assert mod is not None
    seele.hp = seele.max_hp
    before = seele.energy
    b.remove_modifier(mod)  # Heal_Mark OnDestroy at full HP: ModifySPNew FixedAddValue
    assert seele.energy - before == pytest.approx(bailu.kit.ep(1, 0))


def test_1412_cerydra_e1_energy_is_fixed():
    b, (cer, seele), _ = _battle([Build("Cerydra", eidolon=1), Build("Seele", extra_stats={S.ERR: ERR})], start_sp=5)
    before = seele.energy
    cer.kit._skill(seele)  # Skill02_Others_Phase02: ModifySPNew FixedAddValue on the target
    assert seele.energy - before == pytest.approx(cer.kit.ep(1, 2))


def test_1415_cyrene_ode_to_sky_energy_is_fixed():
    b, (cyr, hy), _ = _battle([Build("Cyrene"), Build("Hyacine", extra_stats={S.ERR: ERR})])
    p = cyr.kit.ode_params(cyr.kit._ode_id(hy))
    hy.energy = 0.0
    cyr.kit._builtin_ode(hy)  # Servant Skill02_Phase02 (Hyacine): ModifySPNew FixedAddValue
    assert hy.energy == pytest.approx(p[1])


def test_1218_jiaoqiu_a2_battle_start_energy_scales_with_err():
    b, (jq,), _ = _battle([Build("Jiaoqiu", extra_stats={S.ERR: ERR})])
    assert jq.energy == pytest.approx(jq.max_energy * b.cfg.start_energy + jq.kit.tp(1, 0) * (1 + ERR))


@pytest.mark.parametrize("enhanced", [False, True])
def test_1212_jingliu_technique_energy_scales_with_err(enhanced):
    b, (jl,), _ = _battle([Build("Jingliu", enhanced=enhanced, extra_stats={S.ERR: ERR})])
    before = jl.energy
    jl.kit.technique()  # SkillMaze_Jingliu_Modifier: ModifySPNew AddValue
    assert jl.energy - before == pytest.approx(jl.kit.sk("technique")["params"][0][5] * (1 + ERR))


# ------------------------------------------------------------ Rule 2: tick timing
def test_1003_himeko_technique_fire_vuln_counts_down_at_holder_turn_start():
    b, (hk,), (e,) = _battle([Build("Himeko")])
    _always_succeed(b)
    hk.kit.technique()
    mod = e.get_mod("Incomplete Combustion")  # MAvatar_Himeko_00_FireTakenRatio: ModifierPhase1End
    assert mod is not None and mod.tick == Tick.HOLDER_TURN_START
    turns = int(hk.kit.sk("technique")["params"][0][2])
    b._tick(e, at_start=False)  # the enemy's turn end does not count
    for _ in range(turns - 1):
        b._tick(e, at_start=True)
    assert e.has_mod("Incomplete Combustion")
    b._tick(e, at_start=True)
    assert not e.has_mod("Incomplete Combustion")


def test_1104_gepard_ult_shield_counts_down_at_holder_turn_end():
    b, (gep, seele), _ = _battle([Build("Gepard"), Build("Seele")])
    gep.kit.ult(None)
    mod = seele.get_mod("Enduring Bulwark")  # MAvatar_Gepard_00_Ultra_Shield: default (turn end)
    assert mod is not None and mod.tick == Tick.HOLDER_TURN_END
    turns = int(gep.kit.p("ult", 1))
    for _ in range(turns):
        b._tick(seele, at_start=True)  # turn starts do not count
    assert seele.has_mod("Enduring Bulwark")
    for _ in range(turns):
        b._tick(seele, at_start=False)
    assert not seele.has_mod("Enduring Bulwark")


def test_1414_dhpt_shield_counts_down_at_holder_turn_end():
    b, (dh, seele), _ = _battle([Build("Dan Heng • Permansor Terrae"), Build("Seele")], start_sp=5)
    dh.kit._skill(seele)
    mod = seele.get_mod("Terra Omnibus Shield")  # MAvatar_DanHengPT_00_Shield: default (turn end)
    assert mod is not None and mod.tick == Tick.HOLDER_TURN_END
    turns = int(dh.kit.p("skill", 2))
    for _ in range(turns):
        b._tick(seele, at_start=True)
    assert seele.has_mod("Terra Omnibus Shield")
    for _ in range(turns):
        b._tick(seele, at_start=False)
    assert not seele.has_mod("Terra Omnibus Shield")
