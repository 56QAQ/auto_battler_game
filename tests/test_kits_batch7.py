"""Targeted checks for batch 7a: Phainon (Khaslana transformation), Evernight (Evey, Memoria) and Cyrene (Zone True
DMG, Demiurge and the Odes)."""

import pytest

from hsrsim import events as E
from hsrsim import formulas as F
from hsrsim import stats as S
from hsrsim.battle import Battle
from hsrsim.build import Build, make_character
from hsrsim.entities import Enemy
from hsrsim.enums import ActionKind, DmgTag, Element

from .helpers import generic_build


def _idle(enemy, battle):
    """Enemy AI that does nothing (keeps resource counters deterministic)."""


def _battle(builds, enemies=None):
    chars = [make_character(b) for b in builds]
    enemies = enemies or [Enemy("Dummy", effect_res=0.0, hp=1e12, ai=_idle)]
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


# -------------------------------------------------------------------- Phainon
def test_phainon_skill_coreflame_and_targeted_by_teammate():
    b, (ph, mate) = _battle([Build("Phainon"), generic_build("Bronya")])
    kit = ph.kit
    assert kit.coreflame == pytest.approx(kit.tp(1, 1))  # A2: Coreflame on battle start
    assert ph.max_energy > 0 and ph.energy == 0.0  # the Energy bar only detects Energy Regeneration
    b.sp = 3
    kit.skill(b.default_target())
    assert b.sp == 2
    assert kit.coreflame == pytest.approx(kit.tp(1, 1) + kit.p("skill", 2))
    before = kit.coreflame
    with b.action(mate, ActionKind.SKILL, target=ph):  # a teammate's ability targets Phainon
        b.gain_energy(ph, 10)  # ... and regenerates his Energy (A4)
    assert kit.coreflame == pytest.approx(before + 1 + kit.tp(2, 2))
    mod = ph.get_mod("Pyric Corpus")
    assert mod is not None and mod.stats[S.CRIT_DMG] == pytest.approx(kit.p("talent", 0))
    assert ph.energy == 0.0


def test_phainon_khaslana_transformation_timeline():
    b, (ph, mate) = _battle([Build("Phainon"), generic_build("Bronya")])
    kit = ph.kit
    need = kit.p("talent", 3)
    kit.coreflame = need + 2  # 2 overflow points
    assert kit.ult_ready()
    atk0 = ph.atk
    acts = _actions(b)
    kit.use_ult()
    assert kit.transformed and not kit.ult_ready()
    assert not mate.alive  # teammates depart
    assert b.enemies[0].is_weak_to(Element.PHYSICAL)
    kt = _lv(kit, "140805")
    assert kit.scourge == int(kt[0])
    assert ph.atk == pytest.approx(atk0 + kt[3] * ph.raw(S.BASE_ATK))
    n = int(kit.p("ult", 3))
    bes = list(kit.bes)
    be_spd = kit.p("ult", 2) * ph.raw(S.BASE_SPD)
    assert len(bes) == n and bes[0].spd == pytest.approx(be_spd)
    assert [u.gauge for u in bes] == pytest.approx([F.AV_BASE * i / (n - 1) for i in range(n)])

    snap = {}

    def on_end(ev):
        if ev.mod.name == "Khaslana: SPD Boost" and ev.target is ph:
            snap.update(time=b.time, coreflame=kit.coreflame, mate_alive=mate.alive, transformed=kit.transformed)

    b.events.on(E.MOD_APPLIED, on_end)
    span = F.AV_BASE / be_spd
    b.run(max_av=span + 1.0)
    k_acts = [a for a in acts if a.actor is ph and a.skill and a.skill["id"] in ("140808", "140809", "140811")]
    assert len(k_acts) == n - 1  # the last extra turn only launches the final hit
    final = [a for a in acts if a.label == "Khaslana: Final Hit"]
    assert len(final) == 1 and DmgTag.ULT in final[0].tags
    assert final[0].hits[0].mult["atk"] == pytest.approx(kit.p("ult", 0))  # one enemy: undivided
    assert snap["time"] == pytest.approx(span)
    assert snap["mate_alive"] and not snap["transformed"]
    assert snap["coreflame"] == pytest.approx(2 + kit.tp(1, 0))  # overflow back + A2
    assert not b.enemies[0].is_weak_to(Element.PHYSICAL)
    assert ph.get_mod("Khaslana") is None


