"""Targeted checks for batch 8: Pearl, Ashveil, Evanescia, Silver Wolf LV.999, Mortenax Blade, Rin Tohsaka,
Gilgamesh, Himeko • Nova, Aventurine • Waveflair, Trailblazer (Elation), Saber and Archer."""

import pytest

from hsrsim import events as E
from hsrsim import stats as S
from hsrsim.battle import Battle
from hsrsim.build import Build, make_character
from hsrsim.entities import Enemy
from hsrsim.enums import ActionKind, DmgTag

from .helpers import generic_build


def _battle(builds, enemies=None):
    chars = [make_character(b) for b in builds]
    enemies = enemies or [Enemy("Dummy", effect_res=0.0, hp=1e12)]
    battle = Battle(chars, [enemies])
    battle.start()
    return battle, chars


def _actions(battle):
    acts = []
    battle.events.on(E.ACTION_END, lambda ev: acts.append(ev.action))
    return acts


def _lv(kit, sid):
    rec = kit.sk(sid)
    return rec["params"][kit.level_of(rec) - 1]


def _dummies(n):
    return [Enemy(f"Dummy {i}", effect_res=0.0, hp=1e12) for i in range(n)]


# ---------------------------------------------------------------- Rin Tohsaka
def test_rin_skill_point_use_grants_gem_energy_and_crit_dmg():
    b, (rin, mate) = _battle([Build("Rin Tohsaka"), generic_build("Bronya")])
    kit = rin.kit
    assert b.max_sp == 5 + int(kit.tp(1, 0))  # A2: Skill Point cap +2
    assert kit.gem == int(kit.p("talent", 0))  # Gem Energy on entering combat
    assert rin.stat(S.ATK_PCT) >= kit.tp(1, 1)  # A2 ATK boost on entering combat
    kit.gem = 0
    b.sp = 3
    enemy = b.default_target()
    acts = _actions(b)
    kit.skill(enemy)
    act = acts[-1]
    assert act.skill["id"] == "150802" and b.sp == 2
    assert act.hits[0].mult["atk"] == pytest.approx(kit.p("skill", 0))
    assert kit.gem == 1
    mod = rin.get_mod("Gem Magecraft")
    assert mod is not None and mod.stats[S.CRIT_DMG] == pytest.approx(kit.p("talent", 2))
    # an ally recovering a Skill Point gets the CRIT DMG buff too
    b.gain_sp(1, mate)
    assert mate.has_mod("Gem Magecraft") and kit.gem == 2


def test_rin_enhanced_skill_drains_skill_points_into_gem_bounces():
    b, (rin, _) = _battle([Build("Rin Tohsaka"), generic_build("Bronya")])
    kit = rin.kit
    kit.gem = 0
    b.sp = int(kit.p("talent", 3))  # 7 Skill Points: the Skill is enhanced
    assert kit.enhanced_ready()
    lv = _lv(kit, "150809")
    acts = _actions(b)
    kit.skill(b.default_target())
    act = acts[-1]
    assert act.skill["id"] == "150809"
    drained = int(kit.p("talent", 3)) - int(lv[3])
    assert b.sp == int(lv[3])
    gem = drained * (1 + int(lv[4]))  # Talent (+1 per SP) and the Enhanced Skill (+2 per SP)
    bounces = [h for h in act.hits if not h.primary]
    assert len(bounces) == gem // int(lv[1])
    assert kit.gem == gem % int(lv[1])
    assert all(h.mult["atk"] == pytest.approx(lv[2]) for h in bounces)
    assert rin.has_mod("Ladylike Poise")  # A4 after the Enhanced Skill


def test_rin_joint_follow_up_with_archer_once_per_rin_turn():
    b, (rin, archer, _) = _battle([Build("Rin Tohsaka"), Build("Archer"), generic_build("Bronya")])
    assert b.max_sp == 9  # both A2 traces
    kit, akit = rin.kit, archer.kit
    lv = _lv(kit, "150805")
    assert archer.stat(S.ATK_PCT) >= kit.tp(1, 1)  # A2 is shared with Archer
    b.sp = 4
    akit.cc_count = 1
    kit.archer_skill_used(akit)  # SP above the threshold: no joint attack
    assert kit.joints == 0
    b.sp = int(lv[2])
    records = len(b.records)
    kit.archer_skill_used(akit)
    assert kit.joints == 1
    assert b.sp == int(lv[2]) + int(lv[1])
    labels = {r.owner for r in b.records[records:]}
    assert labels == {"Rin Tohsaka", "Archer"}
    b.sp = 0
    kit.archer_skill_used(akit)
    assert kit.joints == 1  # only once until Rin's turn ends
    b.events.emit(E.TURN_END, entity=rin, extra=False)
    kit.archer_skill_used(akit)
    assert kit.joints == 2


