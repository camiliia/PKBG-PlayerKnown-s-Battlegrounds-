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
        self.combat_enabled = True
        self.damage_multiplier = 0.5 if self.is_elite else 0.42
        self.alerted = False
        self.alert_timer = 0.0
        self.search_timer = 0.0
        self.medkits = rng.randint(1, 3) if self.is_elite else rng.randint(0, 2)
        self.aggression = rng.uniform(1.05, 1.24) if self.is_elite else rng.uniform(0.92, 1.12)
        self.accuracy = rng.uniform(1.08, 1.22) if self.is_elite else rng.uniform(0.9, 1.08)
        self.strafe_sign = rng.choice((-1, 1))
        self.strafe_timer = rng.uniform(0.7, 1.3)
        self.wander_target = position.copy()
        self.path_points: list[Vector2] = []
        self.path_goal_cell: tuple[int, int] | None = None
        self.path_recalc_timer = 0.0
        self.path_current_cell: tuple[int, int] | None = None
        self.path_previous_cell: tuple[int, int] | None = None
        self.path_last_dir: tuple[int, int] | None = None
        self.guard_anchor = position.copy()
        self.guard_radius = 260.0 if self.is_elite else 340.0
        self.guard_label = "guard"
        self.treasure_guard = False
        self.is_treasure_boss = False
        self.patrol_entire_map = self.is_elite
        self.memory_target: Vector2 | None = None
        self.memory_timer = 0.0
        self.reaction_timer = rng.uniform(0.12, 0.28)
        self.fire_pause_timer = rng.uniform(0.24, 0.65)
        self.patrol_pause_timer = rng.uniform(0.25, 0.7)
        self.patrol_speed_scale = 0.58 if self.is_elite else 0.52
        self.stuck_timer = 0.0
        self.debug_state = "patrol"
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
        if self.alert_timer > 0.0:
            self.alert_timer = max(0.0, self.alert_timer - dt)
            if self.alert_timer == 0.0:
                self.alerted = False
        if self.search_timer > 0.0:
            self.search_timer = max(0.0, self.search_timer - dt)
        self.reaction_timer = max(0.0, self.reaction_timer - dt)
        self.fire_pause_timer = max(0.0, self.fire_pause_timer - dt)
        self.patrol_pause_timer = max(0.0, self.patrol_pause_timer - dt)
        if not self.alive:
            return []

        self._update_path_cell_memory(game_map)
        decision = self.brain.update(self, dt, game_map, characters, pickups, safe_zone, rng)
        self.debug_state = decision.state
        self.debug_target_name = decision.target_name
        self.debug_focus = decision.focus

        sprint = safe_zone.is_outside(self.position) or decision.state in {"chase", "zone"}
        speed = self.move_speed * (self.sprint_multiplier if sprint else self.patrol_speed_scale)
        if decision.state == "attack" or (not safe_zone.is_outside(self.position) and not self.alerted and not self.searching):
            speed = self.move_speed * self.patrol_speed_scale
        if self.active_weapon.is_reloading:
            speed *= 0.78
        previous_position = self.position.copy()
        self.apply_movement(decision.move_vector, speed, dt, game_map)
        self._update_path_cell_memory(game_map)
        if decision.move_vector.length_squared() > 0.05:
            moved_distance = self.position.distance_to(previous_position)
            expected_distance = speed * dt
            if moved_distance <= max(1.0, expected_distance * 0.14):
                self.stuck_timer += dt
            else:
                self.stuck_timer = 0.0
        else:
            self.stuck_timer = 0.0
        if self.stuck_timer >= (0.35 if self.is_elite else 0.55):
            self.stuck_timer = 0.0
            self.wander_target = self.brain.repath_bot(self, safe_zone, game_map, rng)
        if decision.state != "attack" and self.active_weapon.magazine < max(4, self.active_weapon.spec.magazine_size // 3):
            self.active_weapon.begin_reload(self)
        return decision.projectiles

    @property
    def searching(self) -> bool:
        return self.search_timer > 0.0

    def set_alerted(
        self,
        duration: float,
        source: Vector2 | None = None,
        investigation_time: float | None = None,
    ) -> None:
        self.alerted = True
        self.alert_timer = max(self.alert_timer, duration)
        self.search_timer = max(self.search_timer, duration * 0.82)
        self.reaction_timer = max(self.reaction_timer, 0.1 if self.is_elite else 0.18)
        self.fire_pause_timer = min(self.fire_pause_timer, 0.18 if self.is_elite else 0.26)
        self.patrol_pause_timer = 0.0
        if source is not None:
            self.memory_target = source.copy()
            self.memory_timer = max(self.memory_timer, investigation_time if investigation_time is not None else duration * 0.65)
            self.wander_target = source.copy()
            self._clear_path_cache()

    def set_searching(
        self,
        duration: float,
        source: Vector2 | None = None,
        investigation_time: float | None = None,
    ) -> None:
        self.search_timer = max(self.search_timer, duration)
        if source is not None:
            self.memory_target = source.copy()
            self.memory_timer = max(self.memory_timer, investigation_time if investigation_time is not None else duration * 0.9)
            self.wander_target = source.copy()
            self._clear_path_cache()
        self.patrol_pause_timer = 0.0

    def set_guard_anchor(
        self,
        anchor: Vector2,
        *,
        radius: float,
        label: str,
        treasure_guard: bool = False,
    ) -> None:
        self.guard_anchor = anchor.copy()
        self.guard_radius = radius
        self.guard_label = label
        self.treasure_guard = treasure_guard
        self.patrol_pause_timer = 0.0
        if self.memory_target is None and self.position.distance_to(self.wander_target) <= 4.0:
            self.wander_target = anchor.copy()
            self._clear_path_cache()

    def _clear_path_cache(self) -> None:
        self.path_points = []
        self.path_goal_cell = None
        self.path_recalc_timer = 0.0

    def _update_path_cell_memory(self, game_map: Map) -> None:
        cell = game_map.world_to_cell(self.position)
        if self.path_current_cell is None:
            self.path_current_cell = cell
            return
        if cell == self.path_current_cell:
            return
        previous = self.path_current_cell
        self.path_previous_cell = previous
        self.path_current_cell = cell
        dx = cell[0] - previous[0]
        dy = cell[1] - previous[1]
        self.path_last_dir = (0 if dx == 0 else (1 if dx > 0 else -1), 0 if dy == 0 else (1 if dy > 0 else -1))
