from __future__ import annotations

import random
from dataclasses import dataclass
from typing import TYPE_CHECKING

from ..helpers import Vector2, safe_normalize

if TYPE_CHECKING:
    from ..entities.bot_player import BotPlayer
    from ..entities.character import CharacterBase
    from ..entities.item import Pickup
    from ..entities.map import Map
    from ..rules.match_manager import SafeZone


@dataclass
class AIDecision:
    projectiles: list
    move_vector: Vector2
    state: str
    target_name: str
    focus: Vector2


class BotBrain:
    """Grid-based bot brain: roam the whole map, path to targets, attack in range."""

    def update(
        self,
        bot: BotPlayer,
        dt: float,
        game_map: Map,
        characters: list[CharacterBase],
        pickups: list[Pickup],
        safe_zone: SafeZone,
        rng: random.Random,
    ) -> AIDecision:
        if not bot.combat_enabled:
            gear_target = self._select_nearest_pickup(bot, pickups, kind="gear")
            if gear_target is not None:
                return self._move_direct(bot, gear_target.position, "arm", gear_target.label)

        if bot.hp <= 40 and bot.medkits > 0 and bot.heal_timer <= 0.0:
            bot.try_begin_heal()
        if bot.heal_timer > 0.0:
            return AIDecision([], Vector2(), "heal", "", bot.position.copy())

        active_aggro = bot.alerted or bot.searching
        target = self._nearest_enemy(bot, characters) if active_aggro else None
        if target is not None and bot.alerted:
            distance = bot.position.distance_to(target.position)
            attack_range = bot.active_weapon.spec.range_limit
            has_sight = game_map.has_line_of_sight(bot.position, target.position)
            if distance <= attack_range and has_sight:
                projectiles = self._attack(bot, target, rng)
                return AIDecision(projectiles, Vector2(), "attack", target.name, target.position.copy())

            # Follow the player through the grid when close enough to matter.
            chase_range = max(attack_range * 1.35, game_map.cell_size * 8)
            if distance <= chase_range or safe_zone.is_outside(bot.position):
                move_vector = self._path_move_vector(bot, game_map, target.position, rng, dt)
                if move_vector.length_squared() > 0.0:
                    bot.aim_direction = safe_normalize(target.position - bot.position)
                return AIDecision([], move_vector, "chase", target.name, target.position.copy())

        if active_aggro and bot.memory_target is not None:
            if bot.position.distance_to(bot.memory_target) > max(18.0, game_map.cell_size * 0.35):
                move_vector = self._path_move_vector(bot, game_map, bot.memory_target, rng, dt)
                if move_vector.length_squared() > 0.0:
                    bot.aim_direction = move_vector.normalize()
                return AIDecision([], move_vector, "search", "last_seen", bot.memory_target.copy())

        if safe_zone.is_outside(bot.position):
            move_vector = self._path_move_vector(bot, game_map, safe_zone.current_center, rng, dt)
            return AIDecision([], move_vector, "zone", "safe_zone", safe_zone.current_center.copy())

        if bot.patrol_pause_timer > 0.0:
            return AIDecision([], Vector2(), "idle", bot.guard_label, bot.position.copy())

        if bot.position.distance_to(bot.wander_target) < max(18.0, game_map.cell_size * 0.35):
            bot.patrol_pause_timer = rng.uniform(0.18, 0.45) if bot.is_elite else rng.uniform(0.3, 0.7)
            bot.wander_target = self.repath_bot(bot, safe_zone, game_map, rng)
            return AIDecision([], Vector2(), "idle", "patrol", bot.position.copy())

        move_vector = self._path_move_vector(bot, game_map, bot.wander_target, rng, dt)
        if move_vector.length_squared() <= 0.0:
            bot.wander_target = self.repath_bot(bot, safe_zone, game_map, rng)
            move_vector = self._path_move_vector(bot, game_map, bot.wander_target, rng, dt)
        if move_vector.length_squared() > 0.0:
            bot.aim_direction = move_vector.normalize()
        return AIDecision([], move_vector, "patrol", "grid", bot.wander_target.copy())

    def repath_bot(
        self,
        bot: BotPlayer,
        safe_zone: SafeZone,
        game_map: Map,
        rng: random.Random,
    ) -> Vector2:
        bot._clear_path_cache()
        for _ in range(24):
            cell = game_map.random_open_cell(rng, margin_cells=2)
            point = game_map.cell_to_world(cell)
            if point.distance_to(bot.position) >= game_map.cell_size * 4 and not safe_zone.is_outside(point):
                return point
        return safe_zone.random_patrol_point(rng, game_map)

    def _move_direct(self, bot: BotPlayer, target: Vector2, state: str, target_name: str) -> AIDecision:
        move_vector = safe_normalize(target - bot.position)
        if move_vector.length_squared() > 0.0:
            bot.aim_direction = move_vector
        return AIDecision([], move_vector, state, target_name, target.copy())

    def _path_move_vector(self, bot: BotPlayer, game_map: Map, goal: Vector2, rng: random.Random, dt: float) -> Vector2:
        stable_goal = self._resolve_stable_goal(bot, game_map, goal)
        goal_cell = game_map.world_to_cell(stable_goal)
        bot.path_recalc_timer = max(0.0, bot.path_recalc_timer - dt)

        current_cell = game_map.world_to_cell(bot.position)
        goal_shift = self._cell_distance(goal_cell, bot.path_goal_cell) if bot.path_goal_cell is not None else 999.0
        first_point_blocked = bool(
            bot.path_points
            and game_map.segment_hits_blocking(bot.position, bot.path_points[0], radius=bot.radius * 0.55) is not None
        )
        needs_path = (
            not bot.path_points
            or bot.path_goal_cell is None
            or (first_point_blocked and bot.stuck_timer >= 0.12)
            or (bot.path_recalc_timer <= 0.0 and goal_shift >= 1.75)
            or (bot.path_recalc_timer <= 0.12 and goal_shift >= 3.0)
        )
        if needs_path:
            forbidden_first_cell = bot.path_previous_cell if bot.path_previous_cell != goal_cell else None
            bot.path_points = game_map.find_path(
                bot.position,
                stable_goal,
                preferred_dir=bot.path_last_dir,
                forbidden_first_cell=forbidden_first_cell,
            )
            bot.path_goal_cell = goal_cell
            bot.path_recalc_timer = rng.uniform(0.45, 0.75) if bot.alerted else rng.uniform(0.55, 0.95)

        self._advance_path_points(bot, game_map)
        if not bot.path_points:
            if current_cell == goal_cell or game_map.segment_hits_blocking(bot.position, stable_goal, radius=bot.radius * 0.55) is None:
                return safe_normalize(stable_goal - bot.position)
            return Vector2()
        return safe_normalize(bot.path_points[0] - bot.position)

    def _resolve_stable_goal(self, bot: BotPlayer, game_map: Map, goal: Vector2) -> Vector2:
        if game_map.is_walkable_point(goal, clearance=bot.radius * 0.75):
            return goal.copy()
        nearest = game_map.find_nearest_walkable_point(
            goal,
            clearance=bot.radius * 0.75,
            search_limit=game_map.cell_size * 5,
        )
        return nearest if nearest is not None else goal.copy()

    def _advance_path_points(self, bot: BotPlayer, game_map: Map) -> None:
        arrival_radius = max(bot.radius * 1.25, game_map.cell_size * 0.35)
        while bot.path_points and bot.position.distance_to(bot.path_points[0]) <= arrival_radius:
            bot.path_points.pop(0)

        max_jump_index = min(2, len(bot.path_points) - 1)
        for index in range(max_jump_index, 0, -1):
            waypoint = bot.path_points[index]
            if game_map.segment_hits_blocking(bot.position, waypoint, radius=bot.radius * 0.45) is None:
                del bot.path_points[:index]
                return

    @staticmethod
    def _cell_distance(a: tuple[int, int], b: tuple[int, int] | None) -> float:
        if b is None:
            return 999.0
        return max(abs(a[0] - b[0]), abs(a[1] - b[1]))

    def _attack(self, bot: BotPlayer, target: CharacterBase, rng: random.Random) -> list:
        aim = safe_normalize(target.position - bot.position)
        if aim.length_squared() > 0.0:
            bot.aim_direction = aim
        if bot.active_weapon.magazine <= 0:
            bot.active_weapon.begin_reload(bot)
            return []
        if bot.active_weapon.cooldown > 0.0 or bot.active_weapon.is_reloading:
            return []
        if bot.reaction_timer > 0.0 or bot.fire_pause_timer > 0.0:
            return []
        fire_chance = 0.82 if bot.is_elite else 0.58
        if rng.random() > fire_chance:
            bot.fire_pause_timer = rng.uniform(0.12, 0.25) if bot.is_elite else rng.uniform(0.22, 0.4)
            return []
        bot.fire_pause_timer = rng.uniform(0.12, 0.24) if bot.is_elite else rng.uniform(0.2, 0.36)
        return bot.active_weapon.fire(bot, aim, bot.movement_ratio(), rng)

    def _nearest_enemy(self, bot: BotPlayer, characters: list[CharacterBase]) -> CharacterBase | None:
        enemies = [
            character
            for character in characters
            if character is not bot and character.alive and character.camp != bot.camp
        ]
        if not enemies:
            return None
        return min(enemies, key=lambda character: bot.position.distance_to(character.position))

    def _select_nearest_pickup(self, bot: BotPlayer, pickups: list[Pickup], *, kind: str) -> Pickup | None:
        candidates = [pickup for pickup in pickups if pickup.kind == kind]
        if not candidates:
            return None
        return min(candidates, key=lambda pickup: bot.position.distance_to(pickup.position))
