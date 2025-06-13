import os
os.environ.setdefault('SDL_VIDEODRIVER', 'dummy')
import pygame
pygame.display.init()

import random
from engine.classes import GameMap


def test_map_generation_reachable():
    random.seed(42)
    gmap = GameMap()
    start = gmap.start_node_id
    start_node = gmap.get_node(start)
    assert start_node is not None
    # there should be at least one next node
    assert start_node.next_nodes
    first_next = start_node.next_nodes[0]
    assert gmap.is_node_reachable(first_next, start)


def test_rescale_changes_coordinates():
    random.seed(1)
    gmap = GameMap()
    node_before = gmap.get_node(gmap.start_node_id)
    old_x, old_y = node_before.x, node_before.y
    gmap.rescale(1000, 800, 10, 20, 5)
    node_after = gmap.get_node(gmap.start_node_id)
    assert node_after.x != old_x or node_after.y != old_y