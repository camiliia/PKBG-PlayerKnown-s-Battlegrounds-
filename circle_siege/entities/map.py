from __future__ import annotations

import heapq
import math
import random
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import pygame

from ..core.config import DEFAULT_THEME_ID, RESOURCE_ROOT, THEME_BY_ID
from ..helpers import Vector2, circle_rect_collision
from ..maps.grid_map_loader import GridMapDocument, load_grid_map_document


@dataclass
class TriggerZone:
    label: str
    kind: str
    rect: pygame.Rect
    one_shot: bool = True


@dataclass
class MapRegion:
    kind: str
    label: str
    rect: pygame.Rect


@dataclass
class LightZone:
    color: tuple[int, int, int]
    rect: pygame.Rect
    intensity: int = 68


@dataclass
class Obstacle:
    rect: pygame.Rect
    fill_color: tuple[int, int, int]
    edge_color: tuple[int, int, int]
    shadow_color: tuple[int, int, int]
    border_radius: int = 0
    blocks_movement: bool = True
    blocks_sight: bool = True
    label: str = ""
    visible: bool = False

    def draw(self, surface: pygame.Surface, camera) -> None:
        if not self.visible:
            return
        screen_rect = camera.world_rect_to_screen_bounds(self.rect)
        pygame.draw.rect(surface, self.fill_color, screen_rect, border_radius=self.border_radius)
        pygame.draw.rect(surface, self.edge_color, screen_rect, width=1, border_radius=self.border_radius)


@dataclass
class Decoration:
    position: Vector2
    radius: int
    fill_color: tuple[int, int, int]
    edge_color: tuple[int, int, int]

    def draw(self, surface: pygame.Surface, camera) -> None:
        pos = camera.world_to_screen(self.position)
        radius = max(2, int(round(self.radius * camera.depth_scale(self.position))))
        pygame.draw.circle(surface, self.edge_color, pos, radius + 2)
        pygame.draw.circle(surface, self.fill_color, pos, radius)


