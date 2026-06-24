from __future__ import annotations

import pygame

from ..core.base_scene import BaseScene
from ..core.config import ARENA_THEMES, PLAYER_SKIN_BY_ID, SCREEN_HEIGHT, SCREEN_WIDTH, TEXT_LIGHT, TEXT_MUTED, UI_PANEL
from ..helpers import draw_outlined_text, draw_text_block, truncate_text


class MenuScene(BaseScene):
    def __init__(self, game) -> None:
        super().__init__(game)
        self.game.audio.play_music("menu")
        self.theme_index = next(
            (index for index, theme in enumerate(ARENA_THEMES) if theme.identifier == self.game.selected_theme_id),
            0,
        )
        self.start_rect = pygame.Rect(SCREEN_WIDTH // 2 - 180, SCREEN_HEIGHT - 176, 360, 64)
        self.profile_rect = pygame.Rect(SCREEN_WIDTH // 2 - 180, SCREEN_HEIGHT - 102, 360, 50)
        self.settings_rect = pygame.Rect(SCREEN_WIDTH // 2 - 180, SCREEN_HEIGHT - 44, 360, 40)
        self.left_rect = pygame.Rect(78, SCREEN_HEIGHT - 164, 56, 56)
        self.right_rect = pygame.Rect(SCREEN_WIDTH - 134, SCREEN_HEIGHT - 164, 56, 56)

        card_width = 270
        card_gap = 22
        cards_total_width = len(ARENA_THEMES) * card_width + (len(ARENA_THEMES) - 1) * card_gap
        cards_left = (SCREEN_WIDTH - cards_total_width) // 2
        self.card_rects = [
            pygame.Rect(cards_left + index * (card_width + card_gap), SCREEN_HEIGHT - 296, card_width, 96)
            for index in range(len(ARENA_THEMES))
        ]
        self.profile_card = pygame.Rect(46, 40, 278, 138)
        self.info_panel = pygame.Rect(SCREEN_WIDTH // 2 - 380, 212, 760, 296)
        self.preview_surface = pygame.Surface((SCREEN_WIDTH, SCREEN_HEIGHT)).convert()
        self._rebuild_preview()

    def _rebuild_preview(self) -> None:
        self.theme = ARENA_THEMES[self.theme_index]
        self.game.selected_theme_id = self.theme.identifier
        if self.theme.preview_image_path:
            preview = self.game.resources.load_image(self.theme.preview_image_path)
            self.preview_surface = pygame.transform.smoothscale(preview, (SCREEN_WIDTH, SCREEN_HEIGHT)).convert()

    def _change_theme(self, direction: int) -> None:
        self.theme_index = (self.theme_index + direction) % len(ARENA_THEMES)
        self._rebuild_preview()

    def handle_events(self, events: list[pygame.event.Event]) -> None:
        for event in events:
            if event.type == pygame.QUIT:
                self.game.running = False
            elif event.type == pygame.KEYDOWN:
                if event.key in (pygame.K_RETURN, pygame.K_KP_ENTER):
                    from .battle_scene import BattleScene

                    self.game.change_scene(BattleScene(self.game, self.theme.identifier))
                elif event.key in (pygame.K_LEFT, pygame.K_a):
                    self._change_theme(-1)
                elif event.key in (pygame.K_RIGHT, pygame.K_d):
                    self._change_theme(1)
                elif event.key == pygame.K_c:
                    from .profile_scene import ProfileScene

                    self.game.change_scene(ProfileScene(self.game))
                elif event.key == pygame.K_s:
                    from .settings_scene import SettingsScene

                    self.game.change_scene(SettingsScene(self.game))
                elif event.key == pygame.K_ESCAPE:
                    self.game.running = False
            elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                if self.start_rect.collidepoint(event.pos):
                    from .battle_scene import BattleScene

                    self.game.change_scene(BattleScene(self.game, self.theme.identifier))
                elif self.profile_rect.collidepoint(event.pos) or self.profile_card.collidepoint(event.pos):
                    from .profile_scene import ProfileScene

                    self.game.change_scene(ProfileScene(self.game))
                elif self.settings_rect.collidepoint(event.pos):
                    from .settings_scene import SettingsScene

                    self.game.change_scene(SettingsScene(self.game))
                elif self.left_rect.collidepoint(event.pos):
                    self._change_theme(-1)
                elif self.right_rect.collidepoint(event.pos):
                    self._change_theme(1)
                else:
                    for index, rect in enumerate(self.card_rects):
                        if rect.collidepoint(event.pos):
                            self.theme_index = index
                            self._rebuild_preview()
                            break

    def update(self, dt: float) -> None:
        return None

    def draw(self, screen: pygame.Surface) -> None:
        screen.blit(self.preview_surface, (0, 0))
        overlay = pygame.Surface((SCREEN_WIDTH, SCREEN_HEIGHT), pygame.SRCALPHA)
        overlay.fill((8, 12, 18, 158))
        screen.blit(overlay, (0, 0))

        self._draw_profile_card(screen)

        draw_outlined_text(screen, self.game.fonts["hero"], "圈地突围", (SCREEN_WIDTH // 2, 104), TEXT_LIGHT, center=True)
        draw_outlined_text(screen, self.game.fonts["title"], "单机版 2D 缩圈竞技原型", (SCREEN_WIDTH // 2, 166), TEXT_MUTED, center=True)

        pygame.draw.rect(screen, (*UI_PANEL, 242), self.info_panel, border_radius=20)
        pygame.draw.rect(screen, self.theme.accent, self.info_panel, width=2, border_radius=20)

        badge = pygame.Rect(self.info_panel.left + 30, self.info_panel.top + 24, 220, 40)
        pygame.draw.rect(screen, self.theme.accent, badge, border_radius=12)
        draw_outlined_text(screen, self.game.fonts["small"], self.theme.label, badge.center, (18, 24, 30), outline=(245, 235, 210), center=True)

        subtitle_rect = pygame.Rect(self.info_panel.left + 42, self.info_panel.top + 86, self.info_panel.width - 84, 42)
        draw_text_block(screen, self.game.fonts["hero_small"], self.theme.subtitle, subtitle_rect, TEXT_LIGHT, line_spacing=0, max_lines=1)

        desc_left = self.info_panel.left + 42
        desc_top = self.info_panel.top + 144
        desc_width = self.info_panel.width - 84
        cursor_y = desc_top
        for desc in self.theme.description:
            block_rect = pygame.Rect(desc_left, cursor_y, desc_width, 54)
            used_rect = draw_text_block(
                screen,
                self.game.fonts["small"],
                f"• {desc}",
                block_rect,
                TEXT_LIGHT,
                line_spacing=4,
                max_lines=2,
            )
            cursor_y = used_rect.bottom + 8

        hint_rect = pygame.Rect(self.info_panel.left + 42, self.info_panel.bottom - 40, self.info_panel.width - 84, 24)
        draw_text_block(screen, self.game.fonts["tiny"], "左右方向键切换地图，按 Enter 立即部署", hint_rect, TEXT_MUTED, max_lines=1)

        self._draw_nav_button(screen, self.left_rect, "←")
        self._draw_nav_button(screen, self.right_rect, "→")

        for index, rect in enumerate(self.card_rects):
            theme = ARENA_THEMES[index]
            selected = index == self.theme_index
            fill = (*UI_PANEL, 238) if selected else (20, 27, 34)
            border = theme.accent if selected else (100, 112, 120)
            pygame.draw.rect(screen, fill, rect, border_radius=16)
            pygame.draw.rect(screen, border, rect, width=2, border_radius=16)

            title_rect = pygame.Rect(rect.left + 14, rect.top + 10, rect.width - 28, 26)
            draw_text_block(screen, self.game.fonts["medium"], theme.label, title_rect, TEXT_LIGHT, max_lines=1)

            subtitle_rect = pygame.Rect(rect.left + 14, rect.top + 42, rect.width - 28, 38)
            draw_text_block(screen, self.game.fonts["tiny"], theme.subtitle, subtitle_rect, TEXT_MUTED, line_spacing=2, max_lines=2)

        pygame.draw.rect(screen, self.theme.accent, self.start_rect, border_radius=16)
        pygame.draw.rect(screen, (248, 236, 210), self.start_rect, width=2, border_radius=16)
        draw_outlined_text(screen, self.game.fonts["title"], "按 Enter 开始部署", self.start_rect.center, (20, 24, 28), outline=(245, 228, 198), center=True)

        pygame.draw.rect(screen, (27, 34, 40), self.profile_rect, border_radius=14)
        pygame.draw.rect(screen, (228, 232, 236), self.profile_rect, width=2, border_radius=14)
        draw_outlined_text(screen, self.game.fonts["medium"], "按 C 打开角色配置", self.profile_rect.center, TEXT_LIGHT, center=True)

        pygame.draw.rect(screen, (23, 29, 35), self.settings_rect, border_radius=12)
        pygame.draw.rect(screen, (180, 188, 195), self.settings_rect, width=2, border_radius=12)
        draw_outlined_text(screen, self.game.fonts["small"], "按 S 打开设置", self.settings_rect.center, TEXT_LIGHT, center=True)

    def _draw_nav_button(self, screen: pygame.Surface, rect: pygame.Rect, arrow: str) -> None:
        pygame.draw.rect(screen, (30, 37, 45), rect, border_radius=14)
        pygame.draw.rect(screen, (230, 234, 236), rect, width=2, border_radius=14)
        draw_outlined_text(screen, self.game.fonts["title"], arrow, rect.center, TEXT_LIGHT, center=True)

    def _draw_profile_card(self, screen: pygame.Surface) -> None:
        skin = PLAYER_SKIN_BY_ID[self.game.player_profile.skin_id]
        pygame.draw.rect(screen, (*UI_PANEL, 236), self.profile_card, border_radius=18)
        pygame.draw.rect(screen, skin.accent_color, self.profile_card, width=2, border_radius=18)

        preview_center = (self.profile_card.left + 54, self.profile_card.centery)
        pygame.draw.circle(screen, skin.primary_color, preview_center, 24)
        pygame.draw.circle(screen, skin.accent_color, preview_center, 30, width=3)
        pygame.draw.line(screen, skin.secondary_color, preview_center, (preview_center[0] + 28, preview_center[1] - 8), 6)
        arrow = [
            (preview_center[0], preview_center[1] - 38),
            (preview_center[0] - 7, preview_center[1] - 26),
            (preview_center[0] + 7, preview_center[1] - 26),
        ]
        pygame.draw.polygon(screen, skin.marker_color, arrow)

        screen.blit(self.game.fonts["small"].render("当前角色", True, TEXT_MUTED), (self.profile_card.left + 98, self.profile_card.top + 18))

        callsign = truncate_text(self.game.fonts["title"], self.game.player_profile.callsign, 156)
        name_render = self.game.fonts["title"].render(callsign, True, TEXT_LIGHT)
        screen.blit(name_render, (self.profile_card.left + 98, self.profile_card.top + 44))

        skin_label = truncate_text(self.game.fonts["small"], f"皮肤：{skin.label}", 160)
        skin_render = self.game.fonts["small"].render(skin_label, True, TEXT_LIGHT)
        screen.blit(skin_render, (self.profile_card.left + 98, self.profile_card.top + 88))
