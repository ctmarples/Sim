"""Content Lab / Developer Tools host for the Landscape Fields prototype."""

from __future__ import annotations

from landscape_fields import (
    DEFAULT_PATCH_THRESHOLD,
    LandscapeFieldsParams,
    LandscapeFieldsState,
    apply_landscape_texture_to_world,
    build_landscape_fields_map,
    dominant_species_maps,
    evaluate_species_on_landscape,
    generate_landscape_fields,
    high_suitability_patches,
    niche_bearing_species,
    suitability_grid,
    suitability_summary,
    summarise_fields,
)
from seasons import HALF_SEASON_DAYS, HALF_SEASON_NAMES, half_season_name
from wild_species import ENVIRONMENT_WEIGHTS, WILD_BY_KEY
from .widgets import Dropdown, FloatField, IntegerField


# Overlay groups for the lab UI (keys → OverlayMode mapping in _apply_overlay).
LANDSCAPE_OVERLAYS = (
    ("soil_texture", "Soil texture"),
    ("fertility_potential", "Fertility potential"),
    ("hydrological_position", "Hydrological pos."),
)
PLANT_OVERLAYS = (
    ("soil_moisture", "Soil moisture"),
    ("fertility", "Fertility"),
    ("temperature", "Temperature"),
    ("disturbance", "Disturbance"),
)
ECOLOGY_OVERLAYS = (
    ("species_suitability", "Species suitability"),
    ("dominant_species", "Dominant species"),
)
SUITABILITY_MODES = (
    ("spatial", "Spatial suitability"),
    ("current", "Current suitability"),
)


