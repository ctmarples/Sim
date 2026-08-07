"""Alpha-stamp texture overlays for terrain (rocks, foliage, pebbles, …).

Drop transparent PNGs in ``assets/terrain/overlays/{kind}_N.png`` (alpha 0
background). Each kind can be enabled per biome with density / scale / opacity.
Stamps are scattered in world UV so adjacent cells stay continuous.

Important: blitting an SRCALPHA layer onto a display-format surface (which often
has an alpha channel) can zero the destination alpha for transparent src
pixels. Terrain must stay opaque — we restore alpha after blit.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, fields
from pathlib import Path

import pygame

from world import TerrainType

_OVERLAY_DIR = Path(__file__).resolve().parent / "assets" / "terrain" / "overlays"

# Built-in kinds (also auto-discovered from filenames).
BUILTIN_KINDS: tuple[str, ...] = ("rocks", "foliage", "pebbles")

_STAMP_CACHE: dict[str, list[pygame.Surface]] = {}
_STAMP_MTIME: dict[str, tuple[int, ...]] = {}
_CELL_CACHE: dict[tuple, pygame.Surface] = {}


@dataclass
class OverlayParams:
    """Per-biome overlay knobs (which stamps + how dense)."""

    rocks: bool = False
    foliage: bool = False
    pebbles: bool = False
    rocks_density: float = 0.35
    foliage_density: float = 0.45
    pebbles_density: float = 0.25
    scale: float = 1.0
    opacity: float = 1.0
    seed: int = 0


def clear_overlay_cache() -> None:
    _STAMP_CACHE.clear()
    _STAMP_MTIME.clear()
    _CELL_CACHE.clear()


def _force_opaque(surf: pygame.Surface) -> None:
    """Restore per-pixel alpha to 255 on opaque terrain surfaces.

    Pygame SRCALPHA blits onto RGBA (non-SRCALPHA) surfaces often leave
    transparent src pixels as dest-alpha=0, which makes later screen blits
    invisible on some builds. Skip true SRCALPHA stamp layers.
    """
    if surf.get_flags() & pygame.SRCALPHA:
        return
    if surf.get_masks()[3] == 0:
        return
    try:
        px_a = pygame.surfarray.pixels_alpha(surf)
    except ValueError:
        return
    px_a[:, :] = 255
    del px_a


def overlay_kinds() -> tuple[str, ...]:
    """Return known kinds: builtins plus any extra stems found on disk."""
    found = set(BUILTIN_KINDS)
    if _OVERLAY_DIR.is_dir():
        for path in _OVERLAY_DIR.glob("*_*.png"):
            stem = path.stem.rsplit("_", 1)[0]
            if stem:
                found.add(stem)
    return tuple(sorted(found))


def _scramble(i: int, salt: int) -> int:
    n = (i * 2654435761 + salt * 1597334677) & 0xFFFFFFFF
    n ^= n >> 16
    n = (n * 2246822519) & 0xFFFFFFFF
    n ^= n >> 13
    return n & 0x7FFFFFFF


def _kind_salt(kind: str) -> int:
    """Stable salt from kind name (avoid Python's randomized ``hash``)."""
    n = 2166136261
    for ch in kind:
        n ^= ord(ch)
        n = (n * 16777619) & 0xFFFFFFFF
    return n & 0x7FFFFFFF


def _hash01(x: int, y: int, salt: int = 0) -> float:
    return _scramble(x * 73856093 ^ y * 19349663, salt) / float(0x7FFFFFFF)


def load_stamps(kind: str) -> list[pygame.Surface]:
    """Load ``{kind}_*.png`` (SRCALPHA). Empty list if none."""
    paths = sorted(_OVERLAY_DIR.glob(f"{kind}_*.png")) if _OVERLAY_DIR.is_dir() else []
    mtimes = tuple(int(p.stat().st_mtime_ns) for p in paths)
    if kind in _STAMP_CACHE and _STAMP_MTIME.get(kind) == mtimes:
        return _STAMP_CACHE[kind]
    stamps: list[pygame.Surface] = []
    for path in paths:
        try:
            surf = pygame.image.load(str(path)).convert_alpha()
        except pygame.error:
            continue
        if surf.get_width() < 1 or surf.get_height() < 1:
            continue
        stamps.append(surf)
    _STAMP_CACHE[kind] = stamps
    _STAMP_MTIME[kind] = mtimes
    return stamps


def _enabled_kinds(params: OverlayParams) -> list[tuple[str, float]]:
    out: list[tuple[str, float]] = []
    if params.rocks:
        out.append(("rocks", max(0.0, params.rocks_density)))
    if params.foliage:
        out.append(("foliage", max(0.0, params.foliage_density)))
    if params.pebbles:
        out.append(("pebbles", max(0.0, params.pebbles_density)))
    return out


def _params_key(p: OverlayParams) -> tuple:
    return (
        bool(p.rocks),
        bool(p.foliage),
        bool(p.pebbles),
        round(p.rocks_density, 4),
        round(p.foliage_density, 4),
        round(p.pebbles_density, 4),
        round(p.scale, 4),
        round(p.opacity, 4),
        int(p.seed),
    )


def _prepare_stamp(
    stamp: pygame.Surface,
    tw: int,
    th: int,
    *,
    flip_h: bool,
    angle_deg: int,
    opacity: float,
) -> pygame.Surface:
    """Scale / flip / rotate stamp; modulate per-pixel alpha only."""
    if tw != stamp.get_width() or th != stamp.get_height():
        drawn = pygame.transform.scale(stamp, (tw, th))
    else:
        drawn = stamp.copy()
    if flip_h:
        drawn = pygame.transform.flip(drawn, True, False)
    if angle_deg % 360 != 0:
        drawn = pygame.transform.rotate(drawn, angle_deg)
    if opacity < 0.999:
        drawn = drawn.copy()
        px_a = pygame.surfarray.pixels_alpha(drawn)
        px_a[:, :] = (px_a.astype("float32") * opacity).clip(0, 255).astype("uint8")
        del px_a
    return drawn


def stamp_cell_overlays(
    dest: pygame.Surface,
    terrain: TerrainType,
    cell_x: int,
    cell_y: int,
    *,
    params: OverlayParams | None = None,
) -> None:
    """Scatter enabled overlay stamps onto a cell surface (world-stable)."""
    if params is None:
        try:
            from terrain_settings import get_overlay

            params = get_overlay(terrain)
        except Exception:
            return
    kinds = _enabled_kinds(params)
    if not kinds:
        return
    size = dest.get_width()
    if size <= 0:
        return
    key = (terrain, cell_x, cell_y, size, _params_key(params))
    hit = _CELL_CACHE.get(key)
    if hit is not None:
        dest.blit(hit, (0, 0))
        _force_opaque(dest)
        return

    layer = pygame.Surface((size, size), pygame.SRCALPHA)
    layer.fill((0, 0, 0, 0))
    scale = max(0.25, min(3.0, float(params.scale)))
    opacity = max(0.0, min(1.0, float(params.opacity)))
    base_salt = 9000 + terrain.value * 131 + int(params.seed) * 17
    # World phase so neighbouring cells don't repeat the same local pattern.
    world_key = cell_x * 73856093 ^ cell_y * 19349663

    for kind, density in kinds:
        stamps = load_stamps(kind)
        if not stamps:
            continue
        ks = _kind_salt(kind)
        # Stratified jittered samples — less grid-regular than independent hashes.
        expected = density * 3.2
        side = max(1, min(5, int(round(expected ** 0.5)) + 1))
        phase = _hash01(cell_x, cell_y, base_salt + (ks % 997))
        phase2 = _hash01(cell_x + 17, cell_y - 9, base_salt + 3 + (ks % 991))
        placed = 0
        for iy in range(side):
            for ix in range(side):
                slot = iy * side + ix
                keep_p = min(1.0, expected / float(side * side))
                if _hash01(world_key + slot, ks, base_salt + 11) >= keep_p:
                    continue
                jx = _hash01(world_key, slot * 13 + 1, base_salt + ks)
                jy = _hash01(world_key, slot * 29 + 2, base_salt + ks + 1)
                u = ((ix + 0.15 + 0.7 * jx) / side + phase) % 1.0
                v = ((iy + 0.15 + 0.7 * jy) / side + phase2) % 1.0
                px = int(u * size)
                py = int(v * size)
                stamp = stamps[_scramble(world_key + slot, base_salt + 3) % len(stamps)]
                jitter = 0.45 + 0.95 * (
                    _scramble(slot, base_salt + 4 + ks) / float(0x7FFFFFFF)
                )
                tw = max(2, int(round(stamp.get_width() * scale * jitter)))
                th = max(2, int(round(stamp.get_height() * scale * jitter)))
                flip_h = (_scramble(slot, base_salt + 5) % 2) == 0
                angle = (0, 90, 180, 270)[_scramble(slot, base_salt + 6) % 4]
                drawn = _prepare_stamp(
                    stamp,
                    tw,
                    th,
                    flip_h=flip_h,
                    angle_deg=angle,
                    opacity=opacity,
                )
                layer.blit(
                    drawn,
                    (px - drawn.get_width() // 2, py - drawn.get_height() // 2),
                )
                placed += 1
                if placed >= 24:
                    break
            if placed >= 24:
                break
        if placed == 0 and density > 0.05 and _hash01(
            cell_x, cell_y, base_salt + ks
        ) < min(0.55, density):
            stamp = stamps[_scramble(world_key, base_salt + 7) % len(stamps)]
            jitter = 0.55 + 0.7 * (_scramble(0, base_salt + 8) / float(0x7FFFFFFF))
            tw = max(2, int(round(stamp.get_width() * scale * jitter)))
            th = max(2, int(round(stamp.get_height() * scale * jitter)))
            drawn = _prepare_stamp(
                stamp,
                tw,
                th,
                flip_h=True,
                angle_deg=(0, 90, 180, 270)[_scramble(1, base_salt + 9) % 4],
                opacity=opacity,
            )
            px = int(_hash01(cell_x, cell_y, base_salt + 10) * size)
            py = int(_hash01(cell_y, cell_x, base_salt + 11) * size)
            layer.blit(
                drawn,
                (px - drawn.get_width() // 2, py - drawn.get_height() // 2),
            )

    _CELL_CACHE[key] = layer
    dest.blit(layer, (0, 0))
    _force_opaque(dest)


def apply_overlays_to_field(
    field: pygame.Surface,
    terrain_grid: list[list[TerrainType]],
    cell_size: int,
) -> None:
    """Stamp overlays onto a multi-cell preview/game field."""
    rows = len(terrain_grid)
    cols = len(terrain_grid[0]) if rows else 0
    any_stamped = False
    for y in range(rows):
        for x in range(cols):
            terr = terrain_grid[y][x]
            try:
                from terrain_settings import get_overlay

                params = get_overlay(terr)
            except Exception:
                continue
            if not _enabled_kinds(params):
                continue
            cell = pygame.Surface((cell_size, cell_size), pygame.SRCALPHA)
            cell.fill((0, 0, 0, 0))
            stamp_cell_overlays(cell, terr, x, y, params=params)
            field.blit(cell, (x * cell_size, y * cell_size))
            any_stamped = True
    if any_stamped:
        _force_opaque(field)


def overlay_params_as_dict(params: OverlayParams) -> dict:
    return asdict(params)


def overlay_params_from_dict(data: dict) -> OverlayParams:
    names = {f.name for f in fields(OverlayParams)}
    kwargs = {k: v for k, v in data.items() if k in names}
    return OverlayParams(**kwargs)
