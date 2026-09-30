"""Targeted checks of distinctive mechanics for the batch-3 kits (real kits, no gear):
Blade, Fu Xuan, Guinaifen, Bailu, Jingliu, Dan Heng • Imbibitor Lunae, Xueyi, Hanya, Misha."""

import pytest

from hsrsim import events as E
from hsrsim import stats as S
from hsrsim.battle import Battle, BattleConfig
from hsrsim.build import Build, make_character
from hsrsim.entities import Enemy
from hsrsim.enums import Element
from hsrsim.kits.blade import FOREST_ID, FUA_SPLITS
from hsrsim.kits.imbibitor_lunae import FULGURANT_SPLITS
from hsrsim.kits.jingliu import MOON_SPLITS


def _battle(builds, n_enemies=1, toughness=1e6, **cfg):
    chars = [make_character(b) for b in builds]
    enemies = [
        Enemy(f"Dummy {i}", hp=1e12, toughness=toughness, effect_res=0.0, weaknesses=list(Element))
        for i in range(n_enemies)
    ]
    b = Battle(chars, [enemies], BattleConfig(**cfg))
    b.start()
    return b, chars, enemies


def _hits(b):
    out = []
    b.events.on(E.AFTER_HIT, lambda ev: out.append(ev.hit))
    return out


# ------------------------------------------------------------------- Blade
def test_blade_hellscape_hp_tally_ult_and_charge_fua():
    b, (blade, _), (e,) = _battle([Build("Blade"), Build("Bronya")])
    k = blade.kit
    mh, atk, sp0 = blade.max_hp, blade.atk, b.sp
    hits = _hits(b)
    k.skill(e)  # Hellscape (30% HP) + Forest of Swords in the same turn (10% HP)
    assert b.sp == sp0 - 1  # Forest of Swords recovers no SP
    hell = blade.get_mod("Hellscape")
    assert hell is not None and hell.value(S.DMG_PCT) == pytest.approx(k.p("skill", 3))
    assert blade.hp == pytest.approx(mh * (1 - k.p("skill", 0) - 0.1))
    assert k.charge == 2 and k.tally == pytest.approx(0.4 * mh)
    rec = k.sk(FOREST_ID)
    lv = rec["params"][k.level_of(rec) - 1]
    forest = [h for h in hits if h.label == "Forest of Swords" and h.primary]
    assert len(forest) == len(rec["splits"])  # per-hit splits from the ability script
    assert sum(h.base for h in forest) == pytest.approx(lv[1] * atk + lv[3] * mh)
    # Ultimate: HP set to 50% (the 10% lost counts), DMG includes 100% of the HP-loss tally
    blade.energy = blade.max_energy
    k.use_ult()
    ult_hit = hits[-1]
    assert blade.hp == pytest.approx(0.5 * mh)
    assert ult_hit.base == pytest.approx(k.p("ult", 0) * atk + k.p("ult", 1) * mh + k.p("ult", 4) * 0.5 * mh)
    assert k.tally == 0.0 and k.charge == 3
    # Charge at 5 -> AoE follow-up on HP + ATK, then all Charges are consumed
    k.add_charge()
    k.add_charge()
    b.process_queue()
    fua = [h for h in hits if h.label == "Shuhu's Gift"]
    assert [h.ratio for h in fua] == FUA_SPLITS  # 0.33 / 0.33 / 0.34 (Avatar_Ren_00_Passive1Atk02_Ability)
    assert sum(h.base for h in fua) == pytest.approx(k.p("talent", 1) * atk + k.p("talent", 3) * mh)
    assert k.charge == 0


def test_blade_forest_of_swords_adjacent_targets_take_one_hit():
    b, (blade, _), enemies = _battle([Build("Blade"), Build("Bronya")], n_enemies=3)
    k = blade.kit
    hits = _hits(b)
    k.skill(enemies[1])
    forest = [h for h in hits if h.label == "Forest of Swords"]
    # Avatar_Ren_00_Skill11_Phase02: 2 half hits on the main target, 1 full hit (split=None) on each adjacent one
    assert [h.ratio for h in forest if h.target is enemies[1]] == [0.5, 0.5]
    assert [h.ratio for h in forest if h.target is enemies[0]] == [1.0]
    assert [h.ratio for h in forest if h.target is enemies[2]] == [1.0]


