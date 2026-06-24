from __future__ import annotations

from dataclasses import replace

import pygame

from ..systems.audio import AudioManager
from .config import DEFAULT_GAME_CONFIG, DEFAULT_PLAYER_PROFILE, DEFAULT_THEME_ID, PlayerProfile, TITLE
from .resource_manager import ResourceManager
from .scene_manager import SceneManager


class Game:
    def __init__(self) -> None:
        pygame.init()
        self.config = DEFAULT_GAME_CONFIG
        pygame.display.set_caption(TITLE)
        self.screen = pygame.display.set_mode((self.config.screen_width, self.config.screen_height))
        self.clock = pygame.time.Clock()
        self.running = True
        self.selected_theme_id = DEFAULT_THEME_ID
        self.player_profile = DEFAULT_PLAYER_PROFILE
        self.delta_time = 0.0
        self.current_fps = float(self.config.target_fps)
        self.resources = ResourceManager()
        self.fonts = self.resources.fonts
        self.audio = AudioManager()
        self.audio.set_master_volume(self.config.master_volume)
        self.audio.set_music_volume(self.config.music_volume)
        self.audio.set_effects_volume(self.config.effects_volume)

        from ..scenes.menu_scene import MenuScene

        self.scene_manager = SceneManager(MenuScene(self))

    def change_scene(self, scene) -> None:
        self.scene_manager.change_scene(scene)

    def apply_config(self, **changes) -> None:
        self.config = replace(self.config, **changes)
        self.audio.set_master_volume(self.config.master_volume)
        self.audio.set_music_volume(self.config.music_volume)
        self.audio.set_effects_volume(self.config.effects_volume)

    def update_player_profile(self, **changes) -> None:
        self.player_profile = replace(self.player_profile, **changes)

    @property
    def scene(self):
        return self.scene_manager.current_scene

    def run(self) -> None:
        while self.running:
            dt = min(0.05, self.clock.tick(self.config.target_fps) / 1000.0)
            self.delta_time = dt
            self.current_fps = self.clock.get_fps() or float(self.config.target_fps)
            self.audio.update(dt)
            events = pygame.event.get()
            self.scene_manager.handle_events(events)
            self.scene_manager.update(dt)
            self.scene_manager.draw(self.screen)
            pygame.display.flip()
        pygame.quit()
