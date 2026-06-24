from __future__ import annotations

import pygame

from ..core.base_scene import BaseScene
from ..core.config import (
    DEFAULT_CALLSIGN_OPTIONS,
    DEFAULT_PLAYER_PROFILE,
    PLAYER_SKINS,
    SCREEN_HEIGHT,
    SCREEN_WIDTH,
    TEXT_LIGHT,
    TEXT_MUTED,
    UI_ACCENT,
    UI_PANEL,
)
from ..helpers import draw_outlined_text, truncate_text


class ProfileScene(BaseScene):
    def __init__(self, game) -> None:
        super().__init__(game)
        self.game.audio.play_music("menu")
        self.callsign = game.player_profile.callsign
        self.skin_index = next(
            (index for index, skin in enumerate(PLAYER_SKINS) if skin.identifier == game.player_profile.skin_id),
            0,
        )
        self.input_active = False
        self.input_rect = pygame.Rect(SCREEN_WIDTH // 2 - 220, 228, 440, 56)
        self.confirm_rect = pygame.Rect(SCREEN_WIDTH // 2 - 180, SCREEN_HEIGHT - 112, 360, 56)
        self.cancel_rect = pygame.Rect(SCREEN_WIDTH // 2 - 180, SCREEN_HEIGHT - 48, 360, 42)
        self.skin_rects = [pygame.Rect(190 + idx * 214, 352, 186, 184) for idx in range(len(PLAYER_SKINS))]
        self.preset_rects = [pygame.Rect(210 + idx * 154, 572, 132, 42) for idx in range(min(5, len(DEFAULT_CALLSIGN_OPTIONS)))]

    @property
    def selected_skin(self):
        return PLAYER_SKINS[self.skin_index]

    def handle_events(self, events: list[pygame.event.Event]) -> None:
        for event in events:
            if event.type == pygame.QUIT:
                self.game.running = False
            elif event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    self._go_back()
                elif event.key in (pygame.K_RETURN, pygame.K_KP_ENTER):
                    self._confirm()
                elif event.key == pygame.K_BACKSPACE and self.input_active:
                    self.callsign = self.callsign[:-1]
                elif event.key in (pygame.K_LEFT, pygame.K_a):
                    self.skin_index = (self.skin_index - 1) % len(PLAYER_SKINS)
                elif event.key in (pygame.K_RIGHT, pygame.K_d):
                    self.skin_index = (self.skin_index + 1) % len(PLAYER_SKINS)
                elif event.key == pygame.K_TAB:
                    self.input_active = not self.input_active
            elif event.type == pygame.TEXTINPUT and self.input_active:
                if len(self.callsign) < 10:
                    self.callsign += event.text
            elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                if self.input_rect.collidepoint(event.pos):
                    self.input_active = True
                elif self.confirm_rect.collidepoint(event.pos):
                    self._confirm()
                elif self.cancel_rect.collidepoint(event.pos):
                    self._go_back()
                else:
                    self.input_active = False
                    for idx, rect in enumerate(self.skin_rects):
                        if rect.collidepoint(event.pos):
                            self.skin_index = idx
                            break
                    for idx, rect in enumerate(self.preset_rects):
                        if rect.collidepoint(event.pos):
                            self.callsign = DEFAULT_CALLSIGN_OPTIONS[idx]
                            break

    def _confirm(self) -> None:
        callsign = self.callsign.strip() or DEFAULT_PLAYER_PROFILE.callsign
        self.game.update_player_profile(callsign=callsign[:10], skin_id=self.selected_skin.identifier)
        self._go_back()

    def _go_back(self) -> None:
        from .menu_scene import MenuScene

        self.game.change_scene(MenuScene(self.game))

    def update(self, dt: float) -> None:
        return None

    def draw(self, screen: pygame.Surface) -> None:
        screen.fill((10, 16, 22))
        draw_outlined_text(screen, self.game.fonts["hero"], "角色配置", (SCREEN_WIDTH // 2, 92), TEXT_LIGHT, center=True)
        draw_outlined_text(screen, self.game.fonts["medium"], "先确定你的呼号和皮肤，再进入战场。", (SCREEN_WIDTH // 2, 148), TEXT_MUTED, center=True)

        panel = pygame.Rect(110, 180, SCREEN_WIDTH - 220, 476)
        pygame.draw.rect(screen, UI_PANEL, panel, border_radius=20)
        pygame.draw.rect(screen, self.selected_skin.accent_color, panel, width=2, border_radius=20)

        title = self.game.fonts["medium"].render("呼号", True, TEXT_LIGHT)
        screen.blit(title, (self.input_rect.left, self.input_rect.top - 34))
        pygame.draw.rect(screen, (22, 30, 38), self.input_rect, border_radius=12)
        border = self.selected_skin.accent_color if self.input_active else (180, 188, 195)
        pygame.draw.rect(screen, border, self.input_rect, width=2, border_radius=12)
        callsign_text = self.callsign or "输入呼号"
        callsign_color = TEXT_LIGHT if self.callsign else TEXT_MUTED
        fitted_callsign = truncate_text(self.game.fonts["title"], callsign_text, self.input_rect.width - 36)
        call_render = self.game.fonts["title"].render(fitted_callsign, True, callsign_color)
        screen.blit(call_render, (self.input_rect.left + 18, self.input_rect.centery - call_render.get_height() // 2))

        subtitle = self.game.fonts["medium"].render("皮肤选择", True, TEXT_LIGHT)
        screen.blit(subtitle, (self.skin_rects[0].left, self.skin_rects[0].top - 34))

        for idx, (skin, rect) in enumerate(zip(PLAYER_SKINS, self.skin_rects, strict=True)):
            selected = idx == self.skin_index
            pygame.draw.rect(screen, (20, 27, 34), rect, border_radius=18)
            pygame.draw.rect(screen, skin.accent_color if selected else (95, 108, 118), rect, width=2, border_radius=18)
            self._draw_skin_preview(screen, rect, skin, selected)
            label = self.game.fonts["medium"].render(skin.label, True, TEXT_LIGHT)
            tip = self.game.fonts["tiny"].render(skin.identifier.upper(), True, TEXT_MUTED)
            screen.blit(label, label.get_rect(center=(rect.centerx, rect.bottom - 44)))
            screen.blit(tip, tip.get_rect(center=(rect.centerx, rect.bottom - 20)))

        preset_title = self.game.fonts["small"].render("快速呼号", True, TEXT_MUTED)
        screen.blit(preset_title, (self.preset_rects[0].left, self.preset_rects[0].top - 26))
        for idx, rect in enumerate(self.preset_rects):
            selected = self.callsign == DEFAULT_CALLSIGN_OPTIONS[idx]
            pygame.draw.rect(screen, (25, 33, 40), rect, border_radius=12)
            pygame.draw.rect(screen, UI_ACCENT if selected else (120, 128, 136), rect, width=2, border_radius=12)
            text = self.game.fonts["small"].render(DEFAULT_CALLSIGN_OPTIONS[idx], True, TEXT_LIGHT)
            screen.blit(text, text.get_rect(center=rect.center))

        pygame.draw.rect(screen, self.selected_skin.accent_color, self.confirm_rect, border_radius=16)
        pygame.draw.rect(screen, (248, 239, 214), self.confirm_rect, width=2, border_radius=16)
        draw_outlined_text(screen, self.game.fonts["title"], "确认角色并返回菜单", self.confirm_rect.center, (18, 24, 28), center=True)

        pygame.draw.rect(screen, (26, 34, 40), self.cancel_rect, border_radius=12)
        pygame.draw.rect(screen, (180, 188, 195), self.cancel_rect, width=2, border_radius=12)
        draw_outlined_text(screen, self.game.fonts["medium"], "Esc 返回", self.cancel_rect.center, TEXT_LIGHT, center=True)

    def _draw_skin_preview(self, screen: pygame.Surface, rect: pygame.Rect, skin, selected: bool) -> None:
        center = pygame.Vector2(rect.centerx, rect.top + 74)
        accent = skin.accent_color if selected else skin.marker_color
        pygame.draw.circle(screen, (*accent, 60), center, 4)
        pygame.draw.circle(screen, accent, center, 34, width=1)

        torso = [
            (center.x - 12, center.y + 2),
            (center.x - 14, center.y + 18),
            (center.x, center.y + 28),
            (center.x + 14, center.y + 18),
            (center.x + 12, center.y + 2),
            (center.x, center.y - 12),
        ]
        pygame.draw.polygon(screen, skin.secondary_color, torso)
        chest = [
            (center.x - 8, center.y + 4),
            (center.x - 8, center.y + 16),
            (center.x, center.y + 22),
            (center.x + 8, center.y + 16),
            (center.x + 8, center.y + 4),
            (center.x, center.y),
        ]
        pygame.draw.polygon(screen, skin.primary_color, chest)
        pygame.draw.circle(screen, skin.accent_color, (center.x, center.y - 15), 9)
        pygame.draw.line(screen, skin.marker_color, (center.x - 5, center.y - 14), (center.x + 5, center.y - 14), 2)
        pygame.draw.line(screen, skin.primary_color, (center.x - 16, center.y + 4), (center.x - 8, center.y + 12), 4)
        pygame.draw.line(screen, skin.primary_color, (center.x + 16, center.y + 4), (center.x + 8, center.y + 12), 4)
        pygame.draw.line(screen, skin.secondary_color, (center.x - 3, center.y + 28), (center.x - 6, center.y + 42), 4)
        pygame.draw.line(screen, skin.secondary_color, (center.x + 3, center.y + 28), (center.x + 6, center.y + 42), 4)
        pygame.draw.line(screen, skin.secondary_color, (center.x + 6, center.y + 4), (center.x + 26, center.y - 6), 5)
        pygame.draw.line(screen, skin.accent_color, (center.x + 8, center.y + 4), (center.x + 30, center.y - 8), 3)
