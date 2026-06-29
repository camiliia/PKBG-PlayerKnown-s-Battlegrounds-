from __future__ import annotations

import math
import random
from dataclasses import dataclass
from typing import Mapping

import pygame

from ..core.config import SCREEN_HEIGHT, SCREEN_WIDTH, TEXT_LIGHT, TEXT_MUTED, UI_PANEL
from ..helpers import Vector2, clamp, draw_outlined_text, lerp


@dataclass(frozen=True)
class TeleportParticle:
    angle: float
    radius: float
    speed: float
    alpha: int
    size: float
    drift: float


class TeleportEffectRenderer:
    def __init__(self, seed: str | int, width: int = SCREEN_WIDTH, height: int = SCREEN_HEIGHT) -> None:
        self.width = width
        self.height = height
        self.center = Vector2(width / 2, height / 2)
        self.rng = random.Random(seed)
        self.particles = self._build_particles()

    def draw(
        self,
        screen: pygame.Surface,
        progress: float,
        theme,
        fonts: Mapping[str, pygame.font.Font],
        title: str,
        subtitle: str,
        reason: str,
        elapsed: float,
    ) -> None:
        progress = clamp(progress, 0.0, 1.0)
        accent = tuple(theme.accent)
        screen.fill((3, 6, 12))
        self._draw_background(screen, accent, progress, elapsed)
        self._draw_spiral_particles(screen, accent, progress)
        self._draw_energy_gate(screen, accent, progress, elapsed)
        self._draw_portal_core(screen, accent, progress, elapsed)
        self._draw_title_panel(screen, fonts, accent, title, subtitle, reason, progress)
        self._draw_flash(screen, progress)

    def _build_particles(self) -> list[TeleportParticle]:
        return [
            TeleportParticle(
                angle=self.rng.uniform(0.0, math.tau),
                radius=self.rng.uniform(120.0, 660.0),
                speed=self.rng.uniform(0.72, 1.75),
                alpha=self.rng.randint(90, 235),
                size=self.rng.uniform(1.4, 5.2),
                drift=self.rng.uniform(-28.0, 28.0),
            )
            for _ in range(190)
        ]

    def _draw_background(self, screen: pygame.Surface, accent: tuple[int, int, int], progress: float, elapsed: float) -> None:
        layer = pygame.Surface((self.width, self.height), pygame.SRCALPHA)
        glow_radius = int(260 + 60 * math.sin(elapsed * 2.2))
        for index in range(7):
            radius = glow_radius + index * 96
            alpha = max(8, 56 - index * 7)
            rect = pygame.Rect(0, 0, radius * 2, int(radius * 1.15))
            rect.center = self._point(self.center)
            pygame.draw.ellipse(layer, (*accent, alpha), rect, width=2)

        for y in range(-18, self.height, 18):
            wave = int(12 * math.sin(elapsed * 3.0 + y * 0.025))
            alpha = int(8 + 22 * progress)
            pygame.draw.line(layer, (*accent, alpha), (0, y + wave), (self.width, y - wave), 1)

        horizon = int(self.height * 0.58)
        for index in range(11):
            offset = int(index * index * 3.2 + progress * 32) % max(1, self.height)
            y = horizon + offset
            if y < self.height:
                pygame.draw.line(layer, (*accent, 18), (0, y), (self.width, y), 1)

        for index in range(-9, 10):
            x = int(self.center.x + index * 74)
            end_x = int(self.center.x + index * 22)
            pygame.draw.line(layer, (*accent, 14), (x, horizon), (end_x, self.height), 1)

        pulse = int(42 + 36 * (math.sin(elapsed * 4.0) ** 2))
        pygame.draw.circle(layer, (*accent, pulse), self._point(self.center), 260)
        screen.blit(layer, (0, 0), special_flags=pygame.BLEND_ADD)

    def _draw_spiral_particles(self, screen: pygame.Surface, accent: tuple[int, int, int], progress: float) -> None:
        layer = pygame.Surface((self.width, self.height), pygame.SRCALPHA)
        collapse = clamp((progress - 0.08) / 0.58, 0.0, 1.0)
        burst = clamp((progress - 0.58) / 0.30, 0.0, 1.0)
        fade = 1.0 - clamp((progress - 0.86) / 0.14, 0.0, 1.0)

        for particle in self.particles:
            spin = particle.angle + progress * math.tau * particle.speed * 1.45
            direction = Vector2(math.cos(spin), math.sin(spin))
            distance = particle.radius * (1.0 - collapse)
            if burst > 0.0:
                distance = lerp(distance, particle.radius * 1.16, burst)
            pos = self.center + direction * distance + Vector2(0, particle.drift * (1.0 - collapse))
            tail = self.center + Vector2(math.cos(spin - 0.18), math.sin(spin - 0.18)) * max(18.0, distance - 24.0)
            alpha = int(particle.alpha * fade * (0.35 + 0.65 * collapse))
            if alpha <= 0:
                continue
            pygame.draw.line(layer, (*accent, max(18, alpha // 2)), self._point(tail), self._point(pos), max(1, int(particle.size)))
            pygame.draw.circle(layer, (*accent, alpha), self._point(pos), max(1, int(particle.size)))

        screen.blit(layer, (0, 0), special_flags=pygame.BLEND_ADD)

    def _draw_energy_gate(
        self,
        screen: pygame.Surface,
        accent: tuple[int, int, int],
        progress: float,
        elapsed: float,
    ) -> None:
        layer = pygame.Surface((self.width, self.height), pygame.SRCALPHA)
        open_amount = clamp((progress - 0.24) / 0.42, 0.0, 1.0)
        pillar_height = int(self.height * (0.08 + open_amount * 1.12))
        pillar_width = int(42 + open_amount * 104 + 10 * math.sin(elapsed * 7.0))
        pillar = pygame.Rect(0, 0, pillar_width, pillar_height)
        pillar.center = self._point(self.center)
        pygame.draw.ellipse(layer, (*accent, int(36 + open_amount * 78)), pillar)
        pygame.draw.rect(layer, (*accent, int(18 + open_amount * 42)), pillar.inflate(-pillar_width // 2, 0), border_radius=20)

        for side in (-1, 1):
            beam_x = int(self.center.x + side * (166 + 18 * math.sin(elapsed * 2.7 + side)))
            pygame.draw.line(layer, (*accent, int(70 * open_amount)), (beam_x, 0), (beam_x, self.height), 3)
            pygame.draw.line(layer, (236, 252, 255, int(48 * open_amount)), (beam_x + side * 5, 0), (beam_x + side * 5, self.height), 1)

        for index in range(6):
            y = int(self.center.y - 180 + index * 72 + 26 * math.sin(elapsed * 3.4 + index))
            half = int(155 + open_amount * 220 - index * 10)
            alpha = int((42 + index * 8) * open_amount)
            pygame.draw.line(layer, (*accent, alpha), (int(self.center.x - half), y), (int(self.center.x + half), y), 2)

        screen.blit(layer, (0, 0), special_flags=pygame.BLEND_ADD)

    def _draw_portal_core(
        self,
        screen: pygame.Surface,
        accent: tuple[int, int, int],
        progress: float,
        elapsed: float,
    ) -> None:
        layer = pygame.Surface((self.width, self.height), pygame.SRCALPHA)
        charge = clamp(progress / 0.52, 0.0, 1.0)
        open_amount = clamp((progress - 0.28) / 0.38, 0.0, 1.0)
        base_radius = int(70 + charge * 148 + math.sin(elapsed * 8.0) * 9)

        for index in range(7):
            radius = base_radius + index * 22
            rect = pygame.Rect(0, 0, radius * 2, radius * 2)
            rect.center = self._point(self.center)
            width = 2 + (index % 2)
            alpha = max(24, int(190 - index * 22))
            pygame.draw.ellipse(layer, (*accent, alpha), rect, width=width)

        for index in range(34):
            angle = elapsed * (1.6 if index % 2 else -1.25) + index * math.tau / 34
            inner = base_radius * (0.56 + 0.12 * math.sin(elapsed * 4.0 + index))
            outer = base_radius * (1.05 + 0.18 * open_amount)
            start = self.center + Vector2(math.cos(angle), math.sin(angle)) * inner
            end = self.center + Vector2(math.cos(angle), math.sin(angle)) * outer
            pygame.draw.line(layer, (*accent, 160), self._point(start), self._point(end), 2)

        for index in range(5):
            radius = base_radius + 44 + index * 24
            rect = pygame.Rect(0, 0, radius * 2, radius * 2)
            rect.center = self._point(self.center)
            start = elapsed * (0.85 + index * 0.18) + index
            pygame.draw.arc(layer, (236, 252, 255, max(30, 112 - index * 14)), rect, start, start + math.pi * 0.72, 3)

        core_radius = max(28, int(base_radius * (0.24 + 0.16 * open_amount)))
        pygame.draw.circle(layer, (235, 252, 255, int(96 + 110 * open_amount)), self._point(self.center), core_radius)
        pygame.draw.circle(layer, (*accent, int(72 + 88 * open_amount)), self._point(self.center), core_radius + 34, width=3)
        screen.blit(layer, (0, 0), special_flags=pygame.BLEND_ADD)

    def _draw_title_panel(
        self,
        screen: pygame.Surface,
        fonts: Mapping[str, pygame.font.Font],
        accent: tuple[int, int, int],
        title: str,
        subtitle: str,
        reason: str,
        progress: float,
    ) -> None:
        title_y = int(126 - 24 * clamp(progress / 0.34, 0.0, 1.0))
        draw_outlined_text(screen, self._font(fonts, "hero_small", "large", "medium"), title, (self.width // 2, title_y), accent, center=True)
        draw_outlined_text(screen, self._font(fonts, "medium", "small"), subtitle, (self.width // 2, title_y + 58), TEXT_LIGHT, center=True)

        panel = pygame.Rect(self.width // 2 - 370, self.height - 164, 740, 96)
        panel_layer = pygame.Surface(panel.size, pygame.SRCALPHA)
        pygame.draw.rect(panel_layer, (*UI_PANEL, 224), panel_layer.get_rect(), border_radius=20)
        pygame.draw.rect(panel_layer, (*accent, 210), panel_layer.get_rect(), width=2, border_radius=20)
        screen.blit(panel_layer, panel)

        font = self._font(fonts, "small", "medium")
        text = font.render(reason, True, TEXT_MUTED)
        screen.blit(text, text.get_rect(center=(panel.centerx, panel.centery - 12)))

        track = pygame.Rect(panel.left + 42, panel.bottom - 30, panel.width - 84, 10)
        pygame.draw.rect(screen, (18, 26, 34), track, border_radius=5)
        fill = track.copy()
        fill.width = max(8, int(track.width * progress))
        pygame.draw.rect(screen, accent, fill, border_radius=5)
        pygame.draw.rect(screen, (224, 241, 244), track, width=1, border_radius=5)

    def _draw_flash(self, screen: pygame.Surface, progress: float) -> None:
        flash = 0
        if 0.48 <= progress <= 0.68:
            flash = int(190 * math.sin((progress - 0.48) / 0.20 * math.pi))
        elif progress > 0.9:
            flash = int(255 * clamp((progress - 0.9) / 0.1, 0.0, 1.0))
        if flash <= 0:
            return
        layer = pygame.Surface((self.width, self.height), pygame.SRCALPHA)
        layer.fill((230, 250, 255, flash))
        screen.blit(layer, (0, 0))

    def _font(self, fonts: Mapping[str, pygame.font.Font], *names: str) -> pygame.font.Font:
        for name in names:
            font = fonts.get(name)
            if font is not None:
                return font
        return next(iter(fonts.values()))

    def _point(self, value: Vector2) -> tuple[int, int]:
        return (int(value.x), int(value.y))
