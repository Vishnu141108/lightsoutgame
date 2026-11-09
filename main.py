"""
Lights Out Puzzle - application entry point.

Run the game with::

    python main.py

The ``Game`` class owns the single Pygame window, the shared settings/audio,
the puzzle generator and the screen manager.  Every screen is a ``Screen``
subclass; ``Game.show()`` constructs the next screen, calls its layout and
enter hooks, and plays a short crossfade using a snapshot of the last frame.
"""

from __future__ import annotations

import os
import sys
import traceback

# Keep the console clean on the first import.
os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")

import pygame

from lights_out import config as C
from lights_out.audio import SAMPLE_RATE, SoundManager
from lights_out.puzzle import PuzzleGenerator
from lights_out.screens.difficulty import DifficultyScreen
from lights_out.screens.gameplay import GameplayScreen
from lights_out.screens.instructions import InstructionsScreen
from lights_out.screens.menu import MainMenuScreen
from lights_out.screens.results import DefeatScreen, VictoryScreen
from lights_out.screens.settings import (
    SettingsScreen,
    SoundScreen,
    ThemesScreen,
    VolumeScreen,
)
from lights_out.ui import Background


# ---------------------------------------------------------------------------
# Window icon
# ---------------------------------------------------------------------------
def make_window_icon() -> pygame.Surface:
    """Draw the app icon: a small plaque of lit and unlit lights."""
    size = 64
    icon = pygame.Surface((size, size), pygame.SRCALPHA)
    pygame.draw.rect(icon, (9, 14, 27), icon.get_rect(), border_radius=15)
    pygame.draw.rect(icon, (71, 56, 26), icon.get_rect(), width=2, border_radius=15)

    pattern = (
        (1, 0, 1),
        (0, 1, 0),
        (1, 0, 1),
    )
    gap = 4
    cell = 14
    total = cell * 3 + gap * 2
    left = (size - total) // 2
    top = (size - total) // 2
    for row in range(3):
        for col in range(3):
            rect = pygame.Rect(
                left + col * (cell + gap),
                top + row * (cell + gap),
                cell,
                cell,
            )
            if pattern[row][col]:
                pygame.draw.rect(icon, (255, 210, 74), rect, border_radius=3)
                pygame.draw.rect(icon, (255, 238, 168), rect, width=1, border_radius=3)
            else:
                pygame.draw.rect(icon, (25, 34, 55), rect, border_radius=3)
                pygame.draw.rect(icon, (52, 68, 103), rect, width=1, border_radius=3)
    return icon


