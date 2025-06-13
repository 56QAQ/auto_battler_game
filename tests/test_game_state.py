import os
os.environ.setdefault('SDL_VIDEODRIVER', 'dummy')
import pygame
pygame.display.init()

from engine.game_state import reset_game_state, get_game_state


def test_get_game_state_singleton():
    reset_game_state()
    state1 = get_game_state()
    state2 = get_game_state()
    assert state1 is state2


def test_reset_game_state_creates_new_instance():
    reset_game_state()
    state1 = get_game_state()
    reset_game_state()
    state2 = get_game_state()
    assert state1 is not state2