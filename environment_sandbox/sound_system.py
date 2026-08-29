"""Small, failure-tolerant sound-effects and positional ambience controller."""

from __future__ import annotations

import json
import math
import time
from pathlib import Path

import pygame


SOUNDS = Path(__file__).resolve().parent / "assets" / "sounds"
PREFS = SOUNDS / "sound_settings.json"


class SoundSystem:
    def __init__(self, *, enabled: bool = True) -> None:
        self.sfx_volume = 0.7
        self.ambience_volume = 0.55
        self.enabled = False
        self._sounds: dict[str, pygame.mixer.Sound] = {}
        self._forest_channel: pygame.mixer.Channel | None = None
        self._stream_channel: pygame.mixer.Channel | None = None
        self._forest_level = 0.0
        self._stream_level = 0.0
        self._sample_wait = 0.0
        self._last_played: dict[str, float] = {}
        self._load_prefs()
        if not enabled:
            return
        try:
            if pygame.mixer.get_init() is None:
                pygame.mixer.init()
            pygame.mixer.set_num_channels(max(8, pygame.mixer.get_num_channels()))
            files = {
                "door": "dragon-studio-open-door-sfx-454245.mp3",
                "page": "xpmonster-turning-page-in-a-book-419580.mp3",
                "book_close": "freesound_community-book-closing-48184.mp3",
                "forest": "bbc_forest-atm_nhu9679709.mp3",
                "stream": "26327991-water-stream-108384.mp3",
                "build": "freesound_community-wooden-mallet-38769.mp3",
                "craft": "freesound_community-deeper-saw-wood-37224.mp3",
                "plant": "freesound_community-digging-with-shovel-63069.mp3",
                "cook": "freesound_community-cooking-onions-72799.mp3",
                "chop": "wings_of_freedom-chopping-wood-435769.mp3",
            }
            self._sounds = {
                key: pygame.mixer.Sound(str(SOUNDS / filename))
                for key, filename in files.items()
                if (SOUNDS / filename).is_file()
            }
            self._forest_channel = pygame.mixer.Channel(0)
            self._stream_channel = pygame.mixer.Channel(1)
            pygame.mixer.set_reserved(2)
            self.enabled = True
        except (pygame.error, OSError):
            self.enabled = False

    def _load_prefs(self) -> None:
        try:
            raw = json.loads(PREFS.read_text(encoding="utf-8"))
            self.sfx_volume = max(0.0, min(1.0, float(raw.get("sfx", self.sfx_volume))))
            self.ambience_volume = max(0.0, min(1.0, float(raw.get("ambience", self.ambience_volume))))
        except (OSError, ValueError, TypeError, json.JSONDecodeError):
            pass

    def save(self) -> None:
        try:
            PREFS.write_text(
                json.dumps({"sfx": self.sfx_volume, "ambience": self.ambience_volume}, indent=2) + "\n",
                encoding="utf-8",
            )
        except OSError:
            pass

    def play(self, name: str, *, cooldown: float = 0.0) -> None:
        if not self.enabled or self.sfx_volume <= 0.0:
            return
        sound = self._sounds.get(name)
        if sound is not None:
            now = time.monotonic()
            if now - self._last_played.get(name, -1e9) < cooldown:
                return
            self._last_played[name] = now
            sound.set_volume(self.sfx_volume)
            sound.play()

    def update_forest(self, dt: float, world: object, focus_x: float, focus_y: float) -> None:
        """Fade looping forest ambience from camera-focus distance to forest floor."""
        if not self.enabled or self._forest_channel is None:
            return
        self._sample_wait -= max(0.0, dt)
        if self._sample_wait <= 0.0:
            self._sample_wait = 0.20
            from world import TerrainType, is_water_terrain

            radius = 12
            cx, cy = int(focus_x), int(focus_y)
            nearest = float(radius + 1)
            nearest_water = float(radius + 1)
            for y in range(max(0, cy - radius), min(world.rows, cy + radius + 1)):
                for x in range(max(0, cx - radius), min(world.cols, cx + radius + 1)):
                    if world.cells[y][x].terrain == TerrainType.FOREST_FLOOR:
                        nearest = min(nearest, math.hypot(x + 0.5 - focus_x, y + 0.5 - focus_y))
                    if is_water_terrain(world.cells[y][x].terrain):
                        nearest_water = min(nearest_water, math.hypot(x + 0.5 - focus_x, y + 0.5 - focus_y))
            target = self.ambience_volume * max(0.0, min(1.0, (10.0 - nearest) / 8.0))
            stream_target = self.ambience_volume * max(0.0, min(1.0, (8.0 - nearest_water) / 6.0))
            # Retain target separately; level itself eases every frame.
            self._forest_target = target
            self._stream_target = stream_target
        target = getattr(self, "_forest_target", 0.0)
        alpha = 1.0 - math.exp(-2.5 * max(0.0, dt))
        self._forest_level += (target - self._forest_level) * alpha
        forest = self._sounds.get("forest")
        if forest is not None and not self._forest_channel.get_busy() and self._forest_level > 0.002:
            self._forest_channel.play(forest, loops=-1, fade_ms=600)
        self._forest_channel.set_volume(self._forest_level)
        if self._stream_channel is not None:
            stream_target = getattr(self, "_stream_target", 0.0)
            self._stream_level += (stream_target - self._stream_level) * alpha
            stream = self._sounds.get("stream")
            if stream is not None and not self._stream_channel.get_busy() and self._stream_level > 0.002:
                self._stream_channel.play(stream, loops=-1, fade_ms=600)
            self._stream_channel.set_volume(self._stream_level)
