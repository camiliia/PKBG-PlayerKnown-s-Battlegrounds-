from __future__ import annotations

import pygame


class SceneManager:
    def __init__(self, initial_scene) -> None:
        self.current_scene = initial_scene

    def change_scene(self, scene) -> None:
        self.current_scene = scene

    def handle_events(self, events: list[pygame.event.Event]) -> None:
        self.current_scene.handle_events(events)

    def update(self, dt: float) -> None:
        self.current_scene.update(dt)

    def draw(self, screen: pygame.Surface) -> None:
        self.current_scene.draw(screen)