# ------------------------------------------------------------------ Fu Xuan
def test_fu_xuan_matrix_knowledge_and_dmg_distribution():
    b, (fx, seele), (e,) = _battle([Build("Fu Xuan", eidolon=1), Build("Seele")])
    k = fx.kit
    cr0, cd0, hp0 = seele.stat(S.CRIT_RATE), seele.stat(S.CRIT_DMG), seele.max_hp
    assert k.p("talent", 0) in seele.factors(S.MITIGATION, ())  # Misfortune Avoidance
    k.skill(e)
    assert seele.stat(S.CRIT_RATE) == pytest.approx(cr0 + k.p("skill", 4))
    assert seele.stat(S.CRIT_DMG) == pytest.approx(cd0 + k.ep(1, 0))
    assert seele.max_hp == pytest.approx(hp0 + k.p("skill", 3) * fx.max_hp)
    # 65% of the HP an enemy hit takes from a teammate is taken from Fu Xuan instead
    fx_hp, s_hp = fx.hp, seele.hp
    b.hit_ally(e, seele, 1.0)
    lost_fx, lost_s = fx_hp - fx.hp, s_hp - seele.hp
    assert lost_fx > 0
    assert lost_fx / (lost_fx + lost_s) == pytest.approx(k.p("skill", 0))


def test_fu_xuan_ult_trigger_count_restores_hp_at_once_when_low():
    b, (fx, _), (e,) = _battle([Build("Fu Xuan"), Build("Seele")])
    k = fx.kit
    k.triggers = 0
    fx.hp = 0.3 * fx.max_hp  # already below the threshold, no trigger count left
    fx.energy = fx.max_energy
    k.use_ult()  # the Ultimate's trigger count is spent right away (Skill03_Phase02 -> Passive_Ability)
    assert k.triggers == 0
    assert fx.hp == pytest.approx(0.3 * fx.max_hp + k.p("talent", 2) * 0.7 * fx.max_hp)


# ---------------------------------------------------------------- Guinaifen
def test_guinaifen_burn_detonation_and_firekiss():
    b, (gui, _), (e,) = _battle([Build("Guinaifen"), Build("Bronya")])
    k = gui.kit
    k.skill(e)
    burn = e.get_mod("Burn (Guinaifen)")
    assert burn is not None and burn.duration == int(k.p("skill", 4))
    full = burn.trigger(b)  # one full Burn tick (no Firekiss yet)
    assert not e.has_mod("Firekiss")
    k.ult(e)
    det = [r for r in b.records if r.label == "Burn (Guinaifen)"][-1]
    assert det.amount == pytest.approx(k.p("ult", 1) * full)
    fk = e.get_mod("Firekiss")  # the detonated Burn dealt DMG -> Firekiss
    assert fk is not None and fk.stacks == 1 and e.stat(S.VULN) == pytest.approx(k.p("talent", 3))


# -------------------------------------------------------------------- Bailu
def test_bailu_invigoration_heals_when_hit():
    b, (bailu, seele), (e,) = _battle([Build("Bailu"), Build("Seele")])
    k = bailu.kit
    bailu.energy = bailu.max_energy
    k.use_ult()
    inv = seele.get_mod("Invigoration")
    assert inv is not None and inv.duration == int(k.p("ult", 2))
    assert inv.data["left"] == int(k.p("talent", 4) + k.tp(2, 0))  # A4: one more trigger
    assert k.tp(3, 0) in seele.factors(S.MITIGATION, ())  # A6
    b.lose_hp(seele, 0.5 * seele.max_hp, e)
    hp = seele.hp
    b.events.emit(E.ALLY_ATTACKED, attacker=e, targets=[seele], action=None)
    assert seele.hp - hp == pytest.approx(k.p("talent", 0) * bailu.max_hp + k.p("talent", 1))
    assert inv.data["left"] == int(k.p("talent", 4) + k.tp(2, 0)) - 1
    k.use_ult()  # already Invigorated: extended by 1 turn instead of re-applied
    assert seele.get_mod("Invigoration").duration == int(k.p("ult", 2)) + 1