def test_rin_archer_team_runs_joint_follow_ups():
    from hsrsim.scenarios import boss_dps

    rep = boss_dps(cycles=5).run([Build("Rin Tohsaka"), Build("Archer"), Build("Bronya"), Build("Huohuo")])
    assert rep.battle.team[0].kit.joints >= 1


# ------------------------------------------------------------------ Gilgamesh
def test_gilgamesh_interest_spd_and_interest_piqued_skill():
    b, (gil, mate) = _battle([Build("Gilgamesh"), generic_build("Bronya")])
    kit = gil.kit
    spd0 = gil.spd
    b.events.emit(E.TURN_START, entity=mate, extra=False)
    assert kit.interest == 1
    assert gil.spd == pytest.approx(spd0 + kit.p("talent", 3) * gil.raw(S.BASE_SPD))
    assert gil.stat(S.CRIT_DMG) >= kit.tp(2, 0)  # A4: CRIT DMG per Interest gained
    acts = _actions(b)
    kit.take_turn()
    assert acts[-1].kind == ActionKind.BASIC  # auto Basic ATK before "Interest Piqued!"
    kit.gain_interest(int(kit.p("talent", 1)))
    assert kit.piqued
    kit.take_turn()
    act = acts[-1]
    assert act.kind == ActionKind.SKILL and act.sp == 0
    assert kit.interest == 0  # cleared after the Skill
    ka = gil.get_mod("King's Acknowledgement")
    assert ka is not None and ka.stats[S.DEF_IGNORE] == pytest.approx(kit.p("skill", 4))
    assert act.hits[0].mult["atk"] == pytest.approx(kit.p("skill", 0) * 0.1)  # splits from the data


def test_gilgamesh_joint_follow_up_with_saber_and_a6():
    b, (gil, saber, mate) = _battle([Build("Gilgamesh"), Build("Saber"), generic_build("Bronya")])
    kit = gil.kit
    lv = _lv(kit, "150905")
    # A6: +20% ATK for everyone, + up to 100% more for Max Energy above 140 (Saber: 360)
    a6 = next(m for m in b.fields if m.name == "Hegemon's Strife")
    assert a6.value(S.ATK_PCT, gil) == pytest.approx(kit.tp(3, 0) + kit.tp(3, 4))  # 360 Max Energy: capped
    assert a6.value(S.CRIT_DMG, saber) == pytest.approx(kit.tp(3, 1) + kit.tp(3, 4))
    excess = max(0.0, mate.max_energy - kit.tp(3, 2))
    assert a6.value(S.ATK_PCT, mate) == pytest.approx(kit.tp(3, 0) + min(kit.tp(3, 4), excess * kit.tp(3, 3)))
    enemy = b.default_target()
    saber.energy = 0.0
    kit.tally = int(lv[4]) - 1
    saber.kit.basic(enemy)  # Saber's attack completes the tally
    b.process_queue()
    assert kit.joints == 1 and kit.tally == 0
    assert saber.energy >= lv[3]
    buff = saber.get_mod("I Grant You Permission To Strike (Saber Ultimate)")
    assert buff is not None and buff.stats[f"{S.FINAL_DMG}:{DmgTag.ULT}"] == pytest.approx(lv[5] - 1.0)
    saber.kit.ult(enemy)
    assert not saber.has_mod("I Grant You Permission To Strike (Saber Ultimate)")


def test_gilgamesh_kings_burden_and_a2_on_teammate_ult():
    b, (gil, saber, _) = _battle([Build("Gilgamesh"), Build("Saber"), generic_build("Bronya")])
    kit = gil.kit
    gil.energy = 0.0
    before = kit.interest
    saber.energy = saber.max_energy
    saber.kit.use_ult()
    assert gil.has_mod("King's Burden")
    assert kit.interest == before + int(kit.tp(1, 0))
    assert gil.energy == pytest.approx(saber.max_energy * kit.tp(1, 1))


# ---------------------------------------------------------------------- Saber
def test_saber_ult_core_resonance_release_and_bounce_toughness():
    b, (saber, _) = _battle([Build("Saber"), generic_build("Bronya")])
    kit = saber.kit
    cr = kit.cr
    acts = _actions(b)
    saber.energy = saber.max_energy
    kit.use_ult()
    act = acts[-1]
    assert kit.cr == cr + int(kit.p("talent", 0))  # any ally's Ultimate grants Core Resonance
    assert saber.has_mod("Dragon Reactor Core")
    assert kit.release_next
    assert len(act.hits) == 1 + int(kit.p("ult", 2))  # AoE on the single enemy + the bounces
    # approximation checked: 40 AoE + the data's 20 Toughness spread over all bounces
    total = sum(h.toughness for h in act.hits)
    assert total == pytest.approx(kit.toughness("ult", 1) + kit.toughness("ult", 0))
    kit.take_turn()
    assert acts[-1].skill["id"] == "101408" and not kit.release_next


