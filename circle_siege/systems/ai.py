from __future__ import annotations

import random
from dataclasses import dataclass
from typing import TYPE_CHECKING

from ..core.config import MAX_MEDKITS
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
            gear_target = self._select_gear_target(bot, pickups)
            if gear_target is not None:
                move_vector = safe_normalize(gear_target.position - bot.position)
                if move_vector.length_squared() > 0.0:
                    bot.aim_direction = move_vector
                return AIDecision([], move_vector, "武装", gear_target.label, gear_target.position.copy())
        visible_target = self._acquire_target(bot, characters, game_map)
        if visible_target:
            bot.memory_target = visible_target.position.copy()
            bot.memory_timer = 2.8
        else:
            bot.memory_timer = max(0.0, bot.memory_timer - dt)

        if (
            bot.hp <= 40
            and bot.medkits > 0
            and bot.heal_timer <= 0.0
            and (not visible_target or bot.position.distance_to(visible_target.position) > 340)
        ):
            bot.try_begin_heal()
        if bot.heal_timer > 0.0:
            return AIDecision([], Vector2(), "治疗", "", bot.position.copy())

        move_vector = Vector2()
        if safe_zone.is_outside(bot.position):
            move_vector += safe_normalize(safe_zone.current_center - bot.position) * 1.1

        if visible_target:
            cover_point = self._select_cover_point(bot, game_map, visible_target.position)
            projectiles, combat_vector, state, focus = self._engage_target(bot, visible_target, game_map, rng, dt, cover_point)
            move_vector += combat_vector
            target_name = visible_target.name if state == "交战" else "掩体点"
            return AIDecision(projectiles, move_vector, state, target_name, focus)

        loot_target = self._select_loot_target(bot, pickups)
        if bot.memory_timer > 0.0 and bot.memory_target is not None:
            move_vector += safe_normalize(bot.memory_target - bot.position) * 0.8
            return AIDecision([], move_vector, "追击", "最后枪声", bot.memory_target.copy())
        if loot_target is not None:
            move_vector += safe_normalize(loot_target.position - bot.position)
            aim = safe_normalize(loot_target.position - bot.position)
            if aim.length_squared() > 0:
                bot.aim_direction = aim
            return AIDecision([], move_vector, "搜刮", loot_target.label, loot_target.position.copy())

        if bot.position.distance_to(bot.wander_target) < 60:
            bot.wander_target = safe_zone.random_patrol_point(rng, game_map)
        move_vector += safe_normalize(bot.wander_target - bot.position) * 0.72
        aim = safe_normalize(bot.wander_target - bot.position)
        if aim.length_squared() > 0:
            bot.aim_direction = aim
        if safe_zone.is_outside(bot.position):
            return AIDecision([], move_vector, "进圈", "安全区", safe_zone.current_center.copy())
        return AIDecision([], move_vector, "巡逻", "路径点", bot.wander_target.copy())

    def _acquire_target(self, bot: BotPlayer, characters: list[CharacterBase], game_map: Map) -> CharacterBase | None:
        if not bot.combat_enabled:
            return None
        best_target = None
        best_score = float("inf")
        for candidate in characters:
            if candidate is bot or not candidate.alive:
                continue
            if candidate.camp == bot.camp:
                continue
            if candidate.is_player_controlled and not (bot.alerted or bot.searching):
                continue
            distance = bot.position.distance_to(candidate.position)
            if distance > bot.active_weapon.spec.range_limit * 1.18:
                continue
            if not game_map.has_line_of_sight(bot.position, candidate.position):
                continue
            score = distance - candidate.hp * 0.2
            if candidate.is_player_controlled:
                score += 90
            if score < best_score:
                best_score = score
                best_target = candidate
        return best_target

    def _engage_target(
        self,
        bot: BotPlayer,
        target: CharacterBase,
        game_map: Map,
        rng: random.Random,
        dt: float,
        cover_point: Vector2 | None,
    ) -> tuple[list, Vector2, str, Vector2]:
        move_vector = Vector2()
        to_target = target.position - bot.position
        distance = max(1.0, to_target.length())
        direction = to_target / distance
        bot.aim_direction = direction

        if cover_point is not None and (bot.hp <= 50 or bot.active_weapon.is_reloading):
            move_vector += safe_normalize(cover_point - bot.position)
            state = "掩护"
            focus = cover_point.copy()
        else:
            bot.strafe_timer -= dt
            if bot.strafe_timer <= 0.0:
                bot.strafe_timer = rng.uniform(0.8, 1.45)
                bot.strafe_sign = rng.choice((-1, 1))
            perpendicular = Vector2(-direction.y, direction.x) * bot.strafe_sign
            preferred = bot.active_weapon.spec.desired_distance * bot.aggression
            if distance > preferred + 120:
                move_vector += direction * 0.62
            elif distance < preferred - 80:
                move_vector -= direction * 0.88
            move_vector += perpendicular * 0.45
            state = "交战"
            focus = target.position.copy()

        line_clear = game_map.has_line_of_sight(bot.position, target.position)
        if bot.active_weapon.magazine <= 0:
            bot.active_weapon.begin_reload(bot)
        should_fire = (
            line_clear
            and distance <= bot.active_weapon.spec.range_limit
            and bot.active_weapon.cooldown <= 0.0
            and not bot.active_weapon.is_reloading
        )
        if should_fire:
            jitter = Vector2(rng.uniform(-6, 6), rng.uniform(-6, 6)) * (2.2 - bot.accuracy)
            aim = safe_normalize(target.position + jitter - bot.position)
            projectiles = bot.active_weapon.fire(bot, aim, bot.movement_ratio(), rng)
        else:
            projectiles = []
        return projectiles, move_vector, state, focus

    def _select_gear_target(self, bot: BotPlayer, pickups: list[Pickup]) -> Pickup | None:
        best_pickup = None
        best_distance = float("inf")
        for pickup in pickups:
            if pickup.kind != "gear":
                continue
            distance = bot.position.distance_to(pickup.position)
            if distance < best_distance:
                best_distance = distance
                best_pickup = pickup
        return best_pickup

    def _select_loot_target(self, bot: BotPlayer, pickups: list[Pickup]) -> Pickup | None:
        best_pickup = None
        best_score = -9999.0
        for pickup in pickups:
            distance = bot.position.distance_to(pickup.position)
            if distance > 260:
                continue
            score = -distance
            if pickup.kind == "medkit" and bot.hp < 70 and bot.medkits < MAX_MEDKITS:
                score += 120
            if pickup.kind == "ammo" and pickup.ammo_type == bot.active_weapon.spec.ammo_type:
                score += 110
            if pickup.kind == "weapon" and pickup.weapon_spec:
                score += pickup.weapon_spec.score - bot.active_weapon.spec.score
            if score > best_score:
                best_score = score
                best_pickup = pickup
        return best_pickup

    def _select_cover_point(self, bot: BotPlayer, game_map: Map, threat_position: Vector2) -> Vector2 | None:
        best_cover = None
        best_score = float("inf")
        for point in game_map.cover_points[:180]:
            if point.distance_to(bot.position) > 260:
                continue
            if point.distance_to(threat_position) < 90:
                continue
            score = point.distance_to(bot.position) + max(0, 180 - point.distance_to(threat_position))
            if score < best_score:
                best_score = score
                best_cover = point
        return best_cover.copy() if best_cover is not None else None
