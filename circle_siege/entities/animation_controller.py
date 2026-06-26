from __future__ import annotations

import math

import pygame

from ..helpers import Vector2, safe_normalize


class AnimationController:
    DIRECTION_ORDER = (
        "east",
        "southeast",
        "south",
        "southwest",
        "west",
        "northwest",
        "north",
        "northeast",
    )
    DIRECTION_VECTORS = {
        "east": Vector2(1, 0),
        "southeast": safe_normalize(Vector2(1, 1)),
        "south": Vector2(0, 1),
        "southwest": safe_normalize(Vector2(-1, 1)),
        "west": Vector2(-1, 0),
        "northwest": safe_normalize(Vector2(-1, -1)),
        "north": Vector2(0, -1),
        "northeast": safe_normalize(Vector2(1, -1)),
    }
    FRAME_COUNTS = {
        "idle": 1,
        "move": 4,
        "fire": 3,
        "dead": 4,
    }
    FRAME_RATES = {
        "idle": 1.0,
        "move": 8.0,
        "fire": 18.0,
        "dead": 7.0,
    }

    SHEET_DIRECTION_ORDER = (
        "north",
        "northeast",
        "east",
        "southeast",
        "south",
        "southwest",
        "west",
        "northwest",
    )

    def __init__(
        self,
        base_surface: pygame.Surface | None = None,
        *,
        directional_bases: dict[str, pygame.Surface] | None = None,
        scale: float = 1.0,
        default_angle: float = 45.0,
    ) -> None:
        self.base_surface = base_surface
        self.directional_bases = directional_bases or {}
        self.scale = scale
        self.default_angle = default_angle
        base_sizes = []
        if base_surface is not None:
            base_sizes.append(max(base_surface.get_width(), base_surface.get_height()))
        for surface in self.directional_bases.values():
            base_sizes.append(max(surface.get_width(), surface.get_height()))
        max_size = max(base_sizes) if base_sizes else 96
        self.canvas_size = max(128, int(max_size * max(scale, 1.0)) + 32)
        self._base_cache: dict[str, pygame.Surface] = {}
        self._frame_cache: dict[tuple[str, str, int], pygame.Surface] = {}
        self._build_frames()

    @classmethod
    def from_direction_sheet(
        cls,
        sheet_surface: pygame.Surface,
        *,
        columns: int = 4,
        rows: int = 2,
        scale: float = 1.0,
        default_angle: float = 45.0,
    ) -> "AnimationController":
        cell_width = sheet_surface.get_width() // columns
        cell_height = sheet_surface.get_height() // rows
        bases: dict[str, pygame.Surface] = {}
        for index, direction in enumerate(cls.SHEET_DIRECTION_ORDER):
            col = index % columns
            row = index // columns
            rect = pygame.Rect(col * cell_width, row * cell_height, cell_width, cell_height)
            bases[direction] = sheet_surface.subsurface(rect).copy()
        return cls(directional_bases=bases, scale=scale, default_angle=default_angle)

    @classmethod
    def from_state_sheets(
        cls,
        state_sheets: dict[str, pygame.Surface],
        *,
        sheet_direction_orders: dict[str, tuple[str, ...]] | None = None,
        scale: float = 1.0,
        default_angle: float = 45.0,
    ) -> "AnimationController":
        controller = cls.__new__(cls)
        controller.base_surface = None
        controller.directional_bases = {}
        controller.scale = scale
        controller.default_angle = default_angle
        controller._base_cache = {}
        controller._frame_cache = {}
        resolved_direction_orders: dict[str, tuple[str, ...]] = {}

        resolved_state_sheets: dict[str, pygame.Surface] = {}
        for state, frame_count in cls.FRAME_COUNTS.items():
            sheet = state_sheets.get(state)
            if sheet is None:
                raise ValueError(f"Missing animation sheet for state '{state}'.")
            resolved_state_sheets[state] = sheet
            row_order = (sheet_direction_orders or {}).get(state, cls.DIRECTION_ORDER)
            if len(row_order) != len(cls.DIRECTION_ORDER):
                raise ValueError(f"State '{state}' row order must contain {len(cls.DIRECTION_ORDER)} directions.")
            resolved_direction_orders[state] = row_order
            cell_width = max(1, sheet.get_width() // frame_count)
            cell_height = max(1, sheet.get_height() // len(row_order))
            controller.canvas_size = max(getattr(controller, "canvas_size", 0), cell_width, cell_height)

        for state, frame_count in cls.FRAME_COUNTS.items():
            sheet = resolved_state_sheets[state]
            row_order = resolved_direction_orders[state]
            cell_width = sheet.get_width() // frame_count
            cell_height = sheet.get_height() // len(row_order)
            for row, direction in enumerate(row_order):
                for col in range(frame_count):
                    rect = pygame.Rect(col * cell_width, row * cell_height, cell_width, cell_height)
                    frame = sheet.subsurface(rect).copy()
                    if frame.get_size() != (controller.canvas_size, controller.canvas_size):
                        frame = pygame.transform.smoothscale(frame, (controller.canvas_size, controller.canvas_size))
                    controller._frame_cache[(state, direction, col)] = frame
                    if state == "idle" and col == 0:
                        controller._base_cache[direction] = frame.copy()
                        controller.directional_bases[direction] = frame.copy()

        return controller

    def get_frame(self, facing: Vector2, state: str, elapsed: float) -> pygame.Surface:
        direction = self.direction_name(facing)
        frame_count = self.FRAME_COUNTS.get(state, 1)
        if state == "dead":
            index = min(frame_count - 1, int(elapsed * self.FRAME_RATES.get(state, 1.0)))
        elif frame_count <= 1:
            index = 0
        else:
            index = int(elapsed * self.FRAME_RATES.get(state, 1.0)) % frame_count
        return self._frame_cache[(state, direction, index)]

    def export_sheet(self, state: str) -> pygame.Surface:
        frame_count = self.FRAME_COUNTS[state]
        sheet = pygame.Surface((self.canvas_size * frame_count, self.canvas_size * len(self.DIRECTION_ORDER)), pygame.SRCALPHA)
        for row, direction in enumerate(self.DIRECTION_ORDER):
            for col in range(frame_count):
                frame = self._frame_cache[(state, direction, col)]
                sheet.blit(frame, (col * self.canvas_size, row * self.canvas_size))
        return sheet

    def direction_name(self, facing: Vector2) -> str:
        facing = safe_normalize(facing)
        if facing.length_squared() <= 0.0:
            return "east"
        best_name = "east"
        best_score = -1e9
        for name, direction in self.DIRECTION_VECTORS.items():
            score = facing.dot(direction)
            if score > best_score:
                best_score = score
                best_name = name
        return best_name

    def _build_frames(self) -> None:
        for direction in self.DIRECTION_ORDER:
            self._base_cache[direction] = self._build_directional_base(direction)
            for state, frame_count in self.FRAME_COUNTS.items():
                for frame_index in range(frame_count):
                    self._frame_cache[(state, direction, frame_index)] = self._build_state_frame(direction, state, frame_index)

    def _build_directional_base(self, direction: str) -> pygame.Surface:
        if direction in self.directional_bases:
            return self.directional_bases[direction].copy()
        vector = self.DIRECTION_VECTORS[direction]
        angle_deg = math.degrees(math.atan2(vector.y, vector.x))
        rotation = self.default_angle - angle_deg
        if self.base_surface is None:
            raise ValueError("AnimationController requires a base surface or directional sheet.")
        return pygame.transform.rotozoom(self.base_surface, rotation, self.scale)

    def _build_state_frame(self, direction: str, state: str, frame_index: int) -> pygame.Surface:
        base = self._base_cache[direction]
        forward = self.DIRECTION_VECTORS[direction]
        right = Vector2(-forward.y, forward.x)
        offset = Vector2()
        rotation = 0.0
        scale = 1.0
        tint_add: tuple[int, int, int] | None = None
        tint_mult: tuple[int, int, int] | None = None

        if state == "move":
            bob = (-2.0, 1.0, 2.0, 0.0)[frame_index]
            sway = (-1.5, 1.5, 1.0, -1.0)[frame_index]
            offset = right * sway + Vector2(0, bob)
            scale = (1.0, 1.018, 1.0, 0.992)[frame_index]
        elif state == "fire":
            recoil = (0.0, 4.5, 2.0)[frame_index]
            offset = -forward * recoil + right * (0.0, 0.6, -0.4)[frame_index]
            scale = (1.0, 0.994, 1.0)[frame_index]
            tint_add = (12, 8, 6) if frame_index == 1 else None
        elif state == "dead":
            sign = 1.0 if forward.x >= 0 else -1.0
            rotation = sign * (0.0, 22.0, 56.0, 84.0)[frame_index]
            offset = Vector2(6.0 * sign * frame_index * 0.45, (0.0, 4.0, 9.0, 14.0)[frame_index])
            tint_mult = (138, 138, 138)

        sprite = base
        if abs(scale - 1.0) > 1e-4:
            size = (
                max(1, int(base.get_width() * scale)),
                max(1, int(base.get_height() * scale)),
            )
            sprite = pygame.transform.smoothscale(base, size)
        if abs(rotation) > 1e-4:
            sprite = pygame.transform.rotate(sprite, rotation)
        sprite = sprite.copy()
        if tint_mult is not None:
            sprite.fill((*tint_mult, 255), special_flags=pygame.BLEND_RGBA_MULT)
        if tint_add is not None:
            sprite.fill((*tint_add, 0), special_flags=pygame.BLEND_RGBA_ADD)

        frame = pygame.Surface((self.canvas_size, self.canvas_size), pygame.SRCALPHA)
        rect = sprite.get_rect(center=(int(self.canvas_size / 2 + offset.x), int(self.canvas_size / 2 + offset.y)))
        frame.blit(sprite, rect)
        return frame
