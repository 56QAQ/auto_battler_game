"""Targeted checks for batch-4 kits: Gallagher, Argenti, Aventurine, Dr. Ratio, Sunday, Jade, Boothill, Rappa,
Trailblazer (Destruction) and Trailblazer (Preservation)."""

import pytest

from hsrsim import events as E
from hsrsim import formulas as F
from hsrsim import stats as S
from hsrsim.battle import Battle, BattleConfig
from hsrsim.build import Build, make_character
from hsrsim.entities import Enemy
from hsrsim.enums import Element
from hsrsim.modifiers import Modifier, ModKind
from hsrsim.scenarios import aoe_dps, boss_dps


def _battle(builds, enemies=None, **cfg):
    chars = [make_character(b) for b in builds]
    enemies = enemies or [Enemy("Dummy", hp=1e12, effect_res=0.0)]
    battle = Battle(chars, [enemies], BattleConfig(**cfg))
    battle.start()
    return battle, chars


def _enemies(n, **kw):
    kw.setdefault("hp", 1e12)
    kw.setdefault("effect_res", 0.0)
    return [Enemy(f"Enemy {i + 1}", **kw) for i in range(n)]


def _labels(battle, label):
    return [r for r in battle.records if r.label == label]


def _lv(kit, sid):
    rec = kit.sk(sid)
    return rec["params"][kit.level_of(rec) - 1]


# ------------------------------------------------------------------ Gallagher
def test_gallagher_besotted_heals_attackers_and_nectar_blitz():
    b, (gal, seele) = _battle([Build("Gallagher"), Build("Seele")])
    k = gal.kit
    enemy = b.default_target()
    gal.energy = gal.max_energy
    k.use_ult()
    bes = enemy.get_mod("Besotted")
    assert bes is not None and bes.duration == int(k.p("ult", 1))
    assert enemy.stat("vuln:break") == pytest.approx(k.p("talent", 0))
    assert gal.gauge == pytest.approx(0.0)  # A4: 100% action advance after the Ultimate
    heals = []
    b.events.on(E.HEALED, heals.append)
    seele.kit.basic(enemy)
    per_heal = k.p("talent", 1) * (1 + gal.stat(S.HEAL_PCT))
    assert [(h.entity, h.amount) for h in heals] == [(seele, pytest.approx(per_heal))]
    heals.clear()
    k.basic(enemy)  # the Ultimate enhanced this Basic ATK into Nectar Blitz
    lv = _lv(k, "130108")
    assert _labels(b, "Nectar Blitz")
    assert enemy.get_mod("Nectar Blitz ATK Reduction").stats[S.ATK_PCT] == pytest.approx(-lv[1])
    assert {h.entity for h in heals} == {gal, seele}  # A6: the Talent heal also applies to teammates
    k.basic(enemy)
    assert b.records[-1].label == "Corkage Fee"


# -------------------------------------------------------------------- Argenti
def test_argenti_apotheosis_energy_and_enhanced_ultimate():
    b, (arg,) = _battle([Build("Argenti")], _enemies(3))
    k = arg.kit
    err = 1 + arg.stat(S.ERR)
    # A4: 2 Energy for each of the 3 enemies entering combat
    assert arg.energy == pytest.approx(arg.max_energy * b.cfg.start_energy + 3 * k.tp(2, 0) * err)
    e0, cr0 = arg.energy, arg.stat(S.CRIT_RATE)
    k.skill(b.default_target())
    assert arg.get_mod("Apotheosis").stacks == 3
    assert arg.stat(S.CRIT_RATE) - cr0 == pytest.approx(3 * k.p("talent", 1))
    assert arg.energy - e0 == pytest.approx((k.sk("skill")["energy"] + 3 * k.p("talent", 0)) * err)
    arg.energy = arg.max_energy
    k.use_ult()
    lv = _lv(k, "130214")
    assert arg.data_flags["ult_energy_spent"] == pytest.approx(lv[3])
    hits = _labels(b, k.sk("130214")["name"])
    assert len(hits) == 3 + int(lv[1])  # AoE on 3 enemies + 6 bounces


