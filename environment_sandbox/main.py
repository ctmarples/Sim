"""Application entry point for the environmental farming sandbox."""

from __future__ import annotations

import os

# Centre the window before the display surface is created.
os.environ.setdefault("SDL_VIDEO_CENTERED", "1")


def build_parser():
    import argparse

    parser = argparse.ArgumentParser(description="Environmental farming sandbox")
    parser.add_argument(
        "--time-demo",
        action="store_true",
        help="Open the ticks/cooldown demo window instead of the full game",
    )
    parser.add_argument(
        "--original-resource-grid",
        "--original-grid",
        "--original",
        dest="original_resource_grid",
        action="store_true",
        help="Draw natural resources at their original full-cell size",
    )
    return parser


def main() -> None:
    args = build_parser().parse_args()

    import pygame

    pygame.init()
    if args.time_demo:
        from time_demo import TimeDemo

        TimeDemo().run()
        return

    import settings

    info = pygame.display.Info()
    settings.configure_for_display(info.current_w, info.current_h)

    # Import Game after display metrics are applied so CELL_SIZE / grid bind correctly.
    from game import Game

    game = Game(use_original_resource_grid=args.original_resource_grid)
    game.run()


if __name__ == "__main__":
    main()