def test_phainon_foundation_bounces_and_e6_true_dmg():
    enemies = [Enemy(f"Dummy {i}", effect_res=0.0, hp=1e12 * (2 if i == 0 else 1), ai=_idle) for i in range(3)]
    b, (ph, _) = _battle([Build("Phainon", eidolon=6), generic_build("Bronya")], enemies)
    kit = ph.kit
    lv = _lv(kit, "140811")
    kit.scourge = int(lv[3])
    acts = _actions(b)
    n_rec = len(b.records)
    kit.foundation(enemies[0])
    act = acts[-1]
    assert act.skill["id"] == "140811" and act.kind == ActionKind.SKILL and b.sp == 3  # no SP cost
    bounce = [h for h in act.hits if h.mult["atk"] == pytest.approx(lv[1])]
    spread = [h for h in act.hits if h.mult["atk"] == pytest.approx(lv[0] / 3)]
    assert len(bounce) == int(lv[3]) * int(lv[2]) and len(spread) == 3
    assert kit.scourge == 0
    true = [r for r in b.records[n_rec:] if DmgTag.TRUE in r.tags]
    assert len(true) == 1 and true[0].target == "Dummy 0"  # the enemy with the highest HP
    assert true[0].amount == pytest.approx(kit.ep(6, 0) * sum(h.damage for h in act.hits))


def test_phainon_calamity_counter_after_enemy_actions():
    enemies = [Enemy(f"Dummy {i}", effect_res=0.0, hp=1e12) for i in range(2)]
    b, (ph, _) = _battle([Build("Phainon"), generic_build("Bronya")], enemies)
    kit = ph.kit
    kit.coreflame = kit.p("talent", 3)
    kit.use_ult()
    for u in list(kit.bes):  # keep Khaslana's extra turns out of the way
        b.remove_unit(u)
    kit.bes.clear()
    lv = _lv(kit, "140809")
    kit.calamity(enemies[0])
    assert kit.soulscorch == 1 and all(e.gauge == 0 for e in enemies)  # enemies act immediately
    assert ph.get_mod("Soulscorch").stats[S.MITIGATION] == pytest.approx(lv[1])
    acts = _actions(b)
    b.run(max_av=b.time + 0.001)
    counter = [a for a in acts if a.label == "Calamity: Counter"]
    assert len(counter) == 1 and counter[0].kind == ActionKind.FUA
    factor = 1 + lv[4] * 3  # 1 stack + 1 per enemy action
    aoe = [h for h in counter[0].hits if h.mult["atk"] == pytest.approx(lv[0] * factor)]
    bounces = [h for h in counter[0].hits if h.mult["atk"] == pytest.approx(lv[3] * factor)]
    assert len(aoe) == 2 and len(bounces) == int(lv[2])
    assert all(DmgTag.SKILL in h.tags for h in counter[0].hits)
    assert kit.soulscorch == 0 and ph.get_mod("Soulscorch") is None


# ------------------------------------------------------------------ Evernight
def test_evernight_summons_evey_and_skill_buffs_memosprite_crit_dmg():
    b, (ev, _) = _battle([Build("Evernight"), generic_build("Bronya")])
    kit = ev.kit
    evey = kit.memosprite()
    assert evey is not None and evey.name == "Evey"
    tal = kit.sk("talent")
    lv = tal["params"][kit.level_of(tal) - 1]
    assert evey.max_hp == pytest.approx(lv[4] * ev.max_hp)
    assert evey.spd == pytest.approx(lv[3])
    assert evey.gauge == 0  # "When summoned, this unit immediately takes action"
    hp0 = ev.hp
    kit.skill(b.default_target())
    # Skill: #6 of the current HP, then A2: 5% of the (new) current HP
    assert ev.hp == pytest.approx(hp0 * (1 - kit.p("skill", 5)) * (1 - kit.tp(1, 1)))
    bonus = evey.stat(S.CRIT_DMG) - ev.stat(S.CRIT_DMG)
    assert bonus == pytest.approx(kit.p("skill", 0) * ev.stat(S.CRIT_DMG) + kit.tp(3, 0))  # 1 Remembrance character