class LandscapeFieldsSession:
    """Disposable landscape-field + niche-targeting experiment."""

    def __init__(self, game):
        self.game = game
        self.message = "Landscape Fields — ecological niche diagnostics."
        self.state: LandscapeFieldsState | None = None
        self.overlay_key = "species_suitability"
        self._buttons: list = []
        import pygame

        self.seed_field = IntegerField(pygame.Rect(0, 0, 1, 1), str(4201), minimum=0)
        self.fields = {
            "soil_region_scale": FloatField(pygame.Rect(0, 0, 1, 1), "0.55", minimum=0.15, maximum=0.95),
            "soil_variation_strength": FloatField(pygame.Rect(0, 0, 1, 1), "1.05", minimum=0.2, maximum=1.4),
            "fertility_region_scale": FloatField(pygame.Rect(0, 0, 1, 1), "0.38", minimum=0.15, maximum=0.95),
            "fertility_variation_strength": FloatField(pygame.Rect(0, 0, 1, 1), "0.88", minimum=0.2, maximum=1.4),
            "hydrology_strength": FloatField(pygame.Rect(0, 0, 1, 1), "1.00", minimum=0.2, maximum=1.5),
            "texture_moisture_retention": FloatField(pygame.Rect(0, 0, 1, 1), "0.22", minimum=0.0, maximum=0.45),
        }
        species = niche_bearing_species()
        self.species_dropdown = Dropdown(
            pygame.Rect(0, 0, 1, 1),
            [(s.key, s.label) for s in species],
            value=next((s.key for s in species if s.key == "yarrow"), species[0].key if species else None),
        )
        self.half_season = 2  # summer early — mid-year default
        self.suitability_mode = "spatial"
        self._inspect: dict | None = None
        self._suitability_cache: list[list[float]] | None = None
        self._suitability_species: str | None = None
        self._suitability_cache_key: tuple | None = None
        self._summary: dict | None = None
        self._patches: dict | None = None
        self._dominant_scores: list[list[float]] | None = None
        self._dominant_keys: list[list[str | None]] | None = None
        self._dominant_colours: dict[str, tuple[int, int, int]] = {}
        self._panel_scroll = 0
        self._panel_rect = __import__("pygame").Rect(12, 92, 430, 640)

    @property
    def selected_species(self):
        key = self.species_dropdown.value
        return WILD_BY_KEY.get(key) if key else None

    @property
    def diagnostic_day(self) -> float:
        """Near the start of the selected half-season (authored profile value)."""
        return float(int(self.half_season) % 8) * HALF_SEASON_DAYS + 0.5

    def start(self) -> None:
        self.game._landscape_fields_active = True
        self.game._landscape_fields_session = self
        self.game._content_lab_active = False
        self.game._content_lab_session = None
        self.regenerate(rebuild_map=True)
        self.game.sim_speed = 0
        self.game.developer_tools = None

    def leave(self) -> None:
        self.game._landscape_fields_active = False
        self.game._landscape_fields_session = None
        self.game.overlay_mode = __import__("indicators").OverlayMode.NONE
        self.game._refresh_indicators()
        self.game.developer_tools = None
        self.game._launch_menu = "developer_tools"

    def _read_params(self) -> LandscapeFieldsParams | None:
        seed = self.seed_field.parse()
        values = {name: field.parse() for name, field in self.fields.items()}
        if seed is None or any(v is None for v in values.values()):
            self.message = "Fix invalid tuning values before regenerating."
            return None
        return LandscapeFieldsParams(
            seed=int(seed),
            soil_region_scale=float(values["soil_region_scale"]),
            soil_variation_strength=float(values["soil_variation_strength"]),
            fertility_region_scale=float(values["fertility_region_scale"]),
            fertility_variation_strength=float(values["fertility_variation_strength"]),
            hydrology_strength=float(values["hydrology_strength"]),
            texture_moisture_retention=float(values["texture_moisture_retention"]),
        )

    def regenerate(self, *, rebuild_map: bool = False) -> None:
        params = self._read_params()
        if params is None:
            return
        try:
            generated = build_landscape_fields_map(params)
            self.game._begin_new_game(generated=generated)
            self.game.discovered_cells = {
                (x, y)
                for y in range(self.game.world.rows)
                for x in range(self.game.world.cols)
            }
            self.game.sim_speed = 0
            self.game._landscape_fields_active = True
            self.game._landscape_fields_session = self

            self.state = generate_landscape_fields(self.game.world, params)
            apply_landscape_texture_to_world(self.game.world, self.state)
            self._invalidate_ecology_caches()
            self._rebuild_ecology_caches()
            self._apply_overlay()
            summary = summarise_fields(self.state)
            self.message = (
                f"Seed {params.seed} · niches via wild_species · "
                f"r(hydro,moist)={summary['correlations']['hydrology_vs_moisture']:.2f}"
            )
            self.game._set_status(f"Landscape Fields regenerated (seed {params.seed}).")
        except Exception as exc:
            self.message = f"Regenerate failed: {exc}"
            self.game._set_status(self.message)

    def _invalidate_ecology_caches(self) -> None:
        self._suitability_cache = None
        self._suitability_species = None
        self._suitability_cache_key = None
        self._summary = None
        self._patches = None
        self._dominant_scores = None
        self._dominant_keys = None
        self._dominant_colours = {}

    def _ecology_cache_key(self, species_key: str | None) -> tuple:
        return (species_key, self.suitability_mode, int(self.half_season) % 8)

    def _rebuild_ecology_caches(self) -> None:
        if self.state is None:
            return
        species = self.selected_species
        if species is not None:
            self._suitability_cache = suitability_grid(
                self.game.world,
                self.state,
                species,
                day=self.diagnostic_day,
                suitability_mode=self.suitability_mode,
            )
            self._suitability_species = species.key
            self._suitability_cache_key = self._ecology_cache_key(species.key)
            self._summary = suitability_summary(self._suitability_cache, self.state.water_mask)
            self._patches = high_suitability_patches(
                self.game.world, self._suitability_cache, threshold=DEFAULT_PATCH_THRESHOLD
            )
        # Dominant map is heavier — build lazily on first request / overlay.
        if self.overlay_key == "dominant_species":
            self._ensure_dominant()

    def _ensure_suitability(self) -> list[list[float]]:
        species = self.selected_species
        if self.state is None or species is None:
            return []
        key = self._ecology_cache_key(species.key)
        if self._suitability_cache is None or self._suitability_cache_key != key:
            self._suitability_cache = suitability_grid(
                self.game.world,
                self.state,
                species,
                day=self.diagnostic_day,
                suitability_mode=self.suitability_mode,
            )
            self._suitability_species = species.key
            self._suitability_cache_key = key
            self._summary = suitability_summary(self._suitability_cache, self.state.water_mask)
            self._patches = high_suitability_patches(
                self.game.world, self._suitability_cache, threshold=DEFAULT_PATCH_THRESHOLD
            )
        return self._suitability_cache

    def _ensure_dominant(self) -> None:
        if self.state is None or self._dominant_keys is not None:
            return
        scores, keys, colours = dominant_species_maps(
            self.game.world,
            self.state,
            niche_bearing_species(),
            day=self.diagnostic_day,
            suitability_mode=self.suitability_mode,
        )
        self._dominant_scores = scores
        self._dominant_keys = keys
        self._dominant_colours = colours

    def _apply_overlay(self) -> None:
        from indicators import OverlayMode

        mapping = {
            "soil_texture": OverlayMode.SOIL_TEXTURE,
            "fertility_potential": OverlayMode.FERTILITY_POTENTIAL,
            "hydrological_position": OverlayMode.HYDROLOGICAL_POSITION,
            "soil_moisture": OverlayMode.MOISTURE_BASELINE,
            "fertility": OverlayMode.LF_PLANT_FERTILITY,
            "temperature": OverlayMode.LF_PLANT_TEMPERATURE,
            "disturbance": OverlayMode.LF_PLANT_DISTURBANCE,
            "species_suitability": OverlayMode.SPECIES_SUITABILITY,
            "dominant_species": OverlayMode.DOMINANT_SPECIES,
        }
        if self.overlay_key == "dominant_species":
            self._ensure_dominant()
        if self.overlay_key == "species_suitability":
            self._ensure_suitability()
        mode = mapping.get(self.overlay_key, OverlayMode.SOIL_TEXTURE)
        self.game.overlay_mode = mode
        self.game._smooth_overlay_cache = None
        self.game._refresh_indicators()

    def overlay_grid(self, key: str | None = None) -> list[list[float]]:
        key = key or self.overlay_key
        if self.state is None:
            return []
        if key == "soil_texture":
            return self.state.soil_texture
        if key == "fertility_potential":
            return self.state.fertility_potential
        if key == "hydrological_position":
            return self.state.hydrological_position
        if key == "soil_moisture":
            return self.state.soil_moisture
        if key == "fertility":
            return self.state.fertility
        if key == "temperature":
            return self.state.temperature
        if key == "disturbance":
            return self.state.disturbance
        if key == "species_suitability":
            return self._ensure_suitability()
        if key == "dominant_species":
            self._ensure_dominant()
            return self._dominant_scores or []
        return self.state.soil_texture

    def dominant_colour_at(self, x: int, y: int) -> tuple[int, int, int] | None:
        self._ensure_dominant()
        if self._dominant_keys is None:
            return None
        if not (0 <= y < len(self._dominant_keys) and 0 <= x < len(self._dominant_keys[y])):
            return None
        key = self._dominant_keys[y][x]
        if key is None:
            return (45, 45, 50)
        return self._dominant_colours.get(key, (120, 120, 120))

    def update_hover(self, cell: tuple[int, int] | None) -> None:
        if self.state is None or cell is None:
            self._inspect = None
            return
        x, y = cell
        if not (0 <= y < len(self.state.soil_texture) and 0 <= x < len(self.state.soil_texture[y])):
            self._inspect = None
            return
        base = self.state.at(x, y)
        species = self.selected_species
        extra: dict = {}
        if species is not None:
            result = evaluate_species_on_landscape(
                self.game.world,
                self.state,
                x,
                y,
                species,
                day=self.diagnostic_day,
                suitability_mode=self.suitability_mode,
            )
            s = result.suitability
            persistent = (
                species.feature in {"BERRY_BUSH", "REED"}
                or species.spawn_peak <= 0
                or species.clear_from_day < 0 and species.fruiting
            )
            extra = {
                "species": species.label,
                "species_key": species.key,
                "responses": {
                    "Temperature": s.temperature,
                    "Moisture": s.moisture,
                    "Fertility": s.fertility,
                    "Disturbance": s.disturbance,
                    "Texture": s.soil_texture,
                },
                "combined": s.combined,
                "display_combined": result.display_combined,
                "spatial_combined": result.spatial_combined,
                "activity": result.activity,
                "current_combined": result.current_combined,
                "temporal_label": result.temporal_label,
                "half_season": half_season_name(self.half_season),
                "persistent_note": persistent,
                "fail_reasons": result.fail_reasons,
                "weights": dict(ENVIRONMENT_WEIGHTS),
            }
        if self._dominant_keys is not None and 0 <= y < len(self._dominant_keys):
            dom = self._dominant_keys[y][x]
            extra["dominant"] = WILD_BY_KEY[dom].label if dom and dom in WILD_BY_KEY else "none"
        self._inspect = {**base, **extra}

    def handle_event(self, event) -> bool:
        import pygame

        if event.type == pygame.MOUSEWHEEL:
            pos = pygame.mouse.get_pos()
            # Species list scroll only when the dropdown popup is under the cursor.
            if self.species_dropdown.open:
                visible = min(self.species_dropdown.max_visible, len(self.species_dropdown.options))
                popup = pygame.Rect(
                    self.species_dropdown.rect.x,
                    self.species_dropdown.rect.bottom,
                    self.species_dropdown.rect.w,
                    max(1, visible) * self.species_dropdown.rect.h,
                )
                if self.species_dropdown.rect.collidepoint(pos) or popup.collidepoint(pos):
                    return self.species_dropdown.handle_event(event)
            # Lab panel scroll only over the panel; map zoom everywhere else.
            if self._panel_rect.collidepoint(pos):
                self._panel_scroll = max(0, min(520, self._panel_scroll - event.y * 24))
                return True
            return False

        old_species = self.species_dropdown.value
        if self.species_dropdown.handle_event(event):
            if self.species_dropdown.value != old_species:
                self._suitability_cache = None
                self._ensure_suitability()
                if self.overlay_key == "species_suitability":
                    self._apply_overlay()
                self.message = f"Species: {self.selected_species.label if self.selected_species else '?'}"
            return True
        if self.seed_field.handle_event(event):
            return True
        for control in self.fields.values():
            if control.handle_event(event):
                return True
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            action = next((a for rect, a in self._buttons if rect.collidepoint(event.pos)), None)
            if action is None:
                return False
            if action == "regenerate":
                self.regenerate(rebuild_map=True)
            elif action == "reroll":
                cur = self.seed_field.parse() or 0
                self.seed_field.text = str(int(cur) + 1)
                self.regenerate(rebuild_map=True)
            elif action.startswith("overlay:"):
                self.overlay_key = action.split(":", 1)[1]
                self._apply_overlay()
                labels = dict(LANDSCAPE_OVERLAYS + PLANT_OVERLAYS + ECOLOGY_OVERLAYS)
                self.message = f"Overlay: {labels.get(self.overlay_key, self.overlay_key)}"
            elif action.startswith("mode:"):
                self.suitability_mode = action.split(":", 1)[1]
                self._invalidate_ecology_caches()
                self._ensure_suitability()
                if self.overlay_key in ("species_suitability", "dominant_species"):
                    self._apply_overlay()
                self.message = f"Suitability: {self.suitability_mode}"
            elif action.startswith("half:"):
                self.half_season = int(action.split(":", 1)[1]) % 8
                self._invalidate_ecology_caches()
                self._ensure_suitability()
                if self.overlay_key in ("species_suitability", "dominant_species"):
                    self._apply_overlay()
                self.message = f"Half-season: {half_season_name(self.half_season)}"
            elif action == "prev_species":
                self._cycle_species(-1)
            elif action == "next_species":
                self._cycle_species(1)
            elif action == "back":
                self.leave()
            return True
        if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
            if self.species_dropdown.open:
                self.species_dropdown.open = False
                return True
            self.leave()
            return True
        if event.type == pygame.KEYDOWN and event.key == pygame.K_r:
            self.regenerate(rebuild_map=True)
            return True
        if event.type == pygame.KEYDOWN and event.key in (pygame.K_LEFTBRACKET, pygame.K_RIGHTBRACKET):
            self._cycle_species(-1 if event.key == pygame.K_LEFTBRACKET else 1)
            return True
        return False

    def _cycle_species(self, delta: int) -> None:
        options = self.species_dropdown.options
        if not options:
            return
        keys = [k for k, _ in options]
        try:
            idx = keys.index(self.species_dropdown.value)
        except ValueError:
            idx = 0
        idx = (idx + delta) % len(keys)
        self.species_dropdown.value = keys[idx]
        self._suitability_cache = None
        self._ensure_suitability()
        if self.overlay_key == "species_suitability":
            self._apply_overlay()
        sp = self.selected_species
        self.message = f"Species: {sp.label if sp else '?'}"

    def draw(self, surface) -> None:
        import pygame

        panel = pygame.Rect(12, 92, 430, 640)
        self._panel_rect = panel
        pygame.draw.rect(surface, (24, 31, 35), panel, border_radius=6)
        pygame.draw.rect(surface, (108, 132, 120), panel, 1, border_radius=6)
        title = pygame.font.SysFont("menlo", 14, bold=True)
        body = pygame.font.SysFont("menlo", 11)
        tiny = pygame.font.SysFont("menlo", 10)
        surface.blit(
            title.render("LANDSCAPE FIELDS — niche targeting", True, (235, 235, 225)),
            (panel.x + 10, panel.y + 8),
        )
        self._buttons = []

        def button(x, y, w, label, action, *, active=False, h=22):
            rect = pygame.Rect(x, y, w, h)
            if not panel.collidepoint(rect.center):
                return
            self._buttons.append((rect, action))
            fill = (72, 98, 88) if active else (58, 70, 70)
            pygame.draw.rect(surface, fill, rect, border_radius=3)
            pygame.draw.rect(surface, (108, 132, 120), rect, 1, border_radius=3)
            text = tiny.render(label, True, (230, 235, 228))
            surface.blit(text, (rect.centerx - text.get_width() // 2, rect.centery - text.get_height() // 2))

        y0 = panel.y + 30 - self._panel_scroll
        y = y0

        surface.blit(body.render("Seed", True, (180, 190, 185)), (panel.x + 12, y + 4))
        self.seed_field.rect = pygame.Rect(panel.x + 55, y, 70, 22)
        self.seed_field.draw(surface, body)
        button(panel.x + 132, y, 88, "Regenerate", "regenerate")
        button(panel.x + 226, y, 80, "Next seed", "reroll")
        y += 30

        surface.blit(body.render("Species", True, (150, 190, 165)), (panel.x + 12, y))
        y += 18
        self.species_dropdown.rect = pygame.Rect(panel.x + 12, y, 280, 24)
        self.species_dropdown.draw(surface, body)
        button(panel.x + 300, y, 28, '[', "prev_species")
        button(panel.x + 332, y, 28, "]", "next_species")
        y += 32

        def overlay_block(heading, items):
            nonlocal y
            surface.blit(tiny.render(heading, True, (150, 190, 165)), (panel.x + 12, y))
            y += 16
            for i, (key, label) in enumerate(items):
                button(
                    panel.x + 12 + (i % 2) * 200,
                    y + (i // 2) * 26,
                    192,
                    label,
                    f"overlay:{key}",
                    active=self.overlay_key == key,
                )
            y += 26 * ((len(items) + 1) // 2) + 8

        overlay_block("LANDSCAPE / INTERMEDIATE", LANDSCAPE_OVERLAYS)
        overlay_block("PLANT ENVIRONMENT", PLANT_OVERLAYS)
        overlay_block("ECOLOGICAL OUTCOME", ECOLOGY_OVERLAYS)

        surface.blit(tiny.render("SUITABILITY MODE", True, (150, 190, 165)), (panel.x + 12, y))
        y += 16
        for i, (key, label) in enumerate(SUITABILITY_MODES):
            button(
                panel.x + 12 + i * 200,
                y,
                192,
                label,
                f"mode:{key}",
                active=self.suitability_mode == key,
            )
        y += 30

        surface.blit(tiny.render("HALF-SEASON", True, (150, 190, 165)), (panel.x + 12, y))
        y += 16
        for i, name in enumerate(HALF_SEASON_NAMES):
            button(
                panel.x + 12 + (i % 2) * 200,
                y + (i // 2) * 24,
                192,
                name,
                f"half:{i}",
                active=int(self.half_season) % 8 == i,
                h=20,
            )
        y += 24 * 4 + 8

        # Compact tuning (two columns of labels + fields)
        surface.blit(tiny.render("TUNING", True, (150, 190, 165)), (panel.x + 12, y))
        y += 16
        labels = {
            "soil_region_scale": "Soil scale",
            "soil_variation_strength": "Soil var",
            "fertility_region_scale": "Fert scale",
            "fertility_variation_strength": "Fert var",
            "hydrology_strength": "Hydro str",
            "texture_moisture_retention": "Tex→moist",
        }
        for i, (name, control) in enumerate(self.fields.items()):
            col = i % 2
            row = i // 2
            xx = panel.x + 12 + col * 205
            yy = y + row * 24
            surface.blit(tiny.render(labels[name], True, (175, 185, 180)), (xx, yy + 4))
            control.rect = pygame.Rect(xx + 88, yy, 70, 20)
            control.draw(surface, tiny)
        y += 24 * 3 + 10

        # Species suitability stats
        if self._summary is not None and self.selected_species is not None:
            s = self._summary
            surface.blit(
                tiny.render(f"SUITABILITY — {self.selected_species.label}", True, (150, 190, 165)),
                (panel.x + 12, y),
            )
            y += 15
            lines = [
                f"mean {s['mean']:.2f}  max {s['max']:.2f}",
                f">0.25 {s['pct_gt_025']*100:.0f}%  >0.50 {s['pct_gt_050']*100:.0f}%  >0.75 {s['pct_gt_075']*100:.0f}%",
            ]
            if self._patches:
                p = self._patches
                centres = ", ".join(f"({c[0]},{c[1]})×{c[2]}" for c in p["centres"][:3]) or "—"
                lines.append(f"patches≥{DEFAULT_PATCH_THRESHOLD:.2f}: {p['count']}  largest {p['largest']}")
                lines.append(f"centres: {centres}")
            for line in lines:
                surface.blit(tiny.render(line, True, (185, 200, 190)), (panel.x + 14, y))
                y += 13
            y += 4

        # Tile inspect
        surface.blit(tiny.render("TILE INSPECT", True, (150, 190, 165)), (panel.x + 12, y))
        y += 15
        if self._inspect:
            info = self._inspect
            surface.blit(
                tiny.render(
                    f"({info['x']}, {info['y']})"
                    + (" WATER" if info.get("water") else "")
                    + (f"  dom={info['dominant']}" if info.get("dominant") else ""),
                    True,
                    (200, 215, 205),
                ),
                (panel.x + 14, y),
            )
            y += 13
            if "species" in info:
                surface.blit(tiny.render(info["species"], True, (220, 230, 210)), (panel.x + 14, y))
                y += 13
                surface.blit(tiny.render("SPATIAL", True, (150, 190, 165)), (panel.x + 14, y))
                y += 12
                for label, score in info["responses"].items():
                    w = ENVIRONMENT_WEIGHTS.get(
                        {
                            "Temperature": "temperature",
                            "Moisture": "soil_moisture",
                            "Fertility": "fertility",
                            "Disturbance": "disturbance",
                            "Texture": "soil_texture",
                        }[label],
                        0,
                    )
                    surface.blit(
                        tiny.render(f"{label:<12} {score:.2f}  (w={w:.2f})", True, (175, 195, 180)),
                        (panel.x + 14, y),
                    )
                    y += 12
                surface.blit(
                    tiny.render(
                        f"Spatial combined {info['spatial_combined']:.2f}",
                        True,
                        (145, 210, 160),
                    ),
                    (panel.x + 14, y),
                )
                y += 14
                surface.blit(tiny.render("TEMPORAL", True, (150, 190, 165)), (panel.x + 14, y))
                y += 12
                surface.blit(
                    tiny.render(
                        f"Half-season  {info['half_season']}",
                        True,
                        (175, 195, 180),
                    ),
                    (panel.x + 14, y),
                )
                y += 12
                surface.blit(
                    tiny.render(
                        f"{info['temporal_label']:<20} {info['activity']:.2f}",
                        True,
                        (175, 195, 180),
                    ),
                    (panel.x + 14, y),
                )
                y += 14
                surface.blit(tiny.render("FINAL", True, (150, 190, 165)), (panel.x + 14, y))
                y += 12
                surface.blit(
                    tiny.render(
                        f"Current suitability {info['current_combined']:.2f}",
                        True,
                        (145, 210, 160),
                    ),
                    (panel.x + 14, y),
                )
                y += 13
                if info.get("persistent_note"):
                    surface.blit(
                        tiny.render(
                            "Low temporal ≠ plant absence (persistent)",
                            True,
                            (210, 190, 120),
                        ),
                        (panel.x + 14, y),
                    )
                    y += 12
                for reason in info.get("fail_reasons") or ():
                    surface.blit(tiny.render(reason, True, (225, 120, 100)), (panel.x + 14, y))
                    y += 12
            else:
                surface.blit(
                    tiny.render(
                        f"tex {info['soil_texture']:.2f}  moist {info['soil_moisture']:.2f}  "
                        f"fert {info['fertility']:.2f}",
                        True,
                        (185, 195, 190),
                    ),
                    (panel.x + 14, y),
                )
                y += 12
                surface.blit(
                    tiny.render(
                        f"hydro {info['hydrological_position']:.2f}  "
                        f"temp {info['temperature']:.2f}  dist {info['disturbance']:.2f}",
                        True,
                        (185, 195, 190),
                    ),
                    (panel.x + 14, y),
                )
        else:
            surface.blit(tiny.render("Hover a map tile…", True, (140, 150, 145)), (panel.x + 14, y))

        surface.blit(tiny.render(self.message, True, (170, 175, 170)), (panel.x + 10, panel.bottom - 48))
        button(panel.x + 10, panel.bottom - 28, 200, "Back to Developer Tools", "back", h=22)

        # Dropdown last so it paints above controls.
        if self.species_dropdown.open:
            self.species_dropdown.draw(surface, body)
