from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path

import pygame
from pytmx import TiledImageLayer, TiledObjectGroup, TiledTileLayer
from pytmx.util_pygame import load_pygame

from ..helpers import Vector2


@dataclass
class TriggerZone:
    label: str
    kind: str
    rect: pygame.Rect
    one_shot: bool = True


@dataclass
class ObstacleDef:
    rect: pygame.Rect
    label: str = ""
    blocks_sight: bool = True


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
class TmxMapBundle:
    pixel_size: tuple[int, int]
    surface: pygame.Surface
    obstacles: list[ObstacleDef]
    spawn_points: list[Vector2]
    loot_points: list[Vector2]
    landmarks: list[tuple[str, Vector2]]
    cover_points: list[Vector2]
    triggers: list[TriggerZone]
    regions: list[MapRegion]
    light_zones: list[LightZone]
    minimap_base: pygame.Surface
    collision_mask: pygame.Mask | None = None


def load_tmx_bundle(path: str | Path) -> TmxMapBundle:
    path = Path(path)
    tmx = load_pygame(str(path))
    has_image_backdrop = any(isinstance(layer, TiledImageLayer) for layer in tmx.layers)
    pixel_width = tmx.width * tmx.tilewidth
    pixel_height = tmx.height * tmx.tileheight
    if tmx.width == 1 and tmx.tilewidth > 256:
        pixel_width = tmx.tilewidth
    if tmx.height == 1 and tmx.tileheight > 256:
        pixel_height = tmx.tileheight

    surface = pygame.Surface((pixel_width, pixel_height)).convert_alpha()
    if tmx.background_color:
        surface.fill(pygame.Color(tmx.background_color))
    else:
        surface.fill((0, 0, 0, 0))

    for layer in tmx.visible_layers:
        if isinstance(layer, TiledTileLayer):
            for x, y, image in layer.tiles():
                surface.blit(image, (x * tmx.tilewidth, y * tmx.tileheight))
        elif isinstance(layer, TiledImageLayer):
            if layer.image:
                if layer.image.get_width() != pixel_width or layer.image.get_height() != pixel_height:
                    scaled = pygame.transform.smoothscale(layer.image, (pixel_width, pixel_height))
                    surface.blit(scaled, (0, 0))
                else:
                    surface.blit(layer.image, (0, 0))
        elif isinstance(layer, TiledObjectGroup):
            for obj in layer:
                if getattr(obj, "image", None):
                    surface.blit(obj.image, (obj.x, obj.y - obj.image.get_height()))

    obstacles: list[ObstacleDef] = []
    spawn_points: list[Vector2] = []
    loot_points: list[Vector2] = []
    landmarks: list[tuple[str, Vector2]] = []
    cover_points: list[Vector2] = []
    triggers: list[TriggerZone] = []
    regions: list[MapRegion] = []
    light_zones: list[LightZone] = []
    collision_mask: pygame.Mask | None = None

    object_groups = [layer for layer in tmx.layers if isinstance(layer, TiledObjectGroup)]
    if object_groups:
        for group in object_groups:
            group_name = group.name.lower()
            for obj in group:
                position = Vector2(obj.x, obj.y)
                label = obj.name or group.name
                rect = _object_rect(obj, default_size=96)
                if group_name in {"obstacle", "collision", "building"}:
                    if hasattr(obj, "visible") and not obj.visible:
                        continue
                    obstacle = _obstacle_rect(obj, has_image_backdrop=has_image_backdrop)
                    obstacles.append(ObstacleDef(rect=obstacle, label=label))
                    cover_points.extend(_cover_points_from_rect(obstacle))
                    if group_name == "building":
                        regions.append(MapRegion(kind="building", label=label, rect=rect))
                elif group_name in {"spawn", "spawns", "player_spawn", "actor"}:
                    spawn_points.append(position)
                    landmarks.append((label, position))
                elif group_name in {"loot", "loot_points", "pickup"}:
                    loot_points.append(position)
                elif group_name in {"landmark", "poi", "elder", "child", "god"}:
                    landmarks.append((label, position))
                    loot_points.append(position)
                    triggers.append(TriggerZone(label=label, kind="landmark", rect=rect))
                elif group_name in {"cover"}:
                    cover_points.append(position)
                elif group_name == "trigger":
                    triggers.append(TriggerZone(label=label, kind="trigger", rect=rect))
                elif group_name.startswith("trigger_"):
                    trigger_kind = group_name.split("_", 1)[1]
                    one_shot = trigger_kind != "danger"
                    triggers.append(TriggerZone(label=label, kind=trigger_kind, rect=rect, one_shot=one_shot))
                elif group_name in {"road", "puddle", "neon", "platform", "billboard", "underpass"}:
                    regions.append(MapRegion(kind=group_name, label=label, rect=rect))
                elif group_name.startswith("light_"):
                    light_zones.append(LightZone(color=_parse_light_color(group_name), rect=rect))
                elif group_name in {"monster"}:
                    landmarks.append((label, position))
                    cover_points.append(position)
                    triggers.append(TriggerZone(label=label, kind="danger", rect=rect))
                else:
                    landmarks.append((label, position))
    else:
        layer_lookup = {getattr(layer, "name", "").lower(): layer for layer in tmx.layers if isinstance(layer, TiledTileLayer)}
        collision_layers = [layer_lookup[name] for name in ("house", "tree") if name in layer_lookup]
        collision_surface = pygame.Surface((pixel_width, pixel_height), pygame.SRCALPHA)
        for layer in collision_layers:
            for x, y, gid in layer.iter_data():
                if gid:
                    rect = pygame.Rect(x * tmx.tilewidth, y * tmx.tileheight, tmx.tilewidth, tmx.tileheight)
                    obstacles.append(ObstacleDef(rect=rect))
                    cover_points.append(Vector2(rect.center))
                    image = tmx.get_tile_image_by_gid(gid)
                    if image is not None:
                        collision_surface.blit(image, rect.topleft)
        walk_layer = layer_lookup.get("path") or layer_lookup.get("ground")
        if walk_layer is not None:
            for x, y, gid in walk_layer.iter_data():
                if gid:
                    point = Vector2(x * tmx.tilewidth + tmx.tilewidth / 2, y * tmx.tileheight + tmx.tileheight / 2)
                    if (x + y) % 7 == 0:
                        spawn_points.append(point)
                    if (x * 3 + y) % 11 == 0:
                        loot_points.append(point)
                    if (x * 5 + y) % 17 == 0:
                        cover_points.append(point)
        center = Vector2(pixel_width / 2, pixel_height / 2)
        landmarks.append(("庭院中心", center))
        triggers.append(TriggerZone(label="庭院中心", kind="landmark", rect=pygame.Rect(int(center.x - 96), int(center.y - 96), 192, 192)))

    if not spawn_points:
        spawn_points = [
            Vector2(pixel_width * 0.2, pixel_height * 0.2),
            Vector2(pixel_width * 0.8, pixel_height * 0.2),
            Vector2(pixel_width * 0.2, pixel_height * 0.8),
            Vector2(pixel_width * 0.8, pixel_height * 0.8),
            Vector2(pixel_width * 0.5, pixel_height * 0.5),
        ]
    if not loot_points:
        loot_points = [point.copy() for point in spawn_points]
    if not cover_points:
        cover_points = [point.copy() for point in spawn_points]

    if collision_mask is None and 'collision_surface' in locals():
        collision_mask = pygame.mask.from_surface(collision_surface)
    if collision_mask is not None:
        obstacles = []

    minimap_base = pygame.transform.smoothscale(surface, (220, 188)).convert()
    return TmxMapBundle(
        pixel_size=(pixel_width, pixel_height),
        surface=surface,
        obstacles=obstacles,
        spawn_points=spawn_points,
        loot_points=loot_points,
        landmarks=landmarks,
        cover_points=cover_points,
        triggers=triggers,
        regions=regions,
        light_zones=light_zones,
        minimap_base=minimap_base,
        collision_mask=collision_mask,
    )


