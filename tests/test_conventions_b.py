"""Data conventions from the ability scripts, second half of the roster (lingsha ... yunli).

* Energy: ``ModifySPNew AddValue`` scales with Energy Regeneration Rate, ``FixedAddValue`` does not.
* Modifier lifetimes: ``LifeStepMoment=ModifierPhase1End`` counts down at the start of the holder's turn, the
  default (turn end) at the end of it.
"""

import pytest

from hsrsim import events as E
from hsrsim import stats as S
from hsrsim.battle import Battle, BattleConfig
from hsrsim.build import Build, make_character
from hsrsim.entities import Enemy

ERR = 0.2


def _battle(builds, **cfg):
    chars = [make_character(b) for b in builds]
    enemies = [Enemy(f"Enemy {i + 1}", hp=1e12, toughness=1e6, effect_res=0.0) for i in range(2)]
    cfg.setdefault("start_energy", 0.0)
    b = Battle(chars, [enemies], BattleConfig(**cfg))
    b.start()
    return b, chars, enemies


def _present_at_action_start(b, holder, name, turns):
    """Take ``turns`` turns of ``holder``; whether ``name`` was on it when each turn's first action started."""
    seen: dict[int, bool] = {}

    def on_action(ev):
        if ev.action.owner is holder:
            seen.setdefault(b.turns, holder.has_mod(name))

    b.events.on(E.ACTION_START, on_action)
    for _ in range(turns):
        b.take_turn(holder)
    return list(seen.values())


# ------------------------------------------------------------ Rule 1: Energy
@pytest.mark.parametrize(
    ("char", "kw", "base"),
    [
        # Moze E1 (Avatar_Moze_00_Rank01_AddSPModifier: ModifySPNew AddValue)
        ("Moze", {"eidolon": 1}, lambda k: k.ep(1, 1)),
        # Serval A4 String Vibration (M_Serval_SkillTree02: ModifySPNew AddValue)
        ("Serval", {}, lambda k: k.tp(2, 0)),
        # The Dahlia Talent (MAvatar_Constance_00_Passive OnEnterBattle: ModifySPNew AddValue)
        ("The Dahlia", {}, lambda k: k.p("talent", 3)),
        # Welt (enhanced) A2 Retribution (MAvatar_Advanced_Welt_SkillTree01Listen: ModifySPNew AddValue)
        ("Welt", {"enhanced": True}, lambda k: k.tp(1, 3)),
    ],
)
def test_battle_start_energy_scales_with_err(char, kw, base):
    b, (c,), _ = _battle([Build(char, extra_stats={S.ERR: ERR}, **kw)])
    assert c.energy == pytest.approx(base(c.kit) * (1 + ERR))


def test_march_7th_hunt_technique_energy_scales_with_err():
    # MAvatar_Mar_7th_10_SkillMazeInLevel: ModifySPNew AddValue
    b, (march,), _ = _battle([Build("1224", extra_stats={S.ERR: ERR})], techniques=True)
    assert march.energy == pytest.approx(march.kit.sk("technique")["params"][0][1] * (1 + ERR))


def test_topaz_technique_energy_scales_with_err():
    # MAvatar_Topaz_Buff (removed by Numby's first attack): ModifySPNew AddValue
    b, (topaz,), _ = _battle([Build("Topaz", extra_stats={S.ERR: ERR})], techniques=True)
    assert topaz.energy == 0.0
    topaz.kit._numby_turn(topaz.kit.numby, b)
    assert topaz.energy == pytest.approx(topaz.kit.sk("technique")["params"][0][0] * (1 + ERR))
    topaz.kit._numby_turn(topaz.kit.numby, b)  # once only
    assert topaz.energy == pytest.approx(topaz.kit.sk("technique")["params"][0][0] * (1 + ERR))


# ------------------------------------------------------ Rule 2: tick timing
def test_sushang_e2_mitigation_expires_at_her_next_turn_start():
    # MAvatar_Sushang_00_Rank02_Buff: LifeTime=1, LifeStepMoment=ModifierPhase1End
    b, (su,), (e, _) = _battle([Build("Sushang", eidolon=2)])
    e.broken = True  # Sword Stance always triggers on a Weakness Broken enemy
    su.kit._sword_stance(e, 1.0)
    assert su.has_mod("Refine in Toil")
    assert _present_at_action_start(b, su, "Refine in Toil", 1) == [False]


@pytest.mark.parametrize(
    ("builds", "cast", "name", "turns"),
    [
        # MAvatar_March7th_00_BPSkill_Shield: LifeStepMoment default (turn end)
        (
            [Build("1001", options={"target": "Seele"}), Build("Seele")],
            lambda k, b: k.skill(b.enemies[0]),
            "The Power of Cuteness",
            lambda k: int(k.p("skill", 1) + k.tp(2, 0)),
        ),
        # MWAvatar_PlayerBoy_10_Shield: LifeStepMoment default (turn end)
        (
            [Build("8003"), Build("Seele")],
            lambda k, b: k.basic(b.enemies[0]),
            "Treasure of the Architects",
            lambda k: int(k.p("talent", 1)),
        ),
        # MAvatar_Luocha_00_Skill02_Shield (E2): LifeStepMoment default (turn end)
        (
            [Build("Luocha", eidolon=2), Build("Seele")],
            lambda k, b: k._skill_effect(b.character("Seele"), auto=False),
            "Bestowal",
            lambda k: int(k.ep(2, 3)),
        ),
    ],
)
def test_shields_count_down_at_the_holders_turn_end(builds, cast, name, turns):
    b, (caster, seele), _ = _battle(builds)
    cast(caster.kit, b)
    n = turns(caster.kit)
    assert seele.get_mod(name) is not None and seele.get_mod(name).duration == n
    # the Shield covers all of Seele's next n turns and expires at the end of the last one
    assert _present_at_action_start(b, seele, name, n) == [True] * n
    assert not seele.has_mod(name)


def test_march_7th_e2_shield_counts_down_at_turn_end():
    # MAvatar_March7th_00_Rank02_Shield: LifeStepMoment default (turn end)
    b, (march, seele), _ = _battle([Build("1001", eidolon=2), Build("Seele")])
    holder = next(c for c in (march, seele) if c.has_mod("Memory of It"))
    n = int(march.kit.ep(2, 1))
    other = seele if holder is march else march
    assert _present_at_action_start(b, holder, "Memory of It", n) == [True] * n
    assert not holder.has_mod("Memory of It")
    assert not other.has_mod("Memory of It")
