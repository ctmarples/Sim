#!/usr/bin/env python3
"""Extract colour palettes from current tiles and rewrite as random scatter fills.

    python generate_terrain_fills.py
    python generate_terrain_fills.py --count 8 --no-preview
"""

from __future__ import annotations

import argparse
import subprocess
import sys

import pygame

from terrain_fills import (
    FILL_VARIANT_TARGET,
    PREVIEW_TERRAINS,
    fill_inventory,
    generate_variant_set,
    palette_summary,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--count",
        type=int,
        default=FILL_VARIANT_TARGET,
        help=f"variants per stem (default {FILL_VARIANT_TARGET})",
    )
    parser.add_argument(
        "--noise",
        type=int,
        default=0,
        help="ignored (scatter fills use palette density only)",
    )
    parser.add_argument(
        "--no-preview",
        action="store_true",
        help="only write PNGs / palettes, do not launch preview",
    )
    args = parser.parse_args()

    pygame.init()
    pygame.display.set_mode((1, 1))

    written = generate_variant_set(count=args.count, noise=args.noise)
    print(f"Wrote {len(written)} scatter tiles from colour buckets:")
    for terrain in PREVIEW_TERRAINS:
        print(f"  {terrain.name}: {palette_summary(terrain)}")
    for _terrain, stem, n, paths in fill_inventory():
        print(f"  {stem}: {n} files — {paths[0].name} … {paths[-1].name}")

    if not args.no_preview:
        return subprocess.call([sys.executable, "preview_terrain_fills.py"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