# ----------------------------------------------------------------- Aventurine
def test_aventurine_wager_stacking_and_blind_bet_follow_up():
    b, (av, seele) = _battle([Build("Aventurine", options={"ult": False}), Build("Seele")])
    k = av.kit
    base = k.skill_shield()
    fw = seele.get_mod("Fortified Wager")  # A4: every ally starts with a Fortified Wager
    assert fw is not None and fw.data["value"] == pytest.approx(k.tp(2, 1) * base)
    assert seele.stat(S.EFFECT_RES) == pytest.approx(
        make_character(Build("Seele")).stat(S.EFFECT_RES) + k.p("talent", 3)
    )
    k.skill(None)
    k.skill(None)
    assert seele.get_mod("Fortified Wager").data["value"] == pytest.approx(k.p("skill", 3) * base)  # capped at 200%
    k.bet = 5
    enemy = b.default_target()
    b.events.emit(E.ALLY_ATTACKED, attacker=enemy, targets=[av], action=None)  # +1 (Wager) +1 (himself)
    b.process_queue()
    fua = _labels(b, "Shot Loaded Right")
    assert len(fua) == int(k.p("talent", 1)) and k.bet == 0
    # A6: after the follow-up every ally's Wager grew (it was capped, so it stays at the cap)
    assert seele.get_mod("Fortified Wager").data["value"] == pytest.approx(k.p("skill", 3) * base)


# ------------------------------------------------------------------ Dr. Ratio
def test_dr_ratio_summation_guaranteed_follow_up_and_wisemans_folly():
    b, (ratio, pela) = _battle([Build("Dr. Ratio"), Build("Pela")])
    k = ratio.kit
    enemy = b.default_target()
    for i in range(3):
        b.apply(Modifier(f"Test Debuff {i}", kind=ModKind.DEBUFF, duration=9), enemy, pela)
    k.skill(enemy)
    assert ratio.get_mod("Summation").stacks == 3
    # A4 added a 4th debuff: 40% + 4 x 20% >= 100% -> the follow-up always triggers
    assert enemy.has_mod("Inference")
    b.process_queue()
    fua = _labels(b, "Cogito, Ergo Sum")
    assert len(fua) == 1
    b.sp = 5
    ratio.energy = ratio.max_energy
    k.use_ult()
    for _ in range(3):
        pela.kit.basic(enemy)
        b.process_queue()
    assert len(_labels(b, "Cogito, Ergo Sum")) == 1 + int(k.p("ult", 1))  # Wiseman's Folly triggers twice


# --------------------------------------------------------------------- Sunday
def test_sunday_skill_advances_and_buffs_and_beatified():
    b, (sunday, seele) = _battle([Build("Sunday"), Build("Seele")])
    k = sunday.kit
    seele.gauge = 5000.0
    k.skill(b.default_target())
    assert seele.gauge == pytest.approx(0.0)  # immediate action
    assert seele.get_mod("Benison of Paper and Rites").stats[S.DMG_PCT] == pytest.approx(k.p("skill", 1))
    assert seele.get_mod("The Sorrowing Body").stats[S.CRIT_RATE] == pytest.approx(k.p("talent", 0))
    sunday.energy = sunday.max_energy
    e0 = seele.energy
    k.use_ult()
    beat = seele.get_mod("The Beatified")
    assert beat.stats[S.CRIT_DMG] == pytest.approx(k.p("ult", 1) * sunday.stat(S.CRIT_DMG) + k.p("ult", 3))
    gain = max(k.p("ult", 0) * seele.max_energy, k.tp(1, 0))  # A2: at least 40 Energy
    assert seele.energy == pytest.approx(min(seele.max_energy, e0 + gain))
    sp0 = b.sp
    k.skill(b.default_target())
    assert b.sp == sp0  # Skill on The Beatified refunds its SP