# ---------------------------------------------------------------------- Archer
def test_archer_circuit_connection_chain_stacks_skill_dmg():
    b, (archer, _) = _battle([Build("Archer"), generic_build("Bronya")])
    kit = archer.kit
    b.sp = 5
    acts = _actions(b)
    kit.chain()
    skills = [a for a in acts if a.kind == ActionKind.SKILL]
    assert len(skills) == 2 and b.sp == 1  # 2 SP each
    assert skills[0].hits[0].extra.get(S.DMG_PCT, 0.0) == 0.0
    assert skills[1].hits[0].extra[S.DMG_PCT] == pytest.approx(kit.p("skill", 1))


def test_archer_follow_up_after_teammate_attack_recovers_sp():
    b, (archer, mate) = _battle([Build("Archer"), generic_build("Bronya")])
    kit = archer.kit
    charge = kit.charge
    assert charge == int(kit.tp(2, 0))  # A4: Charge on entering combat
    sp = b.sp
    acts = _actions(b)
    mate.kit.basic(b.default_target())
    b.process_queue()
    fua = [a for a in acts if a.kind == ActionKind.FUA]
    assert len(fua) == 1 and kit.charge == charge - 1
    assert b.sp == min(b.max_sp, sp + 2)  # teammate Basic ATK + follow-up


# ---------------------------------------------------------------------- Pearl
def test_pearl_certified_banger_is_permanent_and_capped():
    b, (pearl, _) = _battle([Build("Pearl"), generic_build("Bronya")])
    kit = pearl.kit
    b.sp = 3
    kit.skill(None)
    mods = [m for m in pearl.modifiers if m.name == "Certified Banger" and not m.removed]
    assert mods and all(m.duration is None for m in mods)
    assert kit.banger_points() >= kit.p("skill", 0)
    for _ in range(6):
        kit.gain_banger(kit.p("skill", 0))
    assert kit.banger_points() == pytest.approx(kit.p("talent", 2))


# --------------------------------------------------------------------- Ashveil
def test_ashveil_bait_def_shred_and_repeat_skill_refund():
    enemies = _dummies(2)
    b, (ash, _) = _battle([Build("Ashveil"), generic_build("Bronya")], enemies)
    kit = ash.kit
    assert kit.bait is not None  # the lowest-HP enemy becomes the Bait when there is none
    e1 = next(e for e in enemies if e is not kit.bait)
    b.sp = 3
    kit.skill(e1)
    assert kit.bait is e1
    assert all(e.has_mod("Bait") == (e is e1) for e in enemies)  # only the latest Bait counts
    assert enemies[0].stat(S.DEF_REDUCTION) == pytest.approx(kit.p("skill", 3))
    assert b.sp == 2
    acts = _actions(b)
    kit.skill(e1)  # already the Bait: extra hit and 1 Skill Point back
    act = acts[-1]
    assert len(act.hits) == 2 and act.hits[1].mult["atk"] == pytest.approx(kit.p("skill", 2))
    assert b.sp == 2 - 1 + int(kit.p("skill", 4))


def test_ashveil_follow_up_when_teammate_hits_the_bait():
    b, (ash, mate) = _battle([Build("Ashveil"), generic_build("Bronya")])
    kit = ash.kit
    charge = kit.charge
    acts = _actions(b)
    mate.kit.basic(kit.bait)
    b.process_queue()
    assert [a.kind for a in acts].count(ActionKind.FUA) == 1
    assert kit.charge == charge - 1 and kit.gluttony >= int(kit.p("talent", 4))


# ------------------------------------------------------------------- Evanescia
def test_evanescia_energy_banger_coupling_and_master_fox():
    b, (eva, _) = _battle([Build("Evanescia"), generic_build("Bronya")])
    kit = eva.kit
    eva.energy = 0.0
    b.gain_energy(eva, 50, fixed=True)
    assert kit.banger() == 50  # Energy gained -> equal Certified Banger
    acts = _actions(b)
    kit.accum = kit.p("talent", 2) - 10
    b.gain_energy(eva, 20, fixed=True)
    b.process_queue()
    fox = [a for a in acts if a.label == "Master Fox"]
    assert len(fox) == 1 and fox[0].kind == ActionKind.FUA
    # the 10 leftover + the Energy Master Fox regenerates
    assert kit.accum == pytest.approx(10 + kit.p("talent", 3) * (1 + eva.stat(S.ERR)))
    assert any(DmgTag.ELATION in h.tags for h in fox[0].hits)


