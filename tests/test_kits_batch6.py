"""Targeted checks for The Herta, Aglaea, Tribbie, Mydei, Anaxa, Cipher, Castorice and Trailblazer (Remembrance)."""

import pytest

from hsrsim import events as E
from hsrsim import stats as S
from hsrsim.battle import Battle
from hsrsim.build import Build, make_character
from hsrsim.entities import Enemy
from hsrsim.enums import ActionKind, EnemyRank

from .helpers import generic_build


def _battle(builds, enemies=None):
    chars = [make_character(b) for b in builds]
    enemies = enemies or [Enemy("Dummy", effect_res=0.0, hp=1e12)]
    battle = Battle(chars, [enemies])
    battle.start()
    return battle, chars


def _actions(battle):
    """Record every finished action."""
    acts = []
    battle.events.on(E.ACTION_END, lambda ev: acts.append(ev.action))
    return acts


def _lv(kit, sid):
    rec = kit.sk(sid)
    return rec["params"][kit.level_of(rec) - 1]


# ------------------------------------------------------------------ The Herta
def test_the_herta_interpretation_and_enhanced_skill_multiplier():
    boss = Enemy("Boss", hp=1e12, rank=EnemyRank.BOSS)
    b, (herta, _) = _battle([Build("The Herta", traces=False), generic_build("Bronya")], [boss])
    kit = herta.kit
    # 1 stack on entering combat + #6 stacks at wave start
    assert kit.stacks(boss) == 1 + int(kit.p("talent", 5))
    n = kit.stacks(boss)
    kit.inspiration = 1
    acts = _actions(b)
    kit.skill(boss)
    act = acts[-1]
    assert act.skill["id"] == "140109"
    first = act.hits[0]
    lv = _lv(kit, "140109")
    # one Erudition character: +#1% per stack on the primary target, added once
    assert first.mult["atk"] == pytest.approx(lv[0] + kit.p("talent", 0) * n)
    assert act.hits[1].mult["atk"] == pytest.approx(lv[0])
    assert kit.stacks(boss) == 1  # reset after the Enhanced Skill
    assert kit.inspiration == 0


# --------------------------------------------------------------------- Aglaea
def test_aglaea_garmentmaker_summon_and_spd_stacks():
    b, (ag, _) = _battle([Build("Aglaea"), generic_build("Bronya")])
    kit = ag.kit
    enemy = b.default_target()
    kit.skill(enemy)
    gm = kit.memosprite()
    assert gm is not None and gm.name == "Garmentmaker"
    tal = kit.sk("talent")
    lv = tal["params"][kit.level_of(tal) - 1]
    assert gm.spd == pytest.approx(lv[3] * ag.spd)
    assert gm.max_hp == pytest.approx(lv[4] * ag.max_hp + lv[5])
    spd0 = gm.spd
    kit.basic(enemy)  # Aglaea marks the target with Seam Stitch
    assert enemy.has_mod("Seam Stitch")
    n_add = sum(1 for r in b.records if "Seam Stitch" in r.label)
    assert n_add == 1  # Additional DMG after attacking the Seam Stitch target
    kit._gm_turn(gm, b)
    assert kit.gm_stacks == 1
    assert gm.spd == pytest.approx(spd0 + _lv(kit, "1140203")[0])
    # Supreme Stance: Aglaea gains the stacks as SPD% and A2 flat ATK
    spd_before, atk_before = ag.spd, ag.atk
    ag.energy = ag.max_energy
    kit.use_ult()
    assert kit.in_stance
    assert ag.spd == pytest.approx(spd_before + ag.raw(S.BASE_SPD) * kit.p("ult", 0) * kit.gm_stacks)
    assert ag.atk == pytest.approx(atk_before + kit.tp(1, 0) * ag.spd + kit.tp(1, 1) * gm.spd)