# ---------------------------------------------------------------------------
# Application
# ---------------------------------------------------------------------------
class Game:
    """The application shell: window, shared state and screen manager."""

    def __init__(self) -> None:
        # Ask for the same format the sound synthesiser uses, then initialise
        # every Pygame subsystem.  A missing audio device is handled by
        # SoundManager rather than being allowed to abort startup.
        pygame.mixer.pre_init(SAMPLE_RATE, -16, 2, 512)
        pygame.init()
        pygame.display.set_caption(C.GAME_TITLE)

        self.size = (C.SCREEN_WIDTH, C.SCREEN_HEIGHT)
        self.display = pygame.display.set_mode(self.size, pygame.RESIZABLE)
        try:
            pygame.display.set_icon(make_window_icon())
        except pygame.error:
            pass

        self.clock = pygame.time.Clock()
        self.running = True

        # Shared session state.
        self.settings = C.GameSettings()
        self.audio = SoundManager(self.settings)
        self.generator = PuzzleGenerator()

        self.background = Background(self.size)

        # Screen factories.  Screens that need arguments receive them through
        # Game.show(...)'s keyword arguments.
        self._factories = {
            "menu": MainMenuScreen,
            "settings": SettingsScreen,
            "themes": ThemesScreen,
            "sound": SoundScreen,
            "volume": VolumeScreen,
            "difficulty": DifficultyScreen,
            "gameplay": GameplayScreen,
            "instructions": InstructionsScreen,
            "victory": VictoryScreen,
            "defeat": DefeatScreen,
        }

        self.screen = None
        self._snapshot: pygame.Surface | None = None
        self._fade = 0.0
        self._input_lock = 0.0

        self.show("menu")

    # -- screen management --------------------------------------------------
    def show(self, name: str, **kwargs) -> None:
        """Switch to *name*, constructing it with the supplied arguments."""
        if name not in self._factories:
            raise KeyError(f"Unknown screen: {name}")

        surface = pygame.display.get_surface()
        if self.screen is not None and surface is not None:
            # Grab the last completed frame for the crossfade.
            try:
                self._snapshot = surface.copy()
            except pygame.error:
                self._snapshot = None
        else:
            self._snapshot = None

        if self.screen is not None:
            self.screen.on_leave()

        self.screen = self._factories[name](self, **kwargs)
        self.screen.relayout(*self.size)
        self.screen.on_enter()

        self._fade = 1.0
        # A very short lock prevents the click that ended a game from also
        # activating a result-screen button underneath the cursor.
        self._input_lock = min(0.22, max(0.12, C.TRANSITION_SECONDS * 0.65))

    def request_quit(self) -> None:
        self.running = False

    # -- window sizing ------------------------------------------------------
    def _resize_to(self, size) -> None:
        width = max(C.MIN_WIDTH, int(size[0]))
        height = max(C.MIN_HEIGHT, int(size[1]))
        surface = pygame.display.get_surface()
        if surface is None or surface.get_size() != (width, height):
            # Normally SDL has already resized the surface; this branch only
            # runs when clamping to the minimum size (or in headless tests).
            self.display = pygame.display.set_mode((width, height), pygame.RESIZABLE)
        self.size = (width, height)
        self.background.resize(self.size)
        if self.screen is not None:
            self.screen.relayout(width, height)

    def _sync_window_size(self) -> None:
        """Pick up a user resize from SDL and relayout exactly once."""
        surface = pygame.display.get_surface()
        if surface is None:
            return
        size = surface.get_size()
        if size != self.size:
            self._resize_to(size)

    # -- main loop ----------------------------------------------------------
    def run(self) -> None:
        while self.running:
            dt = min(0.05, self.clock.tick(C.FPS) / 1000.0)

            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    self.running = False
                    break

                if event.type in (pygame.VIDEORESIZE, getattr(pygame, "WINDOWSIZECHANGED", -1)):
                    self._sync_window_size()
                    continue

                if self._input_lock > 0.0:
                    continue

                if self.screen is not None:
                    self.screen.handle_event(event)

                if not self.running:
                    break

            if not self.running:
                break

            self._sync_window_size()

            if self._input_lock > 0.0:
                self._input_lock = max(0.0, self._input_lock - dt)

            if self.screen is not None:
                self.screen.update(dt)

            self.audio.update()

            surface = pygame.display.get_surface()
            if surface is None:
                continue

            self.background.draw(surface)
            self.screen.draw(surface)

            if self._fade > 0.0 and self._snapshot is not None:
                self._fade = max(0.0, self._fade - dt / max(0.01, C.TRANSITION_SECONDS))
                alpha = int(255 * (self._fade ** 1.6))
                if alpha > 0:
                    try:
                        self._snapshot.set_alpha(alpha)
                        surface.blit(self._snapshot, (0, 0))
                    except pygame.error:
                        self._fade = 0.0
                        self._snapshot = None

            pygame.display.flip()

    def shutdown(self) -> None:
        self.audio.stop_victory_music()
        self.audio.stop_all()
        pygame.quit()


def main() -> int:
    game = Game()
    try:
        game.run()
    except Exception:  # pragma: no cover - last-resort crash report
        traceback.print_exc()
        return 1
    finally:
        game.shutdown()
    return 0


if __name__ == "__main__":
    sys.exit(main())
