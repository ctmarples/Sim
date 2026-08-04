"""SVG icon catalogue: load once, rasterise to cached Surfaces, blit cheaply.

Coordinate convention (Y down, matching the game)
-------------------------------------------------
* ``ICON_CELL`` (40) SVG units = one map cell edge.
* The **home cell** is the tile the feature lives on. By default it is the
  **bottom-left 40×40** of the viewBox (so a 40×80 tree keeps its trunk in the
  lower cell and canopy may overlap the cell above).
* The **anchor** is the home-cell centre. That point is blitted to the map cell
  centre ``(cx, cy)``. Default for viewBox ``0 0 40 40`` → anchor ``(20, 20)``;
  for ``0 0 40 80`` → home ``(0, 40)``, anchor ``(20, 60)``.
* Override on the root ``<svg>`` if needed::

    data-anchor="20,70"          # or data-anchor-x / data-anchor-y
    data-home="0,40,40"          # home cell x,y,size (optional)

Icon variants (folder discovery)
--------------------------------
Each logical base (e.g. ``crop_plant``, ``tree_round``) resolves to files in
``assets/icons/``:

* If ``base_1.svg``, ``base_2.svg``, … exist, those are the only variants
  (``base.svg`` is ignored).
* Otherwise a single ``base.svg`` is used.

``preload`` caches every discovered file. At draw time a 1-based variant index
selects among them (rolled once per cell when first drawn).

Art may extend outside the home cell in any direction. Scale is always
``cell_px / 40`` so overhanging pixels cover neighbouring tiles.

Editing SVGs (Inkscape / Affinity / Figma / Illustrator)
--------------------------------------------------------
* **``class`` is what the game reads** for recolour / scale / omit. ``id`` is
  only for you (and should match when convenient).
* Shared classes: ``canopy``, ``trunk``, ``stem``, ``flower``, ``body``,
  ``antler``, ``shadow``, plus building faces ``wall_l`` / ``wall_r`` / ``roof`` / …
* Put **every part that should share a tint** on that class (e.g. all legs
  ``class="body"``). Untagged fills stay as baked SVG colours.
* Draw order = paint order: shadows first, then trunk, then canopy.
* Supported shapes: ``path``, ``rect``, ``circle``, ``ellipse``, ``line``,
  ``polygon``, ``polyline``. Prefer ``<ellipse>`` for simple blobs.
* Supported paints: ``fill`` / ``stroke`` as attributes **or** in ``style=``,
  plus ``fill-opacity`` / ``stroke-opacity`` / ``opacity``.
* Supported transforms: ``translate``, ``scale``, ``rotate``, ``matrix``
  (Inkscape forms OK). Nested ``<g transform>`` works.
* Prefer baking Live Path Effects (Path → Object to Path) so ``d`` is final.
* Avoid ``<use>``, gradients, filters, text, clipPaths.
* Inkscape tip: Object → Object Properties → set ``class``. Shadows:
  ``class="shadow"`` on a simple ellipse/path is enough (skip PowerStroke).
* Saving a file busts that icon’s cache via mtime (no restart needed).
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable
import math
import random
import re
import xml.etree.ElementTree as ET

import pygame

_ICONS_DIR = Path(__file__).resolve().parent / "assets" / "icons"

# One map cell in SVG units (home-cell edge).
ICON_CELL: float = 40.0

Colour = tuple[int, int, int]
Paint = tuple[int, int, int, int]  # RGBA; alpha 255 = opaque
Recolour = dict[str, Colour]


@dataclass(frozen=True)
class IconImage:
    """Rasterised icon plus anchor offset in surface pixels."""

    surface: pygame.Surface
    anchor_x: int
    anchor_y: int


def icons_dir() -> Path:
    return _ICONS_DIR


def list_icon_names() -> list[str]:
    if not _ICONS_DIR.is_dir():
        return []
    return sorted(p.stem for p in _ICONS_DIR.glob("*.svg"))


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
    for cls in _classes(elem):
        if cls in recolour:
            return recolour[cls]
    return _parse_colour(_presentation(elem, attr))


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
) -> None:
    """Draw with optional alpha onto an SRCALPHA surface."""
    if paint is None:
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
            _blit_paint(surf, lambda s, c: pygame.draw.rect(s, c, rect), fill)
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
            _blit_paint(surf, lambda s, col: pygame.draw.circle(s, col, c, pr), fill)
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
            _blit_paint(surf, lambda s, col: pygame.draw.ellipse(s, col, rect), fill)
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
                _blit_paint(surf, lambda s, col: pygame.draw.polygon(s, col, pts), fill)
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


def _cache_key(
    name: str,
    cell_px: int,
    recolour: Recolour | None,
    class_scales: dict[str, float] | None,
    omit_classes: frozenset[str] | None,
    mtime_ns: int,
) -> tuple:
    rc = tuple(sorted((k, v) for k, v in (recolour or {}).items()))
    sc = tuple(sorted((k, round(v, 3)) for k, v in (class_scales or {}).items()))
    oc = tuple(sorted(omit_classes or ()))
    return (name, cell_px, rc, sc, oc, mtime_ns)


_SURFACE_CACHE: dict[tuple, IconImage] = {}
_VARIANT_CACHE: dict[str, tuple[str, ...]] = {}


def clear_cache() -> None:
    _SURFACE_CACHE.clear()
    _VARIANT_CACHE.clear()


def variant_names(base: str) -> tuple[str, ...]:
    """Return concrete SVG stems for a logical icon base.

    Numbered convention wins exclusively when present:
    ``base_1.svg``, ``base_2.svg``, … (``base.svg`` is then unused).
    If no numbered files exist, falls back to a single ``base.svg``.
    """
    cached = _VARIANT_CACHE.get(base)
    if cached is not None:
        return cached
    numbered: list[str] = []
    i = 1
    while True:
        stem = f"{base}_{i}"
        if not (_ICONS_DIR / f"{stem}.svg").is_file():
            break
        numbered.append(stem)
        i += 1
    if numbered:
        result = tuple(numbered)
    elif (_ICONS_DIR / f"{base}.svg").is_file():
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
    """Map logical base + optional 1-based variant to a concrete SVG stem."""
    names = variant_names(base)
    if not names:
        raise FileNotFoundError(f"No icon SVG for base '{base}' in {_ICONS_DIR}")
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

def get_icon(
    name: str,
    cell_px: int,
    *,
    recolour: Recolour | None = None,
    class_scales: dict[str, float] | None = None,
    omit_classes: Iterable[str] | None = None,
) -> IconImage:
    """Return a cached icon for ``name`` at ``cell_px`` pixels per map cell.

    Cache keys include the SVG file mtime, so saving an edited icon rebuilds
    that surface on the next blit (no game restart required).
    """
    cell_px = max(4, int(cell_px))
    omit = frozenset(omit_classes) if omit_classes else None
    path = _ICONS_DIR / f"{name}.svg"
    if not path.is_file():
        raise FileNotFoundError(f"Icon SVG not found: {path}")
    if path.stat().st_size == 0:
        raise FileNotFoundError(f"Icon SVG is empty: {path}")
    mtime_ns = path.stat().st_mtime_ns
    key = _cache_key(name, cell_px, recolour, class_scales, omit, mtime_ns)
    cached = _SURFACE_CACHE.get(key)
    if cached is not None:
        return cached
    try:
        icon = _rasterise_svg(
            path,
            cell_px,
            recolour or {},
            class_scales or {},
            set(omit) if omit else set(),
        )
    except ET.ParseError as exc:
        raise FileNotFoundError(f"Icon SVG is invalid ({path.name}): {exc}") from exc
    _SURFACE_CACHE[key] = icon
    return icon


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
    """Rasterise every available variant into the cache.

    For each logical base, caches ``base_1``…``base_N`` when those files exist,
    otherwise ``base.svg``. With ``names=None``, every SVG on disk is loaded.
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
                (base,) if (_ICONS_DIR / f"{base}.svg").is_file() else ()
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
ICON_HOME = "home"
ICON_WORKSTATION = "workstation"
ICON_FORESTER = "forester"
ICON_MASON = "mason"
ICON_HUNTER = "hunter"
ICON_FORAGER = "forager"
ICON_FISHER = "fisher"
ICON_FARM = "farm"
ICON_FIELD = "field"
ICON_CONSTRUCTION = "construction_site"
ICON_DEER_MALE = "deer_male"
ICON_DEER_FEMALE = "deer_female"
ICON_BOAR_MALE = "boar_male"
ICON_BOAR_FEMALE = "boar_female"
ICON_FISH = "fish"
ICON_VILLAGER = "villager"
ICON_PLAYER = "player"
ICON_MEAT_MARKER = "meat_marker"
ICON_FISH_MARKER = "fish_marker"
ICON_SEEDS = "seeds"
ICON_WOOD = "wood"
ICON_HARDWOOD = "hardwood"
ICON_BERRIES = "berries"

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
    ICON_CONSTRUCTION,
    ICON_DEER_MALE,
    ICON_DEER_FEMALE,
    ICON_BOAR_MALE,
    ICON_BOAR_FEMALE,
    ICON_FISH,
    ICON_VILLAGER,
    ICON_PLAYER,
    ICON_MEAT_MARKER,
    ICON_FISH_MARKER,
    ICON_SEEDS,
    ICON_WOOD,
    ICON_HARDWOOD,
    ICON_BERRIES,
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
) -> str | None:
    """Logical icon base for a map ``FeatureType``, or None if none/unknown."""
    # Local import avoids a hard cycle with world.py at module load.
    from trees import resolve_tree
    from settings import ROCK_LARGE_MIN
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
        return crop_icon_base(crop_kind, dense=False)
    if feature == FeatureType.CROP_HERB:
        return crop_icon_base(crop_kind, dense=True)
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
        FeatureType.CONSTRUCTION_SITE: ICON_CONSTRUCTION,
        FeatureType.MUSHROOM: ICON_MUSHROOM,
        FeatureType.BERRY_BUSH: ICON_BERRY_BUSH,
        FeatureType.REED: ICON_REED,
    }
    return mapping.get(feature)