# --------------------------------------------------------------------- Tribbie
def test_tribbie_numinosity_zone_and_follow_up():
    enemies = [Enemy(f"E{i}", effect_res=0.0, hp=1e12) for i in range(3)]
    b, (tri, seele) = _battle([Build("Tribbie"), generic_build("Seele")], enemies)
    kit = tri.kit
    kit.skill(None)
    assert seele.stat(S.RES_PEN) == pytest.approx(kit.p("skill", 0))
    tri.energy = tri.max_energy
    kit.use_ult()
    assert enemies[0].stat(S.VULN) == pytest.approx(kit.p("ult", 1))
    before = sum(1 for r in b.records if r.label == "Tribbie Zone Additional DMG")
    seele.kit.basic(enemies[1])  # single-target attack: 1 target hit -> 1 instance
    after = sum(1 for r in b.records if r.label == "Tribbie Zone Additional DMG")
    assert after - before == 1
    # A4: Max HP + 9% of the team's Max HP while the Zone lasts
    assert tri.stat(S.HP_FLAT) >= kit.tp(2, 0) * seele.max_hp
    # Talent: follow-up after another character's Ultimate
    acts = _actions(b)
    seele.energy = seele.max_energy
    seele.kit.use_ult()
    b.process_queue()
    assert any(a.kind == ActionKind.FUA and a.actor is tri for a in acts)


# ----------------------------------------------------------------------- Mydei
def test_mydei_charge_and_vendetta():
    b, (my, _) = _battle([Build("Mydei"), generic_build("Bronya")])
    kit = my.kit
    hp0, def0 = my.max_hp, my.defense
    assert def0 > 0
    b.lose_hp(my, 0.4 * my.max_hp, my)  # 40% HP lost -> 40 Charge
    assert kit.charge == pytest.approx(40.0)
    assert kit.vendetta is None
    kit.add_charge(60.0)
    assert kit.vendetta is not None
    assert kit.charge == pytest.approx(0.0)
    assert my.max_hp == pytest.approx(hp0 * (1 + kit.p("talent", 4)))
    assert my.defense == pytest.approx(0.0, abs=1e-6)
    kit.add_charge(kit.godslayer_cost())
    assert kit.pending_godslayer
    acts = _actions(b)
    b.process_queue()  # the extra turn uses Godslayer Be God
    assert any(a.skill and a.skill["id"] == "140411" for a in acts)


# ----------------------------------------------------------------------- Anaxa
def test_anaxa_weakness_implant_and_additional_skill():
    enemy = Enemy("Dummy", effect_res=0.0, hp=1e12, weaknesses=())
    b, (anaxa, _) = _battle([Build("Anaxa"), generic_build("Bronya")], [enemy])
    kit = anaxa.kit
    assert kit.weakness_count(enemy) == 0
    acts = _actions(b)
    sp0 = b.sp
    kit.skill(enemy)  # 1 + 4 hits on the only enemy -> 5 different Weaknesses
    assert kit.weakness_count(enemy) == 1 + int(kit.p("skill", 1))
    assert kit.disclosed(enemy)
    b.process_queue()
    skills = [a for a in acts if a.kind == ActionKind.SKILL and a.actor is anaxa]
    assert len(skills) == 2  # Qualitative Disclosure: 1 additional Skill
    assert b.sp == sp0 - 1  # the additional Skill costs no SP


# ---------------------------------------------------------------------- Cipher
def test_cipher_tally_and_ultimate_true_damage():
    b, (cipher, seele) = _battle([Build("Cipher"), generic_build("Seele")])
    kit = cipher.kit
    enemy = b.default_target()
    assert kit.patron is enemy
    assert cipher.spd < 140  # no A2 tally bonus
    seele.kit.basic(enemy)
    b.process_queue()
    dmg = next(r.amount for r in b.records if r.attacker == seele.name)
    fua = sum(r.amount for r in b.records if r.label == "The Hospitable Dolosian")
    assert fua > 0  # follow-up after a teammate attacked the Patron
    assert kit.tally == pytest.approx(kit.p("talent", 1) * (dmg + fua))
    kit.tally = 100_000.0
    cipher.energy = cipher.max_energy
    kit.use_ult()
    true = sum(r.amount for r in b.records if "True DMG" in r.label)
    assert true == pytest.approx(100_000.0 * (kit.p("ult", 1) + kit.p("ult", 2)))
    assert kit.tally == 0.0


