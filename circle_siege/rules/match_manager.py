from __future__ import annotations

import math
import random
from dataclasses import dataclass
from pathlib import Path

import pygame

from ..core.config import (
    BOT_NAMES,
    DEFAULT_MATCH_CONFIG,
    DEFAULT_THEME_ID,
    GRENADE_COLOR,
    GRENADE_FUSE_TIME,
    GRENADE_THROW_SPEED,
    MAX_MEDKITS,
    RESOURCE_ROOT,
    SPAWN_MIN_SEPARATION,
    STARTUP_GEAR_OFFSET_MAX,
    STARTUP_GEAR_OFFSET_MIN,
    THEME_BY_ID,
    UI_ACCENT,
    WEAPON_LIBRARY,
    ZONE_INITIAL_HOLD_BONUS,
    ZONE_INITIAL_MARGIN,
    ZONE_INITIAL_SHRINK_BONUS,
    ZONE_BLUE,
    ZONE_DANGER,
    ZONE_PHASES,
)
from ..core.events import (
    post_camera_shake,
    post_capture_point,
    post_killfeed,
    post_match_end,
    post_player_enter_trigger,
    post_respawn_player,
)
from ..entities.animation_controller import AnimationController
from ..entities.bot_player import BotPlayer
from ..entities.item import Pickup
from ..entities.map import Map
from ..entities.player import Player
from ..entities.projectile import Grenade
from ..helpers import Vector2, lerp, lerp_vec
from ..systems.collision import CollisionManager
from ..systems.particles import ParticleSystem
from .progression import get_next_theme_id


@dataclass
class Banner:
    text: str
    color: tuple[int, int, int]
    ttl: float = 3.6

    def update(self, dt: float) -> bool:
        self.ttl -= dt
        return self.ttl > 0


LOCAL_ALERT_SHOT_RADIUS = 360.0
LOCAL_ALERT_GRENADE_RADIUS = 440.0
LOCAL_ALERT_DIRECT_RATIO = 0.58
LOCAL_ALERT_SEARCH_RATIO = 0.84
TREASURE_START_CLEARANCE_MIN = 380.0
TREASURE_START_CLEARANCE_MAX = 760.0
TREASURE_POINT_SPREAD = 320.0
TREASURE_POINT_FALLBACK_SPREAD = 190.0


class SafeZone:
    def __init__(self, rng: random.Random, world_size: tuple[int, int]) -> None:
        self.rng = rng
        self.world_width = world_size[0]
        self.world_height = world_size[1]
        self.initial_center = Vector2(self.world_width / 2, self.world_height / 2)
        self.initial_radius = (math.hypot(self.world_width, self.world_height) / 2.0) + ZONE_INITIAL_MARGIN
        self.current_center = self.initial_center.copy()
        self.current_radius = self.initial_radius
        self.start_center = self.current_center.copy()
        self.start_radius = self.current_radius
        self.target_center = self.current_center.copy()
        self.target_radius = self.current_radius
        self.phase_index = 0
        self.state = "hold"
        self.state_timer = ZONE_PHASES[0].hold_time + ZONE_INITIAL_HOLD_BONUS
        self.current_dps = max(2.0, ZONE_PHASES[0].dps - 1.5)

    def update(self, dt: float, game_map: Map) -> list[tuple[str, int]]:
        events: list[tuple[str, int]] = []
        if self.state == "final":
            return events

        phase = ZONE_PHASES[min(self.phase_index, len(ZONE_PHASES) - 1)]
        if self.state == "hold":
            self.state_timer -= dt
            if self.state_timer <= 0:
                self.state = "shrink"
                self.state_timer = phase.shrink_time + ZONE_INITIAL_SHRINK_BONUS
                self.start_center = self.current_center.copy()
                self.start_radius = self.current_radius
                self.target_radius = self.initial_radius * phase.radius_scale
                self.target_center = self._pick_next_center(self.target_radius)
                events.append(("shrink_start", self.phase_index + 1))
        elif self.state == "shrink":
            self.state_timer = max(0.0, self.state_timer - dt)
            progress = 1.0 - (self.state_timer / (phase.shrink_time + ZONE_INITIAL_SHRINK_BONUS))
            self.current_center = lerp_vec(self.start_center, self.target_center, progress)
            self.current_radius = lerp(self.start_radius, self.target_radius, progress)
            if self.state_timer <= 0:
                self.current_center = self.target_center.copy()
                self.current_radius = self.target_radius
                self.phase_index += 1
                if self.phase_index >= len(ZONE_PHASES):
                    self.state = "final"
                    self.current_dps = ZONE_PHASES[-1].dps + 4.0
                    events.append(("final", self.phase_index))
                else:
                    self.state = "hold"
                    self.state_timer = ZONE_PHASES[self.phase_index].hold_time + 4.0
                    self.current_dps = max(3.0, ZONE_PHASES[self.phase_index].dps - 1.0)
                    events.append(("phase_locked", self.phase_index))
        return events

    def _pick_next_center(self, next_radius: float) -> Vector2:
        max_offset = max(80.0, self.current_radius - next_radius - 70.0)
        angle = self.rng.uniform(0.0, math.tau)
        offset = Vector2(math.cos(angle), math.sin(angle)) * self.rng.uniform(max_offset * 0.18, max_offset * 0.72)
        candidate = self.current_center + offset
        min_x = next_radius + 40
        max_x = self.world_width - next_radius - 40
        min_y = next_radius + 40
        max_y = self.world_height - next_radius - 40
        candidate.x = self.world_width / 2 if min_x > max_x else max(min_x, min(max_x, candidate.x))
        candidate.y = self.world_height / 2 if min_y > max_y else max(min_y, min(max_y, candidate.y))
        if candidate.distance_to(self.current_center) > self.current_radius - next_radius:
            direction = (candidate - self.current_center).normalize()
            candidate = self.current_center + direction * (self.current_radius - next_radius - 8)
        return candidate

    def is_outside(self, position: Vector2) -> bool:
        return position.distance_to(self.current_center) > self.current_radius

    def time_to_next(self) -> float:
        return max(0.0, self.state_timer)

    def random_patrol_point(self, rng: random.Random, game_map: Map) -> Vector2:
        if game_map.walkable_points:
            candidates = [point.copy() for point in game_map.walkable_points if not self.is_outside(point)]
            if candidates:
                return rng.choice(candidates)
            fallback = game_map.find_nearest_walkable_point(
                self.current_center,
                clearance=30.0,
                search_limit=max(self.world_width, self.world_height) * 0.35,
            )
            if fallback is not None:
                return fallback
        for _ in range(60):
            angle = rng.uniform(0.0, math.tau)
            radius = rng.uniform(0.12, 0.92) * self.current_radius
            candidate = self.current_center + Vector2(math.cos(angle), math.sin(angle)) * radius
            if not game_map.bounds.collidepoint(candidate):
                continue
            if not game_map.is_walkable_point(candidate, clearance=30.0):
                continue
            return candidate
        return game_map.find_nearest_walkable_point(self.current_center, clearance=30.0, search_limit=220.0) or self.current_center.copy()

    def force_advance(self) -> None:
        if self.state != "final":
            self.state_timer = min(self.state_timer, 0.01)


