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
        self.horizon_y = 108.0
        self.ground_y_scale = 0.72
        self.ground_x_skew = 0.16
        self.focus_screen_x = SCREEN_WIDTH / 2
        self.focus_screen_y = SCREEN_HEIGHT * 0.68
        self._base_position = Vector2()
        self._shake_amplitude = 0.0
        self._shake_timer = 0.0
        self._rng = random.Random()

    def focus_ground_y(self) -> float:
        return (self.focus_screen_y - self.horizon_y) / self.ground_y_scale

    def set_world_size(self, width: int, height: int) -> None:
        self.world_width = max(width, SCREEN_WIDTH)
        self.world_height = max(height, SCREEN_HEIGHT)

    def snap_to(self, target: Vector2) -> None:
        desired = target - Vector2(self.focus_screen_x, self.focus_ground_y())
        desired.x = clamp(desired.x, 0.0, self.world_width - SCREEN_WIDTH)
        desired.y = clamp(desired.y, 0.0, self.world_height - SCREEN_HEIGHT)
        self._base_position = desired.copy()
        self.position = desired.copy()

    def update(self, target: Vector2, dt: float) -> None:
        desired = target - Vector2(self.focus_screen_x, self.focus_ground_y())
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
        rel_x = position.x - self.position.x
        rel_y = position.y - self.position.y
        projected_x = rel_x + (rel_y - self.focus_ground_y()) * self.ground_x_skew
        projected_y = self.horizon_y + rel_y * self.ground_y_scale
        return int(round(projected_x)), int(round(projected_y))

    def screen_to_world(self, position: Vector2) -> Vector2:
        rel_y = (position.y - self.horizon_y) / max(0.001, self.ground_y_scale)
        rel_x = position.x - (rel_y - self.focus_ground_y()) * self.ground_x_skew
        return self.position + Vector2(rel_x, rel_y)

    def depth_scale(self, position: Vector2) -> float:
        rel_y = clamp((position.y - self.position.y) / max(1.0, float(SCREEN_HEIGHT)), 0.0, 1.0)
        return 0.84 + rel_y * 0.24

    def project_vertical_distance(self, distance: float) -> int:
        return max(1, int(round(distance * self.ground_y_scale)))

    def world_rect_to_screen_bounds(self, rect: pygame.Rect) -> pygame.Rect:
        points = [
            self.world_to_screen(Vector2(rect.left, rect.top)),
            self.world_to_screen(Vector2(rect.right, rect.top)),
            self.world_to_screen(Vector2(rect.right, rect.bottom)),
            self.world_to_screen(Vector2(rect.left, rect.bottom)),
        ]
        xs = [point[0] for point in points]
        ys = [point[1] for point in points]
        return pygame.Rect(min(xs), min(ys), max(xs) - min(xs), max(ys) - min(ys))

    def view_rect(self) -> pygame.Rect:
        return pygame.Rect(int(self.position.x), int(self.position.y), SCREEN_WIDTH, SCREEN_HEIGHT)
