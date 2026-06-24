from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

import pygame

from ..core.config import GRENADE_BLAST_RADIUS, GRENADE_COLOR, GRENADE_DAMAGE, GRENADE_FUSE_TIME
from ..helpers import Vector2, circle_rect_collision, distance_to_segment
from .sprite_base import WorldSprite

if TYPE_CHECKING:
    from .character import CharacterBase
    from .map import Map


class Bullet(WorldSprite):
    def __init__(
        self,
        position: Vector2,
        velocity: Vector2,
        damage: int,
        radius: int,
        remaining_range: float,
        owner: CharacterBase,
        color: tuple[int, int, int],
    ) -> None:
        super().__init__(layer=3)
        self.position = Vector2(position)
        self.velocity = Vector2(velocity)
        self.damage = damage
        self.radius = radius
        self.remaining_range = remaining_range
        self.owner = owner
        self.color = color
        self.alive = True

    def update(
        self,
        dt: float,
        game_map: Map,
        characters: list[CharacterBase],
    ) -> tuple[Vector2 | None, CharacterBase | None]:
        if not self.alive:
            return None, None
        previous = self.position.copy()
        travel = self.velocity * dt
        self.position += travel
        self.remaining_range -= travel.length()
        if not game_map.bounds.collidepoint(self.position):
            self.alive = False
            return self.position, None
        for obstacle in game_map.obstacles:
            hitbox = obstacle.rect.inflate(self.radius * 2, self.radius * 2)
            if hitbox.clipline(previous, self.position):
                self.alive = False
                return self.position, None
        for character in characters:
            if character is self.owner or not character.alive:
                continue
            hit_distance = character.radius + self.radius + 2
            if distance_to_segment(character.position, previous, self.position) <= hit_distance:
                bullet_rect = self.world_rect()
                target_rect = character.world_rect()
                offset = (target_rect.x - bullet_rect.x, target_rect.y - bullet_rect.y)
                if self.mask is not None and character.mask is not None and self.mask.overlap(character.mask, offset) is None:
                    continue
                self.alive = False
                killed = character.take_damage(self.damage, self.owner)
                self.owner.damage_dealt += self.damage
                if killed:
                    self.owner.kills += 1
                return self.position, character
        if self.remaining_range <= 0:
            self.alive = False
            return self.position, None
        return None, None

    def sync_visual(self, camera: Vector2) -> None:
        size = self.radius * 2 + 18
        center = Vector2(size / 2, size / 2)
        image = pygame.Surface((size, size), pygame.SRCALPHA)
        pygame.draw.circle(image, self.color, (int(center.x), int(center.y)), self.radius)
        if self.velocity.length_squared() > 1e-6:
            tail = center - self.velocity.normalize() * 10
            pygame.draw.line(image, self.color, (int(center.x), int(center.y)), (int(tail.x), int(tail.y)), 2)
        self.image = image
        self.rect = image.get_rect(center=(int(self.position.x - camera.x), int(self.position.y - camera.y)))
        self.mask = pygame.mask.from_surface(self.image)


Projectile = Bullet


class Grenade(WorldSprite):
    def __init__(
        self,
        position: Vector2,
        velocity: Vector2,
        owner: CharacterBase,
        fuse_time: float = GRENADE_FUSE_TIME,
        blast_radius: float = GRENADE_BLAST_RADIUS,
        damage: int = GRENADE_DAMAGE,
        radius: int = 8,
        color: tuple[int, int, int] = GRENADE_COLOR,
    ) -> None:
        super().__init__(layer=3)
        self.position = Vector2(position)
        self.velocity = Vector2(velocity)
        self.owner = owner
        self.fuse_time = fuse_time
        self.blast_radius = blast_radius
        self.damage = damage
        self.radius = radius
        self.color = color
        self.alive = True

    def update(self, dt: float, game_map: Map) -> Vector2 | None:
        if not self.alive:
            return None
        self.fuse_time -= dt
        self.velocity *= max(0.0, 1.0 - dt * 1.35)
        next_pos = self.position + self.velocity * dt

        attempted = Vector2(next_pos)
        hit_world_x = attempted.x < self.radius or attempted.x > game_map.bounds.right - self.radius
        hit_world_y = attempted.y < self.radius or attempted.y > game_map.bounds.bottom - self.radius
        if hit_world_x:
            self.velocity.x *= -0.58
            attempted.x = max(self.radius, min(game_map.bounds.right - self.radius, attempted.x))
        if hit_world_y:
            self.velocity.y *= -0.58
            attempted.y = max(self.radius, min(game_map.bounds.bottom - self.radius, attempted.y))

        test_x = Vector2(attempted.x, self.position.y)
        for obstacle in game_map.obstacles:
            if circle_rect_collision(test_x, self.radius, obstacle.rect):
                self.velocity.x *= -0.52
                attempted.x = self.position.x
                break
        test_y = Vector2(attempted.x, attempted.y)
        for obstacle in game_map.obstacles:
            if circle_rect_collision(test_y, self.radius, obstacle.rect):
                self.velocity.y *= -0.52
                attempted.y = self.position.y
                break

        self.position = attempted
        if self.fuse_time <= 0.0 or self.velocity.length_squared() <= 240.0 and self.fuse_time <= 0.22:
            self.alive = False
            return self.position.copy()
        return None

    def sync_visual(self, camera: Vector2) -> None:
        pulse_radius = self.radius + max(0, int((self.fuse_time % 0.2) * 8))
        size = pulse_radius * 2 + 16
        center = (size // 2, size // 2)
        image = pygame.Surface((size, size), pygame.SRCALPHA)
        pygame.draw.circle(image, (28, 30, 34, 180), center, pulse_radius + 3)
        pygame.draw.circle(image, self.color, center, pulse_radius)
        pygame.draw.circle(image, (252, 235, 188), center, pulse_radius, width=2)
        self.image = image
        self.rect = image.get_rect(center=(int(self.position.x - camera.x), int(self.position.y - camera.y)))
        self.mask = pygame.mask.from_surface(self.image)
