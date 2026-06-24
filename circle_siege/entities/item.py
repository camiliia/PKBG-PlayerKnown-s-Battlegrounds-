from __future__ import annotations

import math
from dataclasses import dataclass

import pygame

from ..core.config import AMMO_LABELS, WeaponSpec
from ..helpers import Vector2
from .sprite_base import WorldSprite


class Pickup(WorldSprite):
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
        if self.kind == "weapon" and self.weapon_spec:
            return self.weapon_spec.label
        if self.kind == "ammo" and self.ammo_type:
            return f"{AMMO_LABELS.get(self.ammo_type, self.ammo_type)}弹药 +{self.amount}"
        return f"医疗包 +{self.amount}"

    def sync_visual(self, camera: Vector2) -> None:
        size = 44
        center = (size // 2, size // 2)
        image = pygame.Surface((size, size), pygame.SRCALPHA)
        pulse = 1.0 + 0.08 * math.sin(pygame.time.get_ticks() * 0.008)
        if self.is_supply:
            pygame.draw.circle(image, (239, 199, 88), center, int(18 * pulse), width=2)
        if self.kind == "weapon" and self.weapon_spec:
            points = [
                (center[0], center[1] - 16),
                (center[0] + 14, center[1]),
                (center[0], center[1] + 16),
                (center[0] - 14, center[1]),
            ]
            pygame.draw.polygon(image, (22, 28, 32), points)
            pygame.draw.polygon(image, self.weapon_spec.color, points, width=3)
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
        self.image = image
        self.rect = image.get_rect(center=(int(self.position.x - camera.x), int(self.position.y - camera.y)))
        self.mask = pygame.mask.from_surface(self.image)
