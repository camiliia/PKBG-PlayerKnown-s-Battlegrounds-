from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from ..entities.projectile import Bullet
from ..helpers import Vector2


@dataclass
class HitEvent:
    impact_position: Vector2
    color: tuple[int, int, int]
    kind: str = "impact"
    radius: float = 0.0
    damage_numbers: list[tuple[Vector2, int]] = field(default_factory=list)
    victims: list[Any] = field(default_factory=list)
    victim: Any = None
    owner: Any = None


class CollisionManager:
    def update_projectiles(self, projectiles, dt: float, game_map, characters) -> tuple[list[Bullet], list[HitEvent]]:
        remaining: list[Bullet] = []
        events: list[HitEvent] = []
        for projectile in projectiles:
            impact_pos, hit_character = projectile.update(dt, game_map, characters)
            if impact_pos is not None:
                color = projectile.color if hit_character is None else (250, 120, 120)
                events.append(
                    HitEvent(
                        impact_position=impact_pos.copy(),
                        color=color,
                        damage_numbers=[(hit_character.position.copy(), projectile.damage)] if hit_character is not None else [],
                        victim=hit_character,
                        owner=projectile.owner,
                    )
                )
            if projectile.alive:
                remaining.append(projectile)
        return remaining, events

    def update_grenades(self, grenades, dt: float, game_map, characters) -> tuple[list, list[HitEvent]]:
        remaining = []
        events: list[HitEvent] = []
        for grenade in grenades:
            explosion_pos = grenade.update(dt, game_map)
            if explosion_pos is not None:
                victims = []
                damage_numbers: list[tuple[Vector2, int]] = []
                for character in characters:
                    if not character.alive:
                        continue
                    distance = explosion_pos.distance_to(character.position)
                    max_distance = grenade.blast_radius + character.radius
                    if distance > max_distance:
                        continue
                    falloff = max(0.35, 1.0 - (distance / max_distance))
                    damage = max(8, int(grenade.damage * falloff))
                    killed = character.take_damage(damage, grenade.owner)
                    grenade.owner.damage_dealt += damage
                    if killed and grenade.owner is not character:
                        grenade.owner.kills += 1
                    victims.append(character)
                    damage_numbers.append((character.position.copy(), damage))
                events.append(
                    HitEvent(
                        impact_position=explosion_pos.copy(),
                        color=grenade.color,
                        kind="explosion",
                        radius=grenade.blast_radius,
                        damage_numbers=damage_numbers,
                        victims=victims,
                        owner=grenade.owner,
                    )
                )
            if grenade.alive:
                remaining.append(grenade)
        return remaining, events
