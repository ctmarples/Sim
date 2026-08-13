"""Application entry point for the environmental farming sandbox."""

from __future__ import annotations

import os

import pygame

# Centre the window before the display surface is created.
os.environ.setdefault("SDL_VIDEO_CENTERED", "1")


def main() -> None:
    pygame.init()
    import argparse

    parser = argparse.ArgumentParser(description="Environmental farming sandbox")
    parser.add_argument(
        "--time-demo",
        action="store_true",
        help="Open the ticks/cooldown demo window instead of the full game",
    )
    args = parser.parse_args()
    if args.time_demo:
        from time_demo import TimeDemo

        TimeDemo().run()
        return

    import settings

    info = pygame.display.Info()
    settings.configure_for_display(info.current_w, info.current_h)

    # Import Game after display metrics are applied so CELL_SIZE / grid bind correctly.
    from game import Game

    game = Game()
    game.run()


if __name__ == "__main__":
    main()
