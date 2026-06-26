from __future__ import annotations

import random

import pygame

from ..core.config import DEFAULT_PLAYER_PROFILE, PLAYER_SKIN_BY_ID, PLAYER_STATS, PlayerProfile
from ..core.events import post_skill_cooldown_end
from ..helpers import Vector2
from .character import CharacterBase
from .map import Map


class Player(CharacterBase):
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

    def update(
        self,
        dt: float,
        game_map: Map,
        keys: pygame.key.ScancodeWrapper,
        mouse_world: Vector2,
        firing: bool,
        rng: random.Random,
    ):
        self.update_common(dt)
        previous_cd = self.skill_cooldown_timer
        self.skill_cooldown_timer = max(0.0, self.skill_cooldown_timer - dt)
        if previous_cd > 0.0 and self.skill_cooldown_timer == 0.0:
            post_skill_cooldown_end(self.skill_name)
        if not self.alive:
            return []

        aim = mouse_world - self.position
        if aim.length_squared() > 0:
            self.aim_direction = aim.normalize()

        move = Vector2(
            float(keys[pygame.K_d] or keys[pygame.K_RIGHT]) - float(keys[pygame.K_a] or keys[pygame.K_LEFT]),
            float(keys[pygame.K_s] or keys[pygame.K_DOWN]) - float(keys[pygame.K_w] or keys[pygame.K_UP]),
        )
        sprinting = bool(keys[pygame.K_LSHIFT] or keys[pygame.K_RSHIFT]) and move.length_squared() > 0 and not firing
        speed = self.move_speed * (self.sprint_multiplier if sprinting else 1.0)
        if self.active_weapon.is_reloading:
            speed *= 0.76
        self.apply_movement(move, speed, dt, game_map)

        projectiles = self.fire(rng) if firing else []
        if firing and not projectiles:
            self.auto_reload()
        return projectiles

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
