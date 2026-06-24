from __future__ import annotations

import random

import pygame

from ..core.config import SCREEN_HEIGHT, SCREEN_WIDTH
from ..helpers import Vector2, clamp


class Camera:
    def __init__(self) -> None:
        self.position = Vector2()
        self.world_width = SCREEN_WIDTH
        self.world_height = SCREEN_HEIGHT
        self._base_position = Vector2()
        self._shake_amplitude = 0.0
        self._shake_timer = 0.0
        self._rng = random.Random()

    def set_world_size(self, width: int, height: int) -> None:
        self.world_width = max(width, SCREEN_WIDTH)
        self.world_height = max(height, SCREEN_HEIGHT)

    def update(self, target: Vector2, dt: float) -> None:
        desired = target - Vector2(SCREEN_WIDTH / 2, SCREEN_HEIGHT / 2)
        self._base_position = self._base_position.lerp(desired, min(1.0, dt * 8.0))
        self._base_position.x = clamp(self._base_position.x, 0.0, self.world_width - SCREEN_WIDTH)
        self._base_position.y = clamp(self._base_position.y, 0.0, self.world_height - SCREEN_HEIGHT)
        self.position = self._base_position.copy()
        if self._shake_timer > 0.0:
            self._shake_timer = max(0.0, self._shake_timer - dt)
            amplitude = self._shake_amplitude * (self._shake_timer / max(0.001, self._shake_timer + dt))
            self.position.x += self._rng.uniform(-amplitude, amplitude)
            self.position.y += self._rng.uniform(-amplitude, amplitude)

    def add_shake(self, amplitude: float, duration: float) -> None:
        self._shake_amplitude = max(self._shake_amplitude, amplitude)
        self._shake_timer = max(self._shake_timer, duration)

    def world_to_screen(self, position: Vector2) -> tuple[int, int]:
        return int(position.x - self.position.x), int(position.y - self.position.y)

    def view_rect(self) -> pygame.Rect:
        return pygame.Rect(int(self.position.x), int(self.position.y), SCREEN_WIDTH, SCREEN_HEIGHT)