class Map:
    def __init__(self, rng: random.Random, theme_id: str = DEFAULT_THEME_ID) -> None:
        self.rng = rng
        self.theme = THEME_BY_ID.get(theme_id, THEME_BY_ID[DEFAULT_THEME_ID])
        self.document = load_grid_map_document(self.theme)
        self.cell_size = self.document.cell_size
        self.cols = self.document.cols
        self.rows = self.document.rows
        self.layers = self.document.layers

        self.bounds = pygame.Rect(0, 0, self.cols * self.cell_size, self.rows * self.cell_size)
        self.obstacles: list[Obstacle] = []
        self.decorations: list[Decoration] = []
        self.spawn_points: list[Vector2] = []
        self.player_spawn_points: list[Vector2] = []
        self.enemy_spawn_points: list[Vector2] = []
        self.loot_points: list[Vector2] = []
        self.cover_points: list[Vector2] = []
        self.landmarks: list[tuple[str, Vector2]] = []
        self.triggers: list[TriggerZone] = []
        self.light_zones: list[LightZone] = []
        self.regions: list[MapRegion] = []
        self.walkable_points: list[Vector2] = []
        self.parallax_layers: list[tuple[pygame.Surface, float, int]] = []
        self.collision_mask: pygame.Mask | None = None
        self.open_passages: dict[str, pygame.Rect] = {}

        self._rebuild_runtime_layers()
        self.ground_surface = self._build_ground_surface()
        self.minimap_base = pygame.transform.smoothscale(self.ground_surface, (220, 188)).convert()

    @property
    def collision_layer(self) -> list[list[int]]:
        return self.layers["collision"]

    @property
    def player_spawn_layer(self) -> list[list[int]]:
        return self.layers["player_spawn"]

    @property
    def enemy_spawn_layer(self) -> list[list[int]]:
        return self.layers["enemy_spawn"]

    @property
    def loot_spawn_layer(self) -> list[list[int]]:
        return self.layers["loot_spawn"]

    def _rebuild_runtime_layers(self) -> None:
        self.obstacles = []
        self.walkable_points = []
        self.player_spawn_points = []
        self.enemy_spawn_points = []
        self.loot_points = []
        self.cover_points = []

        for row in range(self.rows):
            for col in range(self.cols):
                rect = self.cell_rect((col, row))
                if self.is_blocked_cell((col, row)):
                    self.obstacles.append(
                        Obstacle(
                            rect=rect,
                            fill_color=(20, 24, 30),
                            edge_color=(82, 102, 122),
                            shadow_color=(0, 0, 0),
                            label=f"wall:{col}:{row}",
                        )
                    )
                    continue

                center = self.cell_to_world((col, row))
                self.walkable_points.append(center)
                if self.player_spawn_layer[row][col] > 0:
                    self.player_spawn_points.append(center)
                if self.enemy_spawn_layer[row][col] > 0:
                    self.enemy_spawn_points.append(center)
                if self.loot_spawn_layer[row][col] > 0:
                    self.loot_points.append(center)

        if not self.player_spawn_points:
            fallback = self.find_nearest_walkable_point(Vector2(self.bounds.center), clearance=18.0, search_limit=max(self.bounds.size))
            self.player_spawn_points = [fallback] if fallback is not None else [Vector2(self.bounds.center)]
        if not self.enemy_spawn_points:
            self.enemy_spawn_points = self._spread_points(self.walkable_points, limit=12) or [point.copy() for point in self.player_spawn_points]
        if not self.loot_points:
            self.loot_points = self._spread_points(self.walkable_points, limit=64) or [point.copy() for point in self.player_spawn_points]

        self.spawn_points = [point.copy() for point in self.player_spawn_points + self.enemy_spawn_points]
        self.cover_points = self._build_cover_points()
        center = Vector2(self.bounds.center)
        self.landmarks = [
            (self.theme.label, center),
            ("north", Vector2(center.x, self.cell_size * 2.5)),
            ("south", Vector2(center.x, self.bounds.height - self.cell_size * 2.5)),
            ("west", Vector2(self.cell_size * 2.5, center.y)),
            ("east", Vector2(self.bounds.width - self.cell_size * 2.5, center.y)),
        ]
        light_rect = pygame.Rect(0, 0, min(360, self.bounds.width), min(300, self.bounds.height))
        light_rect.center = self.bounds.center
        self.light_zones = [LightZone(color=self.theme.accent, rect=light_rect, intensity=32)]

    def _spread_points(self, points: list[Vector2], *, limit: int) -> list[Vector2]:
        if not points:
            return []
        step = max(1, len(points) // max(1, limit))
        selected = [points[index].copy() for index in range(0, len(points), step)]
        return selected[:limit]

    def _build_cover_points(self) -> list[Vector2]:
        points: list[Vector2] = []
        for col, row in self._blocked_cells():
            for neighbor in ((col + 1, row), (col - 1, row), (col, row + 1), (col, row - 1)):
                if not self.is_blocked_cell(neighbor):
                    points.append(self.cell_to_world(neighbor))
        return self._dedupe_points(points, minimum_distance=self.cell_size * 0.75, limit=160)

    @staticmethod
    def _dedupe_points(points: list[Vector2], *, minimum_distance: float, limit: int) -> list[Vector2]:
        selected: list[Vector2] = []
        for point in points:
            if any(point.distance_to(existing) < minimum_distance for existing in selected):
                continue
            selected.append(point.copy())
            if len(selected) >= limit:
                break
        return selected

    def _blocked_cells(self) -> Iterable[tuple[int, int]]:
        for row in range(self.rows):
            for col in range(self.cols):
                if self.is_blocked_cell((col, row)):
                    yield col, row

    def _build_ground_surface(self) -> pygame.Surface:
        surface = pygame.Surface(self.bounds.size).convert()
        background = self._load_background()
        if background is not None:
            surface.blit(self._scale_surface_cover(background, self.bounds.size), (0, 0))
        else:
            self._paint_default_ground(surface)

        shade = pygame.Surface(self.bounds.size, pygame.SRCALPHA)
        shade.fill((6, 10, 14, 84))
        surface.blit(shade, (0, 0))

        return surface

    def _paint_default_ground(self, surface: pygame.Surface) -> None:
        surface.fill((26, 36, 40))
        for y in range(0, self.bounds.height, 8):
            alpha = y / max(1, self.bounds.height)
            color = (
                int(24 + self.theme.accent[0] * 0.08 * alpha),
                int(34 + self.theme.accent[1] * 0.08 * alpha),
                int(40 + self.theme.accent[2] * 0.08 * alpha),
            )
            pygame.draw.line(surface, color, (0, y), (self.bounds.width, y))

    def _load_background(self) -> pygame.Surface | None:
        background = self.document.background_image
        if not background:
            return None
        path = Path(background)
        if not path.is_absolute():
            path = RESOURCE_ROOT.parent / background
        if not path.exists():
            return None
        try:
            return pygame.image.load(str(path)).convert()
        except pygame.error:
            return None

    @staticmethod
    def _scale_surface_cover(surface: pygame.Surface, size: tuple[int, int]) -> pygame.Surface:
        target_width, target_height = size
        scale = max(target_width / surface.get_width(), target_height / surface.get_height())
        scaled_size = (max(1, int(surface.get_width() * scale)), max(1, int(surface.get_height() * scale)))
        scaled = pygame.transform.smoothscale(surface, scaled_size)
        result = pygame.Surface(size).convert()
        result.blit(scaled, ((target_width - scaled_size[0]) // 2, (target_height - scaled_size[1]) // 2))
        return result

    def cell_rect(self, cell: tuple[int, int]) -> pygame.Rect:
        col, row = cell
        return pygame.Rect(col * self.cell_size, row * self.cell_size, self.cell_size, self.cell_size)

    def cell_to_world(self, cell: tuple[int, int]) -> Vector2:
        col, row = cell
        return Vector2((col + 0.5) * self.cell_size, (row + 0.5) * self.cell_size)

    def world_to_cell(self, point: Vector2 | tuple[float, float]) -> tuple[int, int]:
        vector = Vector2(point)
        col = int(vector.x // self.cell_size)
        row = int(vector.y // self.cell_size)
        return col, row

    def in_bounds_cell(self, cell: tuple[int, int]) -> bool:
        col, row = cell
        return 0 <= col < self.cols and 0 <= row < self.rows

    def is_blocked_cell(self, cell: tuple[int, int]) -> bool:
        col, row = cell
        if not self.in_bounds_cell(cell):
            return True
        return self.collision_layer[row][col] > 0

    def point_in_open_passage(self, point: Vector2) -> bool:
        return any(rect.collidepoint(int(point.x), int(point.y)) for rect in self.open_passages.values())

    def blocks_circle(self, center: Vector2, radius: float) -> bool:
        if self.point_in_open_passage(center):
            return False
        min_col = int((center.x - radius) // self.cell_size)
        max_col = int((center.x + radius) // self.cell_size)
        min_row = int((center.y - radius) // self.cell_size)
        max_row = int((center.y + radius) // self.cell_size)
        for row in range(min_row, max_row + 1):
            for col in range(min_col, max_col + 1):
                if not self.is_blocked_cell((col, row)):
                    continue
                if circle_rect_collision(center, radius, self.cell_rect((col, row))):
                    return True
        return False

    def segment_hits_blocking(self, start: Vector2, end: Vector2, radius: float = 0.0) -> Vector2 | None:
        distance = start.distance_to(end)
        steps = max(2, int(distance / max(4.0, self.cell_size / 4)))
        for index in range(1, steps + 1):
            point = start.lerp(end, index / steps)
            if self.blocks_circle(point, radius):
                return point
        return None

    def has_line_of_sight(self, start: Vector2, end: Vector2) -> bool:
        return self.segment_hits_blocking(start, end, radius=0.0) is None

    def is_walkable_point(self, point: Vector2, clearance: float = 24.0, margin: float = 0.0) -> bool:
        min_edge = clearance + margin
        if point.x < min_edge or point.y < min_edge:
            return False
        if point.x > self.bounds.right - min_edge or point.y > self.bounds.bottom - min_edge:
            return False
        return not self.blocks_circle(point, clearance)

    def find_nearest_walkable_point(
        self,
        origin: Vector2,
        *,
        clearance: float = 28.0,
        search_limit: float = 220.0,
        margin: float = 0.0,
    ) -> Vector2 | None:
        if self.is_walkable_point(origin, clearance=clearance, margin=margin):
            return origin.copy()
        origin_cell = self.world_to_cell(origin)
        max_radius = max(1, int(math.ceil(search_limit / self.cell_size)))
        for radius in range(1, max_radius + 1):
            candidates: list[Vector2] = []
            for row in range(origin_cell[1] - radius, origin_cell[1] + radius + 1):
                for col in range(origin_cell[0] - radius, origin_cell[0] + radius + 1):
                    if abs(col - origin_cell[0]) != radius and abs(row - origin_cell[1]) != radius:
                        continue
                    if self.is_blocked_cell((col, row)):
                        continue
                    point = self.cell_to_world((col, row))
                    if point.distance_to(origin) > search_limit:
                        continue
                    if self.is_walkable_point(point, clearance=clearance, margin=margin):
                        candidates.append(point)
            if candidates:
                return min(candidates, key=lambda point: point.distance_to(origin))
        return None

    def random_safe_point(self, rng: random.Random, margin: int = 90) -> Vector2:
        candidates = [
            point
            for point in self.walkable_points
            if margin <= point.x <= self.bounds.width - margin and margin <= point.y <= self.bounds.height - margin
        ]
        if candidates:
            return rng.choice(candidates).copy()
        return Vector2(self.bounds.center)

    def random_open_cell(self, rng: random.Random, *, margin_cells: int = 1) -> tuple[int, int]:
        candidates = [
            self.world_to_cell(point)
            for point in self.walkable_points
            if margin_cells <= point.x // self.cell_size < self.cols - margin_cells
            and margin_cells <= point.y // self.cell_size < self.rows - margin_cells
        ]
        if candidates:
            return rng.choice(candidates)
        return self.world_to_cell(Vector2(self.bounds.center))

    def find_path(
        self,
        start: Vector2,
        goal: Vector2,
        *,
        max_nodes: int = 3200,
        preferred_dir: tuple[int, int] | None = None,
        forbidden_first_cell: tuple[int, int] | None = None,
    ) -> list[Vector2]:
        start_cell = self.world_to_cell(start)
        goal_cell = self.world_to_cell(goal)
        if self.is_blocked_cell(goal_cell):
            nearest = self.find_nearest_walkable_point(goal, clearance=18.0, search_limit=self.cell_size * 6)
            if nearest is None:
                return []
            goal_cell = self.world_to_cell(nearest)
        if self.is_blocked_cell(start_cell):
            nearest = self.find_nearest_walkable_point(start, clearance=18.0, search_limit=self.cell_size * 6)
            if nearest is None:
                return []
            start_cell = self.world_to_cell(nearest)
        if start_cell == goal_cell:
            return [self.cell_to_world(goal_cell)]

        path = self._find_path_cells(
            start_cell,
            goal_cell,
            max_nodes=max_nodes,
            preferred_dir=preferred_dir,
            forbidden_first_cell=forbidden_first_cell,
        )
        if not path and forbidden_first_cell is not None:
            path = self._find_path_cells(
                start_cell,
                goal_cell,
                max_nodes=max_nodes,
                preferred_dir=preferred_dir,
                forbidden_first_cell=None,
            )
        return [self.cell_to_world(cell) for cell in path[1:]] if path else []

    def _find_path_cells(
        self,
        start_cell: tuple[int, int],
        goal_cell: tuple[int, int],
        *,
        max_nodes: int,
        preferred_dir: tuple[int, int] | None,
        forbidden_first_cell: tuple[int, int] | None,
    ) -> list[tuple[int, int]]:
        frontier: list[tuple[float, int, int, float, int, tuple[int, int]]] = []
        start_h = self._cell_distance(start_cell, goal_cell)
        heapq.heappush(frontier, (start_h, 0, 0, start_h, 0, start_cell))
        came_from: dict[tuple[int, int], tuple[int, int] | None] = {start_cell: None}
        cost_so_far: dict[tuple[int, int], float] = {start_cell: 0.0}
        counter = 0

        while frontier and len(came_from) < max_nodes:
            _, _, _, _, _, current = heapq.heappop(frontier)
            if current == goal_cell:
                break
            current_parent = came_from[current]
            current_dir = self._step_dir(current_parent, current) if current_parent is not None else preferred_dir
            for neighbor, move_cost in self._neighbors(current):
                if current == start_cell and forbidden_first_cell is not None and neighbor == forbidden_first_cell:
                    continue
                new_cost = cost_so_far[current] + move_cost
                if neighbor in cost_so_far and new_cost >= cost_so_far[neighbor]:
                    continue
                cost_so_far[neighbor] = new_cost
                h_cost = self._cell_distance(neighbor, goal_cell)
                priority = new_cost + h_cost
                step_dir = self._step_dir(current, neighbor)
                turn_penalty = 0 if current_dir is not None and step_dir == current_dir else 1
                backtrack_penalty = 1 if forbidden_first_cell is not None and neighbor == forbidden_first_cell else 0
                counter += 1
                heapq.heappush(frontier, (priority, turn_penalty, backtrack_penalty, h_cost, counter, neighbor))
                came_from[neighbor] = current

        if goal_cell not in came_from:
            return []

        cells: list[tuple[int, int]] = []
        current: tuple[int, int] | None = goal_cell
        while current is not None:
            cells.append(current)
            current = came_from[current]
        cells.reverse()
        return cells

    def _neighbors(self, cell: tuple[int, int]) -> Iterable[tuple[tuple[int, int], float]]:
        col, row = cell
        for dx, dy, cost in (
            (1, 0, 1.0),
            (-1, 0, 1.0),
            (0, 1, 1.0),
            (0, -1, 1.0),
            (1, 1, 1.414),
            (-1, 1, 1.414),
            (1, -1, 1.414),
            (-1, -1, 1.414),
        ):
            neighbor = (col + dx, row + dy)
            if self.is_blocked_cell(neighbor):
                continue
            if dx != 0 and dy != 0 and (self.is_blocked_cell((col + dx, row)) or self.is_blocked_cell((col, row + dy))):
                continue
            yield neighbor, cost

    @staticmethod
    def _cell_distance(a: tuple[int, int], b: tuple[int, int]) -> float:
        return math.hypot(a[0] - b[0], a[1] - b[1])

    @staticmethod
    def _step_dir(a: tuple[int, int], b: tuple[int, int]) -> tuple[int, int]:
        dx = b[0] - a[0]
        dy = b[1] - a[1]
        return (0 if dx == 0 else (1 if dx > 0 else -1), 0 if dy == 0 else (1 if dy > 0 else -1))

    def draw_ground(self, surface: pygame.Surface, camera) -> None:
        surface.blit(self.ground_surface, (-camera.position.x, -camera.position.y))

    def draw_parallax(self, surface: pygame.Surface, camera: Vector2) -> None:
        return

    def draw_decorations(self, surface: pygame.Surface, camera) -> None:
        view = camera.view_rect().inflate(80, 80)
        for decoration in self.decorations:
            if view.collidepoint(decoration.position):
                decoration.draw(surface, camera)

    def draw_obstacles(self, surface: pygame.Surface, camera) -> None:
        view = camera.view_rect().inflate(160, 160)
        for obstacle in self.obstacles:
            if obstacle.visible and view.colliderect(obstacle.rect):
                obstacle.draw(surface, camera)

    def set_gate_state(self, prefix: str, is_open: bool, region_rect: pygame.Rect | None = None) -> None:
        if is_open and region_rect is not None:
            self.open_passages[prefix] = region_rect.copy()
        else:
            self.open_passages.pop(prefix, None)

    def nearest_landmark_name(self, position: Vector2) -> str:
        if not self.landmarks:
            return self.theme.label
        name, _ = min(self.landmarks, key=lambda item: position.distance_to(item[1]))
        return name


Arena = Map
