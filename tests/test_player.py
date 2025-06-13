import os
os.environ.setdefault('SDL_VIDEODRIVER', 'dummy')
import pygame
pygame.display.init()

from engine.classes import Player


def test_gain_xp_levels_up():
    player = Player()
    player.gain_xp(player.xp_to_next_level())
    assert player.level == 2
    assert player.xp == 0