class MatchManager:
    def __init__(self, game, theme_id: str) -> None:
        self.game = game
        self.config = DEFAULT_MATCH_CONFIG
        self.rng = random.Random()
        self.theme_id = theme_id or DEFAULT_THEME_ID
        self.theme = THEME_BY_ID[self.theme_id]
        self.game_map = Map(self.rng, self.theme_id)
        self.safe_zone = SafeZone(self.rng, (self.game_map.bounds.width, self.game_map.bounds.height))
        self.particles = ParticleSystem()
        self.collision_manager = CollisionManager()

        self.render_group = pygame.sprite.LayeredUpdates()
        self.character_group = pygame.sprite.Group()
        self.projectile_group = pygame.sprite.Group()
        self.pickup_group = pygame.sprite.Group()

        self.projectiles = []
        self.grenades: list[Grenade] = []
        self.pickups: list[Pickup] = []
        self.killfeed: list[Banner] = []
        self.announcements: list[Banner] = []

        self.elapsed = 0.0
        self.countdown = 2.5
        self.controls_visible = True
        self.controls_hint_timer = 11.0
        self.zone_tick = 0.0
        self.match_end_posted = False
        self.entered_triggers: set[str] = set()
        self.trigger_timers: dict[str, float] = {}
        self.gate_restore_timers: dict[str, float] = {}
        self.capture_progress: dict[str, float] = {}
        self.active_capture_label = ""
        self.active_capture_progress = 0.0
        self.respawn_charges = 0
        self.pending_respawn_timer: float | None = None
        self.pending_respawn_anchor: Vector2 | None = None
        self.player_has_agro = False
        self.peak_alerted_bots = 0
        self.peak_local_alert_bots = 0
        self.last_local_alert_count = 0
        self.treasure_map_target = 3
        self.treasure_maps_found = 0
        self.treasure_sites: list[Vector2] = []
        self.contested_treasure_sites: set[str] = set()
        self.player_energy_gained = 0
        self.treasure_guard_bosses: list[BotPlayer] = []
        self._music_state = "battle"
        self.spawn_positions = self._build_spawn_positions(self.config.player_count)

        self.player = self._spawn_player()
        self.bots = self._spawn_bots()
        self.elite_bots = [bot for bot in self.bots if bot.is_elite]
        self.characters = [self.player, *self.bots]
        self._spawn_startup_gear()
        self._spawn_loot()
        self._assign_guard_roles()
        self.announcements.append(Banner("Find weapons, then collect 3 treasure maps to complete the mission.", (255, 220, 148), ttl=4.2))
        self.announcements.append(Banner(f"Deployed to {self.theme.identifier}. Only attacked enemies engage; treasure maps have boss guards.", self.theme.accent))
        if self.elite_bots:
            self.announcements.insert(2, Banner("Elite guards detected near high-value areas.", (255, 146, 146), ttl=4.2))
        self.announcements = self.announcements[: 3 if self.elite_bots else 2]

    def _theme_weapon_pool(self) -> tuple[str, ...]:
        if self.theme_id == "temple_tmx":
            return ("carbine", "dmr", "carbine", "dmr", "smg")
        if self.theme_id == "courtyard_tmx":
            return ("smg", "shotgun", "smg", "shotgun", "carbine")
        return ("smg", "carbine", "smg", "carbine", "shotgun")

    def _elite_bot_count_for_theme(self) -> int:
        return 2

    def _play_audio_event(self, event_name: str, fallback: str | None = None, volume_scale: float = 1.0) -> None:
        audio = self.game.audio
        if hasattr(audio, "play_event"):
            audio.play_event(event_name, volume_scale=volume_scale)
            return
        if fallback is not None:
            audio.play_sfx(fallback, volume=volume_scale)

    def _play_weapon_fire_audio(self, shooter, projectile_count: int) -> None:
        if projectile_count <= 0:
            return
        weapon_id = getattr(getattr(shooter, "active_weapon", None), "spec", None)
        identifier = getattr(weapon_id, "identifier", "")
        event_name = f"weapon_fire_{identifier}" if identifier else "weapon_fire"
        self._play_audio_event(event_name, "weapon_fire", 0.92 if shooter is self.player else 0.62)

    def _play_hit_audio(self, victim) -> None:
        if victim is None:
            self._play_audio_event("bullet_impact", "mechanism", 0.68)
            return
        if victim is self.player:
            self._play_audio_event("player_hurt", "danger")
        elif getattr(victim, "is_treasure_boss", False) or getattr(victim, "is_elite", False):
            self._play_audio_event("boss_hurt", "body_hit")
        else:
            self._play_audio_event("enemy_hurt", "body_hit")

    def _play_defeat_audio(self, victim) -> None:
        if victim is self.player:
            self._play_audio_event("player_down", "danger")
        elif getattr(victim, "is_treasure_boss", False) or getattr(victim, "is_elite", False):
            self._play_audio_event("boss_defeated", "killfeed")
        else:
            self._play_audio_event("enemy_down", "killfeed")

    def _update_dynamic_music(self) -> None:
        if self.alive_treasure_guard_boss_count() > 0 and any(bot.alive and bot.alerted for bot in self.treasure_guard_bosses):
            next_state = "boss"
        elif self.alerted_bot_count() > 0 or self.searching_bot_count() > 0:
            next_state = "combat"
        else:
            next_state = "battle"
        if next_state != self._music_state:
            self._music_state = next_state
            self.game.audio.play_music(next_state, fade_ms=800)

    def alerted_bot_count(self) -> int:
        return sum(1 for bot in self.bots if bot.alive and bot.alerted)

    def searching_bot_count(self) -> int:
        return sum(1 for bot in self.bots if bot.alive and bot.searching and not bot.alerted)

    def local_alert_status_text(self) -> str:
        alerted = self.alerted_bot_count()
        searching = self.searching_bot_count()
        if alerted > 0 and searching > 0:
            return f"Local alert: {alerted} chasing, {searching} searching"
        if alerted > 0:
            return f"Local alert: {alerted} enemies chasing"
        if searching > 0:
            return f"Local alert: {searching} enemies searching"
        return "Local alert: idle"

    def mission_guidance_text(self) -> str:
        if not self.player.combat_enabled:
            return "Step: pick up a weapon first."
        if self.config.mode == "\u5bfb\u5b9d\u6a21\u5f0f":
            remaining = max(0, self.treasure_map_target - self.treasure_maps_found)
            bosses_remaining = self.alive_treasure_guard_boss_count()
            if bosses_remaining > 0:
                return f"Step: defeat {bosses_remaining} treasure guards before collecting maps."
            if remaining == 0:
                return "Step: mission complete, survive until extraction."
            if self.player_has_agro:
                return f"Step: stabilize the fight, then collect {remaining} more maps."
            return f"Step: collect {remaining} more treasure maps."
        if self.config.mode == "\u751f\u5b58\u6a21\u5f0f":
            if self.player_has_agro:
                return "Step: break line of sight, then reposition."
            return "Step: control noise and clear nearby enemies."
        remaining = max(0, self.config.kill_target - self.player.kills)
        if self.player_has_agro:
            return f"Step: finish {remaining} more eliminations under alert."
        return f"Step: find targets and finish {remaining} eliminations."

    def mission_objective_text(self) -> str:
        if self.config.mode == "\u5bfb\u5b9d\u6a21\u5f0f":
            return f"Objective: defeat 2 treasure guards, then collect {self.treasure_map_target} maps"
        if self.config.mode == "\u751f\u5b58\u6a21\u5f0f":
            return "Objective: be the last survivor"
        return f"Objective: score {self.config.kill_target} eliminations"

    def mission_progress_text(self) -> str:
        if self.config.mode == "\u5bfb\u5b9d\u6a21\u5f0f":
            bosses_down = 2 - self.alive_treasure_guard_boss_count()
            return f"Treasure guards: {bosses_down}/2    Maps: {self.treasure_maps_found}/{self.treasure_map_target}"
        if self.config.mode == "\u751f\u5b58\u6a21\u5f0f":
            return f"Progress: {self.alive_count()} combatants alive"
        remaining = max(0, self.config.kill_target - self.player.kills)
        return f"Progress: {self.player.kills}/{self.config.kill_target}, {remaining} remaining"

    def _finish_reason(self, victory: bool, finish_type: str | None = None) -> str:
        if finish_type == "last_survivor":
            return "Battlefield cleared. Teleporting to the next map."
        if finish_type == "treasure_complete":
            return "All treasure maps collected. Teleporting to the next map."
        if finish_type == "kill_target":
            return "Elimination target reached. Teleporting to the next map."
        if finish_type == "death":
            return "Player eliminated before extraction."
        if finish_type == "timeout":
            return "Time expired before extraction."
        if self.config.mode == "\u5bfb\u5b9d\u6a21\u5f0f":
            if victory:
                return "All treasure maps collected. Mission complete."
            if not self.player.alive:
                return "Player eliminated before completing the treasure mission."
            if self.elapsed >= self.config.match_time_limit:
                return f"Time expired with {self.treasure_maps_found}/{self.treasure_map_target} maps."
            return f"Mission incomplete: {self.treasure_maps_found}/{self.treasure_map_target} maps."
        if self.config.mode == "\u751f\u5b58\u6a21\u5f0f":
            if victory:
                return "You are the last survivor."
            if not self.player.alive:
                return "You were eliminated before the final circle."
            return "Time expired before the battlefield was cleared."
        if victory:
            return "Elimination target reached."
        if not self.player.alive:
            return "Player eliminated before reaching the kill target."
        return f"Time expired at {self.player.kills}/{self.config.kill_target} eliminations."

    def _refresh_alert_state(self) -> int:
        alerted = self.alerted_bot_count()
        searching = self.searching_bot_count()
        local_alert_total = alerted + searching
        self.player_has_agro = local_alert_total > 0
        self.peak_alerted_bots = max(self.peak_alerted_bots, alerted)
        self.peak_local_alert_bots = max(self.peak_local_alert_bots, local_alert_total)
        if self.last_local_alert_count > 0 and local_alert_total == 0:
            self.announcements.append(Banner("Nearby enemies lost the target.", (170, 236, 255), ttl=1.8))
        self.last_local_alert_count = local_alert_total
        return alerted

    def _register_sprite(self, sprite: pygame.sprite.Sprite, group: pygame.sprite.Group | None = None) -> None:
        self.render_group.add(sprite, layer=getattr(sprite, "_layer", 0))
        if hasattr(sprite, "sync_visual"):
            class _InitCamera:
                position = Vector2()

                @staticmethod
                def world_to_screen(position: Vector2) -> tuple[int, int]:
                    return int(position.x), int(position.y)

                @staticmethod
                def project_vertical_distance(distance: float) -> int:
                    return int(distance)

                @staticmethod
                def world_rect_to_screen_bounds(rect: pygame.Rect) -> pygame.Rect:
                    return rect.copy()

            sprite.sync_visual(_InitCamera())
        if group is not None:
            group.add(sprite)

    def _load_character_animation_bundle(
        self,
        prefix: str,
    ) -> tuple[dict[str, pygame.Surface], dict[str, tuple[str, ...]]] | None:
        sheet_dir = RESOURCE_ROOT / "img" / "characters" / "sheets"
        paths: dict[str, Path | None] = {}
        row_orders: dict[str, tuple[str, ...]] = {}
        for state in ("idle", "move", "fire", "dead"):
            preferred = sheet_dir / f"{prefix}_{state}_sheet_v2.png"
            fallback = sheet_dir / f"{prefix}_{state}_sheet.png"
            if preferred.exists():
                paths[state] = preferred
                row_orders[state] = AnimationController.SHEET_DIRECTION_ORDER
            elif fallback.exists():
                paths[state] = fallback
                row_orders[state] = AnimationController.DIRECTION_ORDER
            else:
                paths[state] = None
        if not all(path is not None for path in paths.values()):
            return None
        surfaces = {state: self.game.resources.load_alpha_image(str(path)) for state, path in paths.items() if path is not None}
        return surfaces, row_orders

    def _build_spawn_positions(self, count: int) -> list[Vector2]:
        dynamic_spacing = min(SPAWN_MIN_SEPARATION, min(self.game_map.bounds.width, self.game_map.bounds.height) * 0.24)
        selected: list[Vector2] = []

        player_candidates = [
            self._sanitize_spawn_point(point.copy())
            for point in getattr(self.game_map, "player_spawn_points", [])
        ]
        enemy_candidates = [
            self._sanitize_spawn_point(point.copy())
            for point in getattr(self.game_map, "enemy_spawn_points", [])
        ]

        if not player_candidates:
            player_candidates = [self.game_map.random_safe_point(self.rng, margin=120)]
        if not enemy_candidates:
            enemy_candidates = [
                self._sanitize_spawn_point(point.copy())
                for point in getattr(self.game_map, "spawn_points", [])
            ]

        world_center = Vector2(self.game_map.bounds.center)
        player_spawn = min(player_candidates, key=lambda point: point.distance_to(world_center))
        selected.append(player_spawn.copy())

        enemy_candidates.sort(key=lambda point: point.distance_to(player_spawn), reverse=True)
        for candidate in enemy_candidates:
            if len(selected) >= count:
                break
            if all(candidate.distance_to(existing) >= dynamic_spacing * 0.55 for existing in selected):
                selected.append(candidate.copy())
                continue
            adjusted = self._sanitize_spawn_point(candidate.copy())
            if all(adjusted.distance_to(existing) >= dynamic_spacing * 0.55 for existing in selected):
                selected.append(adjusted)

        while len(selected) < count:
            point = self.game_map.random_safe_point(self.rng, margin=120)
            if all(point.distance_to(existing) >= dynamic_spacing * 0.72 for existing in selected):
                selected.append(point)
                continue
            fallback_distance = min(point.distance_to(existing) for existing in selected)
            if fallback_distance >= dynamic_spacing * 0.45 or len(selected) >= count - 1:
                selected.append(point)
        return selected

    def _sanitize_spawn_point(self, point: Vector2) -> Vector2:
        if self.game_map.is_walkable_point(point, clearance=self.player_profile_radius()):
            return point
        best_candidate: Vector2 | None = None
        best_distance = float("inf")
        angles = [index * (math.tau / 24.0) for index in range(24)]
        for radius in (24.0, 48.0, 72.0, 96.0, 120.0, 156.0, 192.0, 228.0):
            for angle in angles:
                candidate = point + Vector2(math.cos(angle), math.sin(angle)) * radius
                if not self.game_map.bounds.collidepoint(candidate):
                    continue
                if not self.game_map.is_walkable_point(candidate, clearance=self.player_profile_radius()):
                    continue
                distance = point.distance_to(candidate)
                if distance < best_distance:
                    best_distance = distance
                    best_candidate = candidate
            if best_candidate is not None:
                return best_candidate
        return self.game_map.random_safe_point(self.rng, margin=120)

    @staticmethod
    def player_profile_radius() -> float:
        return 26.0

    def _resolve_walkable_position(
        self,
        desired: Vector2,
        *,
        clearance: float = 30.0,
        occupied: list[Vector2] | None = None,
        min_distance: float = 0.0,
        search_limit: float = 220.0,
    ) -> Vector2:
        if occupied is None:
            occupied = []
        candidate = self.game_map.find_nearest_walkable_point(desired, clearance=clearance, search_limit=search_limit)
        if candidate is not None and all(candidate.distance_to(other) >= min_distance for other in occupied):
            return candidate

        angles = [index * (math.tau / 16.0) for index in range(16)]
        for radius in (28.0, 52.0, 84.0, 120.0, 168.0, search_limit):
            for angle in angles:
                shifted = desired + Vector2(math.cos(angle), math.sin(angle)) * radius
                candidate = self.game_map.find_nearest_walkable_point(shifted, clearance=clearance, search_limit=96.0)
                if candidate is None:
                    continue
                if any(candidate.distance_to(other) < min_distance for other in occupied):
                    continue
                return candidate

        fallback_candidates = [
            point.copy()
            for point in self.game_map.walkable_points
            if all(point.distance_to(other) >= min_distance for other in occupied)
        ]
        if fallback_candidates:
            return min(fallback_candidates, key=lambda point: point.distance_to(desired))
        return self.game_map.random_safe_point(self.rng, margin=max(72, int(clearance + 28)))

    def _build_startup_gear_position(self, spawn: Vector2, occupied: list[Vector2]) -> Vector2:
        angles = [index * (math.tau / 12.0) for index in range(12)]
        self.rng.shuffle(angles)
        for angle in angles:
            for radius in (
                STARTUP_GEAR_OFFSET_MIN,
                (STARTUP_GEAR_OFFSET_MIN + STARTUP_GEAR_OFFSET_MAX) / 2.0,
                STARTUP_GEAR_OFFSET_MAX,
            ):
                candidate = spawn + Vector2(math.cos(angle), math.sin(angle)) * radius
                if not self.game_map.bounds.collidepoint(candidate):
                    continue
                if not self.game_map.is_walkable_point(candidate, clearance=28.0):
                    continue
                if any(candidate.distance_to(other) < 72.0 for other in occupied):
                    continue
                return candidate
        return self.game_map.random_safe_point(self.rng, margin=120)

    def _spawn_startup_gear(self) -> None:
        occupied: list[Vector2] = []
        starter_pool = ("smg", "carbine", "shotgun")
        for spawn in self.spawn_positions:
            starter_position = self._build_startup_gear_position(spawn, occupied)
            occupied.append(starter_position)
            starter_weapon = WEAPON_LIBRARY[self.rng.choice(starter_pool)]
            self._add_pickup(Pickup(kind="weapon", position=starter_position, weapon_spec=starter_weapon))

    def _spawn_player(self) -> Player:
        spawn = self.spawn_positions[0].copy()
        resolved_spawn = self.game_map.find_nearest_walkable_point(
            spawn,
            clearance=self.player_profile_radius(),
            search_limit=self.game_map.cell_size * 8,
        )
        if resolved_spawn is not None:
            spawn = resolved_spawn
        player = Player(spawn, self.game.player_profile)
        hero_anim_bundle = self._load_character_animation_bundle("hero")
        hero_dir8_path = RESOURCE_ROOT / "img" / "characters" / "hero_dir8_sheet.png"
        hero_sprite_path = RESOURCE_ROOT / "img" / "characters" / "hero_sprite96_v2.png"
        shield_effect_path = RESOURCE_ROOT / "img" / "characters" / "shield_ring_cyber_v2.png"
        ground_effect_path = RESOURCE_ROOT / "img" / "characters" / "ground_contact_cyber_v2.png"
        if hero_anim_bundle is not None:
            hero_surfaces, hero_row_orders = hero_anim_bundle
            player.set_animation_sheets(
                idle_sheet=hero_surfaces["idle"],
                move_sheet=hero_surfaces["move"],
                fire_sheet=hero_surfaces["fire"],
                dead_sheet=hero_surfaces["dead"],
                sheet_direction_orders=hero_row_orders,
                scale=1.0,
                default_angle=45.0,
            )
            player.accent_color = (112, 222, 255)
            player.marker_color = (218, 246, 255)
        elif hero_dir8_path.exists():
            player.set_directional_sprite_sheet(self.game.resources.load_alpha_image(str(hero_dir8_path)), scale=1.0, default_angle=45.0)
            player.accent_color = (112, 222, 255)
            player.marker_color = (218, 246, 255)
        elif hero_sprite_path.exists():
            player.set_sprite_asset(self.game.resources.load_alpha_image(str(hero_sprite_path)), scale=0.92, default_angle=45.0)
            player.accent_color = (112, 222, 255)
            player.marker_color = (218, 246, 255)
        if shield_effect_path.exists() or ground_effect_path.exists():
            player.set_effect_assets(
                ground_surface=self.game.resources.load_alpha_image(str(ground_effect_path)) if ground_effect_path.exists() else None,
                ground_scale=0.76,
                shield_surface=self.game.resources.load_alpha_image(str(shield_effect_path)) if shield_effect_path.exists() else None,
                shield_scale=0.84,
            )
        player.equip_weapon(WEAPON_LIBRARY["unarmed"])
        player.active_weapon_index = 0
        player.combat_enabled = False
        player.medkits = 1
        self._register_sprite(player, self.character_group)
        return player

    def _spawn_bots(self) -> list[BotPlayer]:
        total_bot_count = self.config.player_count - 1
        elite_count = min(self._elite_bot_count_for_theme(), total_bot_count)

        names = list(BOT_NAMES)
        self.rng.shuffle(names)
        while len(names) < total_bot_count:
            names.extend(BOT_NAMES)

        normal_pool = self._theme_weapon_pool()
        elite_pool = ("dmr", "carbine")
        elite_start = total_bot_count - elite_count
        bots: list[BotPlayer] = []
        standard_anim_bundle = self._load_character_animation_bundle("bot")
        elite_anim_bundle = self._load_character_animation_bundle("elite")
        standard_dir8_path = RESOURCE_ROOT / "img" / "characters" / "bot_dir8_sheet.png"
        elite_dir8_path = RESOURCE_ROOT / "img" / "characters" / "elite_dir8_sheet.png"
        standard_sprite_path = RESOURCE_ROOT / "img" / "characters" / "bot_sprite96_v2.png"
        elite_sprite_path = RESOURCE_ROOT / "img" / "characters" / "elite_sprite96_v2.png"
        shield_effect_path = RESOURCE_ROOT / "img" / "characters" / "shield_ring_cyber_v2.png"
        ground_effect_path = RESOURCE_ROOT / "img" / "characters" / "ground_contact_cyber_v2.png"

        for index in range(total_bot_count):
            is_elite = index >= elite_start
            role = "elite" if is_elite else "standard"
            spawn = self.spawn_positions[index + 1]
            spec = WEAPON_LIBRARY[self.rng.choice(elite_pool if is_elite else normal_pool)]
            name = f"Elite Guard {names[index]}" if is_elite else names[index]
            bot = BotPlayer(name, spawn.copy(), spec, self.rng, role=role)
            anim_bundle = elite_anim_bundle if is_elite else standard_anim_bundle
            dir8_path = elite_dir8_path if is_elite else standard_dir8_path
            sprite_path = elite_sprite_path if is_elite else standard_sprite_path
            if anim_bundle is not None:
                anim_surfaces, anim_row_orders = anim_bundle
                bot.set_animation_sheets(
                    idle_sheet=anim_surfaces["idle"],
                    move_sheet=anim_surfaces["move"],
                    fire_sheet=anim_surfaces["fire"],
                    dead_sheet=anim_surfaces["dead"],
                    sheet_direction_orders=anim_row_orders,
                    scale=1.0,
                    default_angle=45.0,
                )
            elif dir8_path.exists():
                bot.set_directional_sprite_sheet(self.game.resources.load_alpha_image(str(dir8_path)), scale=1.0, default_angle=45.0)
            elif sprite_path.exists():
                scale = 0.98 if is_elite else 0.94
                bot.set_sprite_asset(self.game.resources.load_alpha_image(str(sprite_path)), scale=scale, default_angle=45.0)
            if shield_effect_path.exists() or ground_effect_path.exists():
                bot.set_effect_assets(
                    ground_surface=self.game.resources.load_alpha_image(str(ground_effect_path)) if ground_effect_path.exists() else None,
                    ground_scale=0.68 if is_elite else 0.62,
                    shield_surface=self.game.resources.load_alpha_image(str(shield_effect_path)) if shield_effect_path.exists() else None,
                    shield_scale=0.82 if is_elite else 0.76,
                )
            bot.combat_enabled = True
            self._register_sprite(bot, self.character_group)
            bots.append(bot)
        return bots

    def _add_pickup(
        self,
        pickup: Pickup,
        *,
        occupied: list[Vector2] | None = None,
        min_distance: float = 0.0,
        clearance: float = 28.0,
    ) -> None:
        pickup.position = self._resolve_walkable_position(
            pickup.position,
            clearance=clearance,
            occupied=occupied,
            min_distance=min_distance,
        )
        if occupied is not None:
            occupied.append(pickup.position.copy())
        self.pickups.append(pickup)
        self._register_sprite(pickup, self.pickup_group)

    def _spawn_loot(self) -> None:
        weapon_keys = self._theme_weapon_pool()
        points = self.game_map.loot_points[:]
        self.rng.shuffle(points)
        treasure_points = self._select_treasure_map_positions(points)
        self.treasure_sites = [point.copy() for point in treasure_points]
        occupied: list[Vector2] = []
        for point in treasure_points:
            self._add_pickup(
                Pickup(kind="treasure_map", position=point.copy()),
                occupied=occupied,
                min_distance=72.0,
                clearance=30.0,
            )

        remaining_points = [point for point in points if all(point.distance_to(treasure) > 1.0 for treasure in treasure_points)]
        for index, point in enumerate(remaining_points[: max(30, min(48, len(remaining_points)))]):
            roll = self.rng.random()
            if index < 8 or roll < 0.28:
                spec = WEAPON_LIBRARY[self.rng.choice(weapon_keys)]
                pickup = Pickup(kind="weapon", position=point.copy(), weapon_spec=spec)
            elif roll < 0.7:
                ammo_type = self.rng.choice(("5.56", "9mm", "12g", "7.62"))
                amount = {"5.56": 40, "9mm": 52, "12g": 14, "7.62": 28}[ammo_type]
                pickup = Pickup(kind="ammo", position=point.copy(), ammo_type=ammo_type, amount=amount)
            else:
                pickup = Pickup(kind="medkit", position=point.copy(), amount=1)
            self._add_pickup(pickup, occupied=occupied, min_distance=56.0, clearance=28.0)

    def _treasure_site_key(self, position: Vector2) -> str:
        return f"{int(position.x)}:{int(position.y)}"

    def _guard_label_for_position(self, position: Vector2) -> str:
        nearest = self.game_map.nearest_landmark_name(position)
        return nearest if nearest else self.theme.label

    def _assign_guard_roles(self) -> None:
        self.treasure_guard_bosses = []
        boss_anchors = self.treasure_sites[:] or [self.safe_zone.current_center.copy()]
        boss_candidates = [bot for bot in self.bots if bot.is_elite]
        if len(boss_candidates) < 2:
            boss_candidates.extend(bot for bot in self.bots if bot not in boss_candidates)
        selected_bosses = boss_candidates[:2]

        for index, boss in enumerate(selected_bosses):
            anchor = boss_anchors[index % len(boss_anchors)].copy()
            boss.is_treasure_boss = True
            boss.treasure_guard = True
            boss.patrol_entire_map = False
            boss.name = f"Treasure Guard {index + 1}"
            boss.color = (86, 52, 46)
            boss.accent_color = (255, 162, 92)
            boss.marker_color = (255, 222, 164)
            boss.secondary_color = (34, 24, 22)
            boss.visual_scale_multiplier = 1.16
            boss.sprite_tint = (54, 22, 0)
            boss.sprite_tint_strength = 26
            boss.set_guard_anchor(anchor, radius=210.0, label=f"Treasure Guard {index + 1}", treasure_guard=True)
            boss.wander_target = anchor.copy()
            self.treasure_guard_bosses.append(boss)

        patrol_points = self.game_map.walkable_points or self.game_map.spawn_points
        full_map_radius = math.hypot(self.game_map.bounds.width, self.game_map.bounds.height)
        for index, bot in enumerate(self.bots):
            if bot in self.treasure_guard_bosses:
                continue
            bot.is_treasure_boss = False
            bot.treasure_guard = False
            bot.patrol_entire_map = True
            bot.visual_scale_multiplier = 1.0
            bot.sprite_tint = None
            bot.sprite_tint_strength = 0
            anchor = patrol_points[index % len(patrol_points)].copy() if patrol_points else self.safe_zone.current_center.copy()
            bot.set_guard_anchor(
                anchor,
                radius=full_map_radius,
                label="full_map_patrol",
                treasure_guard=False,
            )
            bot.wander_target = self.safe_zone.random_patrol_point(self.rng, self.game_map)

    def alive_treasure_guard_boss_count(self) -> int:
        return sum(1 for bot in self.treasure_guard_bosses if bot.alive)

    def _treasure_spawn_clearance(self) -> float:
        shortest_edge = float(min(self.game_map.bounds.width, self.game_map.bounds.height))
        return max(TREASURE_START_CLEARANCE_MIN, min(TREASURE_START_CLEARANCE_MAX, shortest_edge * 0.26))

    def _distance_from_start_area(self, point: Vector2) -> float:
        if not self.spawn_positions:
            return point.distance_to(self.player.position)
        return min(point.distance_to(spawn) for spawn in self.spawn_positions)

    def _select_treasure_map_positions(self, points: list[Vector2]) -> list[Vector2]:
        candidate_pool = [position.copy() for _, position in self.game_map.landmarks]
        candidate_pool.extend(point.copy() for point in points)
        if not candidate_pool:
            candidate_pool = [point.copy() for point in points]

        start_clearance = self._treasure_spawn_clearance()
        clearance_steps = (start_clearance, start_clearance * 0.88, start_clearance * 0.72, start_clearance * 0.56)
        spread_steps = (
            TREASURE_POINT_SPREAD,
            TREASURE_POINT_SPREAD * 0.86,
            TREASURE_POINT_SPREAD * 0.72,
            TREASURE_POINT_FALLBACK_SPREAD,
        )
        selected: list[Vector2] = []

        for clearance in clearance_steps:
            for spread in spread_steps:
                candidates = [
                    candidate.copy()
                    for candidate in candidate_pool
                    if self._distance_from_start_area(candidate) >= clearance
                    and all(candidate.distance_to(existing) > 1.0 for existing in selected)
                ]
                while candidates and len(selected) < self.treasure_map_target:
                    best_point = None
                    best_score = -1.0
                    for candidate in candidates:
                        closest_selected = min((candidate.distance_to(existing) for existing in selected), default=spread * 1.15)
                        if closest_selected < spread:
                            continue
                        start_distance = self._distance_from_start_area(candidate)
                        player_distance = candidate.distance_to(self.player.position)
                        score = start_distance * 1.55 + closest_selected * 1.45 + player_distance * 0.22
                        if score > best_score:
                            best_score = score
                            best_point = candidate
                    if best_point is None:
                        break
                    selected.append(best_point.copy())
                    candidates = [point for point in candidates if point.distance_to(best_point) > spread * 0.92]
                if len(selected) >= self.treasure_map_target:
                    break
            if len(selected) >= self.treasure_map_target:
                break

        fallback_points = [
            point.copy()
            for point in points
            if all(point.distance_to(existing) > TREASURE_POINT_FALLBACK_SPREAD * 0.68 for existing in selected)
        ]
        while len(selected) < self.treasure_map_target and fallback_points:
            fallback = max(
                fallback_points,
                key=lambda point: (
                    self._distance_from_start_area(point) * 1.35
                    + min((point.distance_to(existing) for existing in selected), default=TREASURE_POINT_SPREAD)
                    + point.distance_to(self.player.position) * 0.2
                ),
            )
            selected.append(fallback.copy())
            fallback_points = [point for point in fallback_points if point.distance_to(fallback) > TREASURE_POINT_FALLBACK_SPREAD]
        return selected[: self.treasure_map_target]

    def _alert_bots_around(self, source_position: Vector2, *, radius: float, duration: float) -> tuple[int, int]:
        alerted = 0
        searching = 0
        direct_radius = radius * LOCAL_ALERT_DIRECT_RATIO
        search_radius = radius * LOCAL_ALERT_SEARCH_RATIO
        for bot in self.bots:
            if not bot.alive:
                continue
            distance = bot.position.distance_to(source_position)
            if distance > radius:
                continue
            line_of_sight = self.game_map.has_line_of_sight(bot.position, source_position)
            if distance <= direct_radius or (line_of_sight and distance <= search_radius):
                if not bot.alerted:
                    alerted += 1
                bot.set_alerted(duration, source_position, investigation_time=max(3.0, duration * 0.72))
                continue
            if distance > search_radius and not line_of_sight:
                continue
            was_tracking = bot.alerted or bot.searching
            bot.set_searching(max(5.0, duration * 0.65), source_position, investigation_time=max(3.8, duration * 0.92))
            if not was_tracking:
                searching += 1
        self._refresh_alert_state()
        return alerted, searching

    def _alert_treasure_guardians(
        self,
        source_position: Vector2,
        *,
        duration: float,
        aggressive: bool,
    ) -> tuple[int, int]:
        if self.alive_treasure_guard_boss_count() <= 0:
            return 0, 0
        alerted = 0
        searching = 0
        for bot in self.treasure_guard_bosses:
            if not bot.alive:
                continue
            if not aggressive and bot.guard_anchor.distance_to(source_position) > bot.guard_radius * 1.15:
                continue
            if aggressive or bot.position.distance_to(source_position) <= bot.guard_radius * 0.72:
                if not bot.alerted:
                    alerted += 1
                bot.set_alerted(duration, source_position, investigation_time=max(4.2, duration * 0.9))
            else:
                was_tracking = bot.alerted or bot.searching
                bot.set_searching(max(5.0, duration * 0.72), source_position, investigation_time=max(4.0, duration))
                if not was_tracking:
                    searching += 1
        self._refresh_alert_state()
        if alerted > 0:
            self._play_audio_event("boss_alert", "danger")
        return alerted, searching

    def _update_treasure_contest(self) -> None:
        if self.alive_treasure_guard_boss_count() <= 0:
            self.contested_treasure_sites.clear()
            return
        for pickup in self.pickups:
            if pickup.kind != "treasure_map":
                continue
            key = self._treasure_site_key(pickup.position)
            distance = self.player.position.distance_to(pickup.position)
            if distance <= 150.0:
                if key not in self.contested_treasure_sites:
                    self.contested_treasure_sites.add(key)
                    alerted, searching = self._alert_treasure_guardians(pickup.position, duration=16.0, aggressive=True)
                    if alerted > 0 or searching > 0:
                        self.announcements.append(Banner("Treasure area entered. Treasure guards are engaging.", (255, 208, 150), ttl=2.0))
            elif distance >= 210.0:
                self.contested_treasure_sites.discard(key)

    def _reward_player_energy(self, amount: int, source_position: Vector2 | None = None) -> int:
        gained = self.player.gain_energy(amount)
        if gained > 0:
            self.player_energy_gained += gained
            if source_position is not None:
                self.particles.add_damage_number(source_position.copy(), gained, (112, 222, 255))
            if self.player.energy == self.player.max_energy:
                self.announcements.append(Banner("Energy fully charged.", (112, 222, 255), ttl=1.8))
        return gained

    def _announce_local_alert(self, source_label: str, alerted: int, searching: int) -> None:
        if alerted <= 0 and searching <= 0:
            return
        if alerted > 0 and searching > 0:
            text = f"{source_label} alert: {alerted} chasing, {searching} searching"
        elif alerted > 0:
            text = f"{source_label} alert: {alerted} chasing"
        else:
            text = f"{source_label} alert: {searching} searching"
        self.announcements.append(Banner(text, (255, 168, 148), ttl=2.1))

    def handle_zone_events(self, events: list[tuple[str, int]]) -> None:
        for kind, phase_number in events:
            if kind == "shrink_start":
                self.announcements.append(Banner(f"Zone shrink started: phase {phase_number}.", ZONE_BLUE))
                if phase_number in (2, 4):
                    self.spawn_supply_drop()
            elif kind == "phase_locked":
                self.announcements.append(Banner("Safe zone locked. Next phase is starting soon.", UI_ACCENT))
            elif kind == "final":
                self.announcements.append(Banner("Final circle formed.", ZONE_DANGER, ttl=4.5))

    def spawn_supply_drop(self, position: Vector2 | None = None) -> None:
        drop_pos = position.copy() if position is not None else self.safe_zone.random_patrol_point(self.rng, self.game_map)
        if position is None:
            self.announcements.append(Banner("Supply drop inbound.", (247, 213, 116)))
        supply_weapon = self.rng.choice((WEAPON_LIBRARY["carbine"], WEAPON_LIBRARY["dmr"], WEAPON_LIBRARY["shotgun"]))
        occupied: list[Vector2] = []
        self._add_pickup(
            Pickup(kind="weapon", position=drop_pos.copy(), weapon_spec=supply_weapon, is_supply=True),
            occupied=occupied,
            clearance=32.0,
        )
        self._add_pickup(
            Pickup(
                kind="ammo",
                position=drop_pos + Vector2(28, 12),
                ammo_type=supply_weapon.ammo_type,
                amount=supply_weapon.pickup_ammo_bonus + 24,
                is_supply=True,
            ),
            occupied=occupied,
            min_distance=48.0,
            clearance=28.0,
        )
        self._add_pickup(
            Pickup(kind="medkit", position=drop_pos + Vector2(-28, 12), amount=1, is_supply=True),
            occupied=occupied,
            min_distance=48.0,
            clearance=28.0,
        )

    def nearest_pickup_for_player(self) -> Pickup | None:
        nearest = None
        nearest_distance = 68.0
        for pickup in self.pickups:
            distance = self.player.position.distance_to(pickup.position)
            if distance <= nearest_distance:
                nearest_distance = distance
                nearest = pickup
        return nearest

    def consume_pickup(self, character, pickup: Pickup) -> str | None:
        if pickup not in self.pickups:
            return None
        was_armed = character.combat_enabled
        pickup_position = pickup.position.copy()
        if pickup.kind == "gear":
            if not character.arm_combat():
                return None
        elif pickup.kind == "treasure_map":
            if character is not self.player:
                return None
            remaining_bosses = self.alive_treasure_guard_boss_count()
            if remaining_bosses > 0:
                self._play_audio_event("map_locked", "danger")
                self.announcements.append(Banner(f"Defeat {remaining_bosses} treasure guards before collecting maps.", (255, 196, 132), ttl=1.8))
                return None
            self.treasure_maps_found = min(self.treasure_map_target, self.treasure_maps_found + 1)
        elif pickup.kind == "medkit":
            if character.medkits >= MAX_MEDKITS:
                return None
            character.medkits = min(MAX_MEDKITS, character.medkits + pickup.amount)
        elif pickup.kind == "ammo":
            if pickup.ammo_type:
                character.ammo[pickup.ammo_type] = character.ammo.get(pickup.ammo_type, 0) + pickup.amount
        elif pickup.kind == "weapon" and pickup.weapon_spec:
            if not character.combat_enabled:
                character.arm_combat()
            dropped = character.equip_weapon(pickup.weapon_spec)
            if dropped is not None:
                offset = Vector2(self.rng.randint(-22, 22), self.rng.randint(-22, 22))
                self._add_pickup(Pickup(kind="weapon", position=pickup.position + offset, weapon_spec=dropped))
        else:
            return None
        pickup.kill()
        self.pickups.remove(pickup)
        if character is self.player:
            pickup_event = {
                "weapon": "pickup_weapon",
                "ammo": "pickup_ammo",
                "medkit": "pickup_medkit",
                "treasure_map": "map_pickup",
                "gear": "pickup_weapon",
            }.get(pickup.kind, "pickup_item")
            self._play_audio_event(pickup_event, "reload_complete")
        if character is self.player and pickup.kind == "weapon" and not was_armed and character.combat_enabled and pickup.weapon_spec:
            self.announcements.append(Banner(f"Equipped {pickup.weapon_spec.label}. Combat enabled.", (170, 236, 255), ttl=1.8))
        if character is self.player and pickup.kind == "treasure_map":
            self.contested_treasure_sites.discard(self._treasure_site_key(pickup_position))
            remaining = max(0, self.treasure_map_target - self.treasure_maps_found)
            if remaining > 0:
                message = f"Treasure maps: {self.treasure_maps_found}/{self.treasure_map_target}. {remaining} remaining."
            else:
                message = "Final treasure map collected. Mission objective complete."
            self.announcements.append(Banner(message, (247, 220, 148), ttl=2.0))
        return pickup.kind

    def player_pickup(self) -> None:
        nearest = self.nearest_pickup_for_player()
        if nearest is not None:
            pickup_kind = self.consume_pickup(self.player, nearest)
            if pickup_kind == "medkit":
                self.announcements.append(Banner("Medkit acquired.", (144, 230, 188), ttl=1.4))

    def player_throw_grenade(self, target_world: Vector2) -> bool:
        if not self.player.can_throw_grenade():
            return False
        direction = target_world - self.player.position
        if direction.length_squared() <= 1e-6:
            direction = Vector2(1, 0)
        else:
            direction = direction.normalize()
        spawn = self.player.position + direction * (self.player.radius + 18)
        velocity = direction * GRENADE_THROW_SPEED + self.player.last_move * 0.18
        grenade = Grenade(
            position=spawn,
            velocity=velocity,
            owner=self.player,
            fuse_time=GRENADE_FUSE_TIME,
            color=GRENADE_COLOR,
        )
        self.grenades.append(grenade)
        self._register_sprite(grenade, self.projectile_group)
        self.player.grenade_count -= 1
        return True

    def _register_new_projectiles(self, new_projectiles) -> None:
        if not new_projectiles:
            return
        owner = getattr(new_projectiles[0], "owner", None)
        if owner is not None:
            self._play_weapon_fire_audio(owner, len(new_projectiles))
        self.projectiles.extend(new_projectiles)
        for projectile in new_projectiles:
            self._register_sprite(projectile, self.projectile_group)

    def _auto_pickups_for_bots(self) -> None:
        for bot in self.bots:
            if not bot.alive:
                continue
            for pickup in self.pickups[:]:
                if bot.position.distance_to(pickup.position) <= bot.radius + 20:
                    self.consume_pickup(bot, pickup)

    def _process_triggers(self, dt: float) -> None:
        self.active_capture_label = ""
        self.active_capture_progress = 0.0

        for label in list(self.gate_restore_timers):
            self.gate_restore_timers[label] -= dt
            if self.gate_restore_timers[label] <= 0:
                trigger = next((item for item in self.game_map.triggers if item.label == label and item.kind == "mechanism"), None)
                self.game_map.set_gate_state(label, is_open=False, region_rect=trigger.rect if trigger is not None else None)
                del self.gate_restore_timers[label]

        for trigger in self.game_map.triggers:
            inside = trigger.rect.collidepoint(int(self.player.position.x), int(self.player.position.y))
            if not inside:
                self.trigger_timers.pop(trigger.label, None)
                if trigger.kind == "capture" and trigger.label in self.capture_progress and trigger.label not in self.entered_triggers:
                    self.capture_progress[trigger.label] = max(0.0, self.capture_progress[trigger.label] - dt * 0.5)
                continue

            if trigger.kind == "danger":
                timer = self.trigger_timers.get(trigger.label, 0.0) + dt
                self.trigger_timers[trigger.label] = timer
                if trigger.label not in self.entered_triggers:
                    self.entered_triggers.add(trigger.label)
                    post_player_enter_trigger(trigger.label, trigger.kind)
                if timer >= 0.55:
                    self.trigger_timers[trigger.label] = 0.0
                    died = self.player.take_damage(2, None)
                    if died:
                        self._play_defeat_audio(self.player)
                    else:
                        self._play_audio_event("player_hurt", "danger", 0.62)
                    post_camera_shake(2.4, 0.08)
                continue

            if trigger.kind == "capture":
                if trigger.label not in self.trigger_timers:
                    post_player_enter_trigger(trigger.label, trigger.kind)
                progress = min(1.0, self.capture_progress.get(trigger.label, 0.0) + dt / 2.6)
                self.capture_progress[trigger.label] = progress
                self.trigger_timers[trigger.label] = progress
                self.active_capture_label = trigger.label
                self.active_capture_progress = progress
                if progress >= 1.0 and trigger.label not in self.entered_triggers:
                    self.entered_triggers.add(trigger.label)
                    reward = self._resolve_capture_reward(trigger.label, trigger.rect)
                    post_capture_point(trigger.label, reward)
                continue

            if trigger.one_shot and trigger.label in self.entered_triggers:
                continue

            self.entered_triggers.add(trigger.label)
            post_player_enter_trigger(trigger.label, trigger.kind)
            if trigger.kind == "supply":
                self.spawn_supply_drop(Vector2(trigger.rect.center))
            elif trigger.kind == "mechanism":
                self.game_map.set_gate_state(trigger.label, is_open=True, region_rect=trigger.rect)
                self.gate_restore_timers[trigger.label] = 7.5
                post_camera_shake(6.0, 0.2)

    def _resolve_capture_reward(self, label: str, rect: pygame.Rect) -> str:
        center = Vector2(rect.center)
        if "relay" in label.lower() or "beacon" in label.lower():
            self.respawn_charges = min(2, self.respawn_charges + 1)
            self.pending_respawn_anchor = center
            return "respawn"
        self.spawn_supply_drop(center)
        self.player.armor = min(self.player.max_armor, self.player.armor + 12)
        return "supply"

    def update(self, dt: float, keys, mouse_world: Vector2, firing: bool, movement_held_keys: set[int] | None = None) -> None:
        self.elapsed += dt
        self.controls_hint_timer = max(0.0, self.controls_hint_timer - dt)
        if self.controls_hint_timer == 0.0 and self.controls_visible:
            self.controls_visible = False

        if self.pending_respawn_timer is not None:
            self.pending_respawn_timer = max(0.0, self.pending_respawn_timer - dt)
            if self.pending_respawn_timer == 0.0:
                anchor = tuple(self.pending_respawn_anchor) if self.pending_respawn_anchor is not None else None
                self.pending_respawn_timer = None
                post_respawn_player(anchor)

        if self.countdown > 0.0:
            self.countdown = max(0.0, self.countdown - dt)
            self._register_new_projectiles(
                self.player.update(
                    dt=dt,
                    game_map=self.game_map,
                    keys=keys,
                    mouse_world=mouse_world,
                    firing=False,
                    rng=self.rng,
                    held_keys=movement_held_keys,
                )
            )
            self._update_banners(dt)
            self.particles.update(dt)
            return

        zone_events = self.safe_zone.update(dt, self.game_map)
        self.handle_zone_events(zone_events)

        self._register_new_projectiles(
            self.player.update(
                dt=dt,
                game_map=self.game_map,
                keys=keys,
                mouse_world=mouse_world,
                firing=firing,
                rng=self.rng,
                held_keys=movement_held_keys,
            )
        )
        self._update_treasure_contest()

        for bot in self.bots:
            if bot.alive:
                self._register_new_projectiles(
                    bot.update(
                        dt=dt,
                        game_map=self.game_map,
                        characters=self.characters,
                        pickups=self.pickups,
                        safe_zone=self.safe_zone,
                        rng=self.rng,
                    )
                )
        self._refresh_alert_state()

        self._auto_pickups_for_bots()
        self._process_triggers(dt)

        self.projectiles, hit_events = self.collision_manager.update_projectiles(
            self.projectiles,
            dt,
            self.game_map,
            self.characters,
        )
        for event in hit_events:
            self._play_hit_audio(event.victim)
            self.particles.add_impact(event.impact_position, event.color)
            for position, damage in event.damage_numbers:
                self.particles.add_damage_number(position, damage, (255, 218, 190))
            if event.owner is self.player and event.victim in self.bots:
                event.victim.set_alerted(
                    20.0 if getattr(event.victim, "is_elite", False) else 14.0,
                    self.player.position,
                    investigation_time=12.0,
                )
                if getattr(event.victim, "is_elite", False):
                    self._reward_player_energy(8, event.victim.position + Vector2(0, -18))
            if event.victim is self.player:
                post_camera_shake(5.0, 0.12)
            if event.victim is not None and not event.victim.alive and event.owner is not event.victim:
                self._play_defeat_audio(event.victim)
                owner_name = getattr(event.owner, "name", "Unknown")
                post_killfeed(f"{owner_name} eliminated {event.victim.name}", getattr(event.owner, "color", UI_ACCENT))
                if event.owner is self.player:
                    if getattr(event.victim, "is_elite", False):
                        self._reward_player_energy(20, event.victim.position + Vector2(0, -28))
                        self.announcements.append(Banner(f"Elite unit {event.victim.name} eliminated.", (255, 148, 148), ttl=1.8))
                        self.spawn_supply_drop(event.victim.position)
                    else:
                        self.announcements.append(Banner("Target eliminated.", event.owner.color, ttl=1.4))
        self._cleanup_projectile_group()

        self.grenades, explosion_events = self.collision_manager.update_grenades(
            self.grenades,
            dt,
            self.game_map,
            self.characters,
        )
        for event in explosion_events:
            self._play_audio_event("grenade_blast", "grenade_blast")
            self.particles.add_explosion(event.impact_position, event.color, event.radius)
            post_camera_shake(10.0, 0.22)
            for position, damage in event.damage_numbers:
                self.particles.add_damage_number(position, damage, (255, 208, 168))
            for victim in event.victims:
                if event.owner is self.player and victim in self.bots:
                    victim.set_alerted(
                        20.0 if getattr(victim, "is_elite", False) else 14.0,
                        self.player.position,
                        investigation_time=12.0,
                    )
                    if getattr(victim, "is_elite", False):
                        self._reward_player_energy(10, victim.position + Vector2(0, -20))
                if not victim.alive and event.owner is not None and event.owner is not victim:
                    self._play_defeat_audio(victim)
                    post_killfeed(f"{event.owner.name} eliminated {victim.name} with an explosion", event.owner.color)
                    if event.owner is self.player and getattr(victim, "is_elite", False):
                        self._reward_player_energy(20, victim.position + Vector2(0, -30))
                        self.announcements.append(Banner(f"Elite unit {victim.name} destroyed.", (255, 148, 148), ttl=1.8))
                        self.spawn_supply_drop(victim.position)
        self._cleanup_projectile_group()

        self._apply_zone_damage(dt)
        self._update_dynamic_music()
        self._update_banners(dt)
        self.particles.update(dt)

        if self.respawn_charges > 0 and not self.player.alive and self.pending_respawn_timer is None:
            self.pending_respawn_timer = 2.2
            self.pending_respawn_anchor = self.pending_respawn_anchor or self.game_map.random_safe_point(self.rng)

        if self.is_finished() and not self.match_end_posted:
            self.match_end_posted = True
            post_match_end(self.build_summary())

    def _cleanup_projectile_group(self) -> None:
        active_ids = {id(item) for item in self.projectiles}
        active_ids.update(id(item) for item in self.grenades)
        for sprite in list(self.projectile_group):
            if id(sprite) not in active_ids:
                sprite.kill()

    def _apply_zone_damage(self, dt: float) -> None:
        self.zone_tick += dt
        if self.zone_tick < 0.4:
            return
        self.zone_tick = 0.0
        damage = max(1, int(self.safe_zone.current_dps * 0.4))
        for character in self.characters:
            if character.alive and self.safe_zone.is_outside(character.position):
                died = character.take_damage(damage, None)
                if character is self.player:
                    if died:
                        self._play_defeat_audio(character)
                    else:
                        self._play_audio_event("player_hurt", "danger", 0.52)
                if died:
                    post_killfeed(f"{character.name} was eliminated by the zone", ZONE_DANGER)

    def _update_banners(self, dt: float) -> None:
        self.announcements = [banner for banner in self.announcements if banner.update(dt)]
        self.killfeed = [banner for banner in self.killfeed if banner.update(dt)]

    def sync_render_group(self, camera) -> None:
        for sprite in self.render_group.sprites():
            if hasattr(sprite, "sync_visual"):
                sprite.sync_visual(camera)
            if hasattr(sprite, "position"):
                screen_y = camera.world_to_screen(sprite.position)[1]
                self.render_group.change_layer(sprite, getattr(sprite, "_layer", 0) * 10000 + screen_y)

    def alive_count(self) -> int:
        return sum(1 for character in self.characters if character.alive)

    def elite_alive_count(self) -> int:
        return sum(1 for bot in self.elite_bots if bot.alive)

    def is_finished(self) -> bool:
        if self.pending_respawn_timer is not None:
            return False
        if not self.player.alive:
            return True
        if self._player_is_last_survivor():
            return True
        if self.elapsed >= self.config.match_time_limit:
            return True
        if self.config.mode == "\u5bfb\u5b9d\u6a21\u5f0f":
            return self.treasure_maps_found >= self.treasure_map_target
        if self.config.mode == "\u751f\u5b58\u6a21\u5f0f":
            return self.alive_count() == 1
        return self.player.kills >= self.config.kill_target

    def _player_is_last_survivor(self) -> bool:
        return self.player.alive and self.alive_count() == 1

    def _finish_type(self) -> str:
        if not self.player.alive:
            return "death"
        if self._player_is_last_survivor():
            return "last_survivor"
        if self.config.mode == "\u5bfb\u5b9d\u6a21\u5f0f" and self.treasure_maps_found >= self.treasure_map_target:
            return "treasure_complete"
        if self.config.mode != "\u5bfb\u5b9d\u6a21\u5f0f" and self.config.mode != "\u751f\u5b58\u6a21\u5f0f" and self.player.kills >= self.config.kill_target:
            return "kill_target"
        if self.elapsed >= self.config.match_time_limit:
            return "timeout"
        return "incomplete"

    def respawn_player(self, anchor: tuple[float, float] | None = None) -> None:
        position = Vector2(anchor) if anchor is not None else self.pending_respawn_anchor or self.game_map.random_safe_point(self.rng)
        self.player.respawn(position, hp_ratio=0.72, armor_ratio=0.55)
        self.player.respawn_anchor = position.copy()
        self.respawn_charges = max(0, self.respawn_charges - 1)
        self.pending_respawn_anchor = None

    def build_summary(self) -> dict[str, object]:
        finish_type = self._finish_type()
        victory = finish_type in {"last_survivor", "treasure_complete", "kill_target"}
        next_theme_id = get_next_theme_id(self.theme_id)
        return {
            "victory": victory,
            "finish_type": finish_type,
            "advance_to_next_map": victory,
            "next_theme_id": next_theme_id,
            "next_theme_label": THEME_BY_ID[next_theme_id].label,
            "callsign": self.player.name,
            "kills": self.player.kills,
            "damage": int(self.player.damage_dealt),
            "survival_time": self.elapsed,
            "alive_count": self.alive_count(),
            "elite_alive_count": self.elite_alive_count(),
            "grenades_left": self.player.grenade_count,
            "player_energy": self.player.energy,
            "player_energy_gained": self.player_energy_gained,
            "treasure_maps_found": self.treasure_maps_found,
            "treasure_map_target": self.treasure_map_target,
            "objective_text": self.mission_objective_text(),
            "objective_progress_text": self.mission_progress_text(),
            "finish_reason": self._finish_reason(victory, finish_type),
            "peak_alerted_bots": self.peak_alerted_bots,
            "peak_local_alert_bots": self.peak_local_alert_bots,
            "bot_count": len(self.bots),
            "mode": self.config.mode,
            "theme_id": self.theme_id,
            "theme_label": self.theme.label,
        }
