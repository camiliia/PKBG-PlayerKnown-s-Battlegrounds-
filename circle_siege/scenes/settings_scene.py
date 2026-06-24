from __future__ import annotations

import pygame

from ..core.base_scene import BaseScene
from ..core.config import SCREEN_WIDTH, TEXT_LIGHT, TEXT_MUTED, UI_ACCENT, UI_PANEL
from ..helpers import draw_outlined_text, draw_text_block


class SettingsScene(BaseScene):
    def __init__(self, game) -> None:
        super().__init__(game)
        self.game.audio.play_music("menu")
        self.index = 0
        self.entries = ["帧率上限", "主音量", "音乐音量", "音效音量", "鼠标灵敏度"]
        self.fps_options = (60, 90, 120, 144)

    def handle_events(self, events: list[pygame.event.Event]) -> None:
        for event in events:
            if event.type == pygame.QUIT:
                self.game.running = False
            elif event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    self._go_back()
                elif event.key in (pygame.K_RETURN, pygame.K_KP_ENTER):
                    self._go_back()
                elif event.key in (pygame.K_UP, pygame.K_w):
                    self.index = (self.index - 1) % len(self.entries)
                elif event.key in (pygame.K_DOWN, pygame.K_s):
                    self.index = (self.index + 1) % len(self.entries)
                elif event.key in (pygame.K_LEFT, pygame.K_a):
                    self._adjust(-1)
                elif event.key in (pygame.K_RIGHT, pygame.K_d):
                    self._adjust(1)

    def _go_back(self) -> None:
        from .menu_scene import MenuScene

        self.game.change_scene(MenuScene(self.game))

    def _adjust(self, direction: int) -> None:
        config = self.game.config
        if self.index == 0:
            current = self.fps_options.index(config.target_fps) if config.target_fps in self.fps_options else 0
            self.game.apply_config(target_fps=self.fps_options[(current + direction) % len(self.fps_options)])
        elif self.index == 1:
            self.game.apply_config(master_volume=max(0.0, min(1.0, config.master_volume + direction * 0.1)))
        elif self.index == 2:
            self.game.apply_config(music_volume=max(0.0, min(1.0, config.music_volume + direction * 0.1)))
        elif self.index == 3:
            self.game.apply_config(effects_volume=max(0.0, min(1.0, config.effects_volume + direction * 0.1)))
        elif self.index == 4:
            self.game.apply_config(mouse_sensitivity=max(0.5, min(1.5, config.mouse_sensitivity + direction * 0.1)))

    def update(self, dt: float) -> None:
        return None

    def draw(self, screen: pygame.Surface) -> None:
        screen.fill((11, 16, 22))
        draw_outlined_text(screen, self.game.fonts["hero"], "设置", (SCREEN_WIDTH // 2, 120), TEXT_LIGHT, center=True)
        draw_outlined_text(screen, self.game.fonts["medium"], "左右调整参数，回车或 Esc 返回菜单", (SCREEN_WIDTH // 2, 174), TEXT_MUTED, center=True)

        panel = pygame.Rect(SCREEN_WIDTH // 2 - 360, 236, 720, 366)
        pygame.draw.rect(screen, UI_PANEL, panel, border_radius=20)
        pygame.draw.rect(screen, UI_ACCENT, panel, width=2, border_radius=20)

        values = [
            f"{self.game.config.target_fps} FPS",
            f"{int(self.game.config.master_volume * 100)}%",
            f"{int(self.game.config.music_volume * 100)}%",
            f"{int(self.game.config.effects_volume * 100)}%",
            f"{int(self.game.config.mouse_sensitivity * 100)}%",
        ]

        y = panel.top + 48
        for idx, (label, value) in enumerate(zip(self.entries, values, strict=True)):
            selected = idx == self.index
            row = pygame.Rect(panel.left + 28, y - 8, panel.width - 56, 48)
            if selected:
                pygame.draw.rect(screen, (31, 42, 52), row, border_radius=12)
                pygame.draw.rect(screen, UI_ACCENT, row, width=2, border_radius=12)
            label_render = self.game.fonts["medium"].render(label, True, TEXT_LIGHT)
            value_render = self.game.fonts["medium"].render(value, True, UI_ACCENT if selected else TEXT_MUTED)
            screen.blit(label_render, (row.left + 16, row.top + 10))
            screen.blit(value_render, value_render.get_rect(midright=(row.right - 16, row.centery)))
            y += 58

        note_rect = pygame.Rect(panel.left + 36, panel.bottom - 52, panel.width - 72, 34)
        draw_text_block(
            screen,
            self.game.fonts["tiny"],
            "分辨率配置仍保留在 GameConfig 中，这一版先开放帧率、音量和灵敏度调节。",
            note_rect,
            TEXT_MUTED,
            line_spacing=2,
            max_lines=2,
            center=True,
        )
