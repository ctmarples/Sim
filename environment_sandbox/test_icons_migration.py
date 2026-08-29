"""Smoke-test SVG icon migration: load, rasterise, and blit every icon."""

from __future__ import annotations

import os
import sys
from pathlib import Path

# Allow running from repo root or environment_sandbox/
ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")

import pygame

pygame.init()
pygame.display.set_mode((1, 1))

from crops import CROP_BY_KEY, CROPS
from icons import (
    ALL_ICON_NAMES,
    ICON_CROP,
    ICON_CROP_DENSE,
    ICON_SAPLING_CONE,
    ICON_TREE_CONE,
    ICON_TREE_ROUND,
    blit_icon,
    clear_cache,
    ensure_icon_variant,
    get_icon,
    list_icon_names,
    preload,
    resolve_icon_name,
    variant_names,
)
from trees import TREES
from ui import draw_feature
from world import FeatureType


def main() -> None:
    on_disk = set(list_icon_names())
    expected = set(ALL_ICON_NAMES)
    missing = []
    for base in sorted(expected):
        if variant_names(base):
            continue
        if base not in on_disk:
            missing.append(base)
    assert not missing, f"Missing icon files: {missing}"
    extra = sorted(
        s
        for s in on_disk
        if s not in expected and not any(
            s == v for b in expected for v in variant_names(b)
        )
    )
    if extra:
        print(f"Note: extra icons not in ALL_ICON_NAMES: {extra}")

    clear_cache()
    # Each base expands to its folder variants (or a single unnumbered file).
    created = preload(ALL_ICON_NAMES, sizes=(20, 40))
    expected_stems = len(
        {stem for b in ALL_ICON_NAMES for stem in variant_names(b)}
    )
    assert created == expected_stems * 2, (created, expected_stems)

    assert len(variant_names(ICON_TREE_ROUND)) >= 3
    assert len(variant_names(ICON_TREE_CONE)) >= 1
    assert len(variant_names(ICON_CROP)) >= 3
    assert variant_names(ICON_CROP)[0].startswith("crop_plant_")
    from icons import ICON_FLOWER, ICON_FLOWER_DENSE

    assert len(variant_names(ICON_FLOWER)) >= 4
    assert len(variant_names(ICON_FLOWER_DENSE)) >= 3
    assert CROP_BY_KEY["hemp"].flower_colour is not None
    assert CROP_BY_KEY["flax"].icon_base == "flower_plant"

    # Tall tree variants: tree_round_1..N registered under base tree_round.
    round_variants = variant_names(ICON_TREE_ROUND)
    assert len(round_variants) >= 3, round_variants
    tall = get_icon(round_variants[0], 40)
    # Tree art may extend above and right of its bottom-left 40x40 trunk cell.
    assert tall.surface.get_width() >= 40, tall.surface.get_size()
    assert tall.surface.get_height() >= 40, tall.surface.get_size()
    assert tall.anchor_x == 20
    assert tall.anchor_y == tall.surface.get_height() - 20

    # Square icon still anchors at cell centre.
    rock = get_icon(resolve_icon_name("rock", 1), 40)
    assert rock.surface.get_size() == (40, 40)
    assert rock.anchor_x == 20 and rock.anchor_y == 20

    # Rolling variants is stable once chosen.
    import random

    rng = random.Random(0)
    v = ensure_icon_variant(ICON_TREE_ROUND, None, rng)
    assert 1 <= v <= len(round_variants)
    assert ensure_icon_variant(ICON_TREE_ROUND, v, rng) == v
    assert resolve_icon_name(ICON_TREE_ROUND, v) in round_variants

    # Recolour / omit paths used by draw_feature.
    for crop in CROPS:
        omit = () if crop.flower_colour is not None else ("flower",)
        recolour = {"stem": crop.stem_colour}
        if crop.flower_colour is not None:
            recolour["flower"] = crop.flower_colour
        for dense in (False, True):
            get_icon(
                resolve_icon_name(crop.plant_icon(dense=dense), 1),
                40,
                recolour=recolour,
                omit_classes=omit,
            )

    for tree in TREES:
        base = ICON_TREE_CONE if tree.shape == "cone" else ICON_TREE_ROUND
        name = resolve_icon_name(base, 1)
        scales = {"canopy": tree.cone_scale} if tree.shape == "cone" else None
        get_icon(
            name,
            40,
            recolour={"canopy": tree.canopy, "trunk": (90, 55, 30)},
            class_scales=scales,
        )
        sbase = ICON_SAPLING_CONE if tree.shape == "cone" else "sapling_round"
        sname = resolve_icon_name(sbase, 1)
        get_icon(
            sname,
            40,
            recolour={"canopy": tree.sapling_colour, "trunk": (90, 55, 30)},
            class_scales=scales,
        )

    # Blit every feature type onto a surface (migration path).
    canvas = pygame.Surface((640, 400), pygame.SRCALPHA)
    features = [
        (FeatureType.TREE, {"tree_species": "oak"}),
        (FeatureType.TREE, {"tree_species": "pine"}),
        (FeatureType.TREE, {"tree_species": "cedar"}),
        (FeatureType.SAPLING, {"tree_species": "maple"}),
        (FeatureType.ROCK, {}),
        (FeatureType.HOME, {}),
        (FeatureType.WORKSTATION, {}),
        (FeatureType.FORESTER, {}),
        (FeatureType.MASON, {}),
        (FeatureType.HUNTER, {}),
        (FeatureType.FORAGER, {}),
        (FeatureType.FISHER, {}),
        (FeatureType.FARM, {}),
        (FeatureType.FIELD, {}),
        (FeatureType.CONSTRUCTION_SITE, {}),
        (FeatureType.MUSHROOM, {}),
        (FeatureType.BERRY_BUSH, {}),
        (FeatureType.REED, {}),
        (FeatureType.WILD_CROP, {"crop_kind": "sage"}),
        (FeatureType.CROP_HERB, {"crop_kind": "wheat"}),
        (FeatureType.WILD_CROP, {"crop_kind": "flax"}),
    ]
    for i, (feat, kwargs) in enumerate(features):
        x = 30 + (i % 7) * 90
        y = 40 + (i // 7) * 90
        draw_feature(canvas, feat, x, y, 40, vibrancy=1.0, **kwargs)

    # Entity icons
    for i, name in enumerate(
        (
            "deer_male",
            "deer_female",
            "boar_male",
            "boar_female",
            "fish",
            "villager",
            "player",
            "meat_marker",
            "fish_marker",
        )
    ):
        blit_icon(canvas, name, 40 + i * 50, 360, 36)

    out_dir = ROOT / "_debug"
    out_dir.mkdir(exist_ok=True)
    out = out_dir / "icons_migration_test.png"
    pygame.image.save(canvas, str(out))
    assert out.is_file() and out.stat().st_size > 0

    # Second pass: cache hits only (no new surfaces for base preload sizes).
    again = preload(ALL_ICON_NAMES, sizes=(20, 40))
    assert again == 0, f"Cache should hit on second preload, got {again} new"

    print(f"OK: {len(ALL_ICON_NAMES)} icons, cache warm, wrote {out}")


if __name__ == "__main__":
    main()
