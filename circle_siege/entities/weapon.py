from __future__ import annotations

import math
import random
from enum import Enum
from typing import TYPE_CHECKING

from ..core.events import post_reload_complete
from ..core.config import WeaponSpec
from ..helpers import Vector2, safe_normalize

if TYPE_CHECKING:
    from .character import CharacterBase
    from .projectile import Bullet


class WeaponState(str, Enum):
    LOCKED = "locked"
    READY = "ready"
    COOLDOWN = "cooldown"
    RELOADING = "reloading"
    EMPTY = "empty"
    OUT_OF_AMMO = "out_of_ammo"

    @property
    def label(self) -> str:
        return {
            WeaponState.LOCKED: "待武装",
            WeaponState.READY: "就绪",
            WeaponState.COOLDOWN: "冷却中",
            WeaponState.RELOADING: "换弹中",
            WeaponState.EMPTY: "弹夹为空",
            WeaponState.OUT_OF_AMMO: "备弹不足",
        }[self]


class Weapon:
    def __init__(self, spec: WeaponSpec) -> None:
        self.spec = spec
        self.magazine = spec.magazine_size
        self.cooldown = 0.0
        self.reload_timer = 0.0

    @property
    def is_reloading(self) -> bool:
        return self.reload_timer > 0.0

    def state_for(self, owner: CharacterBase) -> WeaponState:
        if self.spec.identifier == "unarmed":
            return WeaponState.LOCKED
        if not owner.combat_enabled:
            return WeaponState.LOCKED
        if self.reload_timer > 0.0:
            return WeaponState.RELOADING
        if self.cooldown > 0.0:
            return WeaponState.COOLDOWN
        if self.magazine <= 0:
            if owner.ammo.get(self.spec.ammo_type, 0) > 0:
                return WeaponState.EMPTY
            return WeaponState.OUT_OF_AMMO
        return WeaponState.READY

    def state_label(self, owner: CharacterBase) -> str:
        return self.state_for(owner).label

    def update(self, dt: float, owner: CharacterBase) -> None:
        self.cooldown = max(0.0, self.cooldown - dt)
        if self.reload_timer > 0.0:
            self.reload_timer = max(0.0, self.reload_timer - dt)
            if self.reload_timer == 0.0:
                need = self.spec.magazine_size - self.magazine
                available = owner.ammo.get(self.spec.ammo_type, 0)
                loaded = min(need, available)
                self.magazine += loaded
                owner.ammo[self.spec.ammo_type] = available - loaded
                post_reload_complete(owner.name, self.spec.label, owner.is_player_controlled)

    def begin_reload(self, owner: CharacterBase) -> bool:
        if not owner.combat_enabled:
            return False
        if self.reload_timer > 0.0:
            return False
        if self.magazine >= self.spec.magazine_size:
            return False
        if owner.ammo.get(self.spec.ammo_type, 0) <= 0:
            return False
        self.reload_timer = self.spec.reload_time
        owner.state = "reload"
        return True

    def can_fire(self, owner: CharacterBase) -> bool:
        return self.state_for(owner) == WeaponState.READY

    def fire(
        self,
        owner: CharacterBase,
        direction: Vector2,
        movement_ratio: float,
        rng: random.Random,
    ) -> list[Bullet]:
        from .projectile import Bullet

        if not self.can_fire(owner):
            return []
        direction = safe_normalize(direction)
        if direction.length_squared() <= 0:
            return []
        self.magazine -= 1
        self.cooldown = self.spec.fire_interval
        owner.muzzle_flash_timer = 0.06
        bullets: list[Bullet] = []
        base_angle = math.atan2(direction.y, direction.x)
        total_spread = self.spec.spread + self.spec.move_spread * movement_ratio
        for _ in range(self.spec.pellets):
            angle = base_angle + rng.uniform(-total_spread, total_spread)
            velocity = Vector2(math.cos(angle), math.sin(angle)) * self.spec.projectile_speed
            spawn = owner.position + Vector2(math.cos(angle), math.sin(angle)) * (owner.radius + 14)
            bullets.append(
                Bullet(
                    position=spawn,
                    velocity=velocity,
                    damage=max(1, int(round(self.spec.damage * owner.damage_multiplier))),
                    radius=self.spec.projectile_radius,
                    remaining_range=self.spec.range_limit,
                    owner=owner,
                    color=self.spec.color,
                )
            )
        return bullets