# ----------------------------------------------------------------------- Jade
def test_jade_debt_collector_additional_dmg_and_follow_up():
    enemies = _enemies(2)
    b, (jade, seele) = _battle([Build("Jade"), Build("Seele")], enemies)
    k = jade.kit
    spd0 = seele.spd
    k.skill(None)
    assert seele.spd == pytest.approx(spd0 + k.p("skill", 0))
    assert not k.can_skill()  # no Skill while a Debt Collector exists
    hp0 = seele.hp
    seele.kit.basic(enemies[0])
    assert len(_labels(b, "Debt Collector (Jade)")) == 1
    assert seele.hp == pytest.approx(hp0 - k.p("skill", 1) * seele.max_hp)
    assert k.charge == 1
    k.charge = 7
    pawned0 = k.pawned  # A2: 1 stack per enemy entering combat
    assert pawned0 == 2 * int(k.tp(1, 1))
    k.basic(enemies[0])  # blast on both enemies: +2 Charge -> follow-up
    b.process_queue()
    assert len(_labels(b, "Fang of Flare Flaying")) == 2
    assert k.charge == 1 and k.pawned == pawned0 + int(k.p("talent", 3))
    atk_pct0 = make_character(Build("Jade")).stat(S.ATK_PCT)
    assert jade.stat(S.ATK_PCT) - atk_pct0 == pytest.approx(k.pawned * k.tp(3, 0))  # A6


# ------------------------------------------------------------------- Boothill
def test_boothill_standoff_enhanced_basic_and_talent_break():
    enemy = Enemy("Dummy", hp=1e12, effect_res=0.0, toughness=30.0, weaknesses=[Element.PHYSICAL])
    b, (bh,) = _battle([Build("Boothill")], [enemy])
    k = bh.kit
    k.trickshot = 2
    sp0, e0 = b.sp, bh.energy
    k.skill(enemy)  # Standoff, then the turn continues with the Enhanced Basic ATK
    assert b.sp == sp0 - 1  # the Enhanced Basic ATK recovers no SP
    assert _labels(b, "Fanning the Hammer") and enemy.broken
    talent = _labels(b, "Five Peas in a Pod")
    assert len(talent) == 1
    cap = k.p("talent", 5) * k.toughness("basic")
    expected = (
        F.break_base_damage(Element.PHYSICAL, b.data.break_base(80), min(enemy.max_toughness, cap))
        * k.p("talent", 1)  # 2 Pocket Trickshot stacks -> 120%
        * (1 + bh.stat(S.BREAK_EFFECT))
        * F.def_multiplier(80, enemy.raw(S.BASE_DEF))
        * (1 + k.p("skill", 0))  # Standoff: +30% DMG taken from Boothill
    )
    assert talent[0].amount == pytest.approx(expected)
    # breaking the Standoff target: +1 Pocket Trickshot, A6 Energy, Standoff dispelled
    assert k.trickshot == 3 and not k.in_standoff and not enemy.has_mod("Standoff (target)")
    rec = k.sk("131508")
    assert bh.energy - e0 == pytest.approx((rec["energy"] + k.tp(3, 0)) * (1 + bh.stat(S.ERR)))


def test_boothill_standoff_lasts_two_turns():
    rep = boss_dps(cycles=3).run([Build("Boothill")])
    b = rep.battle
    skills = [r for r in b.records if r.label == "Fanning the Hammer"]
    assert len(skills) == b.turn_counts["Boothill"]  # Skill+EBA, EBA, Skill+EBA, ... every turn enhanced


