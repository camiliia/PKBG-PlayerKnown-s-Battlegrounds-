from __future__ import annotations

import math
import random

import pygame

from ..core.config import (
    CharacterStats,
    HEAL_AMOUNT,
    HEAL_TIME,
    MAX_GRENADES,
    MAX_MEDKITS,
    MELEE_BUFFER,
    STARTING_AMMO,
    STARTING_GRENADES,
    WeaponSpec,
)
from ..helpers import Vector2, safe_normalize
from .animation_controller import AnimationController
from .map import Map
from .sprite_base import WorldSprite
from .weapon import Weapon


class CharacterBase(WorldSprite):
    _next_id = 1

    def __init__(
        self,
        name: str,
        position: Vector2,
        color: tuple[int, int, int],
        stats: CharacterStats,
        max_weapons: int = 2,
        accent_color: tuple[int, int, int] | None = None,
        secondary_color: tuple[int, int, int] | None = None,
        marker_color: tuple[int, int, int] | None = None,
        camp: str = "neutral",
    ) -> None:
        super().__init__(layer=2)
        self.id = CharacterBase._next_id
        CharacterBase._next_id += 1

        self.name = name
        self.camp = camp
        self.position = Vector2(position)
        self.velocity = Vector2()
        self.color = color
        self.accent_color = accent_color or color
        self.secondary_color = secondary_color or (44, 48, 52)
        self.marker_color = marker_color or (248, 229, 129)
        self.stats = stats
        self.radius = stats.radius
        self.move_speed = stats.move_speed
        self.sprint_multiplier = stats.sprint_multiplier
        self.max_hp = stats.max_hp
        self.hp = stats.max_hp
        self.max_armor = stats.max_armor
        self.armor = stats.max_armor
        self.alive = True
        self.combat_enabled = False
        self.damage_multiplier = 1.0
        self.state = "idle"
        self.weapons: list[Weapon] = []
        self.active_weapon_index = 0
        self.ammo = dict(STARTING_AMMO)
        self.max_weapons = max_weapons
        self.medkits = 1
        self.max_grenades = MAX_GRENADES
        self.grenade_count = STARTING_GRENADES
        self.kills = 0
        self.damage_dealt = 0
        self.aim_direction = Vector2(1, 0)
        self.last_move = Vector2()
        self.debug_move_input = Vector2()
        self.debug_move_desired_delta = Vector2()
        self.debug_move_actual_delta = Vector2()
        self.debug_move_blocked = False
        self.debug_move_slide_used = False
        self.heal_timer = 0.0
        self.damage_flash_timer = 0.0
        self.muzzle_flash_timer = 0.0
        self.invulnerable_timer = 0.0
        self.last_attacker: CharacterBase | None = None
        self.is_player_controlled = False
        self.respawn_anchor = self.position.copy()
        self.state_time = 0.0
        self._tracked_state = self.state
        self.sprite_base: pygame.Surface | None = None
        self.animation_controller: AnimationController | None = None
        self.sprite_scale = 1.0
        self.sprite_default_angle = 45.0
        self.ground_effect_base: pygame.Surface | None = None
        self.ground_effect_scale = 1.0
        self.shield_effect_base: pygame.Surface | None = None
        self.shield_effect_scale = 1.0
        self.is_elite = False
        self.visual_scale_multiplier = 1.0
        self.sprite_tint: tuple[int, int, int] | None = None
        self.sprite_tint_strength = 0

    @property
    def active_weapon(self) -> Weapon:
        return self.weapons[self.active_weapon_index]

    @property
    def current_weapon(self) -> Weapon:
        return self.active_weapon

    @property
    def weapon_state_label(self) -> str:
        return self.active_weapon.state_label(self)

    def set_sprite_asset(self, surface: pygame.Surface, scale: float = 1.0, default_angle: float = 45.0) -> None:
        self.sprite_base = surface
        self.sprite_scale = scale
        self.sprite_default_angle = default_angle
        self.animation_controller = AnimationController(surface, scale=scale, default_angle=default_angle)

    def set_directional_sprite_sheet(
        self,
        sheet_surface: pygame.Surface,
        *,
        scale: float = 1.0,
        default_angle: float = 45.0,
    ) -> None:
        self.sprite_scale = scale
        self.sprite_default_angle = default_angle
        self.animation_controller = AnimationController.from_direction_sheet(
            sheet_surface,
            scale=scale,
            default_angle=default_angle,
        )
        self.sprite_base = self.animation_controller.directional_bases.get("east")

    def set_animation_sheets(
        self,
        *,
        idle_sheet: pygame.Surface,
        move_sheet: pygame.Surface,
        fire_sheet: pygame.Surface,
        dead_sheet: pygame.Surface,
        sheet_direction_orders: dict[str, tuple[str, ...]] | None = None,
        scale: float = 1.0,
        default_angle: float = 45.0,
    ) -> None:
        self.sprite_scale = scale
        self.sprite_default_angle = default_angle
        self.animation_controller = AnimationController.from_state_sheets(
            {
                "idle": idle_sheet,
                "move": move_sheet,
                "fire": fire_sheet,
                "dead": dead_sheet,
            },
            sheet_direction_orders=sheet_direction_orders,
            scale=scale,
            default_angle=default_angle,
        )
        self.sprite_base = self.animation_controller.directional_bases.get("east")

    def set_effect_assets(
        self,
        *,
        ground_surface: pygame.Surface | None = None,
        ground_scale: float = 1.0,
        shield_surface: pygame.Surface | None = None,
        shield_scale: float = 1.0,
    ) -> None:
        if ground_surface is not None:
            self.ground_effect_base = ground_surface
            self.ground_effect_scale = ground_scale
        if shield_surface is not None:
            self.shield_effect_base = shield_surface
            self.shield_effect_scale = shield_scale

    def equip_weapon(self, spec: WeaponSpec, as_active: bool = True) -> WeaponSpec | None:
        if len(self.weapons) == 1 and self.weapons[0].spec.identifier == "unarmed":
            self.weapons[0] = Weapon(spec)
            self.active_weapon_index = 0
            self.ammo[spec.ammo_type] = self.ammo.get(spec.ammo_type, 0) + spec.pickup_ammo_bonus
            return None
        for weapon in self.weapons:
            if weapon.spec.identifier == spec.identifier:
                self.ammo[spec.ammo_type] = self.ammo.get(spec.ammo_type, 0) + spec.pickup_ammo_bonus
                return None
        if len(self.weapons) < self.max_weapons:
            self.weapons.append(Weapon(spec))
            if as_active:
                self.active_weapon_index = len(self.weapons) - 1
            self.ammo[spec.ammo_type] = self.ammo.get(spec.ammo_type, 0) + spec.pickup_ammo_bonus
            return None
        dropped = self.active_weapon.spec
        self.weapons[self.active_weapon_index] = Weapon(spec)
        self.ammo[spec.ammo_type] = self.ammo.get(spec.ammo_type, 0) + spec.pickup_ammo_bonus
        return dropped

    def switch_weapon(self) -> None:
        if len(self.weapons) > 1:
            self.active_weapon_index = (self.active_weapon_index + 1) % len(self.weapons)

    def arm_combat(self) -> bool:
        if self.combat_enabled:
            return False
        self.combat_enabled = True
        if self.state == "idle":
            self.state = "move" if self.velocity.length_squared() > 0.0 else "idle"
        return True

    def update_common(self, dt: float) -> None:
        self._sync_state_clock(dt)
        if not self.alive:
            return
        for weapon in self.weapons:
            weapon.update(dt, self)
        self.damage_flash_timer = max(0.0, self.damage_flash_timer - dt)
        self.muzzle_flash_timer = max(0.0, self.muzzle_flash_timer - dt)
        self.invulnerable_timer = max(0.0, self.invulnerable_timer - dt)
        if self.heal_timer > 0.0:
            self.heal_timer = max(0.0, self.heal_timer - dt)
            self.state = "heal"
            if self.heal_timer == 0.0:
                self.hp = min(self.max_hp, self.hp + HEAL_AMOUNT)
                self.state = "idle"
        elif self.active_weapon.is_reloading:
            self.state = "reload"
        elif self.state in {"fire", "hit", "dash"} and self.velocity.length_squared() <= 1.0:
            self.state = "idle"

    def try_begin_heal(self) -> bool:
        if not self.alive or self.medkits <= 0 or self.medkits > MAX_MEDKITS or self.hp >= self.max_hp or self.heal_timer > 0.0:
            return False
        self.medkits -= 1
        self.heal_timer = HEAL_TIME
        self.state = "heal"
        return True

    def can_throw_grenade(self) -> bool:
        return self.alive and self.combat_enabled and self.grenade_count > 0 and self.heal_timer <= 0.0

    def take_damage(self, amount: int, attacker: CharacterBase | None, minimum_hp: int = 0) -> bool:
        if not self.alive or self.invulnerable_timer > 0.0:
            return False
        minimum_hp = max(0, min(self.max_hp, minimum_hp))
        absorbed = min(self.armor, amount // 2)
        self.armor -= absorbed
        damage_to_hp = max(1, amount - absorbed)
        if minimum_hp > 0:
            if self.hp <= minimum_hp:
                damage_to_hp = 0
            else:
                damage_to_hp = min(damage_to_hp, self.hp - minimum_hp)
        self.hp -= damage_to_hp
        self.heal_timer = 0.0
        self.damage_flash_timer = 0.18
        self.last_attacker = attacker
        self.state = "hit"
        if self.hp <= 0:
            self.hp = 0
            self.alive = False
            self.velocity = Vector2()
            self.last_move = Vector2()
            self.state = "dead"
            return True
        return False

    def respawn(self, position: Vector2, hp_ratio: float = 0.7, armor_ratio: float = 0.5) -> None:
        self.position = Vector2(position)
        self.velocity = Vector2()
        self.hp = max(1, int(self.max_hp * hp_ratio))
        self.armor = max(0, int(self.max_armor * armor_ratio))
        self.heal_timer = 0.0
        self.damage_flash_timer = 0.0
        self.muzzle_flash_timer = 0.0
        self.invulnerable_timer = 2.4
        self.alive = True
        self.state = "idle"
        self.state_time = 0.0
        self._tracked_state = self.state
        self.last_move = Vector2()

    def movement_ratio(self) -> float:
        if self.velocity.length_squared() <= 0:
            return 0.0
        return min(1.0, self.velocity.length() / (self.move_speed * self.sprint_multiplier))

    def apply_movement(self, direction: Vector2, speed: float, dt: float, game_map: Map) -> None:
        if self.heal_timer > 0.0:
            self.last_move = Vector2()
            self.velocity = Vector2()
            self._set_move_debug(Vector2(), Vector2(), Vector2(), blocked=False, slide_used=False)
            return
        raw_direction = Vector2(direction)
        direction = safe_normalize(raw_direction)
        delta = direction * speed * dt
        if delta.length_squared() <= 0:
            self.last_move = Vector2()
            self.velocity = Vector2()
            self._set_move_debug(raw_direction, delta, Vector2(), blocked=False, slide_used=False)
            if self.state not in {"fire", "hit", "heal", "dead"}:
                self.state = "idle"
            return
        self.state = "run" if speed > self.move_speed * 1.1 else "move"
        start_position = self.position.copy()
        collided = self._move_by_delta(delta, game_map)
        actual_delta = self.position - start_position
        slide_used = False

        blocked_threshold = max(0.45, delta.length() * 0.18)
        if collided and actual_delta.length() <= blocked_threshold:
            normal_position = self.position.copy()
            slide_position, slide_delta = self._best_slide_position(start_position, delta, game_map)
            if slide_delta.length_squared() > actual_delta.length_squared():
                self.position = slide_position
                actual_delta = slide_delta
                slide_used = True
            else:
                self.position = normal_position

        self.last_move = actual_delta
        self.velocity = actual_delta / max(dt, 1e-6) if actual_delta.length_squared() > 0 else Vector2()
        self._set_move_debug(raw_direction, delta, actual_delta, blocked=collided and actual_delta.length() <= blocked_threshold, slide_used=slide_used)

    def _move_by_delta(self, delta: Vector2, game_map: Map) -> bool:
        collided = False
        self.last_move = delta
        previous_x = self.position.x
        self.position.x += delta.x
        attempted_x = self.position.x
        self._resolve_collisions(game_map, axis="x", fallback_position=previous_x)
        collided = collided or abs(self.position.x - attempted_x) > 0.001
        previous_y = self.position.y
        self.position.y += delta.y
        attempted_y = self.position.y
        self._resolve_collisions(game_map, axis="y", fallback_position=previous_y)
        collided = collided or abs(self.position.y - attempted_y) > 0.001
        before_clamp = self.position.copy()
        self.position.x = max(self.radius, min(game_map.bounds.right - self.radius, self.position.x))
        self.position.y = max(self.radius, min(game_map.bounds.bottom - self.radius, self.position.y))
        return collided or self.position.distance_squared_to(before_clamp) > 0.001

    def _best_slide_position(self, start_position: Vector2, delta: Vector2, game_map: Map) -> tuple[Vector2, Vector2]:
        if abs(delta.x) <= 0.001 or abs(delta.y) <= 0.001:
            return start_position.copy(), Vector2()
        best_position = start_position.copy()
        best_delta = Vector2()
        for slide_delta in (Vector2(delta.x, 0), Vector2(0, delta.y)):
            self.position = start_position.copy()
            self._move_by_delta(slide_delta, game_map)
            actual = self.position - start_position
            if actual.length_squared() > best_delta.length_squared():
                best_position = self.position.copy()
                best_delta = actual
        return best_position, best_delta

    def _set_move_debug(self, raw_input: Vector2, desired_delta: Vector2, actual_delta: Vector2, *, blocked: bool, slide_used: bool) -> None:
        self.debug_move_input = Vector2(raw_input)
        self.debug_move_desired_delta = Vector2(desired_delta)
        self.debug_move_actual_delta = Vector2(actual_delta)
        self.debug_move_blocked = blocked
        self.debug_move_slide_used = slide_used

    def _resolve_collisions(self, game_map: Map, axis: str, fallback_position: float) -> None:
        if game_map.point_in_open_passage(self.position):
            return
        hitbox = pygame.Rect(0, 0, self.radius * 2, self.radius * 2)
        hitbox.center = (round(self.position.x), round(self.position.y))
        for obstacle in game_map.obstacles:
            if not hitbox.colliderect(obstacle.rect):
                continue
            if axis == "x":
                if self.last_move.x > 0:
                    hitbox.right = obstacle.rect.left - MELEE_BUFFER // 2
                elif self.last_move.x < 0:
                    hitbox.left = obstacle.rect.right + MELEE_BUFFER // 2
                self.position.x = hitbox.centerx
            else:
                if self.last_move.y > 0:
                    hitbox.bottom = obstacle.rect.top - MELEE_BUFFER // 2
                elif self.last_move.y < 0:
                    hitbox.top = obstacle.rect.bottom + MELEE_BUFFER // 2
                self.position.y = hitbox.centery
        if game_map.collision_mask is not None and game_map.blocks_circle(self.position, self.radius):
            if axis == "x":
                self.position.x = fallback_position
            else:
                self.position.y = fallback_position

    def fire(self, rng: random.Random):
        if self.heal_timer > 0.0 or not self.alive or not self.combat_enabled:
            return []
        bullets = self.active_weapon.fire(self, self.aim_direction, self.movement_ratio(), rng)
        if bullets:
            self.state = "fire"
        return bullets

    def auto_reload(self) -> None:
        if self.combat_enabled and self.active_weapon.magazine <= 0:
            self.active_weapon.begin_reload(self)

    def _sync_state_clock(self, dt: float = 0.0) -> None:
        if self.state != self._tracked_state:
            self._tracked_state = self.state
            self.state_time = 0.0
        else:
            self.state_time += dt

    def _animation_state_name(self) -> str:
        if not self.alive:
            return "dead"
        if self.muzzle_flash_timer > 0.0 or self.state == "fire":
            return "fire"
        if self.state in {"move", "run", "dash"} and self.movement_ratio() > 0.02:
            return "move"
        return "idle"

    def rect(self) -> pygame.Rect:
        rect = pygame.Rect(0, 0, self.radius * 2, self.radius * 2)
        rect.center = (round(self.position.x), round(self.position.y))
        return rect

    @staticmethod
    def _mix_color(base: tuple[int, int, int], target: tuple[int, int, int], amount: float) -> tuple[int, int, int]:
        return tuple(int(base[i] + (target[i] - base[i]) * amount) for i in range(3))

    @staticmethod
    def _local_point(origin: Vector2, right: Vector2, forward: Vector2, lateral: float, depth: float) -> Vector2:
        return origin + right * lateral + forward * depth

    def _local_points(
        self,
        origin: Vector2,
        right: Vector2,
        forward: Vector2,
        points: list[tuple[float, float]],
    ) -> list[tuple[int, int]]:
        return [
            (int(round((origin + right * lateral + forward * depth).x)), int(round((origin + right * lateral + forward * depth).y)))
            for lateral, depth in points
        ]

    def _draw_weapon(self, image: pygame.Surface, origin: Vector2, forward: Vector2, right: Vector2) -> None:
        if not self.weapons:
            return

        spec = self.active_weapon.spec
        profile = {
            "smg": (28, 5, 11),
            "carbine": (34, 4, 13),
            "shotgun": (36, 5, 13),
            "dmr": (40, 4, 14),
        }.get(spec.identifier, (30, 4, 12))
        length, barrel_width, stock_length = profile

        grip = self._local_point(origin, right, forward, 4.0, 8.0)
        muzzle = self._local_point(origin, right, forward, 4.0, length)
        stock = self._local_point(origin, right, forward, 3.0, -stock_length)
        receiver = self._local_point(origin, right, forward, 4.0, 12.0)

        pygame.draw.line(image, (16, 20, 24), stock, muzzle, barrel_width + 4)
        pygame.draw.line(image, spec.color, grip, muzzle, barrel_width)
        pygame.draw.line(image, self._mix_color(spec.color, (235, 238, 240), 0.42), receiver, muzzle, 2)

        magazine = self._local_points(
            origin,
            right,
            forward,
            [(1, 10), (7, 10), (7, 3), (2, 1)],
        )
        body = self._local_points(
            origin,
            right,
            forward,
            [(-1, 6), (9, 6), (9, 18), (-1, 17)],
        )
        pygame.draw.polygon(image, (32, 38, 44), body)
        pygame.draw.polygon(image, spec.color, magazine)

        if spec.identifier in {"carbine", "dmr"}:
            scope = self._local_points(
                origin,
                right,
                forward,
                [(0, 15), (8, 15), (7, 20), (1, 20)],
            )
            pygame.draw.polygon(image, (88, 105, 122), scope)

        if self.muzzle_flash_timer > 0.0:
            flash = self._local_point(origin, right, forward, 4.0, length + 8.0)
            pygame.draw.circle(image, spec.color, flash, 6)
            pygame.draw.circle(image, (255, 244, 206), flash, 3)

    def _blit_effect(
        self,
        image: pygame.Surface,
        surface: pygame.Surface | None,
        center: Vector2,
        scale: float,
        alpha: int,
    ) -> None:
        if surface is None or alpha <= 0:
            return
        size = (
            max(1, int(surface.get_width() * scale)),
            max(1, int(surface.get_height() * scale)),
        )
        effect = surface if size == surface.get_size() else pygame.transform.smoothscale(surface, size)
        if alpha < 255:
            effect = effect.copy()
            effect.fill((255, 255, 255, alpha), special_flags=pygame.BLEND_RGBA_MULT)
        rect = effect.get_rect(center=(int(center.x), int(center.y)))
        image.blit(effect, rect)

    def _draw_ground_effect(self, image: pygame.Surface, body_center: Vector2) -> None:
        if self.ground_effect_base is None or not self.alive:
            return
        pulse = 0.5 + 0.5 * math.sin(pygame.time.get_ticks() * 0.011 + self.id)
        alpha = 54 if self.is_player_controlled else 34
        if self.state == "dash":
            alpha = 76
        elif self.heal_timer > 0.0:
            alpha = max(alpha, 46)
        scale = self.ground_effect_scale * (1.0 + 0.015 * pulse)
        self._blit_effect(image, self.ground_effect_base, body_center + Vector2(0, 10), scale, alpha)

    def _draw_shield_effect(self, image: pygame.Surface, body_center: Vector2) -> bool:
        if self.shield_effect_base is None:
            return False
        if self.invulnerable_timer <= 0.0 and self.armor <= 0:
            return False
        pulse = 0.5 + 0.5 * math.sin(pygame.time.get_ticks() * 0.018 + self.id)
        alpha = 0
        if self.armor > 0:
            alpha = 74 if self.is_player_controlled else 58
        if self.invulnerable_timer > 0.0:
            alpha = max(alpha, int(106 + 34 * pulse))
        scale = self.shield_effect_scale * (1.0 + 0.02 * pulse)
        self._blit_effect(image, self.shield_effect_base, body_center, scale, alpha)
        return True

    def _draw_downed_model(
        self,
        image: pygame.Surface,
        center: Vector2,
        forward: Vector2,
        right: Vector2,
    ) -> None:
        torso = self._local_points(
            center,
            right,
            forward,
            [(-15, -4), (-12, 10), (0, 18), (12, 10), (15, -4), (0, -14)],
        )
        pygame.draw.polygon(image, (38, 42, 48, 210), torso)
        pygame.draw.polygon(image, (16, 18, 20), torso, width=2)
        helmet = self._local_point(center, right, forward, -3.0, 18.0)
        pygame.draw.ellipse(image, (*self._mix_color(self.color, (26, 30, 34), 0.52), 220), pygame.Rect(helmet.x - 9, helmet.y - 7, 18, 14))
        weapon_tip = self._local_point(center, right, forward, 18.0, -3.0)
        weapon_tail = self._local_point(center, right, forward, 2.0, -18.0)
        pygame.draw.line(image, (26, 30, 34), weapon_tail, weapon_tip, 5)

    def sync_visual(self, camera) -> None:
        self._sync_state_clock(0.0)
        visual_scale = max(0.5, float(getattr(self, "visual_scale_multiplier", 1.0)))
        canvas_size = int((self.radius * 2 + 58) * visual_scale)
        center = Vector2(canvas_size / 2, canvas_size / 2)
        image = pygame.Surface((canvas_size, canvas_size), pygame.SRCALPHA)
        screen_pos = camera.world_to_screen(self.position)
        ground_anchor = (screen_pos[0], screen_pos[1] + max(8, int(self.radius * 0.9)))

        facing_source = self.aim_direction if self.aim_direction.length_squared() > 0 else self.last_move
        if not self.is_player_controlled and self.alive and self.state in {"move", "run"} and self.last_move.length_squared() > 0.0:
            facing_source = self.last_move
        facing = safe_normalize(facing_source)
        if facing.length_squared() <= 0:
            facing = Vector2(1, 0)
        forward = facing
        right = Vector2(-forward.y, forward.x)

        move_tick = pygame.time.get_ticks() * 0.018
        stride = math.sin(move_tick) * (3.4 if self.movement_ratio() > 0.05 else 0.0)
        body_center = center + Vector2(0, 1.2 if self.state == "run" else 0.0)
        self._draw_ground_effect(image, body_center)
        shadow_rect = pygame.Rect(0, 0, 38, 24)
        shadow_rect.center = (int(body_center.x + 3), int(body_center.y + 7))
        pygame.draw.ellipse(image, (10, 12, 14, 118), shadow_rect)

        if self.sprite_base is not None or self.animation_controller is not None:
            mask_surface = pygame.Surface((canvas_size, canvas_size), pygame.SRCALPHA)
            controller = self.animation_controller
            sprite = controller.get_frame(forward, self._animation_state_name(), self.state_time).copy() if controller is not None else self.sprite_base.copy()
            if visual_scale != 1.0:
                sprite = pygame.transform.smoothscale(
                    sprite,
                    (
                        max(1, int(sprite.get_width() * visual_scale)),
                        max(1, int(sprite.get_height() * visual_scale)),
                    ),
                )
            if self.sprite_tint is not None and self.sprite_tint_strength > 0:
                tint = pygame.Surface(sprite.get_size(), pygame.SRCALPHA)
                tint.fill((*self.sprite_tint, max(0, min(255, self.sprite_tint_strength))))
                sprite.blit(tint, (0, 0), special_flags=pygame.BLEND_RGBA_ADD)
            if self.damage_flash_timer > 0.0 and self.alive:
                sprite.fill((34, 0, 0, 0), special_flags=pygame.BLEND_RGBA_SUB)
                sprite.fill((84, 24, 24, 0), special_flags=pygame.BLEND_RGBA_ADD)
            sprite_rect = sprite.get_rect(center=(int(body_center.x), int(body_center.y)))
            image.blit(sprite, sprite_rect)
            mask_surface.blit(sprite, sprite_rect)

            if self.muzzle_flash_timer > 0.0:
                flash = self._local_point(body_center, right, forward, 8.0, self.radius + 24.0)
                pygame.draw.circle(image, self.active_weapon.spec.color, flash, 6)
                pygame.draw.circle(image, (255, 244, 206), flash, 3)

            shield_drawn = self._draw_shield_effect(image, body_center)
            if self.armor > 0 and not shield_drawn:
                ring_color = (138, 228, 255) if self.is_player_controlled else (125, 210, 255)
                ring_width = 2 if self.is_elite else 1
                pygame.draw.circle(image, ring_color, (int(body_center.x), int(body_center.y)), self.radius + 10, width=ring_width)
            if self.is_player_controlled:
                arrow = [
                    (int(body_center.x), int(body_center.y - self.radius - 18)),
                    (int(body_center.x - 6), int(body_center.y - self.radius - 7)),
                    (int(body_center.x + 6), int(body_center.y - self.radius - 7)),
                ]
                pygame.draw.polygon(image, self.marker_color, arrow)
            else:
                beacon = self._local_point(body_center, right, forward, 0.0, -18.0)
                beacon_radius = 5 if self.is_elite else 3
                pygame.draw.circle(image, self._mix_color(self.color, (255, 140, 140), 0.4), beacon, beacon_radius)
                if self.is_elite:
                    elite_rect = pygame.Rect(0, 0, (self.radius + 15) * 2, (self.radius + 15) * 2)
                    elite_rect.center = (int(body_center.x), int(body_center.y))
                    pygame.draw.arc(image, self.accent_color, elite_rect, math.radians(18), math.radians(154), 2)
                    pygame.draw.arc(image, self.accent_color, elite_rect, math.radians(206), math.radians(340), 2)
                if getattr(self, "is_treasure_boss", False):
                    boss_rect = pygame.Rect(0, 0, (self.radius + 23) * 2, (self.radius + 23) * 2)
                    boss_rect.center = (int(body_center.x), int(body_center.y))
                    pygame.draw.arc(image, self.marker_color, boss_rect, math.radians(10), math.radians(170), 3)
                    pygame.draw.arc(image, self.marker_color, boss_rect, math.radians(190), math.radians(350), 3)
                    crown_y = int(body_center.y - self.radius - 23)
                    crown = [
                        (int(body_center.x - 10), crown_y + 8),
                        (int(body_center.x - 5), crown_y),
                        (int(body_center.x), crown_y + 8),
                        (int(body_center.x + 5), crown_y),
                        (int(body_center.x + 10), crown_y + 8),
                    ]
                    pygame.draw.lines(image, self.marker_color, False, crown, 3)

            if self.heal_timer > 0.0:
                pulse_rect = pygame.Rect(0, 0, 18, 18)
                pulse_center = self._local_point(body_center, right, forward, -12.0, -3.0)
                pulse_rect.center = (int(pulse_center.x), int(pulse_center.y))
                pygame.draw.ellipse(image, (76, 164, 124), pulse_rect)
                pygame.draw.line(image, (226, 243, 231), (pulse_rect.centerx - 4, pulse_rect.centery), (pulse_rect.centerx + 4, pulse_rect.centery), 2)
                pygame.draw.line(image, (226, 243, 231), (pulse_rect.centerx, pulse_rect.centery - 4), (pulse_rect.centerx, pulse_rect.centery + 4), 2)
            if self.invulnerable_timer > 0.0 and not shield_drawn:
                shield_rect = pygame.Rect(0, 0, (self.radius + 14) * 2, (self.radius + 14) * 2)
                shield_rect.center = (int(body_center.x), int(body_center.y))
                pygame.draw.arc(image, (170, 236, 255), shield_rect, 0.0, math.tau * 0.42, 2)
                pygame.draw.arc(image, (170, 236, 255), shield_rect, math.tau * 0.54, math.tau * 0.94, 2)
            if self.damage_flash_timer > 0.0:
                outline_rect = pygame.Rect(0, 0, (self.radius + 12) * 2, (self.radius + 12) * 2)
                outline_rect.center = (int(body_center.x), int(body_center.y))
                pygame.draw.ellipse(image, (244, 154, 154), outline_rect, width=2)

            bar_back = pygame.Rect(int(body_center.x - 22), int(body_center.y - sprite.get_height() // 2 - 10), 44, 6)
            pygame.draw.rect(image, (25, 30, 34), bar_back, border_radius=3)
            fill = bar_back.copy()
            fill.width = max(0, int(bar_back.width * (self.hp / self.max_hp)))
            pygame.draw.rect(image, (78, 198, 118), fill, border_radius=3)
            if self.armor > 0:
                armor = pygame.Rect(int(body_center.x - 22), int(body_center.y - sprite.get_height() // 2 - 2), 44, 4)
                pygame.draw.rect(image, (18, 26, 34), armor, border_radius=2)
                armor_fill = armor.copy()
                armor_fill.width = max(0, int(armor.width * (self.armor / max(1, self.max_armor))))
                pygame.draw.rect(image, (92, 172, 255), armor_fill, border_radius=2)

            self.image = image
            self.rect = image.get_rect(midbottom=ground_anchor)
            self.mask = pygame.mask.from_surface(mask_surface)
            return

        if not self.alive:
            self._draw_downed_model(image, body_center, forward, right)
            self.image = image
            self.rect = image.get_rect(midbottom=ground_anchor)
            self.mask = pygame.mask.from_surface(self.image)
            return

        suit_color = self._mix_color(self.secondary_color, self.color, 0.28 if self.is_player_controlled else 0.18)
        plate_color = self._mix_color(self.accent_color, (235, 238, 242), 0.2)
        leg_color = self._mix_color(self.secondary_color, (18, 22, 26), 0.38)
        helmet_color = self._mix_color(self.color, (236, 239, 244), 0.16)
        visor_color = self.marker_color if self.is_player_controlled else (255, 170, 170)
        if self.damage_flash_timer > 0.0:
            suit_color = self._mix_color(suit_color, (255, 188, 188), 0.42)
            plate_color = self._mix_color(plate_color, (255, 214, 214), 0.32)

        left_leg = self._local_points(
            body_center,
            right,
            forward,
            [(-9, -12), (-6, -20 + stride), (-2, -18 + stride), (-3, -8)],
        )
        right_leg = self._local_points(
            body_center,
            right,
            forward,
            [(3, -8), (2, -18 - stride), (6, -20 - stride), (9, -12)],
        )
        pygame.draw.polygon(image, leg_color, left_leg)
        pygame.draw.polygon(image, leg_color, right_leg)

        left_boot = self._local_point(body_center, right, forward, -4.8, -20 + stride)
        right_boot = self._local_point(body_center, right, forward, 5.6, -20 - stride)
        pygame.draw.circle(image, (26, 30, 34), left_boot, 4)
        pygame.draw.circle(image, (26, 30, 34), right_boot, 4)

        pack_rect = pygame.Rect(0, 0, 18, 12)
        pack_center = self._local_point(body_center, right, forward, 0.0, -8.0)
        pack_rect.center = (int(pack_center.x), int(pack_center.y))
        pygame.draw.ellipse(image, self._mix_color(self.secondary_color, (12, 14, 18), 0.2), pack_rect)

        torso = self._local_points(
            body_center,
            right,
            forward,
            [(-11, -8), (-13, 4), (-8, 14), (0, 18), (8, 14), (13, 4), (11, -8), (0, -12)],
        )
        pygame.draw.polygon(image, suit_color, torso)
        pygame.draw.polygon(image, (16, 18, 20), torso, width=2)

        chest_plate = self._local_points(
            body_center,
            right,
            forward,
            [(-8, 0), (-8, 9), (0, 14), (8, 9), (8, 0), (0, -3)],
        )
        pygame.draw.polygon(image, plate_color, chest_plate)

        left_shoulder = self._local_point(body_center, right, forward, -13.0, 3.0)
        right_shoulder = self._local_point(body_center, right, forward, 13.0, 3.0)
        pygame.draw.circle(image, plate_color, left_shoulder, 5)
        pygame.draw.circle(image, plate_color, right_shoulder, 5)

        head_center = self._local_point(body_center, right, forward, 0.0, 17.0)
        helmet_rect = pygame.Rect(0, 0, 18, 16)
        helmet_rect.center = (int(head_center.x), int(head_center.y))
        pygame.draw.ellipse(image, helmet_color, helmet_rect)
        pygame.draw.ellipse(image, (18, 20, 24), helmet_rect, width=2)
        visor_start = self._local_point(head_center, right, forward, -5.0, 1.0)
        visor_end = self._local_point(head_center, right, forward, 5.0, 1.0)
        pygame.draw.line(image, visor_color, visor_start, visor_end, 2)

        if self.active_weapon.is_reloading:
            left_hand = self._local_point(body_center, right, forward, -4.0, 2.0)
            right_hand = self._local_point(body_center, right, forward, 8.0, 4.0)
        elif self.heal_timer > 0.0:
            left_hand = self._local_point(body_center, right, forward, -4.0, 6.0)
            right_hand = self._local_point(body_center, right, forward, 4.0, 8.0)
        else:
            left_hand = self._local_point(body_center, right, forward, -6.0, 7.0)
            right_hand = self._local_point(body_center, right, forward, 9.0, 6.0)
        pygame.draw.line(image, plate_color, left_shoulder, left_hand, 5)
        pygame.draw.line(image, plate_color, right_shoulder, right_hand, 5)

        self._draw_weapon(image, body_center, forward, right)

        shield_drawn = self._draw_shield_effect(image, body_center)
        if self.armor > 0 and not shield_drawn:
            ring_color = (138, 228, 255) if self.is_player_controlled else (125, 210, 255)
            pygame.draw.circle(image, ring_color, (int(body_center.x), int(body_center.y)), self.radius + 8, width=1)
        if self.is_player_controlled:
            arrow = [
                (int(body_center.x), int(body_center.y - self.radius - 16)),
                (int(body_center.x - 6), int(body_center.y - self.radius - 5)),
                (int(body_center.x + 6), int(body_center.y - self.radius - 5)),
            ]
            pygame.draw.polygon(image, self.marker_color, arrow)
        else:
            beacon = self._local_point(body_center, right, forward, 0.0, -16.0)
            pygame.draw.circle(image, self._mix_color(self.color, (255, 140, 140), 0.4), beacon, 3)

        if self.heal_timer > 0.0:
            pulse_rect = pygame.Rect(0, 0, 18, 18)
            pulse_center = self._local_point(body_center, right, forward, -12.0, -3.0)
            pulse_rect.center = (int(pulse_center.x), int(pulse_center.y))
            pygame.draw.ellipse(image, (76, 164, 124), pulse_rect)
            pygame.draw.line(image, (226, 243, 231), (pulse_rect.centerx - 4, pulse_rect.centery), (pulse_rect.centerx + 4, pulse_rect.centery), 2)
            pygame.draw.line(image, (226, 243, 231), (pulse_rect.centerx, pulse_rect.centery - 4), (pulse_rect.centerx, pulse_rect.centery + 4), 2)
        if self.invulnerable_timer > 0.0 and not shield_drawn:
            shield_rect = pygame.Rect(0, 0, (self.radius + 12) * 2, (self.radius + 12) * 2)
            shield_rect.center = (int(body_center.x), int(body_center.y))
            pygame.draw.arc(image, (170, 236, 255), shield_rect, 0.0, math.tau * 0.42, 2)
            pygame.draw.arc(image, (170, 236, 255), shield_rect, math.tau * 0.54, math.tau * 0.94, 2)
        if self.damage_flash_timer > 0.0:
            outline_rect = pygame.Rect(0, 0, (self.radius + 10) * 2, (self.radius + 10) * 2)
            outline_rect.center = (int(body_center.x), int(body_center.y))
            pygame.draw.ellipse(image, (244, 154, 154), outline_rect, width=2)

        bar_back = pygame.Rect(int(body_center.x - 22), int(body_center.y - self.radius - 16), 44, 6)
        pygame.draw.rect(image, (25, 30, 34), bar_back, border_radius=3)
        fill = bar_back.copy()
        fill.width = max(0, int(bar_back.width * (self.hp / self.max_hp)))
        pygame.draw.rect(image, (78, 198, 118), fill, border_radius=3)
        if self.armor > 0:
            armor = pygame.Rect(int(body_center.x - 22), int(body_center.y - self.radius - 8), 44, 4)
            pygame.draw.rect(image, (18, 26, 34), armor, border_radius=2)
            armor_fill = armor.copy()
            armor_fill.width = max(0, int(armor.width * (self.armor / max(1, self.max_armor))))
            pygame.draw.rect(image, (92, 172, 255), armor_fill, border_radius=2)

        self.image = image
        self.rect = image.get_rect(midbottom=ground_anchor)
        self.mask = pygame.mask.from_surface(self.image)


Character = CharacterBase
