from __future__ import annotations

import math
import random
from dataclasses import dataclass

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
    THEME_BY_ID,
    UI_ACCENT,
    WEAPON_LIBRARY,
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
from ..entities.bot_player import BotPlayer
from ..entities.item import Pickup
from ..entities.map import Map
from ..entities.player import Player
from ..entities.projectile import Grenade
from ..helpers import Vector2, lerp, lerp_vec
from ..systems.collision import CollisionManager
from ..systems.particles import ParticleSystem


@dataclass
class Banner:
    text: str
    color: tuple[int, int, int]
    ttl: float = 3.6

    def update(self, dt: float) -> bool:
        self.ttl -= dt
        return self.ttl > 0


class SafeZone:
    def __init__(self, rng: random.Random, world_size: tuple[int, int]) -> None:
        self.rng = rng
        self.world_width = world_size[0]
        self.world_height = world_size[1]
        self.initial_center = Vector2(self.world_width / 2, self.world_height / 2)
        self.initial_radius = max(420.0, min(self.world_width, self.world_height) * 0.46)
        self.current_center = self.initial_center.copy()
        self.current_radius = self.initial_radius
        self.start_center = self.current_center.copy()
        self.start_radius = self.current_radius
        self.target_center = self.current_center.copy()
        self.target_radius = self.current_radius
        self.phase_index = 0
        self.state = "hold"
        self.state_timer = ZONE_PHASES[0].hold_time + 8.0
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
                self.state_timer = phase.shrink_time + 3.0
                self.start_center = self.current_center.copy()
                self.start_radius = self.current_radius
                self.target_radius = self.initial_radius * phase.radius_scale
                self.target_center = self._pick_next_center(self.target_radius)
                events.append(("shrink_start", self.phase_index + 1))
        elif self.state == "shrink":
            self.state_timer = max(0.0, self.state_timer - dt)
            progress = 1.0 - (self.state_timer / (phase.shrink_time + 3.0))
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
        candidate.x = max(next_radius + 40, min(self.world_width - next_radius - 40, candidate.x))
        candidate.y = max(next_radius + 40, min(self.world_height - next_radius - 40, candidate.y))
        if candidate.distance_to(self.current_center) > self.current_radius - next_radius:
            direction = (candidate - self.current_center).normalize()
            candidate = self.current_center + direction * (self.current_radius - next_radius - 8)
        return candidate

    def is_outside(self, position: Vector2) -> bool:
        return position.distance_to(self.current_center) > self.current_radius

    def time_to_next(self) -> float:
        return max(0.0, self.state_timer)

    def random_patrol_point(self, rng: random.Random, game_map: Map) -> Vector2:
        for _ in range(60):
            angle = rng.uniform(0.0, math.tau)
            radius = rng.uniform(0.1, 0.9) * min(self.current_radius, 560)
            candidate = self.current_center + Vector2(math.cos(angle), math.sin(angle)) * radius
            if not game_map.bounds.collidepoint(candidate):
                continue
            if any(obstacle.rect.inflate(40, 40).collidepoint(candidate) for obstacle in game_map.obstacles):
                continue
            return candidate
        return self.current_center.copy()

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

        self.player = self._spawn_player()
        self.bots = self._spawn_bots()
        self.elite_bots = [bot for bot in self.bots if bot.is_elite]
        self.characters = [self.player, *self.bots]
        self._spawn_loot()
        self.announcements.append(Banner(f"已部署到 {self.theme.label}。先抢点，再卡缩圈。", self.theme.accent))
        if self.elite_bots:
            self.announcements.append(Banner("侦测到精英猎手信号。留意高威胁目标。", (255, 146, 146), ttl=4.2))

    def _theme_weapon_pool(self) -> tuple[str, ...]:
        if self.theme_id == "temple_tmx":
            return ("carbine", "dmr", "carbine", "dmr", "smg")
        if self.theme_id == "courtyard_tmx":
            return ("smg", "shotgun", "smg", "shotgun", "carbine")
        return ("smg", "carbine", "smg", "carbine", "shotgun")

    def _elite_bot_count_for_theme(self) -> int:
        if self.theme_id in {"cyber_city_tmx", "temple_tmx"}:
            return 1
        return 0

    def _register_sprite(self, sprite, group: pygame.sprite.Group | None = None) -> None:
        self.render_group.add(sprite, layer=getattr(sprite, "_layer", 0))
        if hasattr(sprite, "sync_visual"):
            sprite.sync_visual(Vector2())
        if group is not None:
            group.add(sprite)

    def _spawn_player(self) -> Player:
        spawn = self.rng.choice(self.game_map.spawn_points).copy()
        player = Player(spawn, self.game.player_profile)
        hero_sprite_path = RESOURCE_ROOT / "img" / "characters" / "hero_sprite96_v2.png"
        shield_effect_path = RESOURCE_ROOT / "img" / "characters" / "shield_ring_cyber_v2.png"
        ground_effect_path = RESOURCE_ROOT / "img" / "characters" / "ground_contact_cyber_v2.png"
        if hero_sprite_path.exists():
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
        if self.theme_id == "temple_tmx":
            player.equip_weapon(WEAPON_LIBRARY["carbine"])
            player.equip_weapon(WEAPON_LIBRARY["dmr"], as_active=False)
        elif self.theme_id == "courtyard_tmx":
            player.equip_weapon(WEAPON_LIBRARY["smg"])
            player.equip_weapon(WEAPON_LIBRARY["shotgun"], as_active=False)
        else:
            player.equip_weapon(WEAPON_LIBRARY["smg"])
            player.equip_weapon(WEAPON_LIBRARY["carbine"], as_active=False)
        player.active_weapon_index = 0
        player.medkits = 3
        self._register_sprite(player, self.character_group)
        return player

    def _spawn_bots(self) -> list[BotPlayer]:
        total_bot_count = self.config.player_count - 1
        elite_count = min(self._elite_bot_count_for_theme(), total_bot_count)
        spawn_pool = self.game_map.spawn_points[:]
        while len(spawn_pool) < total_bot_count + 2:
            spawn_pool.append(self.game_map.random_safe_point(self.rng))
        self.rng.shuffle(spawn_pool)

        names = list(BOT_NAMES)
        self.rng.shuffle(names)
        while len(names) < total_bot_count:
            names.extend(BOT_NAMES)

        normal_pool = self._theme_weapon_pool()
        elite_pool = ("dmr", "carbine")
        elite_start = total_bot_count - elite_count
        bots: list[BotPlayer] = []
        standard_sprite_path = RESOURCE_ROOT / "img" / "characters" / "bot_sprite96_v2.png"
        elite_sprite_path = RESOURCE_ROOT / "img" / "characters" / "elite_sprite96_v2.png"
        shield_effect_path = RESOURCE_ROOT / "img" / "characters" / "shield_ring_cyber_v2.png"
        ground_effect_path = RESOURCE_ROOT / "img" / "characters" / "ground_contact_cyber_v2.png"

        for index in range(total_bot_count):
            is_elite = index >= elite_start
            role = "elite" if is_elite else "standard"
            spawn = spawn_pool[index + 1]
            spec = WEAPON_LIBRARY[self.rng.choice(elite_pool if is_elite else normal_pool)]
            name = f"精英·{names[index]}" if is_elite else names[index]
            bot = BotPlayer(name, spawn.copy(), spec, self.rng, role=role)
            sprite_path = elite_sprite_path if is_elite else standard_sprite_path
            if sprite_path.exists():
                scale = 0.98 if is_elite else 0.94
                bot.set_sprite_asset(self.game.resources.load_alpha_image(str(sprite_path)), scale=scale, default_angle=45.0)
            if shield_effect_path.exists() or ground_effect_path.exists():
                bot.set_effect_assets(
                    ground_surface=self.game.resources.load_alpha_image(str(ground_effect_path)) if ground_effect_path.exists() else None,
                    ground_scale=0.68 if is_elite else 0.62,
                    shield_surface=self.game.resources.load_alpha_image(str(shield_effect_path)) if shield_effect_path.exists() else None,
                    shield_scale=0.82 if is_elite else 0.76,
                )
            self._register_sprite(bot, self.character_group)
            bots.append(bot)
        return bots

    def _add_pickup(self, pickup: Pickup) -> None:
        self.pickups.append(pickup)
        self._register_sprite(pickup, self.pickup_group)

    def _spawn_loot(self) -> None:
        weapon_keys = self._theme_weapon_pool()
        points = self.game_map.loot_points[:]
        self.rng.shuffle(points)
        for index, point in enumerate(points[: max(30, min(48, len(points)))]):
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
            self._add_pickup(pickup)

    def handle_zone_events(self, events: list[tuple[str, int]]) -> None:
        for kind, phase_number in events:
            if kind == "shrink_start":
                self.announcements.append(Banner(f"毒圈开始收缩，第 {phase_number} 阶段。", ZONE_BLUE))
                if phase_number in (2, 4):
                    self.spawn_supply_drop()
            elif kind == "phase_locked":
                self.announcements.append(Banner("安全区已锁定，下一阶段即将开始。", UI_ACCENT))
            elif kind == "final":
                self.announcements.append(Banner("最终决赛圈已形成，掩体空间极少。", ZONE_DANGER, ttl=4.5))

    def spawn_supply_drop(self, position: Vector2 | None = None) -> None:
        drop_pos = position.copy() if position is not None else self.safe_zone.random_patrol_point(self.rng, self.game_map)
        if position is None:
            self.announcements.append(Banner("空投已落在安全区内。", (247, 213, 116)))
        supply_weapon = self.rng.choice((WEAPON_LIBRARY["carbine"], WEAPON_LIBRARY["dmr"], WEAPON_LIBRARY["shotgun"]))
        self._add_pickup(Pickup(kind="weapon", position=drop_pos.copy(), weapon_spec=supply_weapon, is_supply=True))
        self._add_pickup(
            Pickup(
                kind="ammo",
                position=drop_pos + Vector2(28, 12),
                ammo_type=supply_weapon.ammo_type,
                amount=supply_weapon.pickup_ammo_bonus + 24,
                is_supply=True,
            )
        )
        self._add_pickup(Pickup(kind="medkit", position=drop_pos + Vector2(-28, 12), amount=1, is_supply=True))

    def nearest_pickup_for_player(self) -> Pickup | None:
        nearest = None
        nearest_distance = 68.0
        for pickup in self.pickups:
            distance = self.player.position.distance_to(pickup.position)
            if distance <= nearest_distance:
                nearest_distance = distance
                nearest = pickup
        return nearest

    def consume_pickup(self, character, pickup: Pickup) -> None:
        if pickup not in self.pickups:
            return
        if pickup.kind == "medkit":
            if character.medkits >= MAX_MEDKITS:
                return
            character.medkits += pickup.amount
        elif pickup.kind == "ammo":
            if pickup.ammo_type:
                character.ammo[pickup.ammo_type] = character.ammo.get(pickup.ammo_type, 0) + pickup.amount
        elif pickup.kind == "weapon" and pickup.weapon_spec:
            dropped = character.equip_weapon(pickup.weapon_spec)
            if dropped is not None:
                offset = Vector2(self.rng.randint(-22, 22), self.rng.randint(-22, 22))
                self._add_pickup(Pickup(kind="weapon", position=pickup.position + offset, weapon_spec=dropped))
        pickup.kill()
        self.pickups.remove(pickup)

    def player_pickup(self) -> None:
        nearest = self.nearest_pickup_for_player()
        if nearest is not None:
            self.consume_pickup(self.player, nearest)

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
                self.game_map.set_gate_state(label, is_open=False)
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
                    self.player.take_damage(2, None)
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
                self.game_map.set_gate_state(trigger.label, is_open=True)
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

    def update(self, dt: float, keys, mouse_world: Vector2, firing: bool) -> None:
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
            self._update_banners(dt)
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
            )
        )
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

        self._auto_pickups_for_bots()
        self._process_triggers(dt)

        self.projectiles, hit_events = self.collision_manager.update_projectiles(
            self.projectiles,
            dt,
            self.game_map,
            self.characters,
        )
        for event in hit_events:
            self.particles.add_impact(event.impact_position, event.color)
            for position, damage in event.damage_numbers:
                self.particles.add_damage_number(position, damage, (255, 218, 190))
            if event.victim is self.player:
                post_camera_shake(5.0, 0.12)
            if event.victim is not None and not event.victim.alive and event.owner is not event.victim:
                post_killfeed(f"{event.owner.name} 淘汰了 {event.victim.name}", event.owner.color)
                if event.owner is self.player:
                    if getattr(event.victim, "is_elite", False):
                        self.announcements.append(Banner(f"你击倒了精英单位 {event.victim.name}。", (255, 148, 148), ttl=1.8))
                        self.spawn_supply_drop(event.victim.position)
                    else:
                        self.announcements.append(Banner("命中致命一击。", event.owner.color, ttl=1.4))
        self._cleanup_projectile_group()

        self.grenades, explosion_events = self.collision_manager.update_grenades(
            self.grenades,
            dt,
            self.game_map,
            self.characters,
        )
        for event in explosion_events:
            self.particles.add_explosion(event.impact_position, event.color, event.radius)
            post_camera_shake(10.0, 0.22)
            for position, damage in event.damage_numbers:
                self.particles.add_damage_number(position, damage, (255, 208, 168))
            for victim in event.victims:
                if not victim.alive and event.owner is not None and event.owner is not victim:
                    post_killfeed(f"{event.owner.name} 爆破淘汰了 {victim.name}", event.owner.color)
                    if event.owner is self.player and getattr(victim, "is_elite", False):
                        self.announcements.append(Banner(f"精英单位 {victim.name} 被爆破清除。", (255, 148, 148), ttl=1.8))
                        self.spawn_supply_drop(victim.position)
        self._cleanup_projectile_group()

        self._apply_zone_damage(dt)
        self._update_banners(dt)

        if not self.player.alive and self.respawn_charges > 0 and self.pending_respawn_timer is None:
            self.pending_respawn_timer = max(2.5, self.config.respawn_time or 3.0)
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
                if died:
                    post_killfeed(f"{character.name} 倒在了毒圈外", ZONE_DANGER)

    def _update_banners(self, dt: float) -> None:
        self.announcements = [banner for banner in self.announcements if banner.update(dt)]
        self.killfeed = [banner for banner in self.killfeed if banner.update(dt)]

    def sync_render_group(self, camera_position: Vector2) -> None:
        for sprite in self.render_group.sprites():
            if hasattr(sprite, "sync_visual"):
                sprite.sync_visual(camera_position)
            if hasattr(sprite, "position"):
                self.render_group.change_layer(sprite, getattr(sprite, "_layer", 0) * 10000 + int(sprite.position.y))

    def alive_count(self) -> int:
        return sum(1 for character in self.characters if character.alive)

    def elite_alive_count(self) -> int:
        return sum(1 for bot in self.elite_bots if bot.alive)

    def is_finished(self) -> bool:
        if self.elapsed >= self.config.match_time_limit:
            return True
        if self.config.mode == "生存模式":
            if self.pending_respawn_timer is not None:
                return False
            return not self.player.alive or self.alive_count() == 1
        return self.player.kills >= self.config.kill_target

    def respawn_player(self, anchor: tuple[float, float] | None = None) -> None:
        position = Vector2(anchor) if anchor is not None else self.pending_respawn_anchor or self.game_map.random_safe_point(self.rng)
        self.player.respawn(position, hp_ratio=0.72, armor_ratio=0.55)
        self.player.respawn_anchor = position.copy()
        self.respawn_charges = max(0, self.respawn_charges - 1)
        self.pending_respawn_anchor = None

    def build_summary(self) -> dict[str, object]:
        victory = self.player.alive and (self.alive_count() == 1 or self.player.kills >= self.config.kill_target)
        return {
            "victory": victory,
            "callsign": self.player.name,
            "kills": self.player.kills,
            "damage": int(self.player.damage_dealt),
            "survival_time": self.elapsed,
            "alive_count": self.alive_count(),
            "elite_alive_count": self.elite_alive_count(),
            "grenades_left": self.player.grenade_count,
            "mode": self.config.mode,
            "theme_id": self.theme_id,
            "theme_label": self.theme.label,
        }
