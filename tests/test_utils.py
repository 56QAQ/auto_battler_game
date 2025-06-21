import math
import os

import pygame

from data.enums import StatSource, TriggerTarget, TriggerTiming
from engine import utils
from engine.classes import Item

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
pygame.display.init()


def test_lerp():
    assert utils.lerp(0, 10, 0.5) == 5


def test_clamp():
    assert utils.clamp(5, 0, 10) == 5
    assert utils.clamp(-1, 0, 10) == 0
    assert utils.clamp(15, 0, 10) == 10


def test_lerp_color():
    c1 = (0, 0, 0)
    c2 = (255, 255, 255)
    assert utils.lerp_color(c1, c2, 0.5) == (127, 127, 127)


def test_normalize_vector():
    nx, ny, dist = utils.normalize_vector(3, 4, 5)
    assert math.isclose(nx, 0.6)
    assert math.isclose(ny, 0.8)
    assert math.isclose(dist, 5)
    nx, ny, dist = utils.normalize_vector(0, 0, 0)
    assert (nx, ny, dist) == (0.0, 0.0, 0.1)


def test_format_trigger_description():
    trigger = {
        "timing_type": TriggerTiming.ON_HIT,
        "target_type": TriggerTarget.SELF,
        "base_value_source": StatSource.AD,
        "base_value_multiplier": 1.0,
        "base_value_flat": 0,
    }
    item = Item("Amp Coil")
    desc = utils.format_trigger_description(trigger, [item])
    assert "On Hit:" in desc
    assert "Self ->" in desc
    assert "Deal" in desc


def test_determine_outcome():
    # Force deterministic outcome using monkeypatching
    def fake_random():
        return 0.05  # falls into fail region with default probs

    orig = utils.random.random
    utils.random.random = fake_random
    try:
        assert (
            utils.determine_outcome({"fail": 0.1, "success": 0.8, "great": 0.1})
            == "fail"
        )
    finally:
        utils.random.random = orig
