from __future__ import annotations

from pathlib import Path

import pygame


def load_font_from_candidates(candidates: tuple[str, ...], size: int) -> pygame.font.Font:
    for candidate in candidates:
        path = Path(candidate)
        if path.exists():
            return pygame.font.Font(str(path), size)
    return pygame.font.Font(None, size)


class ResourceManager:
    def __init__(self) -> None:
        body_candidates = (
            "C:/Windows/Fonts/simsun.ttc",
            "C:/Windows/Fonts/nsimsun.ttc",
            "C:/Windows/Fonts/msyh.ttc",
            "C:/Windows/Fonts/simhei.ttf",
        )
        title_candidates = (
            "C:/Windows/Fonts/simhei.ttf",
            "C:/Windows/Fonts/msyhbd.ttc",
            "C:/Windows/Fonts/msyh.ttc",
            "C:/Windows/Fonts/simsun.ttc",
        )
        self.fonts = {
            "tiny": load_font_from_candidates(body_candidates, 18),
            "debug": load_font_from_candidates(body_candidates, 18),
            "small": load_font_from_candidates(body_candidates, 20),
            "medium": load_font_from_candidates(body_candidates, 24),
            "title": load_font_from_candidates(title_candidates, 32),
            "hero": load_font_from_candidates(title_candidates, 68),
            "hero_small": load_font_from_candidates(title_candidates, 44),
        }
        self.images: dict[str, pygame.Surface] = {}
        self.alpha_images: dict[str, pygame.Surface] = {}

    def load_image(self, path: str) -> pygame.Surface:
        if path not in self.images:
            self.images[path] = pygame.image.load(path).convert()
        return self.images[path]

    def load_alpha_image(self, path: str) -> pygame.Surface:
        if path not in self.alpha_images:
            self.alpha_images[path] = pygame.image.load(path).convert_alpha()
        return self.alpha_images[path]
