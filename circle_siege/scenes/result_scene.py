from __future__ import annotations

import pygame

from ..core.base_scene import BaseScene
from ..core.config import DEFAULT_THEME_ID, SCREEN_WIDTH, TEXT_LIGHT, TEXT_MUTED, THEME_BY_ID, UI_PANEL
from ..helpers import draw_outlined_text, draw_text_block, format_time, truncate_text


class ResultScene(BaseScene):
    def __init__(self, game, summary: dict[str, object]) -> None:
        super().__init__(game)
        self.game.audio.stop_ambient()
        self.game.audio.play_music("menu")
        self.summary = summary
        self.theme_id = str(summary.get("theme_id", DEFAULT_THEME_ID))
        self.theme_label = str(summary.get("theme_label", THEME_BY_ID[self.theme_id].label))

    def handle_events(self, events: list[pygame.event.Event]) -> None:
        for event in events:
            if event.type == pygame.QUIT:
                self.game.running = False
            elif event.type == pygame.KEYDOWN:
                if event.key in (pygame.K_RETURN, pygame.K_KP_ENTER):
                    from .battle_scene import BattleScene

                    self.game.change_scene(BattleScene(self.game, self.theme_id))
                elif event.key == pygame.K_ESCAPE:
                    from .menu_scene import MenuScene

                    self.game.change_scene(MenuScene(self.game))

    def update(self, dt: float) -> None:
        return None

    def draw(self, screen: pygame.Surface) -> None:
        screen.fill((10, 16, 22))
        victory = bool(self.summary["victory"])
        if self.summary.get("mode") == "寻宝模式":
            headline = "寻宝成功" if victory else "任务失败"
        else:
            headline = "成功吃鸡" if victory else "作战失败"
        color = (247, 220, 123) if victory else (236, 118, 118)
        draw_outlined_text(screen, self.game.fonts["hero"], headline, (SCREEN_WIDTH // 2, 182), color, center=True)

        subtitle = f"战场：{self.theme_label}    呼号：{self.summary.get('callsign', self.game.player_profile.callsign)}"
        subtitle = truncate_text(self.game.fonts["medium"], subtitle, 820)
        draw_outlined_text(screen, self.game.fonts["medium"], subtitle, (SCREEN_WIDTH // 2, 244), TEXT_MUTED, center=True)

        panel = pygame.Rect(SCREEN_WIDTH // 2 - 340, 286, 680, 376)
        pygame.draw.rect(screen, UI_PANEL, panel, border_radius=18)
        pygame.draw.rect(screen, (231, 235, 238), panel, width=2, border_radius=18)

        mode_line = truncate_text(
            self.game.fonts["medium"],
            f"模式：{self.summary.get('mode', '')}    战场：{self.theme_label}",
            panel.width - 48,
        )
        mode_render = self.game.fonts["medium"].render(mode_line, True, TEXT_LIGHT)
        screen.blit(mode_render, mode_render.get_rect(center=(panel.centerx, panel.top + 32)))

        draw_text_block(
            screen,
            self.game.fonts["small"],
            str(self.summary.get("objective_text", "")),
            pygame.Rect(panel.left + 24, panel.top + 58, panel.width - 48, 20),
            TEXT_LIGHT,
            line_spacing=0,
            max_lines=1,
            center=True,
        )
        draw_text_block(
            screen,
            self.game.fonts["small"],
            str(self.summary.get("objective_progress_text", "")),
            pygame.Rect(panel.left + 24, panel.top + 84, panel.width - 48, 20),
            TEXT_MUTED,
            line_spacing=0,
            max_lines=1,
            center=True,
        )
        draw_text_block(
            screen,
            self.game.fonts["small"],
            f"结束判定：{self.summary.get('finish_reason', '')}",
            pygame.Rect(panel.left + 24, panel.top + 110, panel.width - 48, 36),
            color,
            line_spacing=2,
            max_lines=2,
            center=True,
        )
        pygame.draw.line(screen, (231, 235, 238), (panel.left + 24, panel.top + 156), (panel.right - 24, panel.top + 156), 1)

        rows = (
            f"淘汰数：{self.summary['kills']}",
            f"总伤害：{self.summary['damage']}",
            f"藏宝图：{self.summary.get('treasure_maps_found', 0)}/{self.summary.get('treasure_map_target', 0)}",
            f"生存时间：{format_time(float(self.summary['survival_time']))}",
            f"场上剩余：{self.summary['alive_count']}",
            f"剩余精英：{self.summary.get('elite_alive_count', 0)}",
            f"剩余手雷：{self.summary.get('grenades_left', 0)}",
            f"局部警戒峰值：{self.summary.get('peak_local_alert_bots', 0)}/{self.summary.get('bot_count', 0)}    同时追击峰值：{self.summary.get('peak_alerted_bots', 0)}",
        )
        y = panel.top + 180
        for row in rows:
            render = self.game.fonts["medium"].render(row, True, TEXT_LIGHT)
            screen.blit(render, render.get_rect(center=(panel.centerx, y)))
            y += 24

        hint = self.game.fonts["medium"].render("按 Enter 重新部署，按 Esc 返回主菜单", True, TEXT_MUTED)
        screen.blit(hint, hint.get_rect(center=(SCREEN_WIDTH // 2, 694)))
