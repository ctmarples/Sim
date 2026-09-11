"""Content Lab / Developer Tools host for the Landscape Fields prototype."""

from __future__ import annotations

from landscape_fields import (
    LandscapeFieldsParams,
    LandscapeFieldsState,
    apply_landscape_texture_to_world,
    build_landscape_fields_map,
    field_correlations,
    generate_landscape_fields,
    summarise_fields,
)
from .widgets import FloatField, IntegerField


OVERLAY_CHOICES = (
    ("soil_texture", "Soil texture"),
    ("fertility_potential", "Fertility potential"),
    ("hydrological_position", "Hydrological position"),
    ("soil_moisture_baseline", "Moisture baseline"),
    ("combined", "Combined (RGB)"),
)


class LandscapeFieldsSession:
    """Disposable landscape-field experiment on a small GeneratedMap."""

    def __init__(self, game):
        self.game = game
        self.message = "Landscape Fields prototype — production generators unchanged."
        self.state: LandscapeFieldsState | None = None
        self.overlay_key = "soil_texture"
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
        self._inspect: dict | None = None

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
            self._apply_overlay()
            summary = summarise_fields(self.state)
            corr = summary["correlations"]
            self.message = (
                f"Seed {params.seed} · sandy {summary['sandy_share']*100:.0f}% · "
                f"clayey {summary['clayey_share']*100:.0f}% · "
                f"r(hydro,moist)={corr['hydrology_vs_moisture']:.2f} · "
                f"r(tex,fert)={corr['texture_vs_fertility']:.2f}"
            )
            self.game._set_status(f"Landscape Fields regenerated (seed {params.seed}).")
        except Exception as exc:
            self.message = f"Regenerate failed: {exc}"
            self.game._set_status(self.message)

    def _apply_overlay(self) -> None:
        from indicators import OverlayMode

        mapping = {
            "soil_texture": OverlayMode.SOIL_TEXTURE,
            "fertility_potential": OverlayMode.FERTILITY_POTENTIAL,
            "hydrological_position": OverlayMode.HYDROLOGICAL_POSITION,
            "soil_moisture_baseline": OverlayMode.MOISTURE_BASELINE,
            "combined": OverlayMode.LANDSCAPE_COMBINED,
        }
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
        if key == "soil_moisture_baseline":
            return self.state.soil_moisture_baseline
        if key == "combined":
            # Cheap RGB-ish scalar: texture/fertility/hydro as weighted luma for fallback;
            # real combined colouring is handled in overlay_colour.
            return [
                [
                    0.34 * self.state.soil_texture[y][x]
                    + 0.33 * self.state.fertility_potential[y][x]
                    + 0.33 * self.state.hydrological_position[y][x]
                    for x in range(self.game.world.cols)
                ]
                for y in range(self.game.world.rows)
            ]
        return self.state.soil_texture

    def update_hover(self, cell: tuple[int, int] | None) -> None:
        if self.state is None or cell is None:
            self._inspect = None
            return
        x, y = cell
        if 0 <= y < len(self.state.soil_texture) and 0 <= x < len(self.state.soil_texture[y]):
            self._inspect = self.state.at(x, y)
        else:
            self._inspect = None

    def handle_event(self, event) -> bool:
        import pygame

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
                self.message = f"Overlay: {dict(OVERLAY_CHOICES).get(self.overlay_key, self.overlay_key)}"
            elif action == "back":
                self.leave()
            return True
        if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
            self.leave()
            return True
        if event.type == pygame.KEYDOWN and event.key == pygame.K_r:
            self.regenerate(rebuild_map=True)
            return True
        return False

    def draw(self, surface) -> None:
        import pygame

        panel = pygame.Rect(12, 92, 420, 620)
        pygame.draw.rect(surface, (24, 31, 35), panel, border_radius=6)
        pygame.draw.rect(surface, (108, 132, 120), panel, 1, border_radius=6)
        title = pygame.font.SysFont("menlo", 15, bold=True)
        body = pygame.font.SysFont("menlo", 12)
        surface.blit(
            title.render("CONTENT LAB — LANDSCAPE FIELDS", True, (235, 235, 225)),
            (panel.x + 12, panel.y + 10),
        )
        surface.blit(
            body.render("Experimental · production generation untouched", True, (150, 170, 160)),
            (panel.x + 12, panel.y + 32),
        )
        self._buttons = []

        def button(x, y, w, label, action, *, active=False):
            rect = pygame.Rect(x, y, w, 26)
            self._buttons.append((rect, action))
            fill = (72, 98, 88) if active else (58, 70, 70)
            pygame.draw.rect(surface, fill, rect, border_radius=3)
            pygame.draw.rect(surface, (108, 132, 120), rect, 1, border_radius=3)
            text = body.render(label, True, (230, 235, 228))
            surface.blit(text, (rect.centerx - text.get_width() // 2, rect.centery - text.get_height() // 2))

        y = panel.y + 58
        surface.blit(body.render("Seed", True, (180, 190, 185)), (panel.x + 14, y + 5))
        self.seed_field.rect = pygame.Rect(panel.x + 70, y, 90, 26)
        self.seed_field.draw(surface, body)
        button(panel.x + 170, y, 100, "Regenerate", "regenerate")
        button(panel.x + 278, y, 110, "Next seed", "reroll")
        y += 40

        surface.blit(body.render("Overlays", True, (150, 190, 165)), (panel.x + 14, y))
        y += 22
        for i, (key, label) in enumerate(OVERLAY_CHOICES):
            button(
                panel.x + 14 + (i % 2) * 196,
                y + (i // 2) * 30,
                188,
                label,
                f"overlay:{key}",
                active=self.overlay_key == key,
            )
        y += 30 * ((len(OVERLAY_CHOICES) + 1) // 2) + 14

        surface.blit(body.render("Tuning", True, (150, 190, 165)), (panel.x + 14, y))
        y += 22
        labels = {
            "soil_region_scale": "Soil region scale",
            "soil_variation_strength": "Soil variation",
            "fertility_region_scale": "Fertility region scale",
            "fertility_variation_strength": "Fertility variation",
            "hydrology_strength": "Hydrology strength",
            "texture_moisture_retention": "Texture→moisture",
        }
        for name, control in self.fields.items():
            surface.blit(body.render(labels[name], True, (185, 195, 190)), (panel.x + 14, y + 5))
            control.rect = pygame.Rect(panel.x + 210, y, 80, 26)
            control.draw(surface, body)
            y += 30

        y += 8
        surface.blit(body.render("Tile inspect", True, (150, 190, 165)), (panel.x + 14, y))
        y += 22
        if self._inspect:
            lines = [
                f"({self._inspect['x']}, {self._inspect['y']})"
                + ("  WATER" if self._inspect["water"] else ""),
                f"soil_texture           {self._inspect['soil_texture']:.2f}",
                f"fertility_potential    {self._inspect['fertility_potential']:.2f}",
                f"hydrological_position  {self._inspect['hydrological_position']:.2f}",
                f"soil_moisture_baseline {self._inspect['soil_moisture_baseline']:.2f}",
                f"elevation (norm)       {self._inspect['elevation']:.2f}",
            ]
            for line in lines:
                surface.blit(body.render(line, True, (200, 215, 205)), (panel.x + 18, y))
                y += 18
        else:
            surface.blit(body.render("Hover a map tile…", True, (140, 150, 145)), (panel.x + 18, y))
            y += 18

        if self.state is not None:
            corr = field_correlations(self.state)
            y = panel.bottom - 118
            surface.blit(body.render("Correlations (non-water)", True, (150, 190, 165)), (panel.x + 14, y))
            y += 20
            for label, key in (
                ("texture vs fertility", "texture_vs_fertility"),
                ("texture vs moisture", "texture_vs_moisture"),
                ("hydrology vs moisture", "hydrology_vs_moisture"),
                ("fertility vs moisture", "fertility_vs_moisture"),
            ):
                surface.blit(
                    body.render(f"{label:24} {corr[key]:+.2f}", True, (170, 185, 175)),
                    (panel.x + 18, y),
                )
                y += 16

        surface.blit(body.render(self.message, True, (190, 195, 190)), (panel.x + 12, panel.bottom - 48))
        button(panel.x + 12, panel.bottom - 30, 220, "Back to Developer Tools", "back")