# ------------------------------------------------------------------ Jingliu
def test_jingliu_transmigration_consumes_teammate_hp_for_atk():
    b, (jl, bro, seele), (e,) = _battle([Build("Jingliu"), Build("Bronya"), Build("Seele")])
    k = jl.kit
    cr0 = jl.stat(S.CRIT_RATE)
    k.skill(e)
    assert not k.in_transmigration and k.syzygy == 1
    k.skill(e)
    assert k.in_transmigration and jl.av == pytest.approx(0.0)  # entered with a 100% action advance
    assert jl.stat(S.CRIT_RATE) == pytest.approx(cr0 + k.p("talent", 6))
    hits = _hits(b)
    sp = b.sp
    hp_b, hp_s = bro.hp, seele.hp
    k.take_turn()  # Moon On Glacial River
    consumed = (hp_b - bro.hp) + (hp_s - seele.hp)
    assert consumed == pytest.approx(k.p("talent", 1) * (bro.max_hp + seele.max_hp))
    bonus = min(k.p("talent", 2) * consumed, k.p("talent", 3) * jl.raw(S.BASE_ATK))
    rec = k.sk("121209")
    lv = rec["params"][k.level_of(rec) - 1]
    moon = [h for h in hits if h.label == "Moon On Glacial River"]
    assert [h.ratio for h in moon] == MOON_SPLITS  # 5 hits (Avatar_Jingliu_00_PassiveAtkReady_Ability)
    assert sum(h.base for h in moon) == pytest.approx(lv[0] * (jl.atk + bonus))  # the ATK bonus ends with the attack
    assert b.sp == sp and k.syzygy == 1


# ---------------------------------------------------- Imbibitor Lunae
def test_imbibitor_lunae_fulgurant_leap_stacks_and_squama():
    b, (il, _), enemies = _battle([Build("1213"), Build("Bronya")], n_enemies=3)
    k = il.kit
    mid = enemies[1]
    spent = []
    b.events.on(E.SP_CHANGED, lambda ev: ev.entity is il and ev.delta < 0 and spent.append(-ev.delta))
    hits = _hits(b)
    assert b.sp == 3
    k.enhanced_basic(mid, 3)
    assert b.sp == 0 and sum(spent) == 3
    assert len(hits) == len(FULGURANT_SPLITS) + 2 * 4  # 7 hits + 2 adjacent targets from the 4th hit
    rh = il.get_mod("Righteous Heart")
    assert rh is not None and rh.stacks == int(k.p("talent", 1))
    assert il.get_mod("Outroar").stacks == 4
    # the 7th hit carries 6 Righteous Heart stacks (one per previous hit) and 4 Outroar stacks
    last = [h for h in hits if h.primary][-1]
    assert last.parts is not None
    # Squama Sacrosancta from the Ultimate pays for the next attack and counts as SP consumption
    il.energy = il.max_energy
    k.use_ult()
    assert k.squama == int(k.p("ult", 2))
    b.sp = 1
    spent.clear()
    k.enhanced_basic(mid, 3)
    assert b.sp == 0 and k.squama == 0 and sum(spent) == 3


