from __future__ import annotations

import random

import pygame

from ..core.config import DEFAULT_PLAYER_PROFILE, PLAYER_SKIN_BY_ID, PLAYER_STATS, PlayerProfile
from ..core.events import post_skill_cooldown_end
from ..helpers import Vector2
from .character import CharacterBase
from .map import Map


class Player(CharacterBase):
    MOVE_LEFT_KEYS = (pygame.K_a, pygame.K_LEFT)
    MOVE_RIGHT_KEYS = (pygame.K_d, pygame.K_RIGHT)
    MOVE_UP_KEYS = (pygame.K_w, pygame.K_UP)
    MOVE_DOWN_KEYS = (pygame.K_s, pygame.K_DOWN)
    SPRINT_KEYS = (pygame.K_LSHIFT, pygame.K_RSHIFT)

    def __init__(self, position: Vector2, profile: PlayerProfile | None = None) -> None:
        profile = profile or DEFAULT_PLAYER_PROFILE
        skin = PLAYER_SKIN_BY_ID[profile.skin_id]
        super().__init__(
            name=profile.callsign,
            position=position,
            color=skin.primary_color,
            stats=PLAYER_STATS,
            max_weapons=2,
            accent_color=skin.accent_color,
            secondary_color=skin.secondary_color,
            marker_color=skin.marker_color,
            camp="player",
        )
        self.is_player_controlled = True
        self.damage_multiplier = 1.1
        self.profile = profile
        self.skin = skin
        self.skill_name = "位移冲刺"
        self.skill_cooldown_duration = 5.5
        self.skill_cooldown_timer = 0.0
        self.dash_distance = 220.0
        self.energy = 0
        self.max_energy = 100
        self.recent_enemy_pressure: dict[int, tuple[float, bool]] = {}

    def update(
        self,
        dt: float,
        game_map: Map,
        keys: pygame.key.ScancodeWrapper,
        mouse_world: Vector2,
        firing: bool,
        rng: random.Random,
        held_keys: set[int] | None = None,
    ):
        self.update_common(dt)
        if self.recent_enemy_pressure:
            updated_pressure: dict[int, tuple[float, bool]] = {}
            for attacker_id, (timer, is_elite) in self.recent_enemy_pressure.items():
                timer = max(0.0, timer - dt)
                if timer > 0.0:
                    updated_pressure[attacker_id] = (timer, is_elite)
            self.recent_enemy_pressure = updated_pressure
        previous_cd = self.skill_cooldown_timer
        self.skill_cooldown_timer = max(0.0, self.skill_cooldown_timer - dt)
        if previous_cd > 0.0 and self.skill_cooldown_timer == 0.0:
            post_skill_cooldown_end(self.skill_name)
        if not self.alive:
            return []

        aim = mouse_world - self.position
        if aim.length_squared() > 0:
            self.aim_direction = aim.normalize()

        move = self.read_move_input(keys, held_keys)
        sprinting = self.is_sprint_pressed(keys, held_keys) and move.length_squared() > 0 and not firing
        speed = self.move_speed * (self.sprint_multiplier if sprinting else 1.0)
        if self.active_weapon.is_reloading:
            speed *= 0.76
        self.apply_movement(move, speed, dt, game_map)

        projectiles = self.fire(rng) if firing else []
        if firing and not projectiles:
            self.auto_reload()
        return projectiles

    @classmethod
    def read_move_input(cls, keys, held_keys: set[int] | None = None) -> Vector2:
        return Vector2(
            float(cls._any_pressed(keys, held_keys, cls.MOVE_RIGHT_KEYS)) - float(cls._any_pressed(keys, held_keys, cls.MOVE_LEFT_KEYS)),
            float(cls._any_pressed(keys, held_keys, cls.MOVE_DOWN_KEYS)) - float(cls._any_pressed(keys, held_keys, cls.MOVE_UP_KEYS)),
        )

    @classmethod
    def is_sprint_pressed(cls, keys, held_keys: set[int] | None = None) -> bool:
        return cls._any_pressed(keys, held_keys, cls.SPRINT_KEYS)

    @staticmethod
    def _any_pressed(keys, held_keys: set[int] | None, key_codes: tuple[int, ...]) -> bool:
        for key in key_codes:
            if held_keys is not None and key in held_keys:
                return True
            try:
                if keys[key]:
                    return True
            except (IndexError, KeyError, TypeError):
                continue
        return False

    def use_mobility_skill(self, game_map: Map, move_direction: Vector2 | None = None) -> bool:
        if not self.alive or self.skill_cooldown_timer > 0.0 or self.heal_timer > 0.0:
            return False
        direction = move_direction.copy() if move_direction is not None else Vector2()
        if direction.length_squared() <= 1e-6:
            direction = self.aim_direction.copy()
        if direction.length_squared() <= 1e-6:
            direction = Vector2(1, 0)
        direction = direction.normalize()
        dash_speed = self.dash_distance / 0.18
        self.apply_movement(direction, dash_speed, 0.18, game_map)
        self.skill_cooldown_timer = self.skill_cooldown_duration
        self.state = "dash"
        return True

    def gain_energy(self, amount: int) -> int:
        if amount <= 0:
            return 0
        previous = self.energy
        self.energy = min(self.max_energy, self.energy + amount)
        return self.energy - previous

    def enemy_pressure_counts(self) -> tuple[int, int]:
        total = len(self.recent_enemy_pressure)
        elite = sum(1 for _, is_elite in self.recent_enemy_pressure.values() if is_elite)
        return total, elite

    def take_damage(self, amount: int, attacker: CharacterBase | None, minimum_hp: int = 0) -> bool:
        if attacker is not None and getattr(attacker, "camp", "") == "enemy":
            is_elite = bool(getattr(attacker, "is_elite", False))
            self.recent_enemy_pressure[attacker.id] = (4.6 if is_elite else 3.4, is_elite)
            total_pressure, elite_pressure = self.enemy_pressure_counts()
            amount = max(1, int(round(amount * (0.46 if is_elite else 0.36))))
            if is_elite:
                minimum_hp = 0 if elite_pressure >= 2 else max(minimum_hp, 18)
            else:
                minimum_hp = 0 if total_pressure >= 4 else max(minimum_hp, 10)
        return super().take_damage(amount, attacker, minimum_hp=minimum_hp)