def _cover_points_from_rect(rect: pygame.Rect) -> list[Vector2]:
    return [
        Vector2(rect.left - 18, rect.centery),
        Vector2(rect.right + 18, rect.centery),
        Vector2(rect.centerx, rect.top - 18),
        Vector2(rect.centerx, rect.bottom + 18),
    ]


def _obstacle_rect(obj, *, has_image_backdrop: bool) -> pygame.Rect:
    width = int(round(getattr(obj, "width", 0) or 0))
    height = int(round(getattr(obj, "height", 0) or 0))
    min_thickness = 12 if has_image_backdrop else 10
    collision_pad = 4 if has_image_backdrop else 2

    if width <= 0 and height <= 0:
        rect = pygame.Rect(int(round(obj.x - min_thickness / 2)), int(round(obj.y - min_thickness / 2)), min_thickness, min_thickness)
    else:
        if width <= 0:
            width = min_thickness
        if height <= 0:
            height = min_thickness
        rect = pygame.Rect(int(round(obj.x)), int(round(obj.y)), width, height)

    smallest_edge = min(rect.width, rect.height)
    if smallest_edge <= 14:
        collision_pad = min(collision_pad, 1)
    elif smallest_edge <= 28:
        collision_pad = min(collision_pad, 2)

    if collision_pad > 0:
        rect = rect.inflate(collision_pad * 2, collision_pad * 2)
    return rect


def _object_rect(obj, default_size: int) -> pygame.Rect:
    if obj.width and obj.height:
        return pygame.Rect(int(obj.x), int(obj.y), int(obj.width), int(obj.height))
    return pygame.Rect(int(obj.x - default_size / 2), int(obj.y - default_size / 2), default_size, default_size)


def _parse_light_color(group_name: str) -> tuple[int, int, int]:
    color_name = group_name.split("_", 1)[1] if "_" in group_name else "cyan"
    if color_name == "magenta":
        return (246, 110, 255)
    if color_name == "amber":
        return (255, 190, 88)
    if color_name == "lime":
        return (126, 255, 188)
    return (104, 214, 255)
