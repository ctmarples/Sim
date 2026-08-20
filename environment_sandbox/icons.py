"""Icon catalogue: SVG at runtime (class recolour / omit / scale); optional PNG.

Coordinate convention (Y down, matching the game)
-------------------------------------------------
* ``ICON_CELL`` (40) units = one map cell edge (SVG viewBox / PNG export space).
* The **home cell** is the tile the feature lives on. By default it is the
  **bottom-left 40×40** of the viewBox (so a 40×80 tree keeps its trunk in the
  lower cell and canopy may overlap the cell above).
* The **anchor** is the home-cell centre. That point is blitted to the map cell
  centre ``(cx, cy)``.
* PNGs are baked with ``python export_icons_png.py`` (see ``_png_anchors.json``).
  With ``settings.ICON_USE_PNG`` (default False), map/UI use SVG. Set True to
  prefer baked ``.png`` (recolour / omit / scale ignored for that blit).
  Buildings can get a soft per-shape TL→BR stipple gradient via
  ``settings.ICON_BUILDING_STIPPLE``. Stipple is baked once at full-zoom
  building size (``CELL_SIZE * ZOOM_MAX * BUILDING_FOOTPRINT``) into
  ``assets/icons/_stipple_tmp/``; lower zooms nearest-neighbour scale that
  bake so max zoom stays 1:1 pixel-sharp.

Icon variants (folder discovery)
--------------------------------
Each logical base (e.g. ``crop_plant``, ``tree_round``) resolves to files in
``assets/icons/``:

* If ``base_1.png`` / ``base_1.svg``, ``base_2…`` exist, those are the only
  variants (``base.png`` / ``base.svg`` is ignored).
* Otherwise a single ``base.png`` or ``base.svg`` is used.

``preload`` caches every discovered file. At draw time a 1-based variant index
selects among them (rolled once per cell when first drawn).

Editing art
-----------
* Prefer editing the SVG, then re-run ``export_icons_png.py``.
* SVG ``class`` still drives runtime recolour: ``canopy``, ``trunk``, ``stem``,
  ``flower``, ``body``, ``antler``, ``shadow``, building faces, etc.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable
import json
import math
import random
import re
import xml.etree.ElementTree as ET

import pygame

_ICONS_DIR = Path(__file__).resolve().parent / "assets" / "icons"
_PNG_MANIFEST_PATH = _ICONS_DIR / "_png_anchors.json"
_STIPPLE_TMP_DIR = _ICONS_DIR / "_stipple_tmp"

# Logical icon aliases for legacy/resource names used by gameplay code.
_ICON_BASE_ALIASES: dict[str, str] = {
    "meat": "meat_marker",
}

# One map cell in SVG / export units (home-cell edge).
ICON_CELL: float = 40.0

Colour = tuple[int, int, int]
Paint = tuple[int, int, int, int]  # RGBA; alpha 255 = opaque
Recolour = dict[str, Colour]

_PNG_MANIFEST: dict | None = None


@dataclass(frozen=True)
class IconImage:
    """Rasterised icon plus anchor offset in surface pixels."""

    surface: pygame.Surface
    anchor_x: int
    anchor_y: int


def icons_dir() -> Path:
    return _ICONS_DIR


def _is_icon_stem(stem: str) -> bool:
    if not stem or stem.startswith("_"):
        return False
    if " " in stem or stem.count(".") > 0:
        return False
    return True


def _has_icon_file(stem: str) -> bool:
    return (_ICONS_DIR / f"{stem}.png").is_file() or (_ICONS_DIR / f"{stem}.svg").is_file()


def list_icon_names() -> list[str]:
    if not _ICONS_DIR.is_dir():
        return []
    stems: set[str] = set()
    for path in _ICONS_DIR.glob("*.png"):
        if _is_icon_stem(path.stem):
            stems.add(path.stem)
    for path in _ICONS_DIR.glob("*.svg"):
        if _is_icon_stem(path.stem):
            stems.add(path.stem)
    return sorted(stems)


def _load_png_manifest() -> dict:
    global _PNG_MANIFEST
    if _PNG_MANIFEST is not None:
        return _PNG_MANIFEST
    if not _PNG_MANIFEST_PATH.is_file():
        _PNG_MANIFEST = {"export_cell_px": int(ICON_CELL), "icons": {}}
        return _PNG_MANIFEST
    try:
        data = json.loads(_PNG_MANIFEST_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        _PNG_MANIFEST = {"export_cell_px": int(ICON_CELL), "icons": {}}
        return _PNG_MANIFEST
    if not isinstance(data, dict):
        _PNG_MANIFEST = {"export_cell_px": int(ICON_CELL), "icons": {}}
        return _PNG_MANIFEST
    _PNG_MANIFEST = data
    return _PNG_MANIFEST


def reload_png_manifest() -> None:
    """Drop cached PNG anchor manifest (call after re-export)."""
    global _PNG_MANIFEST
    _PNG_MANIFEST = None


def _local(tag: str) -> str:
    if "}" in tag:
        return tag.rsplit("}", 1)[-1]
    return tag


def _parse_colour(value: str | None) -> Colour | None:
    if value is None:
        return None
    v = value.strip().lower()
    if v in ("none", "transparent", "null"):
        return None
    if v.startswith("#") and len(v) == 7:
        return (int(v[1:3], 16), int(v[3:5], 16), int(v[5:7], 16))
    if v.startswith("#") and len(v) == 4:
        return (int(v[1] * 2, 16), int(v[2] * 2, 16), int(v[3] * 2, 16))
    return None


def _parse_float(value: str | None, default: float = 0.0) -> float:
    if value is None or value == "":
        return default
    try:
        return float(value)
    except ValueError:
        return default


def _parse_points(points: str) -> list[tuple[float, float]]:
    raw = points.replace(",", " ").split()
    nums = [float(n) for n in raw]
    return [(nums[i], nums[i + 1]) for i in range(0, len(nums) - 1, 2)]


def _viewbox(root: ET.Element) -> tuple[float, float, float, float]:
    vb = root.get("viewBox")
    if vb:
        parts = [float(p) for p in vb.replace(",", " ").split()]
        if len(parts) == 4:
            return parts[0], parts[1], parts[2], parts[3]
    w = _parse_float(root.get("width"), 40.0)
    h = _parse_float(root.get("height"), 40.0)
    return 0.0, 0.0, w, h


def _classes(elem: ET.Element) -> set[str]:
    raw = elem.get("class") or ""
    return {c for c in raw.replace(",", " ").split() if c}


def _style_map(elem: ET.Element) -> dict[str, str]:
    raw = elem.get("style") or ""
    out: dict[str, str] = {}
    for part in raw.split(";"):
        if ":" not in part:
            continue
        key, val = part.split(":", 1)
        key, val = key.strip().lower(), val.strip()
        if key and val:
            out[key] = val
    return out


def _presentation(elem: ET.Element, name: str) -> str | None:
    """CSS ``style`` wins over presentation attributes (SVG / Inkscape)."""
    style = _style_map(elem)
    if name in style:
        return style[name]
    return elem.get(name)


def _resolve_paint(
    elem: ET.Element, attr: str, recolour: Recolour
) -> Colour | None:
    raw = _presentation(elem, attr)
    explicit = _parse_colour(raw)
    for cls in _classes(elem):
        if cls in recolour:
            # Class recolour replaces fill; only replace stroke when the SVG
            # defines a stroke colour (avoid turning fill-only shapes into outlines).
            if attr == "stroke" and (
                raw is None or raw.strip().lower() in ("", "none")
            ):
                return explicit
            return recolour[cls]
    return explicit


def _elem_opacity(elem: ET.Element, *, paint: str = "fill") -> float:
    """Combine paint-opacity with element opacity from attrs or ``style``."""
    opacity = 1.0
    for key in (f"{paint}-opacity", "opacity"):
        raw = _presentation(elem, key)
        if raw is None or raw.strip().lower() in ("", "undefined", "null"):
            continue
        try:
            opacity *= max(0.0, min(1.0, float(raw)))
        except ValueError:
            continue
    return opacity


# Affine 2D transform as row-major 2×3: x' = a*x + c*y + e, y' = b*x + d*y + f
Transform2D = tuple[float, float, float, float, float, float]
_IDENTITY: Transform2D = (1.0, 0.0, 0.0, 1.0, 0.0, 0.0)


def _mul_xform(a: Transform2D, b: Transform2D) -> Transform2D:
    """Return ``a ∘ b`` (apply b first, then a)."""
    a0, a1, a2, a3, a4, a5 = a
    b0, b1, b2, b3, b4, b5 = b
    return (
        a0 * b0 + a2 * b1,
        a1 * b0 + a3 * b1,
        a0 * b2 + a2 * b3,
        a1 * b2 + a3 * b3,
        a0 * b4 + a2 * b5 + a4,
        a1 * b4 + a3 * b5 + a5,
    )


def _apply_xform(xf: Transform2D, x: float, y: float) -> tuple[float, float]:
    a, b, c, d, e, f = xf
    return a * x + c * y + e, b * x + d * y + f


def _parse_transform(raw: str | None) -> Transform2D:
    """Parse SVG transform list into a single matrix. Unknown bits are skipped."""
    if not raw:
        return _IDENTITY
    xf = _IDENTITY
    for kind, args in re.findall(
        r"(matrix|translate|scale|rotate)\s*\(([^)]*)\)", raw
    ):
        nums = [float(n) for n in re.split(r"[,\s]+", args.strip()) if n]
        if kind == "matrix" and len(nums) >= 6:
            local = (nums[0], nums[1], nums[2], nums[3], nums[4], nums[5])
        elif kind == "translate":
            tx = nums[0] if nums else 0.0
            ty = nums[1] if len(nums) > 1 else 0.0
            local = (1.0, 0.0, 0.0, 1.0, tx, ty)
        elif kind == "scale":
            sx = nums[0] if nums else 1.0
            sy = nums[1] if len(nums) > 1 else sx
            local = (sx, 0.0, 0.0, sy, 0.0, 0.0)
        elif kind == "rotate" and nums:
            ang = math.radians(nums[0])
            cos_a, sin_a = math.cos(ang), math.sin(ang)
            local = (cos_a, sin_a, -sin_a, cos_a, 0.0, 0.0)
            if len(nums) >= 3:
                cx, cy = nums[1], nums[2]
                local = _mul_xform(
                    (1.0, 0.0, 0.0, 1.0, cx, cy),
                    _mul_xform(local, (1.0, 0.0, 0.0, 1.0, -cx, -cy)),
                )
        else:
            continue
        xf = _mul_xform(xf, local)
    return xf


def _as_paint(colour: Colour | None, alpha: float = 1.0) -> Paint | None:
    if colour is None:
        return None
    a = max(0, min(255, int(round(alpha * 255))))
    if a <= 0:
        return None
    return colour[0], colour[1], colour[2], a


def _blit_paint(
    surf: pygame.Surface,
    draw,
    paint: Paint | None,
    *,
    stipple: bool = False,
) -> None:
    """Draw with optional alpha onto an SRCALPHA surface.

    When ``stipple`` is True the paint is drawn to a temp buffer, soft
    TL→BR stipple-shaded as its own shape, then composited.
    """
    if paint is None:
        return
    if stipple:
        tmp = pygame.Surface(surf.get_size(), pygame.SRCALPHA)
        if paint[3] >= 255:
            draw(tmp, paint[:3])
        else:
            draw(tmp, paint)
        tmp = stipple_shade_surface(tmp)
        surf.blit(tmp, (0, 0))
        return
    if paint[3] >= 255:
        draw(surf, paint[:3])
        return
    # Draw into a temp buffer so RGB draws can carry per-pixel alpha.
    tmp = pygame.Surface(surf.get_size(), pygame.SRCALPHA)
    draw(tmp, paint)
    surf.blit(tmp, (0, 0))


def _scale_xy(
    x: float,
    y: float,
    *,
    origin: tuple[float, float],
    factors: tuple[float, float],
) -> tuple[float, float]:
    ox, oy = origin
    sx, sy = factors
    return ox + (x - ox) * sx, oy + (y - oy) * sy


def _elem_scale(
    elem: ET.Element, class_scales: dict[str, float]
) -> tuple[float, float]:
    scale = 1.0
    for cls in _classes(elem):
        if cls in class_scales:
            scale = class_scales[cls]
    return scale, scale


def _map_pt(
    x: float,
    y: float,
    *,
    vb: tuple[float, float, float, float],
    scale: float,
    origin: tuple[float, float],
    factors: tuple[float, float],
    xform: Transform2D = _IDENTITY,
) -> tuple[int, int]:
    x, y = _apply_xform(xform, x, y)
    x, y = _scale_xy(x, y, origin=origin, factors=factors)
    vx, vy, _vw, _vh = vb
    px = (x - vx) * scale
    py = (y - vy) * scale
    return int(round(px)), int(round(py))


def _stroke_width(elem: ET.Element, scale: float) -> int:
    sw = _parse_float(_presentation(elem, "stroke-width"), 1.0)
    return max(1, int(round(sw * scale)))


def _layout_anchor(
    root: ET.Element, vb: tuple[float, float, float, float]
) -> tuple[float, float]:
    """Return SVG-space anchor (maps to the map cell centre).

    Default: centre of the bottom-left ICON_CELL×ICON_CELL home square.
    """
    vx, vy, vw, vh = vb
    raw = root.get("data-anchor")
    if raw:
        parts = raw.replace(",", " ").split()
        if len(parts) >= 2:
            return float(parts[0]), float(parts[1])
    ax = root.get("data-anchor-x")
    ay = root.get("data-anchor-y")
    if ax is not None and ay is not None:
        return float(ax), float(ay)

    home = root.get("data-home")
    if home:
        parts = home.replace(",", " ").split()
        if len(parts) >= 3:
            hx, hy, hs = float(parts[0]), float(parts[1]), float(parts[2])
            return hx + hs / 2.0, hy + hs / 2.0

    # Bottom-left home cell inside the viewBox.
    home_x = vx
    home_y = vy + vh - ICON_CELL
    return home_x + ICON_CELL / 2.0, home_y + ICON_CELL / 2.0


def _tokenize_path(d: str) -> list[str | float]:
    """Split SVG path `d` into command letters and float args."""
    tokens: list[str | float] = []
    i = 0
    n = len(d)
    while i < n:
        ch = d[i]
        if ch in "MmLlHhVvCcQqSsTtAaZz":
            tokens.append(ch)
            i += 1
            continue
        if ch in ", \t\n\r":
            i += 1
            continue
        j = i
        if d[j] in "+-":
            j += 1
        while j < n and (d[j].isdigit() or d[j] == "."):
            j += 1
        if j < n and d[j] in "eE":
            j += 1
            if j < n and d[j] in "+-":
                j += 1
            while j < n and d[j].isdigit():
                j += 1
        if j == i:
            i += 1
            continue
        tokens.append(float(d[i:j]))
        i = j
    return tokens


def _cubic_points(
    p0: tuple[float, float],
    p1: tuple[float, float],
    p2: tuple[float, float],
    p3: tuple[float, float],
    steps: int | None = None,
) -> list[tuple[float, float]]:
    if steps is None:
        # Adaptive: short Inkscape LPE wiggles don't need many samples.
        span = max(
            abs(p3[0] - p0[0]),
            abs(p3[1] - p0[1]),
            abs(p1[0] - p0[0]),
            abs(p1[1] - p0[1]),
            abs(p2[0] - p3[0]),
            abs(p2[1] - p3[1]),
        )
        steps = 2 if span < 0.5 else 4 if span < 2.0 else 8
    out: list[tuple[float, float]] = []
    for i in range(1, steps + 1):
        t = i / steps
        u = 1.0 - t
        x = (
            u * u * u * p0[0]
            + 3 * u * u * t * p1[0]
            + 3 * u * t * t * p2[0]
            + t * t * t * p3[0]
        )
        y = (
            u * u * u * p0[1]
            + 3 * u * u * t * p1[1]
            + 3 * u * t * t * p2[1]
            + t * t * t * p3[1]
        )
        out.append((x, y))
    return out


def _quad_points(
    p0: tuple[float, float],
    p1: tuple[float, float],
    p2: tuple[float, float],
    steps: int = 8,
) -> list[tuple[float, float]]:
    out: list[tuple[float, float]] = []
    for i in range(1, steps + 1):
        t = i / steps
        u = 1.0 - t
        x = u * u * p0[0] + 2 * u * t * p1[0] + t * t * p2[0]
        y = u * u * p0[1] + 2 * u * t * p1[1] + t * t * p2[1]
        out.append((x, y))
    return out


def _arc_points(
    p0: tuple[float, float],
    p1: tuple[float, float],
    rx: float,
    ry: float,
    x_axis_rot_deg: float,
    large_arc: bool,
    sweep: bool,
    steps: int = 12,
) -> list[tuple[float, float]]:
    """Approximate an SVG elliptical arc as a polyline (endpoint-parameterised)."""
    x1, y1 = p0
    x2, y2 = p1
    if rx <= 1e-9 or ry <= 1e-9 or (abs(x1 - x2) < 1e-9 and abs(y1 - y2) < 1e-9):
        return [p1]

    phi = math.radians(x_axis_rot_deg % 360.0)
    cos_phi, sin_phi = math.cos(phi), math.sin(phi)

    # Midpoint relative coords.
    dx = (x1 - x2) / 2.0
    dy = (y1 - y2) / 2.0
    x1p = cos_phi * dx + sin_phi * dy
    y1p = -sin_phi * dx + cos_phi * dy

    # Ensure radii are large enough.
    lam = (x1p * x1p) / (rx * rx) + (y1p * y1p) / (ry * ry)
    if lam > 1.0:
        s = math.sqrt(lam)
        rx *= s
        ry *= s

    rx2, ry2 = rx * rx, ry * ry
    x1p2, y1p2 = x1p * x1p, y1p * y1p
    num = rx2 * ry2 - rx2 * y1p2 - ry2 * x1p2
    den = rx2 * y1p2 + ry2 * x1p2
    if den <= 1e-12:
        return [p1]
    co = math.sqrt(max(0.0, num / den))
    if large_arc == sweep:
        co = -co
    cxp = co * (rx * y1p) / ry
    cyp = co * (-ry * x1p) / rx

    cx = cos_phi * cxp - sin_phi * cyp + (x1 + x2) / 2.0
    cy = sin_phi * cxp + cos_phi * cyp + (y1 + y2) / 2.0

    def angle(ux: float, uy: float, vx: float, vy: float) -> float:
        dot = ux * vx + uy * vy
        n = math.hypot(ux, uy) * math.hypot(vx, vy)
        if n <= 1e-12:
            return 0.0
        ang = math.acos(max(-1.0, min(1.0, dot / n)))
        if ux * vy - uy * vx < 0:
            ang = -ang
        return ang

    start = angle(1.0, 0.0, (x1p - cxp) / rx, (y1p - cyp) / ry)
    delta = angle(
        (x1p - cxp) / rx,
        (y1p - cyp) / ry,
        (-x1p - cxp) / rx,
        (-y1p - cyp) / ry,
    )
    if not sweep and delta > 0:
        delta -= 2 * math.pi
    elif sweep and delta < 0:
        delta += 2 * math.pi

    out: list[tuple[float, float]] = []
    n = max(2, int(round(steps * abs(delta) / math.pi)))
    for i in range(1, n + 1):
        t = start + delta * (i / n)
        x = rx * math.cos(t)
        y = ry * math.sin(t)
        out.append(
            (
                cos_phi * x - sin_phi * y + cx,
                sin_phi * x + cos_phi * y + cy,
            )
        )
    return out


def _path_subpaths(d: str) -> list[list[tuple[float, float]]]:
    """Flatten path `d` into polylines (absolute coords) for fill/stroke."""
    tokens = _tokenize_path(d)
    subpaths: list[list[tuple[float, float]]] = []
    pts: list[tuple[float, float]] = []
    i = 0
    cx = cy = 0.0
    start = (0.0, 0.0)
    last_c: tuple[float, float] | None = None

    def take(n: int) -> list[float]:
        nonlocal i
        vals = [float(tokens[i + k]) for k in range(n)]
        i += n
        return vals

    while i < len(tokens):
        cmd = tokens[i]
        if not isinstance(cmd, str):
            # Implicit repeat of previous command — shouldn't happen often.
            break
        i += 1
        absolute = cmd.isupper()
        op = cmd.upper()

        if op == "Z":
            if pts:
                pts.append(start)
                subpaths.append(pts)
                pts = []
            cx, cy = start
            last_c = None
            continue

        if op == "M":
            if pts:
                subpaths.append(pts)
                pts = []
            vals = take(2)
            x, y = vals
            if not absolute:
                x += cx
                y += cy
            cx, cy = x, y
            start = (cx, cy)
            pts = [(cx, cy)]
            last_c = None
            # Extra pairs are treated as LineTos.
            while i < len(tokens) and not isinstance(tokens[i], str):
                vals = take(2)
                x, y = vals
                if not absolute:
                    x += cx
                    y += cy
                cx, cy = x, y
                pts.append((cx, cy))
            continue

        if op == "L":
            while i < len(tokens) and not isinstance(tokens[i], str):
                vals = take(2)
                x, y = vals
                if not absolute:
                    x += cx
                    y += cy
                cx, cy = x, y
                pts.append((cx, cy))
                last_c = None
            continue

        if op == "H":
            while i < len(tokens) and not isinstance(tokens[i], str):
                x = take(1)[0]
                if not absolute:
                    x += cx
                cx = x
                pts.append((cx, cy))
                last_c = None
            continue

        if op == "V":
            while i < len(tokens) and not isinstance(tokens[i], str):
                y = take(1)[0]
                if not absolute:
                    y += cy
                cy = y
                pts.append((cx, cy))
                last_c = None
            continue

        if op == "C":
            while i + 5 < len(tokens) and not isinstance(tokens[i], str):
                vals = take(6)
                x1, y1, x2, y2, x, y = vals
                if not absolute:
                    x1 += cx
                    y1 += cy
                    x2 += cx
                    y2 += cy
                    x += cx
                    y += cy
                pts.extend(
                    _cubic_points((cx, cy), (x1, y1), (x2, y2), (x, y))
                )
                last_c = (x2, y2)
                cx, cy = x, y
            continue

        if op == "S":
            while i + 3 < len(tokens) and not isinstance(tokens[i], str):
                vals = take(4)
                x2, y2, x, y = vals
                if not absolute:
                    x2 += cx
                    y2 += cy
                    x += cx
                    y += cy
                if last_c is not None:
                    x1 = 2 * cx - last_c[0]
                    y1 = 2 * cy - last_c[1]
                else:
                    x1, y1 = cx, cy
                pts.extend(
                    _cubic_points((cx, cy), (x1, y1), (x2, y2), (x, y))
                )
                last_c = (x2, y2)
                cx, cy = x, y
            continue

        if op == "Q":
            while i + 3 < len(tokens) and not isinstance(tokens[i], str):
                vals = take(4)
                x1, y1, x, y = vals
                if not absolute:
                    x1 += cx
                    y1 += cy
                    x += cx
                    y += cy
                pts.extend(_quad_points((cx, cy), (x1, y1), (x, y)))
                last_c = (x1, y1)
                cx, cy = x, y
            continue

        if op == "T":
            while i + 1 < len(tokens) and not isinstance(tokens[i], str):
                vals = take(2)
                x, y = vals
                if not absolute:
                    x += cx
                    y += cy
                if last_c is not None:
                    x1 = 2 * cx - last_c[0]
                    y1 = 2 * cy - last_c[1]
                else:
                    x1, y1 = cx, cy
                pts.extend(_quad_points((cx, cy), (x1, y1), (x, y)))
                last_c = (x1, y1)
                cx, cy = x, y
            continue

        if op == "A":
            # Sample elliptical arcs (Inkscape PowerStroke / LPE paths use these).
            while i + 6 < len(tokens) and not isinstance(tokens[i], str):
                vals = take(7)
                rx, ry, rot_deg, large, sweep, x, y = vals
                if not absolute:
                    x += cx
                    y += cy
                pts.extend(
                    _arc_points(
                        (cx, cy),
                        (x, y),
                        abs(rx),
                        abs(ry),
                        rot_deg,
                        bool(large),
                        bool(sweep),
                    )
                )
                cx, cy = x, y
                last_c = None
            continue

        # Unknown command — abort this path.
        break

    if pts:
        subpaths.append(pts)
    return subpaths


def _rasterise_svg(
    path: Path,
    cell_px: int,
    recolour: Recolour,
    class_scales: dict[str, float],
    omit_classes: set[str],
    *,
    stipple: bool = False,
) -> IconImage:
    tree = ET.parse(path)
    root = tree.getroot()
    vb = _viewbox(root)
    scale = cell_px / ICON_CELL
    surf_w = max(1, int(round(vb[2] * scale)))
    surf_h = max(1, int(round(vb[3] * scale)))
    surf = pygame.Surface((surf_w, surf_h), pygame.SRCALPHA)
    surf.fill((0, 0, 0, 0))
    anchor = _layout_anchor(root, vb)
    # class_scales grow/shrink around the home-cell anchor.
    origin = anchor

    def walk(elem: ET.Element, xform: Transform2D = _IDENTITY) -> None:
        tag = _local(elem.tag)
        if tag in ("defs", "namedview", "metadata", "style", "clipPath", "mask"):
            return
        if omit_classes and _classes(elem) & omit_classes:
            return
        local_xf = _parse_transform(elem.get("transform"))
        xform = _mul_xform(xform, local_xf)
        factors = _elem_scale(elem, class_scales)
        fill_rgb = _resolve_paint(elem, "fill", recolour)
        stroke_rgb = _resolve_paint(elem, "stroke", recolour)
        # Default SVG fill is black when omitted (except for some tags).
        if (
            fill_rgb is None
            and _presentation(elem, "fill") is None
            and tag not in ("g", "svg", "title", "desc")
        ):
            if stroke_rgb is None and tag not in ("title", "desc"):
                fill_rgb = (0, 0, 0)
        fill = _as_paint(fill_rgb, _elem_opacity(elem, paint="fill"))
        stroke = _as_paint(stroke_rgb, _elem_opacity(elem, paint="stroke"))

        def map_xy(x: float, y: float) -> tuple[int, int]:
            return _map_pt(
                x, y, vb=vb, scale=scale, origin=origin, factors=factors, xform=xform
            )

        if tag in ("svg", "g"):
            for child in elem:
                walk(child, xform)
            return
        if tag in ("title", "desc"):
            return

        if tag == "rect":
            x = _parse_float(elem.get("x"))
            y = _parse_float(elem.get("y"))
            w = _parse_float(elem.get("width"))
            h = _parse_float(elem.get("height"))
            corners = [
                map_xy(x, y),
                map_xy(x + w, y),
                map_xy(x + w, y + h),
                map_xy(x, y + h),
            ]
            xs = [p[0] for p in corners]
            ys = [p[1] for p in corners]
            rect = pygame.Rect(min(xs), min(ys), max(xs) - min(xs), max(ys) - min(ys))
            _blit_paint(
                surf, lambda s, c: pygame.draw.rect(s, c, rect), fill, stipple=stipple
            )
            if stroke is not None:
                sw = _stroke_width(elem, scale)
                _blit_paint(
                    surf, lambda s, c, _sw=sw: pygame.draw.rect(s, c, rect, _sw), stroke
                )
            return

        if tag == "circle":
            cx = _parse_float(elem.get("cx"))
            cy = _parse_float(elem.get("cy"))
            r = _parse_float(elem.get("r"))
            c = map_xy(cx, cy)
            # Approximate radius under uniform scale; non-uniform transforms use avg.
            edge = map_xy(cx + r, cy)
            pr = max(1, int(round(math.hypot(edge[0] - c[0], edge[1] - c[1]))))
            _blit_paint(
                surf,
                lambda s, col: pygame.draw.circle(s, col, c, pr),
                fill,
                stipple=stipple,
            )
            if stroke is not None:
                sw = _stroke_width(elem, scale)
                _blit_paint(
                    surf,
                    lambda s, col, _sw=sw: pygame.draw.circle(s, col, c, pr, _sw),
                    stroke,
                )
            return

        if tag == "ellipse":
            cx = _parse_float(elem.get("cx"))
            cy = _parse_float(elem.get("cy"))
            rx = _parse_float(elem.get("rx"))
            ry = _parse_float(elem.get("ry"))
            c = map_xy(cx, cy)
            ex = map_xy(cx + rx, cy)
            ey = map_xy(cx, cy + ry)
            prx = max(1, int(round(abs(ex[0] - c[0]))))
            pry = max(1, int(round(abs(ey[1] - c[1]))))
            rect = pygame.Rect(c[0] - prx, c[1] - pry, prx * 2, pry * 2)
            _blit_paint(
                surf,
                lambda s, col: pygame.draw.ellipse(s, col, rect),
                fill,
                stipple=stipple,
            )
            if stroke is not None:
                sw = _stroke_width(elem, scale)
                _blit_paint(
                    surf,
                    lambda s, col, _sw=sw: pygame.draw.ellipse(s, col, rect, _sw),
                    stroke,
                )
            return

        if tag == "line":
            x1 = _parse_float(elem.get("x1"))
            y1 = _parse_float(elem.get("y1"))
            x2 = _parse_float(elem.get("x2"))
            y2 = _parse_float(elem.get("y2"))
            p1 = map_xy(x1, y1)
            p2 = map_xy(x2, y2)
            colour = stroke if stroke is not None else fill
            if colour is not None:
                sw = _stroke_width(elem, scale)
                _blit_paint(
                    surf,
                    lambda s, col, _sw=sw: pygame.draw.line(s, col, p1, p2, _sw),
                    colour,
                )
            return

        if tag in ("polygon", "polyline"):
            pts = [
                map_xy(px, py)
                for px, py in _parse_points(elem.get("points") or "")
            ]
            if len(pts) < 2:
                return
            if tag == "polygon":
                _blit_paint(
                    surf,
                    lambda s, col: pygame.draw.polygon(s, col, pts),
                    fill,
                    stipple=stipple,
                )
                if stroke is not None:
                    sw = _stroke_width(elem, scale)
                    _blit_paint(
                        surf,
                        lambda s, col, _sw=sw: pygame.draw.polygon(s, col, pts, _sw),
                        stroke,
                    )
            else:
                colour = stroke if stroke is not None else fill
                if colour is not None:
                    sw = _stroke_width(elem, scale)
                    _blit_paint(
                        surf,
                        lambda s, col, _sw=sw: pygame.draw.lines(
                            s, col, False, pts, _sw
                        ),
                        colour,
                    )
            return

        if tag == "path":
            d = elem.get("d") or ""
            sw = _stroke_width(elem, scale)
            for sub in _path_subpaths(d):
                pts = [map_xy(px, py) for px, py in sub]
                if len(pts) < 2:
                    continue
                closed = (
                    abs(sub[0][0] - sub[-1][0]) < 1e-6
                    and abs(sub[0][1] - sub[-1][1]) < 1e-6
                )
                if fill is not None and closed and len(pts) >= 3:
                    _blit_paint(
                        surf,
                        lambda s, col, _pts=pts: pygame.draw.polygon(s, col, _pts),
                        fill,
                        stipple=stipple,
                    )
                if stroke is not None:
                    _blit_paint(
                        surf,
                        lambda s, col, _pts=pts, _sw=sw, _cl=closed: pygame.draw.lines(
                            s, col, _cl, _pts, _sw
                        ),
                        stroke,
                    )
                elif fill is not None and not closed:
                    _blit_paint(
                        surf,
                        lambda s, col, _pts=pts, _sw=sw: pygame.draw.lines(
                            s, col, False, _pts, _sw
                        ),
                        fill,
                    )
            return

        for child in elem:
            walk(child, xform)

    walk(root)
    ax = int(round((anchor[0] - vb[0]) * scale))
    ay = int(round((anchor[1] - vb[1]) * scale))
    return IconImage(surface=surf, anchor_x=ax, anchor_y=ay)


def stipple_shade_surface(surf: pygame.Surface) -> pygame.Surface:
    """Soft TL→BR stipple gradient over a filled shape's own bounds.

    Light speckles denser toward the top-left, dark speckles toward the
    bottom-right. Transition is continuous (smoothstep) so there is no hard
    lighting edge. Baked fill luminance still modulates intensity.
    """
    import numpy as np

    w, h = surf.get_size()
    if w < 2 or h < 2:
        return surf

    rgba = pygame.surfarray.array3d(surf).transpose(1, 0, 2).astype(np.float32)
    alpha = pygame.surfarray.array_alpha(surf).T.astype(np.float32) / 255.0
    mask = alpha > (24.0 / 255.0)
    if int(mask.sum()) < 8:
        return surf

    yy, xx = np.mgrid[0:h, 0:w]
    ys = yy[mask]
    xs = xx[mask]
    min_x = float(xs.min())
    max_x = float(xs.max())
    min_y = float(ys.min())
    max_y = float(ys.max())
    span_x = max(1.0, max_x - min_x)
    span_y = max(1.0, max_y - min_y)
    # 0 at top-left of this shape, 1 at bottom-right.
    u = np.clip((xx.astype(np.float32) - min_x) / span_x, 0.0, 1.0)
    v = np.clip((yy.astype(np.float32) - min_y) / span_y, 0.0, 1.0)
    t = 0.5 * (u + v)
    # Soften the diagonal so midtones blend — no hard light/dark cut.
    t = t * t * (3.0 - 2.0 * t)

    tone = (
        0.299 * rgba[:, :, 0] + 0.587 * rgba[:, :, 1] + 0.114 * rgba[:, :, 2]
    ) / 255.0

    def _noise(salt: int) -> np.ndarray:
        n = ((xx * 374761393 + yy * 668265263 + salt * 982451653) & 0xFFFFFFFF).astype(
            np.uint32
        )
        n = ((n ^ (n >> 13)) * np.uint32(1274126177)) & 0xFFFFFFFF
        return (n & 0xFFFFFF).astype(np.float32) / float(0xFFFFFF)

    n1 = _noise(11)
    n2 = _noise(29)
    n3 = _noise(7)

    # Continuous bright/dark probabilities: overlap in the middle, fade at ends.
    bright_p = 0.38 * ((1.0 - t) ** 1.55) * (0.30 + 0.70 * tone)
    dark_p = 0.42 * (t ** 1.55) * (0.40 + 0.60 * (1.0 - tone))
    light_hit = mask & (n1 < bright_p)
    dark_hit = mask & (n2 < dark_p)

    out = rgba.copy()
    # Brighten toward white with a slight warm bias (stronger near TL).
    amt = (0.10 + 0.26 * (1.0 - t)) * (0.45 + 0.55 * (n3 > 0.45).astype(np.float32))
    for c, warm in ((0, 1.0), (1, 0.92), (2, 0.78)):
        out[:, :, c] = np.where(
            light_hit,
            np.clip(rgba[:, :, c] + (255.0 - rgba[:, :, c]) * amt * warm, 0, 255),
            out[:, :, c],
        )
    hot = light_hit & (n3 > 0.90) & (t < 0.45)
    out[:, :, 0] = np.where(hot, np.clip(out[:, :, 0] + 14, 0, 255), out[:, :, 0])
    out[:, :, 1] = np.where(hot, np.clip(out[:, :, 1] + 9, 0, 255), out[:, :, 1])

    # Darken toward shade (stronger near BR); keep a touch of blue in deep dots.
    dark = (0.08 + 0.30 * t) * (0.50 + 0.50 * (n3 < 0.55).astype(np.float32))
    out[:, :, 0] = np.where(
        dark_hit, np.clip(out[:, :, 0] * (1.0 - dark), 0, 255), out[:, :, 0]
    )
    out[:, :, 1] = np.where(
        dark_hit, np.clip(out[:, :, 1] * (1.0 - dark * 0.95), 0, 255), out[:, :, 1]
    )
    out[:, :, 2] = np.where(
        dark_hit, np.clip(out[:, :, 2] * (1.0 - dark * 0.85), 0, 255), out[:, :, 2]
    )

    # Soften a fraction of stipple pixels so grain isn't pure salt-and-pepper.
    soft = out.copy()
    blur = mask & (n3 >= 0.62)
    for c in range(3):
        acc = np.zeros((h, w), dtype=np.float32)
        cnt = np.zeros((h, w), dtype=np.float32)
        ch = out[:, :, c]
        for dy in (-1, 0, 1):
            for dx_ in (-1, 0, 1):
                rolled = np.roll(np.roll(ch, dy, axis=0), dx_, axis=1)
                mroll = np.roll(
                    np.roll(mask.astype(np.float32), dy, axis=0), dx_, axis=1
                )
                acc += rolled * mroll
                cnt += mroll
        mean = np.where(cnt > 0, acc / np.maximum(cnt, 1.0), ch)
        soft[:, :, c] = np.where(blur, 0.75 * ch + 0.25 * mean, ch)

    result = surf.copy()
    pix = pygame.surfarray.pixels3d(result)
    pix[:, :, :] = soft.transpose(1, 0, 2).astype(np.uint8)
    del pix
    return result


def _cache_key(
    name: str,
    cell_px: int,
    recolour: Recolour | None,
    class_scales: dict[str, float] | None,
    omit_classes: frozenset[str] | None,
    mtime_ns: int,
    *,
    stipple: bool = False,
) -> tuple:
    rc = tuple(sorted((k, v) for k, v in (recolour or {}).items()))
    sc = tuple(sorted((k, round(v, 3)) for k, v in (class_scales or {}).items()))
    oc = tuple(sorted(omit_classes or ()))
    return (name, cell_px, rc, sc, oc, mtime_ns, bool(stipple))


def _stipple_native_px() -> int:
    """Bake size for building stipple — 1:1 at full zoom (footprint draw size)."""
    try:
        from settings import BUILDING_FOOTPRINT, CELL_SIZE, ZOOM_MAX

        return max(
            4,
            int(round(float(CELL_SIZE) * float(ZOOM_MAX) * float(BUILDING_FOOTPRINT))),
        )
    except Exception:
        return max(4, int(ICON_CELL) * 3)


def _stipple_variant_token(
    recolour: Recolour | None,
    class_scales: dict[str, float] | None,
    omit_classes: frozenset[str] | None,
) -> str:
    """Stable short id for tmp PNG filenames (recolour / scale / omit)."""
    import hashlib

    payload = json.dumps(
        {
            "rc": sorted((k, list(v)) for k, v in (recolour or {}).items()),
            "sc": sorted((k, round(v, 3)) for k, v in (class_scales or {}).items()),
            "oc": sorted(omit_classes or ()),
        },
        separators=(",", ":"),
    )
    return hashlib.sha1(payload.encode("utf-8")).hexdigest()[:10]


def _stipple_tmp_paths(
    name: str, mtime_ns: int, token: str, *, tile_px: int
) -> tuple[Path, Path]:
    stem = f"{name}_{mtime_ns}_{int(tile_px)}_{token}"
    return _STIPPLE_TMP_DIR / f"{stem}.png", _STIPPLE_TMP_DIR / f"{stem}.json"


def _scale_icon_image(icon: IconImage, cell_px: int, native_px: int) -> IconImage:
    """Nearest-neighbour scale so stipple pixels stay sharp (no smooth blur)."""
    scale = float(cell_px) / float(max(1, native_px))
    if abs(scale - 1.0) <= 1e-6:
        return icon
    tw = max(1, int(round(icon.surface.get_width() * scale)))
    th = max(1, int(round(icon.surface.get_height() * scale)))
    surf = pygame.transform.scale(icon.surface, (tw, th))
    return IconImage(
        surface=surf,
        anchor_x=int(round(icon.anchor_x * scale)),
        anchor_y=int(round(icon.anchor_y * scale)),
    )


def _load_stipple_tmp(
    png_path: Path, meta_path: Path, *, tile_px: int
) -> IconImage | None:
    if not png_path.is_file() or not meta_path.is_file():
        return None
    try:
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        if int(meta.get("tile_px", -1)) != int(tile_px):
            return None
        surf = pygame.image.load(str(png_path)).convert_alpha()
    except (OSError, ValueError, json.JSONDecodeError, pygame.error, TypeError):
        return None
    return IconImage(
        surface=surf,
        anchor_x=int(meta.get("anchor_x", surf.get_width() // 2)),
        anchor_y=int(meta.get("anchor_y", surf.get_height() // 2)),
    )


def _save_stipple_tmp(icon: IconImage, png_path: Path, meta_path: Path, *, tile_px: int) -> None:
    try:
        _STIPPLE_TMP_DIR.mkdir(parents=True, exist_ok=True)
        pygame.image.save(icon.surface, str(png_path))
        meta_path.write_text(
            json.dumps(
                {
                    "anchor_x": icon.anchor_x,
                    "anchor_y": icon.anchor_y,
                    "tile_px": int(tile_px),
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
    except OSError:
        pass


_SURFACE_CACHE: dict[tuple, IconImage] = {}
_HIT_CACHE: dict[tuple, IconImage] = {}
_VARIANT_CACHE: dict[str, tuple[str, ...]] = {}


def clear_cache() -> None:
    _SURFACE_CACHE.clear()
    _HIT_CACHE.clear()
    _VARIANT_CACHE.clear()
    reload_png_manifest()


def variant_names(base: str) -> tuple[str, ...]:
    """Return concrete icon stems for a logical icon base.

    Numbered convention wins exclusively when present:
    ``base_1.png``/``.svg``, ``base_2…`` (plain ``base`` is then unused).
    If no numbered files exist, falls back to a single ``base`` file.
    """
    base = _ICON_BASE_ALIASES.get(base, base)
    cached = _VARIANT_CACHE.get(base)
    if cached is not None:
        return cached
    numbered: list[str] = []
    i = 1
    while True:
        stem = f"{base}_{i}"
        if not _has_icon_file(stem):
            break
        numbered.append(stem)
        i += 1
    if numbered:
        result = tuple(numbered)
    elif _has_icon_file(base):
        result = (base,)
    else:
        result = ()
    _VARIANT_CACHE[base] = result
    return result


def has_icon_variants(base: str) -> bool:
    return len(variant_names(base)) > 1


def refresh_variant_index() -> None:
    """Drop discovered variant lists so the next lookup re-scans the folder."""
    _VARIANT_CACHE.clear()

def roll_icon_variant(base: str, rng: random.Random) -> int:
    """Pick a 1-based variant index for ``base`` (stable for single-file icons)."""
    names = variant_names(base)
    if len(names) <= 1:
        return 1
    return int(rng.randint(1, len(names)))


def resolve_icon_name(base: str, variant: int | None = None) -> str:
    """Map logical base + optional 1-based variant to a concrete icon stem."""
    names = variant_names(base)
    if not names:
        raise FileNotFoundError(f"No icon for base '{base}' in {_ICONS_DIR}")
    if len(names) == 1:
        return names[0]
    idx = 0 if variant is None else max(0, int(variant) - 1)
    return names[idx % len(names)]


def ensure_icon_variant(
    base: str,
    current: int | None,
    rng: random.Random,
) -> int:
    """Return a variant index, rolling once when ``current`` is unset."""
    names = variant_names(base)
    if not names:
        return 1
    if current is not None and 1 <= current <= len(names):
        return current
    if current is not None and len(names) == 1:
        return 1
    return roll_icon_variant(base, rng)



def _load_png_icon(name: str, cell_px: int) -> IconImage | None:
    """Load a baked PNG and scale anchors/surface to ``cell_px``."""
    path = _ICONS_DIR / f"{name}.png"
    if not path.is_file() or path.stat().st_size == 0:
        return None
    manifest = _load_png_manifest()
    export_cell = int(manifest.get("export_cell_px") or ICON_CELL)
    meta = (manifest.get("icons") or {}).get(name) or {}
    try:
        surf = pygame.image.load(str(path)).convert_alpha()
    except pygame.error:
        return None
    ax = int(meta.get("anchor_x", surf.get_width() // 2))
    ay = int(meta.get("anchor_y", surf.get_height() // 2))
    scale = float(cell_px) / float(max(1, export_cell))
    if abs(scale - 1.0) > 1e-6:
        tw = max(1, int(round(surf.get_width() * scale)))
        th = max(1, int(round(surf.get_height() * scale)))
        surf = pygame.transform.smoothscale(surf, (tw, th))
        ax = int(round(ax * scale))
        ay = int(round(ay * scale))
    return IconImage(surface=surf, anchor_x=ax, anchor_y=ay)


def _prefer_png() -> bool:
    try:
        from settings import ICON_USE_PNG

        return bool(ICON_USE_PNG)
    except Exception:
        return False


def get_icon(
    name: str,
    cell_px: int,
    *,
    recolour: Recolour | None = None,
    class_scales: dict[str, float] | None = None,
    omit_classes: Iterable[str] | None = None,
    prefer_png: bool | None = None,
    stipple: bool = False,
) -> IconImage:
    """Return a cached icon for ``name`` at ``cell_px`` pixels per map cell.

    When ``prefer_png`` (default: ``settings.ICON_USE_PNG``) is True and a
    ``.png`` exists, that file is used even if recolour kwargs were passed
    (baked colours; class tint / omit / scale do not apply). When False,
    ``.svg`` is preferred whenever present so the SVG pipeline runs; PNG is
    only a fallback if no SVG exists.

    ``stipple`` bakes a soft per-shape TL→BR gradient once at full-zoom
    building size, writing ``_stipple_tmp`` PNGs, then nearest-neighbour
    scales for lower zoom (max zoom stays 1:1).
    """
    cell_px = max(4, int(cell_px))
    omit = frozenset(omit_classes) if omit_classes else None
    want_png = _prefer_png() if prefer_png is None else bool(prefer_png)
    want_stipple = bool(stipple)
    rc = tuple(sorted((k, v) for k, v in (recolour or {}).items()))
    sc = tuple(sorted((k, round(v, 3)) for k, v in (class_scales or {}).items()))
    oc = tuple(sorted(omit or ()))
    hit_key = (name, cell_px, rc, sc, oc, want_png, want_stipple)
    hit = _HIT_CACHE.get(hit_key)
    if hit is not None:
        return hit
    png_hit_key = (name, cell_px, (), (), (), True, want_stipple)
    if want_png:
        hit = _HIT_CACHE.get(png_hit_key)
        if hit is not None:
            _HIT_CACHE[hit_key] = hit
            return hit

    def remember(icon: IconImage) -> IconImage:
        _HIT_CACHE[hit_key] = icon
        if want_png:
            _HIT_CACHE[png_hit_key] = icon
        return icon

    png_path = _ICONS_DIR / f"{name}.png"
    svg_path = _ICONS_DIR / f"{name}.svg"
    tile_px = _stipple_native_px() if want_stipple else cell_px

    if want_png and png_path.is_file():
        path = png_path
        source = "png"
        # Baked PNG: ignore class recolour / omit / scale in the cache key so
        # all callers share one surface per size.
        recolour = None
        class_scales = None
        omit = None
    elif svg_path.is_file():
        path = svg_path
        source = "svg"
    elif png_path.is_file():
        path = png_path
        source = "png"
    else:
        raise FileNotFoundError(f"Icon not found: {name}.png / {name}.svg")
    if path.stat().st_size == 0:
        raise FileNotFoundError(f"Icon file is empty: {path}")
    mtime_ns = path.stat().st_mtime_ns

    # Stipple: serve from a single tile-resolution bake; scale for zoom.
    if want_stipple and cell_px != tile_px:
        base = get_icon(
            name,
            tile_px,
            recolour=recolour,
            class_scales=class_scales,
            omit_classes=omit,
            prefer_png=prefer_png,
            stipple=True,
        )
        key = _cache_key(
            f"{source}:{name}",
            cell_px,
            recolour,
            class_scales,
            omit,
            mtime_ns,
            stipple=True,
        )
        cached = _SURFACE_CACHE.get(key)
        if cached is not None:
            return remember(cached)
        icon = _scale_icon_image(base, cell_px, tile_px)
        _SURFACE_CACHE[key] = icon
        return remember(icon)

    key = _cache_key(
        f"{source}:{name}",
        cell_px,
        recolour,
        class_scales,
        omit,
        mtime_ns,
        stipple=want_stipple,
    )
    cached = _SURFACE_CACHE.get(key)
    if cached is not None:
        return remember(cached)

    if want_stipple:
        token = _stipple_variant_token(recolour, class_scales, omit)
        tmp_png, tmp_meta = _stipple_tmp_paths(
            f"{source}_{name}", mtime_ns, token, tile_px=tile_px
        )
        loaded = _load_stipple_tmp(tmp_png, tmp_meta, tile_px=tile_px)
        if loaded is not None:
            _SURFACE_CACHE[key] = loaded
            return remember(loaded)

    if source == "png":
        icon = _load_png_icon(name, cell_px)
        if icon is None:
            raise FileNotFoundError(f"Icon PNG failed to load: {path}")
        if want_stipple:
            shaded = stipple_shade_surface(icon.surface)
            icon = IconImage(
                surface=shaded, anchor_x=icon.anchor_x, anchor_y=icon.anchor_y
            )
    else:
        try:
            icon = _rasterise_svg(
                path,
                cell_px,
                recolour or {},
                class_scales or {},
                set(omit) if omit else set(),
                stipple=want_stipple,
            )
        except ET.ParseError as exc:
            raise FileNotFoundError(f"Icon SVG is invalid ({path.name}): {exc}") from exc

    if want_stipple:
        token = _stipple_variant_token(recolour, class_scales, omit)
        tmp_png, tmp_meta = _stipple_tmp_paths(
            f"{source}_{name}", mtime_ns, token, tile_px=tile_px
        )
        _save_stipple_tmp(icon, tmp_png, tmp_meta, tile_px=tile_px)

    _SURFACE_CACHE[key] = icon
    return remember(icon)



def blit_icon(
    surface: pygame.Surface,
    name: str,
    cx: int,
    cy: int,
    cell_px: int,
    *,
    variant: int | None = None,
    recolour: Recolour | None = None,
    class_scales: dict[str, float] | None = None,
    omit_classes: Iterable[str] | None = None,
    prefer_png: bool | None = None,
    stipple: bool = False,
) -> pygame.Rect:
    """Blit icon so its anchor lands on (cx, cy).

    ``name`` is a logical base (``crop_plant``) or concrete stem; numbered
    variants are resolved via ``variant`` (1-based).
    """
    stem = resolve_icon_name(name, variant)
    try:
        icon = get_icon(
            stem,
            cell_px,
            recolour=recolour,
            class_scales=class_scales,
            omit_classes=omit_classes,
            prefer_png=prefer_png,
            stipple=stipple,
        )
    except (FileNotFoundError, OSError):
        return pygame.Rect(cx, cy, 0, 0)
    dest = pygame.Rect(
        cx - icon.anchor_x,
        cy - icon.anchor_y,
        icon.surface.get_width(),
        icon.surface.get_height(),
    )
    surface.blit(icon.surface, dest.topleft)
    return dest


def preload(
    names: Iterable[str] | None = None,
    *,
    sizes: Iterable[int] = (40,),
) -> int:
    """Rasterise / load every available variant into the cache.

    For each logical base, caches ``base_1``…``base_N`` when those files exist,
    otherwise ``base``. With ``names=None``, every icon stem on disk is loaded.
    """
    refresh_variant_index()
    if names is None:
        targets = list_icon_names()
    else:
        targets = []
        seen: set[str] = set()
        for base in names:
            variants = variant_names(base)
            stems = variants if variants else (
                (base,) if _has_icon_file(base) else ()
            )
            for stem in stems:
                if stem not in seen:
                    targets.append(stem)
                    seen.add(stem)
    before = len(_SURFACE_CACHE)
    for name in targets:
        for size in sizes:
            get_icon(name, size)
    return len(_SURFACE_CACHE) - before


def preload_building_stipple(
    names: Iterable[str] | None = None,
    *,
    tile_px: int | None = None,
) -> int:
    """Bake building stipple PNGs once at full-zoom pixel size.

    Writes ``assets/icons/_stipple_tmp/`` and warms the surface cache so zoom
    only nearest-neighbour scales. No-op when ``ICON_BUILDING_STIPPLE`` is False.
    """
    try:
        from settings import ICON_BUILDING_STIPPLE
    except Exception:
        ICON_BUILDING_STIPPLE = True
    if not ICON_BUILDING_STIPPLE:
        return 0
    px = max(4, int(tile_px if tile_px is not None else _stipple_native_px()))
    refresh_variant_index()
    bases = tuple(names) if names is not None else BUILDING_ICON_NAMES
    targets: list[str] = []
    seen: set[str] = set()
    for base in bases:
        variants = variant_names(base)
        stems = variants if variants else ((base,) if _has_icon_file(base) else ())
        for stem in stems:
            if stem not in seen:
                targets.append(stem)
                seen.add(stem)
    before = len(_SURFACE_CACHE)
    for name in targets:
        try:
            get_icon(name, px, stipple=True)
        except (FileNotFoundError, OSError):
            continue
    return len(_SURFACE_CACHE) - before


# Logical icon ids used by draw code (bases; numbered variants are discovered).
ICON_TREE_ROUND = "tree_round"
ICON_TREE_CONE = "tree_cone"
ICON_SAPLING_ROUND = "sapling_round"
ICON_SAPLING_CONE = "sapling_cone"
ICON_ROCK = "rock"
ICON_ROCK_BIG = "rock_big"
ICON_MUSHROOM = "mushroom"
ICON_BERRY_BUSH = "berry_bush"
ICON_REED = "reed"
ICON_CROP = "crop_plant"
ICON_CROP_DENSE = "crop_plant_dense"
ICON_FLOWER = "flower_plant"
ICON_FLOWER_DENSE = "flower_plant_dense"
ICON_HOME = "storehouse"
ICON_WORKSTATION = "workstation"
ICON_FORESTER = "forester"
ICON_MASON = "mason"
ICON_HUNTER = "hunter"
ICON_FORAGER = "forager"
ICON_FISHER = "fisher"
ICON_FARM = "farm"
ICON_FIELD = "field"
ICON_MILL = "mill"
ICON_KITCHEN = "kitchen"
ICON_CRAFT_BENCH = "craft_bench"
ICON_ALCHEMIST = "alchemist"
ICON_TAILOR = "tailor"
ICON_COBBLER = "cobbler"
ICON_MARKET = "market"
ICON_TENT = "tent"
ICON_HOUSE_SMALL = "house_small"
ICON_HOUSE = "house"
ICON_BARN = "barn"
ICON_PANTRY = "pantry"
ICON_DRYING_RACK = "drying_rack"
ICON_CONSTRUCTION = "construction_site"

# Buildings that use stipple; baked at CELL_SIZE on map/game load.
BUILDING_ICON_NAMES: tuple[str, ...] = (
    ICON_HOME,
    ICON_WORKSTATION,
    ICON_FORESTER,
    ICON_MASON,
    ICON_HUNTER,
    ICON_FORAGER,
    ICON_FISHER,
    ICON_FARM,
    ICON_FIELD,
    ICON_MILL,
    ICON_KITCHEN,
    ICON_CRAFT_BENCH,
    ICON_ALCHEMIST,
    ICON_TAILOR,
    ICON_COBBLER,
    ICON_MARKET,
    ICON_TENT,
    ICON_HOUSE_SMALL,
    ICON_HOUSE,
    ICON_BARN,
    ICON_PANTRY,
    ICON_DRYING_RACK,
    ICON_CONSTRUCTION,
)

ICON_DEER_MALE = "deer_male"
ICON_DEER_FEMALE = "deer_female"
ICON_BOAR_MALE = "boar_male"
ICON_BOAR_FEMALE = "boar_female"
ICON_BEE = "bee"
ICON_BEE_HIVE = "bee_hive"
ICON_RABBIT = "rabbit"
ICON_BURROW = "burrow"
ICON_HONEY = "honey"
ICON_FISH = "fish"
ICON_FISH_CARP = "fish_carp"
ICON_FISH_PERCH = "fish_perch"
ICON_FISH_PIKE = "fish_pike"
ICON_FISH_ROACH = "fish_roach"
ICON_WOLF_MALE = "wolf_male"
ICON_WOLF_FEMALE = "wolf_female"
ICON_FOX_MALE = "fox_male"
ICON_FOX_FEMALE = "fox_female"
ICON_FROG = "frog"
ICON_VOLE = "vole"
ICON_OWL_LEFT = "owl_left"
ICON_OWL_RIGHT = "owl_right"
ICON_HAWK_LEFT = "hawk_left"
ICON_HAWK_RIGHT = "hawk_right"
ICON_VILLAGER = "villager"
ICON_PLAYER = "player"
ICON_MEAT_MARKER = "meat_marker"
ICON_FISH_MARKER = "fish_marker"
ICON_SEEDS = "seeds"
ICON_WOOD = "wood"
ICON_HARDWOOD = "log_hardwood"
ICON_LOG_WOOD = "log_wood"
ICON_LOG_HARDWOOD = "log_hardwood"
ICON_AXE = "axe"
ICON_SPEAR = "wooden_spear"
ICON_KNIFE = "knife"
ICON_HOE = "hoe"
ICON_CROP_WEEDS = "crop_weeds"
ICON_FISHING_ROD = "fishing_rod"
ICON_BOW = "bow"
ICON_STONE_ARROWS = "stone_arrows"
ICON_TWINE = "twine"
ICON_COINS = "coins"
ICON_BERRIES = "berries"
ICON_BREAD = "bread"
ICON_STEW = "stew"
ICON_FISH_STEW = "fish_stew"

ALL_ICON_NAMES: tuple[str, ...] = (
    ICON_TREE_ROUND,
    ICON_TREE_CONE,
    ICON_SAPLING_ROUND,
    ICON_SAPLING_CONE,
    ICON_ROCK,
    ICON_ROCK_BIG,
    ICON_MUSHROOM,
    ICON_BERRY_BUSH,
    ICON_REED,
    ICON_CROP,
    ICON_CROP_DENSE,
    ICON_FLOWER,
    ICON_FLOWER_DENSE,
    ICON_HOME,
    ICON_WORKSTATION,
    ICON_FORESTER,
    ICON_MASON,
    ICON_HUNTER,
    ICON_FORAGER,
    ICON_FISHER,
    ICON_FARM,
    ICON_FIELD,
    ICON_MILL,
    ICON_KITCHEN,
    ICON_CRAFT_BENCH,
    ICON_ALCHEMIST,
    ICON_TAILOR,
    ICON_COBBLER,
    ICON_MARKET,
    ICON_TENT,
    ICON_HOUSE_SMALL,
    ICON_HOUSE,
    ICON_BARN,
    ICON_PANTRY,
    ICON_DRYING_RACK,
    ICON_CONSTRUCTION,
    ICON_DEER_MALE,
    ICON_DEER_FEMALE,
    ICON_BOAR_MALE,
    ICON_BOAR_FEMALE,
    ICON_BEE,
    ICON_BEE_HIVE,
    ICON_RABBIT,
    ICON_BURROW,
    ICON_HONEY,
    ICON_FISH,
    ICON_FISH_CARP,
    ICON_FISH_PERCH,
    ICON_FISH_PIKE,
    ICON_FISH_ROACH,
    ICON_WOLF_MALE,
    ICON_WOLF_FEMALE,
    ICON_FOX_MALE,
    ICON_FOX_FEMALE,
    ICON_FROG,
    ICON_VOLE,
    ICON_OWL_LEFT,
    ICON_OWL_RIGHT,
    ICON_HAWK_LEFT,
    ICON_HAWK_RIGHT,
    ICON_VILLAGER,
    ICON_PLAYER,
    ICON_MEAT_MARKER,
    ICON_FISH_MARKER,
    ICON_SEEDS,
    ICON_WOOD,
    ICON_HARDWOOD,
    ICON_LOG_WOOD,
    ICON_LOG_HARDWOOD,
    ICON_AXE,
    ICON_SPEAR,
    ICON_KNIFE,
    ICON_HOE,
    ICON_CROP_WEEDS,
    ICON_FISHING_ROD,
    ICON_BOW,
    ICON_STONE_ARROWS,
    ICON_TWINE,
    ICON_COINS,
    ICON_BERRIES,
    ICON_BREAD,
    ICON_STEW,
    ICON_FISH_STEW,
    "mushroom_stew",
    "hide",
    "leather",
    "leather_shoes",
    "leather_satchel",
)


def crop_icon_base(crop_kind: str | None, *, dense: bool = False) -> str:
    """Resolve plant icon base for a crop key (``crop_plant`` / ``flower_plant``)."""
    from crops import CROP_BY_KEY

    crop = CROP_BY_KEY.get(crop_kind or "sage") or CROP_BY_KEY["sage"]
    return crop.plant_icon(dense=dense)


def icon_base_for_feature(
    feature: object,
    *,
    tree_species: str | None = None,
    crop_kind: str | None = None,
    deposit: int = 0,
    growth_ticks: int = 0,
) -> str | None:
    """Logical icon base for a map ``FeatureType``, or None if none/unknown."""
    # Local import avoids a hard cycle with world.py at module load.
    from trees import resolve_tree
    from resource_balance import ROCK_LARGE_MIN
    from wild_species import resolve_species
    from world import FeatureType

    if not isinstance(feature, FeatureType) or feature == FeatureType.NONE:
        return None
    if feature == FeatureType.TREE:
        tree = resolve_tree(tree_species)
        return ICON_TREE_CONE if tree.shape == "cone" else ICON_TREE_ROUND
    if feature == FeatureType.SAPLING:
        tree = resolve_tree(tree_species)
        return ICON_SAPLING_CONE if tree.shape == "cone" else ICON_SAPLING_ROUND
    if feature in (FeatureType.HERB, FeatureType.WILD_CROP):
        species = resolve_species(feature.name, crop_kind)
        if species is not None and species.icon_base:
            return species.icon_base
        return crop_icon_base(crop_kind, dense=False)
    if feature == FeatureType.CROP_HERB:
        return crop_icon_base(crop_kind, dense=growth_ticks <= 0)
    species = resolve_species(feature.name, crop_kind)
    if species is not None and species.icon_base:
        return species.icon_base
    mapping = {
        FeatureType.ROCK: ICON_ROCK_BIG if deposit >= ROCK_LARGE_MIN else ICON_ROCK,
        FeatureType.HOME: ICON_HOME,
        FeatureType.WORKSTATION: ICON_WORKSTATION,
        FeatureType.FORESTER: ICON_FORESTER,
        FeatureType.MASON: ICON_MASON,
        FeatureType.HUNTER: ICON_HUNTER,
        FeatureType.FORAGER: ICON_FORAGER,
        FeatureType.FISHER: ICON_FISHER,
        FeatureType.FARM: ICON_FARM,
        FeatureType.FIELD: ICON_FIELD,
        FeatureType.MILL: ICON_MILL,
        FeatureType.KITCHEN: ICON_KITCHEN,
        FeatureType.CRAFT_BENCH: ICON_CRAFT_BENCH,
        FeatureType.ALCHEMIST: ICON_ALCHEMIST,
        FeatureType.TAILOR: ICON_TAILOR,
        FeatureType.COBBLER: ICON_COBBLER,
        FeatureType.MARKET: ICON_MARKET,
        FeatureType.TENT: ICON_TENT,
        FeatureType.HOUSE_SMALL: ICON_HOUSE_SMALL,
        FeatureType.HOUSE: ICON_HOUSE,
        FeatureType.BARN: ICON_BARN,
        FeatureType.PANTRY: ICON_PANTRY,
        FeatureType.DRYING_RACK: ICON_DRYING_RACK,
        FeatureType.COMMUNITY: ICON_TENT,
        FeatureType.CONSTRUCTION_SITE: ICON_CONSTRUCTION,
        FeatureType.MUSHROOM: ICON_MUSHROOM,
        FeatureType.WOOD_BUSH: ICON_WOOD,
        FeatureType.BERRY_BUSH: ICON_BERRY_BUSH,
        FeatureType.REED: ICON_REED,
    }
    return mapping.get(feature)