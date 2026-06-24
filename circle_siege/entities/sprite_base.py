from __future__ import annotations

import pygame

from ..helpers import Vector2


class WorldSprite(pygame.sprite.Sprite):
    def __init__(self, layer: int) -> None:
        super().__init__()
        self._layer = layer
        self.image = pygame.Surface((4, 4), pygame.SRCALPHA)
        self.rect = self.image.get_rect()
        self.mask = pygame.mask.from_surface(self.image)

    def sync_visual(self, camera: Vector2) -> None:
        raise NotImplementedError

    def world_rect(self) -> pygame.Rect:
        if hasattr(self, "position"):
            return self.image.get_rect(center=(int(self.position.x), int(self.position.y)))
        return self.rect.copy()
