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

    # Apply authored map-object definitions before Game and its consumers bind
    # catalogue tuples at import time.
    try:
        from developer_tools.objects_editor import apply_saved_overrides
        apply_saved_overrides()
    except Exception as exc:
        # Authored content must never make the game itself unlaunchable. The
        # editor can surface and repair an invalid override after startup.
        print(f"Ignoring invalid map-object overrides: {type(exc).__name__}: {exc}")
    try:
        from developer_tools.wild_species_editor import reload_wild_species
        wild_result=reload_wild_species()
        if not wild_result.success:print(wild_result.message)
    except Exception as exc:
        print(f"Ignoring invalid Wild Species overrides: {type(exc).__name__}: {exc}")
    try:
        from developer_tools.crop_editor import reload_crops
        crop_ok,crop_message=reload_crops()
        if not crop_ok:print(crop_message)
    except Exception as exc:
        print(f"Ignoring invalid Farm Crop overrides: {type(exc).__name__}: {exc}")
    try:
        from developer_tools.plant_editor import PlantEditorService
        plant_ok,plant_message=PlantEditorService().load()
        if not plant_ok:print(plant_message)
    except Exception as exc:
        print(f"Ignoring invalid Plant overrides: {type(exc).__name__}: {exc}")

    # Import Game after display metrics are applied so CELL_SIZE / grid bind correctly.
    from game import Game

    game = Game(use_original_resource_grid=args.original_resource_grid)
    game.run()


if __name__ == "__main__":
    main()
