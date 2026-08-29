#!/usr/bin/env python3
"""Export category-organized ``assets/icons/**/*.svg`` beside each source SVG.

Usage (from environment_sandbox)::

    python export_icons_png.py

Writes:
  assets/icons/<category>/<stem>.png
  assets/icons/_png_anchors.json

Re-run after editing SVGs. The game prefers PNG for plain loads and still
falls back to SVG when class recolour / omit / scale is requested.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")

import pygame

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

pygame.init()
pygame.display.set_mode((1, 1))

from icons import (  # noqa: E402
    ICON_CELL,
    _rasterise_svg,
    clear_cache,
    icons_dir,
)

# High-res bake so runtime downscales cleanly (4× ICON_CELL).
EXPORT_CELL_PX = int(ICON_CELL * 4)


def _is_exportable_stem(stem: str) -> bool:
    if not stem or stem.startswith("_"):
        return False
    if " " in stem or stem.count(".") > 0:
        return False
    return True


def main() -> int:
    icons = icons_dir()
    svgs = [
        path
        for path in sorted(icons.rglob("*.svg"))
        if not any(part.startswith("_") for part in path.relative_to(icons).parts[:-1])
    ]
    clear_cache()
    manifest: dict[str, dict] = {
        "export_cell_px": EXPORT_CELL_PX,
        "icon_cell": ICON_CELL,
        "icons": {},
    }
    exported = 0
    skipped = 0
    errors: list[str] = []

    for path in svgs:
        stem = path.stem
        if not _is_exportable_stem(stem):
            skipped += 1
            print(f"skip  {path.name}")
            continue
        if path.stat().st_size == 0:
            skipped += 1
            print(f"empty {path.name}")
            continue
        try:
            icon = _rasterise_svg(path, EXPORT_CELL_PX, {}, {}, set())
        except Exception as exc:  # noqa: BLE001 — report and continue
            errors.append(f"{path.name}: {exc}")
            print(f"fail  {path.name}: {exc}")
            continue
        out = path.with_suffix(".png")
        pygame.image.save(icon.surface, str(out))
        manifest["icons"][stem] = {
            "anchor_x": icon.anchor_x,
            "anchor_y": icon.anchor_y,
            "width": icon.surface.get_width(),
            "height": icon.surface.get_height(),
        }
        exported += 1
        print(
            f"ok    {stem}.png  "
            f"{icon.surface.get_width()}x{icon.surface.get_height()}  "
            f"anchor=({icon.anchor_x},{icon.anchor_y})"
        )

    dest = icons / "_png_anchors.json"
    dest.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(
        f"\nExported {exported} PNGs "
        f"(skipped {skipped}, errors {len(errors)}) → {dest.name}"
    )
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