# --------------------------------------------------------- Silver Wolf LV.999
def test_silver_wolf_lv999_hidden_mmr_and_godmode():
    b, (sw, _) = _battle([Build("Silver Wolf LV.999"), generic_build("Bronya")])
    kit = sw.kit
    cr0 = sw.stat(S.CRIT_RATE)
    kit.gain_punchline(10)
    assert kit.mmr == 10
    assert sw.stat(S.CRIT_RATE) == pytest.approx(cr0 + 10 * kit.p("talent", 3))
    assert not kit.ult_ready()
    kit.gain_mmr(kit.p("talent", 0))
    assert kit.ult_ready()
    kit.use_ult()
    assert kit.god and kit.basics_left == int(kit.p("talent", 4))
    assert not kit.ult_ready()  # cannot use the Ultimate in Godmode


# -------------------------------------------------------------- Mortenax Blade
def test_mortenax_blade_infinite_fury_zone_and_free_skill():
    b, (blade, _) = _battle([Build("Mortenax Blade"), generic_build("Bronya")])
    kit = blade.kit
    enemy = b.default_target()
    blade.energy = blade.max_energy
    kit.use_ult()
    assert kit.in_fury and kit.countdown is not None
    assert kit.countdown.spd == pytest.approx(kit.p("ult", 4))
    bind = enemy.get_mod("Balefire Bind")
    assert bind is not None and bind.stats[S.VULN] == pytest.approx(kit.p("ult", 3))
    sp = b.sp
    blade.hp = 10.0
    acts = _actions(b)
    kit.skill(enemy)
    assert acts[0].kind == ActionKind.SKILL and b.sp == sp  # no Skill Point cost
    assert blade.hp == pytest.approx(1.0)  # HP consumption stops at 1
    kit.take_turn()
    assert acts[-1].skill["id"] == "150708"  # HP 1: Enhanced Basic ATK


# ---------------------------------------------------------------- Himeko • Nova
def test_himeko_nova_semaphore_and_assist_skill():
    b, (hn, mate) = _battle([Build("Himeko • Nova"), generic_build("Bronya")])
    kit = hn.kit
    b.sp = 3
    kit.skill(None)
    assert mate.stat(S.DMG_PCT) >= kit.p("skill", 0)
    acts = _actions(b)
    kit.assist(hn, b.default_target())
    act = acts[-1]
    lv = _lv(kit, "151022")
    assert act.kind == ActionKind.SKILL and act.sp == 0
    assert act.hits[0].mult["atk"] == pytest.approx(lv[3])  # Himeko • Nova's own multiplier
    assert "assist" in act.hits[0].tags


# ------------------------------------------------------- Aventurine • Waveflair
def test_waveflair_fervor_from_teammate_attacks_and_cheers():
    b, (av, mate) = _battle([Build("Aventurine • Waveflair"), generic_build("Bronya")])
    kit = av.kit
    p0 = b.elation.punchline
    mate.kit.basic(b.default_target())
    assert kit.fervor == int(kit.p("talent", 6)) + int(kit.tp(3, 3))  # A6 first trigger adds Fervor
    assert b.elation.punchline >= p0 + int(kit.p("talent", 5))
    acts = _actions(b)
    kit.add_fervor(int(kit.p("talent", 0)))
    b.process_queue()
    cheers = [a for a in acts if a.kind == ActionKind.ELATION]
    assert cheers and cheers[0].skill["id"] == "151320"
    assert kit.all_in_next


# ------------------------------------------------------ Trailblazer (Elation)
@pytest.mark.parametrize("cid", ["8009", "8010"])
def test_trailblazer_elation_ult_triggers_ally_elation_skill(cid):
    b, (tb, sparxie) = _battle([Build(cid), Build("Sparxie")])
    kit = tb.kit
    assert kit.elation_skill_id == f"{cid}20"
    seen = []
    orig = sparxie.kit.elation_skill
    sparxie.kit.elation_skill = lambda p: (seen.append(p), orig(p))
    tb.energy = tb.max_energy
    kit.use_ult()
    b.process_queue()
    assert seen == [kit.p("ult", 4)]
    assert b.elation.certified_banger(sparxie) >= kit.p("ult", 3)
    assert sparxie.has_mod("Fly You Starward")
