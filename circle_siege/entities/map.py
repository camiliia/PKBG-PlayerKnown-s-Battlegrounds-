from __future__ import annotations

import random
from dataclasses import dataclass

import pygame

from ..core.config import DEFAULT_THEME_ID, THEME_BY_ID, WORLD_HEIGHT, WORLD_WIDTH
from ..helpers import Vector2
from ..maps.map_loader import LightZone, MapRegion, ObstacleDef, TriggerZone, load_tmx_bundle


@dataclass
class Obstacle:
    rect: pygame.Rect
    fill_color: tuple[int, int, int]
    edge_color: tuple[int, int, int]
    shadow_color: tuple[int, int, int]
    border_radius: int = 8
    blocks_sight: bool = True
    label: str = ""
    visible: bool = True

    def draw(self, surface: pygame.Surface, camera: Vector2) -> None:
        if not self.visible:
            return
        screen_rect = self.rect.move(-camera.x, -camera.y)
        shadow = screen_rect.move(10, 10)
        pygame.draw.rect(surface, self.shadow_color, shadow, border_radius=self.border_radius + 2)
        pygame.draw.rect(surface, self.fill_color, screen_rect, border_radius=self.border_radius)
        pygame.draw.rect(surface, self.edge_color, screen_rect, width=2, border_radius=self.border_radius)


@dataclass
class Decoration:
    position: Vector2
    radius: int
    fill_color: tuple[int, int, int]
    edge_color: tuple[int, int, int]

    def draw(self, surface: pygame.Surface, camera: Vector2) -> None:
        pos = (int(self.position.x - camera.x), int(self.position.y - camera.y))
        pygame.draw.circle(surface, self.edge_color, pos, self.radius + 2)
        pygame.draw.circle(surface, self.fill_color, pos, self.radius)


