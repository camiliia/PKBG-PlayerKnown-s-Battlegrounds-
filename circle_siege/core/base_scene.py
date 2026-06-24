from __future__ import annotations

import pygame


class BaseScene:
    def __init__(self, game) -> None:
        self.game = game

    def handle_events(self, events: list[pygame.event.Event]) -> None:
        raise NotImplementedError

    def update(self, dt: float) -> None:
        raise NotImplementedError

    def draw(self, screen: pygame.Surface) -> None:
        raise NotImplementedError

