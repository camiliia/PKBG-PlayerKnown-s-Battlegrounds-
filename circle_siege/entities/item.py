from __future__ import annotations

import math
from pathlib import Path

import pygame

from ..core.config import AMMO_LABELS, RESOURCE_ROOT, WeaponSpec
from ..helpers import Vector2
from .sprite_base import WorldSprite


class Pickup(WorldSprite):
    PICKUP_ASSET_ROOT = RESOURCE_ROOT / "img" / "pickups"
    TREASURE_BOX = (72, 72)
    WEAPON_BOXES: dict[str, tuple[int, int]] = {
        "smg": (68, 68),
        "carbine": (76, 76),
        "shotgun": (84, 68),
        "dmr": (96, 64),
    }
    WEAPON_IMAGE_PATHS: dict[str, Path] = {
        "smg": PICKUP_ASSET_ROOT / "pickup_weapon_smg.png",
        "carbine": PICKUP_ASSET_ROOT / "pickup_weapon_carbine.png",
        "shotgun": PICKUP_ASSET_ROOT / "pickup_weapon_shotgun.png",
        "dmr": PICKUP_ASSET_ROOT / "pickup_weapon_dmr.png",
    }
    TREASURE_IMAGE_PATH = PICKUP_ASSET_ROOT / "pickup_treasure_map.png"
    _asset_cache: dict[tuple[str, tuple[int, int]], pygame.Surface] = {}

    def __init__(
        self,
        kind: str,
        position: Vector2,
        amount: int = 0,
        ammo_type: str | None = None,
        weapon_spec: WeaponSpec | None = None,
        is_supply: bool = False,
    ) -> None:
        super().__init__(layer=1)
        self.kind = kind
        self.position = Vector2(position)
        self.amount = amount
        self.ammo_type = ammo_type
        self.weapon_spec = weapon_spec
        self.is_supply = is_supply

    @property
    def label(self) -> str:
        if self.kind == "gear":
            return "武装模块"
        if self.kind == "treasure_map":
            return "藏宝图"
        if self.kind == "weapon" and self.weapon_spec:
            return self.weapon_spec.label
        if self.kind == "ammo" and self.ammo_type:
            return f"{AMMO_LABELS.get(self.ammo_type, self.ammo_type)}弹药 +{self.amount}"
        return f"医疗包 +{self.amount}"

    def sync_visual(self, camera) -> None:
        image = self._build_asset_visual()
        if image is None:
            image = self._build_fallback_visual()
        self.image = image
        screen_pos = camera.world_to_screen(self.position)
        self.rect = image.get_rect(midbottom=(screen_pos[0], screen_pos[1] + 10))
        self.mask = pygame.mask.from_surface(self.image)

    def _build_asset_visual(self) -> pygame.Surface | None:
        sprite = self._asset_surface_for_pickup()
        if sprite is None:
            return None

        canvas_w = sprite.get_width() + 20
        canvas_h = sprite.get_height() + 20
        image = pygame.Surface((canvas_w, canvas_h), pygame.SRCALPHA)

        shadow_width = max(18, int(sprite.get_width() * 0.66))
        shadow_height = max(8, int(sprite.get_height() * 0.16))
        shadow_rect = pygame.Rect(0, 0, shadow_width, shadow_height)
        shadow_rect.center = (canvas_w // 2, canvas_h - shadow_height)
        pygame.draw.ellipse(image, (0, 0, 0, 68), shadow_rect)

        if self.kind == "treasure_map":
            glow_rect = pygame.Rect(0, 0, int(sprite.get_width() * 0.9), int(sprite.get_height() * 0.6))
            glow_rect.center = (canvas_w // 2, canvas_h // 2 - 2)
            pygame.draw.ellipse(image, (247, 233, 188, 30), glow_rect)
            glow_rect.inflate_ip(10, 6)
            pygame.draw.ellipse(image, (255, 243, 214, 18), glow_rect)

        sprite_rect = sprite.get_rect(center=(canvas_w // 2, canvas_h // 2 - 3))
        image.blit(sprite, sprite_rect)
        return image

    def _asset_surface_for_pickup(self) -> pygame.Surface | None:
        if self.kind == "treasure_map":
            return self._load_asset_surface(self.TREASURE_IMAGE_PATH, self.TREASURE_BOX)
        if self.kind == "weapon" and self.weapon_spec:
            image_path = self.WEAPON_IMAGE_PATHS.get(self.weapon_spec.identifier)
            box = self.WEAPON_BOXES.get(self.weapon_spec.identifier, (66, 66))
            if image_path is None:
                return None
            return self._load_asset_surface(image_path, box)
        return None

    @classmethod
    def _load_asset_surface(cls, path: Path, box: tuple[int, int]) -> pygame.Surface | None:
        cache_key = (str(path), box)
        cached = cls._asset_cache.get(cache_key)
        if cached is not None:
            return cached
        if not path.exists():
            return None
        original = pygame.image.load(str(path)).convert_alpha()
        scaled = cls._fit_surface_to_box(original, box)
        cls._asset_cache[cache_key] = scaled
        return scaled

    @staticmethod
    def _fit_surface_to_box(surface: pygame.Surface, box: tuple[int, int]) -> pygame.Surface:
        scale = min(box[0] / surface.get_width(), box[1] / surface.get_height())
        width = max(1, int(round(surface.get_width() * scale)))
        height = max(1, int(round(surface.get_height() * scale)))
        return pygame.transform.smoothscale(surface, (width, height))

    def _build_fallback_visual(self) -> pygame.Surface:
        size = 44
        center = (size // 2, size // 2)
        image = pygame.Surface((size, size), pygame.SRCALPHA)
        pulse = 1.0 + 0.08 * math.sin(pygame.time.get_ticks() * 0.008)
        if self.is_supply:
            pygame.draw.circle(image, (239, 199, 88), center, int(18 * pulse), width=2)
        if self.kind == "gear":
            outer = [
                (center[0], center[1] - 16),
                (center[0] + 16, center[1]),
                (center[0], center[1] + 16),
                (center[0] - 16, center[1]),
            ]
            inner = [
                (center[0], center[1] - 8),
                (center[0] + 8, center[1]),
                (center[0], center[1] + 8),
                (center[0] - 8, center[1]),
            ]
            pygame.draw.polygon(image, (18, 28, 38), outer)
            pygame.draw.polygon(image, (118, 220, 255), outer, width=3)
            pygame.draw.polygon(image, (84, 182, 226), inner)
            pygame.draw.circle(image, (230, 246, 255), center, 3)
        elif self.kind == "weapon" and self.weapon_spec:
            self._draw_weapon_pickup(image, center)
        elif self.kind == "treasure_map":
            paper = pygame.Rect(center[0] - 13, center[1] - 10, 26, 20)
            pygame.draw.rect(image, (224, 211, 168), paper, border_radius=4)
            pygame.draw.rect(image, (156, 126, 78), paper, width=2, border_radius=4)
            fold = [(paper.right - 8, paper.top), (paper.right, paper.top), (paper.right, paper.top + 8)]
            pygame.draw.polygon(image, (242, 228, 188), fold)
            pygame.draw.line(image, (146, 98, 66), (paper.left + 6, paper.top + 6), (paper.right - 8, paper.top + 6), 2)
            pygame.draw.line(
                image,
                (146, 98, 66),
                (paper.left + 6, paper.top + 11),
                (paper.right - 10, paper.top + 11),
                2,
            )
            pygame.draw.circle(image, (214, 92, 92), (paper.centerx + 5, paper.centery + 2), 3)
        elif self.kind == "ammo":
            pygame.draw.circle(image, (27, 31, 35), center, 14)
            pygame.draw.circle(image, (219, 208, 170), center, 14, width=3)
            pygame.draw.rect(image, (219, 208, 170), (center[0] - 6, center[1] - 10, 12, 20), border_radius=3)
        else:
            rect = pygame.Rect(center[0] - 14, center[1] - 14, 28, 28)
            pygame.draw.rect(image, (37, 46, 51), rect, border_radius=5)
            pygame.draw.rect(image, (212, 88, 88), rect, width=3, border_radius=5)
            pygame.draw.rect(image, (212, 88, 88), (center[0] - 4, center[1] - 10, 8, 20), border_radius=3)
            pygame.draw.rect(image, (212, 88, 88), (center[0] - 10, center[1] - 4, 20, 8), border_radius=3)
        return image

    def _draw_weapon_pickup(self, image: pygame.Surface, center: tuple[int, int]) -> None:
        if self.weapon_spec is None:
            return
        profile = {
            "smg": ((-10, 2), (10, 2), 4),
            "carbine": ((-12, 0), (12, 0), 4),
            "shotgun": ((-13, -1), (13, -1), 5),
            "dmr": ((-14, -2), (14, -2), 3),
        }.get(self.weapon_spec.identifier, ((-11, 1), (11, 1), 4))
        start, end, width = profile
        muzzle = (center[0] + end[0], center[1] + end[1])
        stock = (center[0] + start[0], center[1] + start[1])
        pygame.draw.line(image, (22, 28, 32), stock, muzzle, width + 4)
        pygame.draw.line(image, self.weapon_spec.color, stock, muzzle, width)
        pygame.draw.rect(image, (46, 54, 62), (center[0] - 3, center[1] - 5, 8, 10), border_radius=2)
        pygame.draw.rect(image, self.weapon_spec.color, (center[0] - 1, center[1] + 1, 4, 10), border_radius=2)
        if self.weapon_spec.identifier in {"carbine", "dmr"}:
            pygame.draw.rect(image, (176, 206, 238), (center[0] - 1, center[1] - 8, 6, 3), border_radius=1)