# -------------------------------------------------------------------- Xueyi
def test_xueyi_karma_ult_bonus_and_follow_up():
    b, (xy, _), (e,) = _battle([Build("Xueyi"), Build("Bronya")], toughness=100)
    k = xy.kit
    hits = _hits(b)
    k.basic(e)  # 10 Toughness -> 1 Karma
    assert k.karma == 1
    k.skill(e)  # 20 Toughness -> 2 Karma
    assert k.karma == 3
    assert e.toughness == pytest.approx(70)
    k.ult(e)  # 40 Toughness to reduce: +min(60%, 4 x 15%) DMG, A4 +10% (Toughness >= 50%)
    ult = hits[-1]
    assert ult.extra[S.DMG_PCT] == pytest.approx(min(k.p("ult", 2), 4 * k.p("ult", 1)) + k.tp(2, 1))
    assert k.karma == 7
    k.basic(e)
    assert k.karma == 8 and k.fua_pending
    xy.energy = 0.0  # keep the Ultimate out of the insert window
    b.process_queue()
    fua = [h for h in hits if h.label == "Karmic Perpetuation"]
    assert len(fua) == 3 and k.karma == 0


def test_xueyi_technique_adds_karma():
    # StageAbility_Maze_Xueyi_Modifier adds MAvatar_Xueyi_00_Passive_AddCount after the Technique's DMG
    b, (xy, _), enemies = _battle([Build("Xueyi"), Build("Bronya")], n_enemies=3, toughness=100, techniques=True)
    reduced = sum(100 - e.toughness for e in enemies)
    assert reduced == pytest.approx(3 * xy.kit.toughness("technique"))
    assert xy.kit.karma == int(reduced // 10)


# -------------------------------------------------------------------- Hanya
def test_hanya_burden_recovers_sp_and_sanction():
    b, (hanya, seele), (e,) = _battle([Build("Hanya"), Build("Seele")])
    k = hanya.kit
    assert b.sp == 3
    k.skill(e)
    burden = e.get_mod("Burden")
    assert b.sp == 2 and burden is not None and burden.data["count"] == 1  # the Skill counts as the 1st use
    energy = hanya.energy
    seele.kit.basic(e)
    assert b.sp == 2 + 1 + 1  # Seele's Basic ATK + Burden recovery
    assert burden.data["triggers"] == 1 and burden.data["count"] == 0
    assert seele.get_mod("Sanction").value(S.DMG_PCT) == pytest.approx(k.p("talent", 0))
    assert seele.get_mod("Scrivener").value(S.ATK_PCT) == pytest.approx(k.tp(1, 0))  # A2
    assert hanya.energy - energy == pytest.approx(k.tp(3, 0) * (1 + hanya.stat(S.ERR)))  # A6
    # Ultimate: SPD from Hanya's SPD + ATK% on the target ally
    spd = seele.spd
    hanya.energy = hanya.max_energy
    k.use_ult()
    assert seele.spd == pytest.approx(spd + k.p("ult", 2) * hanya.spd)


# -------------------------------------------------------------------- Misha
def test_misha_sp_consumption_adds_ult_hits_and_freeze():
    b, (misha, bro), (e,) = _battle([Build("Misha"), Build("Bronya")])
    k = misha.kit
    assert k.hits == int(k.p("ult", 0))
    energy = misha.energy
    k.skill(e)  # +1 hit from the Skill, +1 from the SP it consumed
    assert k.hits == int(k.p("ult", 0)) + 2
    bro.kit.skill(e)  # an ally consuming 1 SP
    assert k.hits == int(k.p("ult", 0)) + 3
    skill_energy = float(k.sk("skill")["energy"])
    err = 1 + misha.stat(S.ERR)
    assert misha.energy - energy == pytest.approx((skill_energy + 2 * k.p("talent", 0)) * err)
    hits = _hits(b)
    misha.energy = misha.max_energy
    k.use_ult()
    ult_hits = [h for h in hits if h.label == k.sk("ult")["name"]]
    assert len(ult_hits) == int(k.p("ult", 0)) + 3
    assert k.hits == int(k.p("ult", 0))  # reset after the Ultimate
    assert e.has_mod("Frozen")  # A2: 20% + 80% base chance before the first hit
    # A6: CRIT DMG vs Frozen enemies applies from the first hit on (the Freeze lands just before it)
    assert ult_hits[0].extra.get(S.CRIT_DMG) == pytest.approx(k.tp(3, 0))
