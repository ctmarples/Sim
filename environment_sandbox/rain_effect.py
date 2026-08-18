"""Cheap screen-space rain particles; never invalidates world render caches."""

from __future__ import annotations

import random

import pygame


class RainEffect:
    def __init__(self, seed: int, max_drops: int = 320) -> None:
        rng = random.Random(int(seed) ^ 0xA17F4)
        self._drops = [
            [
                rng.random(),
                rng.random(),
                rng.uniform(0.72, 1.35),
                rng.uniform(-0.13, -0.05),
                rng.random(),
            ]
            for _ in range(max_drops)
        ]
        self._surface: pygame.Surface | None = None

    def reset_seed(self, seed: int) -> None:
        self.__init__(seed, len(self._drops))

    def update(self, dt: float, intensity: float) -> None:
        if intensity <= 0.0:
            return
        step = min(0.1, max(0.0, float(dt)))
        for drop in self._drops:
            drop[0] = (drop[0] + drop[3] * step) % 1.08
            drop[1] = (drop[1] + drop[2] * step) % 1.08

    def draw(
        self,
        target: pygame.Surface,
        rect: pygame.Rect,
        intensity: float,
        *,
        rainfall: list[list[float]] | None = None,
        world_view: tuple[float, float, float, float] | None = None,
    ) -> None:
        strength = max(0.0, min(1.0, float(intensity)))
        if strength <= 0.0 or rect.w <= 0 or rect.h <= 0:
            return
        size = rect.size
        if self._surface is None or self._surface.get_size() != size:
            self._surface = pygame.Surface(size, pygame.SRCALPHA)
        rain = self._surface
        rain.fill((0, 0, 0, 0))
        alpha = int(75 + 105 * strength)
        length = int(7 + 8 * strength)
        colour = (175, 205, 230, alpha)
        rows = len(rainfall) if rainfall else 0
        cols = len(rainfall[0]) if rows else 0
        # Evaluate the complete fixed pool against local rainfall. Previously
        # the pool was first reduced by regional strength and then filtered by
        # local strength, unintentionally squaring intensity and making local
        # differences almost invisible in light/moderate events.
        for nx, ny, speed, drift, threshold in self._drops:
            local_strength = strength
            if rows and cols and world_view is not None:
                wx = int(world_view[0] + nx * world_view[2])
                wy = int(world_view[1] + ny * world_view[3])
                if not (0 <= wx < cols and 0 <= wy < rows):
                    continue
                local_strength = max(0.0, min(1.0, rainfall[wy][wx]))
            if threshold > local_strength:
                continue
            x = int(nx * rect.w)
            y = int(ny * rect.h)
            local_alpha = int(alpha * (0.45 + 0.55 * local_strength))
            local_colour = (*colour[:3], local_alpha)
            pygame.draw.line(
                rain,
                local_colour,
                (x, y),
                (x - max(2, length // 3), y + length),
                1,
            )
        # One composited blit; terrain/world caches remain untouched.
        target.blit(rain, rect.topleft)