class Map:
    def __init__(self, rng: random.Random, theme_id: str = DEFAULT_THEME_ID) -> None:
        self.rng = rng
        self.theme = THEME_BY_ID.get(theme_id, THEME_BY_ID[DEFAULT_THEME_ID])
        self.bounds = pygame.Rect(0, 0, WORLD_WIDTH, WORLD_HEIGHT)
        self.obstacles: list[Obstacle] = []
        self.decorations: list[Decoration] = []
        self.spawn_points: list[Vector2] = []
        self.loot_points: list[Vector2] = []
        self.landmarks: list[tuple[str, Vector2]] = []
        self.cover_points: list[Vector2] = []
        self.triggers: list[TriggerZone] = []
        self.light_zones: list[LightZone] = []
        self.regions: list[MapRegion] = []
        self.parallax_layers: list[tuple[pygame.Surface, float, int]] = []
        self.ground_surface = pygame.Surface((WORLD_WIDTH, WORLD_HEIGHT)).convert()
        self.minimap_base = pygame.Surface((220, 188)).convert()
        if self.theme.tmx_path:
            self._load_tmx_authored_map()
        else:
            self._generate_fallback()

    def _load_tmx_authored_map(self) -> None:
        bundle = load_tmx_bundle(self.theme.tmx_path)
        self.bounds = pygame.Rect(0, 0, bundle.pixel_size[0], bundle.pixel_size[1])
        self.spawn_points = bundle.spawn_points
        self.loot_points = bundle.loot_points
        self.landmarks = bundle.landmarks
        self.cover_points = bundle.cover_points
        self.triggers = bundle.triggers
        self.light_zones = bundle.light_zones
        self.regions = bundle.regions
        self.obstacles = [
            Obstacle(
                rect=info.rect,
                fill_color=(0, 0, 0),
                edge_color=(0, 0, 0),
                shadow_color=(0, 0, 0),
                border_radius=0,
                blocks_sight=info.blocks_sight,
                label=info.label,
                visible=False,
            )
            for info in bundle.obstacles
        ]

        if self.theme.identifier == "cyber_city_tmx":
            self._paint_cyber_city(bundle.surface)
        else:
            self.ground_surface = bundle.surface
            self.minimap_base = bundle.minimap_base
            self.decorations = [
                Decoration(position=point.copy(), radius=8, fill_color=(94, 168, 128), edge_color=(34, 72, 46))
                for point in bundle.cover_points[:80]
            ]

    def _paint_cyber_city(self, base_surface: pygame.Surface) -> None:
        surface = base_surface.copy()
        overlay = pygame.Surface(self.bounds.size, pygame.SRCALPHA)
        overlay.fill((8, 12, 18, 78))
        surface.blit(overlay, (0, 0))

        for x in range(0, self.bounds.width, 64):
            pygame.draw.line(surface, (10, 18, 26, 110), (x, 0), (x, self.bounds.height), 1)
        for y in range(0, self.bounds.height, 64):
            pygame.draw.line(surface, (10, 18, 26, 110), (0, y), (self.bounds.width, y), 1)

        for region in self.regions:
            if region.kind == "road":
                pygame.draw.rect(surface, (38, 48, 62), region.rect, border_radius=12)
                pygame.draw.rect(surface, (62, 78, 96), region.rect, width=2, border_radius=12)
                if region.rect.width > region.rect.height:
                    for x in range(region.rect.left + 28, region.rect.right - 20, 92):
                        pygame.draw.rect(surface, (196, 208, 218), (x, region.rect.centery - 3, 48, 6), border_radius=3)
                else:
                    for y in range(region.rect.top + 28, region.rect.bottom - 20, 92):
                        pygame.draw.rect(surface, (196, 208, 218), (region.rect.centerx - 3, y, 6, 48), border_radius=3)
            elif region.kind == "building":
                pygame.draw.rect(surface, (22, 30, 42), region.rect, border_radius=14)
                pygame.draw.rect(surface, (82, 118, 155), region.rect, width=2, border_radius=14)
                roof = region.rect.inflate(-18, -18)
                pygame.draw.rect(surface, (14, 20, 30), roof, border_radius=10)
            elif region.kind == "platform":
                pygame.draw.rect(surface, (28, 36, 52), region.rect, border_radius=10)
                pygame.draw.rect(surface, (88, 102, 140), region.rect, width=2, border_radius=10)
            elif region.kind == "puddle":
                puddle = pygame.Surface((region.rect.width, region.rect.height), pygame.SRCALPHA)
                puddle.fill((42, 92, 132, 84))
                surface.blit(puddle, region.rect.topleft)
                pygame.draw.ellipse(surface, (126, 210, 255), region.rect, width=2)
            elif region.kind == "billboard":
                pygame.draw.rect(surface, (44, 18, 68), region.rect, border_radius=8)
                pygame.draw.rect(surface, (240, 112, 255), region.rect, width=3, border_radius=8)
                for idx in range(4):
                    pygame.draw.line(
                        surface,
                        (112, 214, 255),
                        (region.rect.left + 12, region.rect.top + 12 + idx * 12),
                        (region.rect.right - 12, region.rect.top + 12 + idx * 12),
                        2,
                    )
            elif region.kind == "neon":
                neon = pygame.Surface((region.rect.width, region.rect.height), pygame.SRCALPHA)
                neon.fill((0, 0, 0, 0))
                pygame.draw.rect(neon, (118, 232, 255, 56), neon.get_rect(), border_radius=6)
                surface.blit(neon, region.rect.topleft)
                pygame.draw.rect(surface, (118, 232, 255), region.rect, width=2, border_radius=6)
            elif region.kind == "underpass":
                under = pygame.Surface((region.rect.width, region.rect.height), pygame.SRCALPHA)
                under.fill((8, 12, 22, 138))
                surface.blit(under, region.rect.topleft)
                pygame.draw.rect(surface, (80, 112, 158), region.rect, width=2, border_radius=8)

        self.ground_surface = surface
        self.minimap_base = pygame.transform.smoothscale(surface, (220, 188)).convert()

        self.decorations = [
            Decoration(position=point.copy(), radius=10, fill_color=(60, 130, 170), edge_color=(140, 250, 255))
            for point in self.cover_points[:120]
        ]
        self.parallax_layers = self._build_cyber_parallax_layers()

    def _generate_fallback(self) -> None:
        self.ground_surface.fill((58, 86, 58))
        self.minimap_base.fill((33, 50, 38))
        self.spawn_points = [
            Vector2(WORLD_WIDTH * 0.2, WORLD_HEIGHT * 0.2),
            Vector2(WORLD_WIDTH * 0.8, WORLD_HEIGHT * 0.2),
            Vector2(WORLD_WIDTH * 0.2, WORLD_HEIGHT * 0.8),
            Vector2(WORLD_WIDTH * 0.8, WORLD_HEIGHT * 0.8),
        ]
        self.loot_points = [point.copy() for point in self.spawn_points]
        self.cover_points = [point + Vector2(18, 0) for point in self.spawn_points]
        center = Vector2(WORLD_WIDTH / 2, WORLD_HEIGHT / 2)
        self.landmarks = [(self.theme.label, center)]
        self.triggers = [TriggerZone(label=self.theme.label, kind="landmark", rect=pygame.Rect(int(center.x - 120), int(center.y - 120), 240, 240))]

    def draw_ground(self, surface: pygame.Surface, camera: Vector2) -> None:
        surface.blit(self.ground_surface, (-camera.x, -camera.y))

    def draw_parallax(self, surface: pygame.Surface, camera: Vector2) -> None:
        if not self.parallax_layers:
            return
        for layer_surface, factor, y_base in self.parallax_layers:
            x = -int(camera.x * factor) % max(1, layer_surface.get_width())
            y = y_base - int(camera.y * factor * 0.12)
            for offset in (-layer_surface.get_width(), 0, layer_surface.get_width()):
                surface.blit(layer_surface, (x + offset, y))

    def draw_decorations(self, surface: pygame.Surface, camera: Vector2) -> None:
        view = pygame.Rect(int(camera.x) - 40, int(camera.y) - 40, surface.get_width() + 80, surface.get_height() + 80)
        for decoration in self.decorations:
            if view.collidepoint(decoration.position):
                decoration.draw(surface, camera)

    def draw_obstacles(self, surface: pygame.Surface, camera: Vector2) -> None:
        view = pygame.Rect(int(camera.x) - 80, int(camera.y) - 80, surface.get_width() + 160, surface.get_height() + 160)
        for obstacle in self.obstacles:
            if obstacle.visible and view.colliderect(obstacle.rect):
                obstacle.draw(surface, camera)

    def set_gate_state(self, prefix: str, is_open: bool) -> None:
        for obstacle in self.obstacles:
            if obstacle.label.startswith(prefix):
                obstacle.blocks_sight = not is_open
                obstacle.visible = not is_open

    def random_safe_point(self, rng: random.Random, margin: int = 90) -> Vector2:
        for _ in range(180):
            point = Vector2(
                rng.randint(margin, max(margin + 1, self.bounds.width - margin)),
                rng.randint(margin, max(margin + 1, self.bounds.height - margin)),
            )
            if any(obstacle.rect.inflate(60, 60).collidepoint(point) for obstacle in self.obstacles):
                continue
            return point
        return Vector2(self.bounds.width / 2, self.bounds.height / 2)

    def nearest_landmark_name(self, position: Vector2) -> str:
        if not self.landmarks:
            return self.theme.label
        name, _ = min(self.landmarks, key=lambda item: position.distance_to(item[1]))
        return name

    def _build_cyber_parallax_layers(self) -> list[tuple[pygame.Surface, float, int]]:
        layers: list[tuple[pygame.Surface, float, int]] = []
        width = self.bounds.width
        far = pygame.Surface((width, 420), pygame.SRCALPHA)
        for x in range(0, width, 180):
            h = self.rng.randint(140, 320)
            rect = pygame.Rect(x, 420 - h, self.rng.randint(96, 160), h)
            pygame.draw.rect(far, (10, 18, 30, 220), rect, border_radius=6)
            for wy in range(rect.top + 16, rect.bottom - 16, 18):
                pygame.draw.rect(far, (92, 176, 255, 40), (rect.left + 12, wy, rect.width - 24, 4), border_radius=2)
        layers.append((far, 0.08, 24))

        mid = pygame.Surface((width, 360), pygame.SRCALPHA)
        for x in range(0, width, 150):
            h = self.rng.randint(120, 280)
            rect = pygame.Rect(x, 360 - h, self.rng.randint(84, 144), h)
            pygame.draw.rect(mid, (18, 26, 44, 200), rect, border_radius=4)
            if x % 300 == 0:
                pygame.draw.rect(mid, (246, 110, 255, 110), (rect.left + 18, rect.top + 24, rect.width - 36, 8), border_radius=3)
        layers.append((mid, 0.16, 74))

        near = pygame.Surface((width, 260), pygame.SRCALPHA)
        for x in range(0, width, 240):
            pygame.draw.rect(near, (24, 36, 60, 190), (x, 180, 180, 80), border_radius=8)
            pygame.draw.rect(near, (104, 214, 255, 120), (x + 18, 190, 120, 10), border_radius=5)
            pygame.draw.rect(near, (255, 190, 88, 80), (x + 48, 214, 92, 8), border_radius=4)
        layers.append((near, 0.24, 138))
        return layers


Arena = Map
