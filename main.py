import pygame

pygame.init()
# create a tiny hidden window so display.Info() has something to query
pygame.display.set_mode((1000, 1000), pygame.HIDDEN)
import sys

from engine.game_state import GameState, get_game_state
from engine.logic import run_combat_tick
from states.enums import GamePhase
from states.input_handler import handle_game_event
from states.state_machine import go_to_main_menu
from ui import constants as ui_c
from ui.drawing import (
    draw_combat_phase,
    draw_difficulty_select,
    draw_event_choice,
    draw_game_over,
    draw_main_menu,
    draw_map_phase,
    draw_preparation_phase,
    draw_run_complete,
    draw_settings,
    draw_theme_select,
)
from ui.fonts import load_fonts
from ui.ui_context import UIContext


def main():
    pygame.init()
    state = get_game_state()  # Initialize the global state
    width, height = state.resolution_options[state.resolution_index]
    ui_c.update_resolution(width, height)
    state.game_map.rescale(
        ui_c.MAP_WIDTH,
        ui_c.MAP_HEIGHT,
        ui_c.MAP_X_START,
        ui_c.MAP_Y_START,
        ui_c.MAP_NODE_RADIUS,
    )
    screen = pygame.display.set_mode((ui_c.SCREEN_WIDTH, ui_c.SCREEN_HEIGHT))
    pygame.display.set_caption("Clockwork Requiem - Refactored")
    clock = pygame.time.Clock()

    fonts = load_fonts()
    context = UIContext(screen, fonts)
    go_to_main_menu(state)  # Set the first phase

    running = True
    while running:
        delta_time = clock.tick(ui_c.FPS) / 1000.0

        # --- Event Handling ---
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False

            new_state = handle_game_event(event, state, context)
            if new_state:  # A new run was started
                state = new_state

        # --- Game Logic Update ---
        if state.current_phase == GamePhase.COMBAT:
            run_combat_tick(state, delta_time)

        # --- Drawing ---
        screen.fill(ui_c.BG)
        phase = state.current_phase

        if phase == GamePhase.MAIN_MENU:
            draw_main_menu(state, context)
        elif phase == GamePhase.DIFFICULTY_SELECT:
            draw_difficulty_select(state, context)
        elif phase == GamePhase.THEME_SELECT:
            draw_theme_select(state, context)
        elif phase == GamePhase.PREPARATION:
            draw_preparation_phase(state, context)
        elif phase == GamePhase.COMBAT:
            draw_combat_phase(state, context)
        elif phase == GamePhase.MAP_NAVIGATION:
            draw_map_phase(state, context)
        elif phase == GamePhase.GAME_OVER:
            draw_game_over(state, context)
        elif phase == GamePhase.RUN_COMPLETE:
            draw_run_complete(state, context)
        elif phase == GamePhase.EVENT_CHOICE:
            draw_event_choice(state, context)
        elif phase == GamePhase.SETTINGS:
            draw_settings(state, context)

        pygame.display.flip()

    pygame.quit()
    sys.exit()


if __name__ == "__main__":
    main()