def test_evernight_dream_consumes_memoria_and_dismisses_evey():
    b, (ev, _) = _battle([Build("Evernight"), generic_build("Bronya")])
    kit = ev.kit
    evey = kit.memosprite()
    kit.memoria = 20.0
    lv = _lv(kit, "1141307")
    spd0 = ev.spd
    acts = _actions(b)
    sp0 = b.sp
    kit.dream(evey)
    act = acts[-1]
    assert act.actor is evey and act.kind == ActionKind.MEMOSPRITE
    assert act.hits[0].mult["hp"] == pytest.approx(lv[0] * 20)
    assert kit.memosprite() is None  # Evey disappears
    parting = _lv(kit, "1141306")
    assert ev.spd == pytest.approx(spd0 + (parting[0] + parting[1] * 20) * ev.raw(S.BASE_SPD))
    assert b.sp == min(b.max_sp, sp0 + 1)  # A2
    assert kit.trigger_armed


# --------------------------------------------------------------------- Cyrene
def test_cyrene_zone_true_dmg_and_future():
    b, (cy, mate) = _battle([Build("Cyrene"), generic_build("Bronya")])
    kit = cy.kit
    assert cy.max_energy == 0.0
    b.sp = 3
    rec0 = kit.recollection
    kit.skill(None)
    assert kit.zone_active() and b.sp == 2
    assert kit.recollection == pytest.approx(rec0 + kit.p("skill", 2))
    n0 = len(b.records)
    enemy = b.default_target()
    with b.action(mate, ActionKind.BASIC, target=enemy) as act:
        act.hit(enemy, 1.0)
    new = b.records[n0:]
    true = [r for r in new if DmgTag.TRUE in r.tags]
    assert len(true) == 1 and true[0].owner == mate.name
    assert true[0].amount == pytest.approx(kit.p("skill", 0) * act.hits[0].damage)
    # the teammate holds "Future": its turn grants Recollection
    before = kit.recollection
    b.take_turn(mate)
    assert kit.recollection == pytest.approx(before + kit.p("talent", 0))
    b.take_turn(mate)  # "Future" was consumed
    assert kit.recollection == pytest.approx(before + kit.p("talent", 0))


def test_cyrene_ultimate_demiurge_and_odes():
    b, (cy, ph, mate) = _battle([Build("Cyrene"), Build("Phainon"), generic_build("Bronya")])
    kit = cy.kit
    kit.recollection = kit.p("talent", 3)
    mate.energy = 0.0
    kit.use_ult()
    demi = kit.memosprite()
    assert demi is not None and demi.name == "Demiurge" and not demi.on_timeline and not demi.targetable
    waiting = _lv(kit, "1141503")[0]
    assert demi.max_hp == pytest.approx(kit.p("ult", 0) * cy.max_hp * (1 + waiting))
    assert mate.energy == pytest.approx(mate.max_energy)  # "activates all teammates' Ultimate"
    assert kit.zone_active() and kit.zone.duration is None
    # Demiurge's extra turn: Ode to Worldbearing on Phainon (the first teammate)
    assert ph.kit.ode == pytest.approx(kit.ode_params("1141521"))
    assert ph.kit.coreflame >= ph.kit.p("talent", 3)
    assert kit.rippled and not kit.ult_ready()
    # "Reunion at First Sight": the next Ode goes to the next teammate (non-Chrysos: DMG boost)
    kit.recollection = kit.p("talent", 4)
    assert kit.ult_ready()
    kit.use_ult()
    lv = _lv(kit, "1141502")
    mod = mate.get_mod("This Ode, to All Lives")
    assert mod is not None and mod.stats[S.DMG_PCT] == pytest.approx(lv[1]) and mod.duration == int(lv[2])
