from __future__ import annotations

import random
from dataclasses import dataclass

import pygame

from ..helpers import Vector2


@dataclass
class ImpactEffect:
    position: Vector2
    color: tuple[int, int, int]
    ttl: float = 0.22
    radius: int = 9

    def update(self, dt: float) -> bool:
        self.ttl -= dt
        self.radius += 36 * dt
        return self.ttl > 0

    def draw(self, surface: pygame.Surface, camera) -> None:
        alpha = max(0, min(255, int(255 * (self.ttl / 0.22))))
        ring = pygame.Surface((int(self.radius * 4), int(self.radius * 4)), pygame.SRCALPHA)
        pygame.draw.circle(ring, (*self.color, alpha), (ring.get_width() // 2, ring.get_height() // 2), int(self.radius), width=2)
        center = camera.world_to_screen(self.position)
        surface.blit(ring, (int(center[0] - ring.get_width() / 2), int(center[1] - ring.get_height() / 2)))


@dataclass
class DamageNumber:
    position: Vector2
    value: int
    color: tuple[int, int, int]
    ttl: float = 0.7

    def update(self, dt: float) -> bool:
        self.ttl -= dt
        self.position.y -= 36 * dt
        return self.ttl > 0

    def draw(self, surface: pygame.Surface, camera, font: pygame.font.Font) -> None:
        alpha = max(0, min(255, int(255 * (self.ttl / 0.7))))
        text = font.render(str(self.value), True, self.color)
        tint = pygame.Surface(text.get_size(), pygame.SRCALPHA)
        tint.fill((255, 255, 255, alpha))
        text.blit(tint, (0, 0), special_flags=pygame.BLEND_RGBA_MULT)
        rect = text.get_rect(center=camera.world_to_screen(self.position))
        surface.blit(text, rect)


@dataclass
class RainDrop:
    position: Vector2
    speed: float
    length: float
    alpha: int

    def update(self, dt: float, width: int, height: int, rng: random.Random) -> None:
        self.position.x -= self.speed * 0.16 * dt
        self.position.y += self.speed * dt
        if self.position.y > height + 40 or self.position.x < -40:
            self.position.x = rng.uniform(0, width + 80)
            self.position.y = rng.uniform(-height * 0.2, -20)


class ParticleSystem:
    def __init__(self) -> None:
        self.effects: list[ImpactEffect] = []
        self.damage_numbers: list[DamageNumber] = []
        self.rain_enabled = False
        self.rain_drops: list[RainDrop] = []
        self._rain_rng = random.Random(7)

    def add_impact(self, position: Vector2, color: tuple[int, int, int], radius: int = 9, ttl: float = 0.22) -> None:
        self.effects.append(ImpactEffect(position.copy(), color, ttl=ttl, radius=radius))

    def add_explosion(self, position: Vector2, color: tuple[int, int, int], radius: float) -> None:
        self.effects.append(ImpactEffect(position.copy(), color, ttl=0.38, radius=max(18, int(radius * 0.18))))
        self.effects.append(ImpactEffect(position.copy(), (255, 235, 210), ttl=0.22, radius=max(12, int(radius * 0.1))))

    def add_damage_number(self, position: Vector2, value: int, color: tuple[int, int, int]) -> None:
        self.damage_numbers.append(DamageNumber(position.copy(), value, color))

    def enable_rain(self, width: int, height: int, count: int = 180) -> None:
        self.rain_enabled = True
        if self.rain_drops:
            return
        for _ in range(count):
            self.rain_drops.append(
                RainDrop(
                    position=Vector2(self._rain_rng.uniform(0, width), self._rain_rng.uniform(0, height)),
                    speed=self._rain_rng.uniform(620, 980),
                    length=self._rain_rng.uniform(10, 18),
                    alpha=self._rain_rng.randint(80, 150),
                )
            )

    def disable_rain(self) -> None:
        self.rain_enabled = False
        self.rain_drops.clear()

    def update(self, dt: float, screen_size: tuple[int, int] | None = None) -> None:
        self.effects = [effect for effect in self.effects if effect.update(dt)]
        self.damage_numbers = [number for number in self.damage_numbers if number.update(dt)]
        if self.rain_enabled and screen_size is not None:
            width, height = screen_size
            for drop in self.rain_drops:
                drop.update(dt, width, height, self._rain_rng)

    def draw(self, surface: pygame.Surface, camera, font: pygame.font.Font | None = None) -> None:
        for effect in self.effects:
            effect.draw(surface, camera)
        if font is not None:
            for number in self.damage_numbers:
                number.draw(surface, camera, font)

    def draw_weather(self, surface: pygame.Surface) -> None:
        if not self.rain_enabled:
            return
        rain_layer = pygame.Surface(surface.get_size(), pygame.SRCALPHA)
        for drop in self.rain_drops:
            start = (int(drop.position.x), int(drop.position.y))
            end = (int(drop.position.x + drop.length * 0.22), int(drop.position.y + drop.length))
            pygame.draw.line(rain_layer, (176, 224, 255, drop.alpha), start, end, 1)
            if self._rain_rng.random() < 0.015:
                pygame.draw.circle(rain_layer, (190, 236, 255, 72), start, 2)
        surface.blit(rain_layer, (0, 0))
