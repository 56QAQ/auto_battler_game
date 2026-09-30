"""Silver Wolf LV.999's Enhanced Basic ATK "Bonus Stage: αWolf Instant": 1/3 of the bounces -> Top Loot Box ->
1/3 -> box -> 1/3 -> box -> Final Hit; it ends as soon as an attack finds no surviving enemy and resumes, in an
extra turn, from where it stopped once attackable enemies appear (new wave or Pure Fiction refill)."""

import pytest

from hsrsim import events as E
from hsrsim.battle import Battle, InfiniteWave
from hsrsim.build import Build, make_character
from hsrsim.entities import Enemy

from .helpers import generic_build


def _battle(waves):
    chars = [make_character(Build("Silver Wolf LV.999")), make_character(generic_build("Bronya"))]
    b = Battle(chars, waves)
    b.start()
    return b, chars[0]


def _godmode(sw):
    kit = sw.kit
    kit.gain_mmr(kit.p("talent", 0))
    kit.use_ult()
    assert kit.god
    return kit


def _trace(b):
    labels = []
    b.events.on(E.AFTER_HIT, lambda ev: labels.append(ev.hit.label))
    return labels


def _shape(labels):
    """Collapse hit labels into [bounces, "box", bounces, "box", ..., "final"]."""
    out: list = []
    for lab in labels:
        if "bounce" in lab:
            if out and isinstance(out[-1], int):
                out[-1] += 1
            else:
                out.append(1)
        elif lab.startswith("Top Loot Box") and out[-1:] != ["box"]:
            out.append("box")
        elif "Final Hit" in lab and out[-1:] != ["final"]:
            out.append("final")
    return out


def _enh(kit):
    rec = kit.sk("150608")
    lv = rec["params"][kit.level_of(rec) - 1]
    return int(lv[2]), int(lv[4])


def test_bounces_in_thirds_each_followed_by_a_box_then_the_final_hit():
    b, sw = _battle([[Enemy(f"Dummy {i}", hp=1e12) for i in range(3)]])
    kit = _godmode(sw)
    total, boxes = _enh(kit)
    assert (total, boxes) == (100, 3)
    labels = _trace(b)
    kit.enhanced_basic(b.enemies[0])
    assert _shape(labels) == [33, "box", 34, "box", 33, "box", "final"]
    assert kit.pending is None and kit.basics_left == int(kit.p("talent", 4)) - 1


def test_ends_as_soon_as_no_enemy_survives_and_keeps_what_remains():
    b, sw = _battle([[Enemy("Weak", hp=1.0)]])
    kit = _godmode(sw)
    total, boxes = _enh(kit)
    left = kit.basics_left
    labels = _trace(b)
    kit.enhanced_basic(b.enemies[0])
    assert _shape(labels) == [1]  # the first bounce defeats it: nothing else is attacked
    assert kit.pending == {"bounces": total - 1, "boxes": boxes, "final": True}
    assert kit.basics_left == left and kit.god  # not a full use


@pytest.mark.parametrize("fatal_box, bounces_left", [(1, 67), (2, 33), (3, 0)])
def test_a_box_that_defeats_everyone_ends_it_too(fatal_box, bounces_left):
    b, sw = _battle([[Enemy(f"Dummy {i}", hp=1e12) for i in range(2)]])
    kit = _godmode(sw)
    original, opened = kit.loot_box, []

    def loot_box(act, **kw):
        original(act, **kw)
        opened.append(1)
        if len(opened) == fatal_box:
            for e in b.enemies:
                e.hp = 0.0

    kit.loot_box = loot_box
    kit.enhanced_basic(b.enemies[0])
    # the Final Hit is still owed even when only it remains (3rd box)
    assert kit.pending == {"bounces": bounces_left, "boxes": 3 - fatal_box, "final": True}


def test_pure_fiction_refill_resumes_in_an_extra_turn_from_where_it_stopped():
    wave = InfiniteWave(pool=[Enemy("Weak", hp=1.0), Enemy("Tank", hp=1e12)], max_count=3, on_field=1)
    b, sw = _battle([wave])
    kit = _godmode(sw)
    left = kit.basics_left
    labels = _trace(b)
    turns = []
    b.events.on(E.TURN_START, lambda ev: turns.append((ev.entity.name, bool(ev.extra))))
    kit.enhanced_basic(b.enemies[0])  # the Weak one dies on the first bounce; the Tank enters when the action ends
    assert kit.pending is not None and kit.resume_queued
    assert [e.name for e in b.alive_enemies()] == ["Tank #2"]
    b.process_queue()
    assert ("Silver Wolf LV.999", True) in turns  # the extra turn
    assert _shape(labels) == [33, "box", 34, "box", 33, "box", "final"]  # continued the same schedule
    assert kit.pending is None and kit.basics_left == left - 1


def test_new_wave_resumes_too():
    b, sw = _battle([[Enemy("Weak", hp=1.0)], [Enemy("Next", hp=1e12)]])
    kit = _godmode(sw)
    kit.enhanced_basic(b.enemies[0])
    assert kit.pending is not None
    b.process_queue()  # wave 2 starts, the extra turn resumes the Enhanced Basic ATK
    assert b.wave_index == 1 and kit.pending is None


def _extra_turns(b, sw):
    return len([q for q in b.queue if q.label == "extra turn" and q.owner is sw])


@pytest.mark.parametrize("mmr, left, extra", [(99, 79, 0), (140, 120, 1), (60, 40, 0)])
def test_ult_spends_60_mmr_before_e2_counts(mmr, left, extra):
    """99 MMR: -60 (cost) -> 39, +20 (A6 "Secret Level Maxed") +20 (Punchline from "Welcome to the Cosmic City")
    = 79 < 120: no E2 extra turn. 140 MMR: 80 + 40 = 120: one."""
    chars = [
        make_character(Build("Silver Wolf LV.999", eidolon=2, light_cone="23057")),
        make_character(generic_build("Bronya")),
    ]
    b = Battle(chars, [[Enemy("Dummy", hp=1e12)]])
    b.start()
    kit = chars[0].kit
    assert kit.p("talent", 0) == 60 and kit.tp(3, 0) == 20 and kit.ep(2, 0) == 120
    kit.mmr = float(mmr)
    kit.use_ult()
    assert kit.god
    assert kit.mmr == pytest.approx(left)
    assert kit.basics_left == int(kit.p("talent", 4)) + extra
    assert _extra_turns(b, chars[0]) == extra