# ------------------------------------------------------------------- Castorice
def test_castorice_newbud_and_netherwing():
    b, (cas, bronya) = _battle([Build("Castorice"), generic_build("Bronya")])
    kit = cas.kit
    assert kit.max_newbud() == pytest.approx(34000.0)
    hp = bronya.hp
    b.lose_hp(bronya, 1000.0, None)
    assert kit.newbud == pytest.approx(min(1000.0, hp - 1.0))
    assert cas.get_mod("Desolation Across Palms") is not None
    assert not kit.ult_ready()
    kit.newbud = kit.max_newbud()
    assert kit.ult_ready()
    enemy = b.default_target()
    res0 = enemy.stat(S.RES_REDUCTION)
    kit.use_ult()
    nw = kit.memosprite()
    assert nw is not None and nw.name == "Netherwing"
    assert nw.max_hp == pytest.approx(34000.0)
    assert nw.spd == pytest.approx(kit.p("ult", 0))
    assert enemy.stat(S.RES_REDUCTION) - res0 == pytest.approx(kit.p("ult", 3))
    assert kit.newbud == 0.0
    # while Netherwing is out, the Skill becomes Boneclaw (Joint ATK) and HP loss heals Netherwing
    nw.hp = 0.5 * nw.max_hp
    acts = _actions(b)
    kit.skill(enemy)
    assert acts[-1].skill["id"] == "140709"
    assert nw.hp > 0.5 * nw.max_hp
    assert any(h.attacker is nw for h in acts[-1].hits)


# --------------------------------------------------------- Trailblazer (Remembrance)
def test_trailblazer_remembrance_mem_and_support():
    b, (tb, seele) = _battle([Build("8008"), generic_build("Seele")])
    kit = tb.kit
    e0 = tb.energy
    kit.skill(None)
    mem = kit.memosprite()
    assert mem is not None and mem.name == "Mem"
    assert mem.spd == pytest.approx(kit.p("talent", 0))
    assert mem.max_hp == pytest.approx(kit.p("talent", 1) * tb.max_hp + kit.p("talent", 3))
    # summoned: #1 of "Go, Mem, Go!" + A2 (first summon) Charge, then 1% per #3 Energy regenerated (Skill's)
    per_energy = int((tb.energy - e0) / kit.p("talent", 2)) * 0.01
    assert kit.charge == pytest.approx(_lv(kit, "1800705")[0] + kit.tp(1, 1) + per_energy)
    # team CRIT DMG aura: 12% of Mem's CRIT DMG + 24%
    cd = _lv(kit, "1800703")
    mod = next(m for m in mem.modifiers if m.name == "Friends! Together!")
    v = mod.value(S.CRIT_DMG, seele)
    assert v == pytest.approx(cd[0] * (mem.stat(S.CRIT_DMG) - v) + cd[1])  # Mem's CRIT DMG without the aura
    assert seele.stat(S.CRIT_DMG) == pytest.approx(seele.raw(S.CRIT_DMG))
    assert seele.stat(S.CRIT_DMG) - v == pytest.approx(seele.base[S.CRIT_DMG])
    # Lemme! Help You! at 100% Charge: Mem's Support True DMG on every hit of the holder
    kit.charge = 1.0
    kit._mem_turn(mem, b)
    assert seele.has_mod("Mem's Support") and kit.charge < 0.05  # reset (then +1% per 10 Energy)
    seele.kit.basic(b.default_target())
    hit = next(r for r in b.records if r.attacker == seele.name and "True" not in r.label)
    true = next(r for r in b.records if r.label == "Mem's Support (True DMG)")
    assert true.amount == pytest.approx(hit.amount * kit.support_ratio(seele))
