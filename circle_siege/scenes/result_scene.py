from __future__ import annotations

import pygame

from ..core.base_scene import BaseScene
from ..core.config import DEFAULT_THEME_ID, SCREEN_WIDTH, TEXT_LIGHT, TEXT_MUTED, THEME_BY_ID, UI_PANEL
from ..helpers import draw_outlined_text, format_time, truncate_text


class ResultScene(BaseScene):
    def __init__(self, game, summary: dict[str, object]) -> None:
        super().__init__(game)
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
        headline = "成功吃鸡" if victory else "作战失败"
        color = (247, 220, 123) if victory else (236, 118, 118)
        draw_outlined_text(screen, self.game.fonts["hero"], headline, (SCREEN_WIDTH // 2, 182), color, center=True)

        subtitle = f"战场：{self.theme_label}    呼号：{self.summary.get('callsign', self.game.player_profile.callsign)}"
        subtitle = truncate_text(self.game.fonts["medium"], subtitle, 820)
        draw_outlined_text(screen, self.game.fonts["medium"], subtitle, (SCREEN_WIDTH // 2, 244), TEXT_MUTED, center=True)

        panel = pygame.Rect(SCREEN_WIDTH // 2 - 300, 298, 600, 294)
        pygame.draw.rect(screen, UI_PANEL, panel, border_radius=18)
        pygame.draw.rect(screen, (231, 235, 238), panel, width=2, border_radius=18)

        rows = (
            f"淘汰数：{self.summary['kills']}",
            f"总伤害：{self.summary['damage']}",
            f"生存时间：{format_time(float(self.summary['survival_time']))}",
            f"场上剩余：{self.summary['alive_count']}",
            f"剩余精英：{self.summary.get('elite_alive_count', 0)}",
            f"剩余手雷：{self.summary.get('grenades_left', 0)}",
        )
        y = panel.top + 42
        for row in rows:
            render = self.game.fonts["title"].render(row, True, TEXT_LIGHT)
            screen.blit(render, render.get_rect(center=(panel.centerx, y)))
            y += 44

        hint = self.game.fonts["medium"].render("按 Enter 重新部署，按 Esc 返回主菜单", True, TEXT_MUTED)
        screen.blit(hint, hint.get_rect(center=(SCREEN_WIDTH // 2, 638)))
