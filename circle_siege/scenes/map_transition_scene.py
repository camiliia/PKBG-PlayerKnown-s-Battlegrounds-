from __future__ import annotations

import pygame

from ..core.base_scene import BaseScene
from ..core.config import DEFAULT_THEME_ID, THEME_BY_ID
from ..presentation.transition_effects import TeleportEffectRenderer


class MapTransitionScene(BaseScene):
    """区域清空后的地图传送过场。"""

    def __init__(self, game, summary: dict[str, object]) -> None:
        super().__init__(game)
        self.summary = summary
        self.timer = 0.0
        self.duration = 3.2
        self.finished = False
        self.current_theme_id = str(summary.get("theme_id", DEFAULT_THEME_ID))
        self.next_theme_id = str(summary.get("next_theme_id", DEFAULT_THEME_ID))
        self.next_theme = THEME_BY_ID.get(self.next_theme_id, THEME_BY_ID[DEFAULT_THEME_ID])
        self.effect = TeleportEffectRenderer(f"{self.current_theme_id}->{self.next_theme_id}")
        self.burst_played = False
        self.arrive_played = False
        self.game.audio.stop_ambient()
        self.game.audio.stop_music()
        self._play_audio_event("teleport_charge", "mechanism")

    def _play_audio_event(self, event_name: str, fallback: str) -> None:
        audio = self.game.audio
        if hasattr(audio, "play_event"):
            audio.play_event(event_name)
            return
        audio.play_sfx(fallback)

    def handle_events(self, events: list[pygame.event.Event]) -> None:
        for event in events:
            if event.type == pygame.QUIT:
                self.game.running = False
            elif event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
                self._finish()

    def update(self, dt: float) -> None:
        self.timer = min(self.duration, self.timer + dt)
        if not self.burst_played and self.timer >= 1.72:
            self.burst_played = True
            self._play_audio_event("teleport_burst", "killfeed")
        if not self.arrive_played and self.timer >= self.duration - 0.42:
            self.arrive_played = True
            self._play_audio_event("map_arrive", "mechanism")
        if self.timer >= self.duration:
            self._finish()

    def _finish(self) -> None:
        if self.finished:
            return
        self.finished = True
        if not self.arrive_played:
            self.arrive_played = True
            self._play_audio_event("map_arrive", "mechanism")
        from .battle_scene import BattleScene

        self.game.selected_theme_id = self.next_theme_id
        self.game.change_scene(BattleScene(self.game, self.next_theme_id))

    def draw(self, screen: pygame.Surface) -> None:
        progress = self.timer / self.duration if self.duration > 0 else 1.0
        reason = str(self.summary.get("finish_reason", "只剩玩家存活，正在进入下一张地图。"))
        self.effect.draw(
            screen,
            progress,
            self.next_theme,
            self.game.fonts,
            "区域清空",
            f"正在传送至：{self.next_theme.label}",
            reason,
            self.timer,
        )