# ---------------------------------------------------------------------- Rappa
def test_rappa_sealform_petalblade_toughness_and_charge_break():
    enemies = _enemies(3, toughness=100.0, weaknesses=[Element.PHYSICAL])  # no Imaginary Weakness
    b, (rappa,) = _battle([Build("Rappa")], enemies)
    k = rappa.kit
    rappa.energy = rappa.max_energy
    k.use_ult()
    assert rappa.stat(S.BREAK_EFF) == pytest.approx(k.p("ult", 0))
    assert k.ink == int(k.p("ult", 2)) and not k.can_skill()
    assert b.queue  # extra turn
    b.queue.clear()
    k.charge = 4
    target = enemies[0]
    k.basic(target)
    lv = _lv(k, "131718")
    eff = 1 + rappa.stat(S.BREAK_EFF)
    t1, t3 = k.sk("131708")["toughness"], k.sk("131712")["toughness"]
    talent_tough = (k.p("talent", 3) + k.p("talent", 5) * 4) * eff
    main = (2 * t1[0] + t3[1]) * lv[3] * eff + talent_tough
    adj = (2 * t1[2] + t3[1]) * lv[3] * eff + talent_tough
    far = t3[1] * lv[3] * eff + talent_tough
    assert [e.toughness for e in enemies] == pytest.approx([100 - main, 100 - adj, 100 - far])
    brk = _labels(b, "Ninja Tech: Endurance Gauge")
    assert len(brk) == 3 and k.charge == 0 and k.ink == int(k.p("ult", 2)) - 1
    expected = (
        F.break_base_damage(Element.IMAGINARY, b.data.break_base(80), 100.0)
        * (k.p("talent", 2) + k.p("talent", 4) * 4)
        * (1 + rappa.stat(S.BREAK_EFFECT))
        * F.def_multiplier(80, target.raw(S.BASE_DEF))
        * F.res_multiplier(0.2)
        * F.NOT_BROKEN_MULT
    )
    assert brk[0].amount == pytest.approx(expected)
    k.basic(target)
    k.basic(target)
    assert not k.in_seal and rappa.stat(S.BREAK_EFF) == pytest.approx(0.0)


# ------------------------------------------------------- Trailblazer (Destruction)
def test_trailblazer_destruction_fighting_will_and_perfect_pickoff():
    enemies = _enemies(3, toughness=1e6)
    b, (tb,) = _battle([Build("8001")], enemies)
    k = tb.kit
    k.skill(enemies[1])
    main, left, right = (r.amount for r in b.records[:3])
    assert main / left == pytest.approx(1 + k.tp(3, 0))  # A6 only on the designated target
    assert left == pytest.approx(right)
    tb.energy = tb.max_energy
    k.use_ult()
    assert b.records[-1].label == "Blowout: RIP Home Run"  # "auto" picks the blast mode with adjacent enemies
    b2, (tb2,) = _battle([Build("8002")], [Enemy("Dummy", hp=1e12, toughness=10.0, weaknesses=[Element.PHYSICAL])])
    atk0 = tb2.atk
    tb2.kit.basic(b2.default_target())  # breaks the enemy
    assert tb2.atk == pytest.approx(atk0 + tb2.raw(S.BASE_ATK) * tb2.kit.p("talent", 0))
    tb2.energy = tb2.max_energy
    tb2.kit.use_ult()
    assert b2.records[-1].label == "Blowout: Farewell Hit"


# ---------------------------------------------------- Trailblazer (Preservation)
def test_trailblazer_preservation_magma_will_and_shields():
    enemies = _enemies(3)
    b, (tb, seele) = _battle([Build("8003"), Build("Seele")], enemies)
    k = tb.kit
    k.basic(enemies[1])
    assert k.magma == 1
    shield = seele.get_mod("Treasure of the Architects")
    assert shield is not None
    assert shield.data["value"] == pytest.approx(k.p("talent", 0) * tb.defense + k.p("talent", 3))
    k.magma = 4
    n0 = len(b.records)
    k.basic(enemies[1])  # enhanced: blast, consumes 4 Magma Will
    assert len(b.records) - n0 == 3 and k.magma == 0
    b.events.emit(E.ALLY_ATTACKED, attacker=enemies[0], targets=[tb], action=None)
    assert k.magma == 1
    tb.energy = tb.max_energy
    k.use_ult()
    n0 = len(b.records)
    k.basic(enemies[1])  # the Ultimate enhances the next Basic ATK without consuming Magma Will
    assert len(b.records) - n0 == 3 and k.magma == 1


def test_batch4_kits_run_in_aoe_with_techniques():
    for cid in ("1301", "1302", "1304", "1305", "1313", "1314", "1315", "1317", "8001", "8003"):
        rep = aoe_dps(cycles=2, count=3).run([Build(cid, eidolon=6), Build("Seele")], techniques=True)
        assert rep.total > 0
