from __future__ import annotations

import random

from ..core.config import BOT_STATS, ELITE_BOT_STATS, WeaponSpec
from ..helpers import Vector2
from ..systems.ai import BotBrain
from .character import CharacterBase
from .map import Map


class BotPlayer(CharacterBase):
    def __init__(self, name: str, position: Vector2, weapon_spec: WeaponSpec, rng: random.Random, role: str = "standard") -> None:
        self.role = role
        self.is_elite = role == "elite"

        if self.is_elite:
            primary = (68, 68, 76)
            secondary = (22, 22, 28)
            marker = (255, 118, 118)
            accent = (255, 88, 88)
            stats = ELITE_BOT_STATS
        else:
            primary = (198, 86, 86)
            secondary = (54, 48, 44)
            marker = (255, 186, 186)
            accent = (236, 96, 96)
            stats = BOT_STATS

        super().__init__(
            name=name,
            position=position,
            color=primary,
            stats=stats,
            max_weapons=1,
            accent_color=accent,
            secondary_color=secondary,
            marker_color=marker,
            camp="enemy",
        )
        self.is_elite = role == "elite"
        self.equip_weapon(weapon_spec)
        self.medkits = rng.randint(1, 3) if self.is_elite else rng.randint(0, 2)
        self.aggression = rng.uniform(1.05, 1.24) if self.is_elite else rng.uniform(0.92, 1.12)
        self.accuracy = rng.uniform(1.08, 1.22) if self.is_elite else rng.uniform(0.9, 1.08)
        self.strafe_sign = rng.choice((-1, 1))
        self.strafe_timer = rng.uniform(0.7, 1.3)
        self.wander_target = position.copy()
        self.memory_target: Vector2 | None = None
        self.memory_timer = 0.0
        self.debug_state = "巡逻"
        self.debug_target_name = ""
        self.debug_focus = position.copy()
        self.brain = BotBrain()

    def update(
        self,
        dt: float,
        game_map: Map,
        characters,
        pickups,
        safe_zone,
        rng: random.Random,
    ):
        self.update_common(dt)
        if not self.alive:
            return []

        decision = self.brain.update(self, dt, game_map, characters, pickups, safe_zone, rng)
        self.debug_state = decision.state
        self.debug_target_name = decision.target_name
        self.debug_focus = decision.focus

        sprint = safe_zone.is_outside(self.position) or decision.state not in ("交战", "治疗")
        speed = self.move_speed * (self.sprint_multiplier if sprint else 1.0)
        if self.active_weapon.is_reloading:
            speed *= 0.78
        self.apply_movement(decision.move_vector, speed, dt, game_map)
        if decision.state != "交战" and self.active_weapon.magazine < max(4, self.active_weapon.spec.magazine_size // 3):
            self.active_weapon.begin_reload(self)
        return decision.projectiles
