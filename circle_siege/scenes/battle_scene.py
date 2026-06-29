from __future__ import annotations

import pygame

from ..core.base_scene import BaseScene
from ..core.config import SCREEN_HEIGHT, SCREEN_WIDTH
from ..core.events import (
    CAPTURE_POINT,
    MATCH_END,
    PLAYER_ENTER_TRIGGER,
    RELOAD_COMPLETE,
    RESPAWN_PLAYER,
    SHAKE_CAMERA,
    SHOW_KILLFEED,
    SKILL_COOLDOWN_END,
)
from ..helpers import Vector2, draw_outlined_text
from ..presentation.hud import HUDRenderer
from ..rules.match_manager import Banner, MatchManager
from ..systems.camera import Camera


class BattleScene(BaseScene):
    def __init__(self, game, theme_id: str) -> None:
        super().__init__(game)
        self.game.audio.play_music("battle", fade_ms=700)
        self.match = MatchManager(game, theme_id)
        self.camera = Camera()
        self.camera.horizon_y = 0.0
        self.camera.ground_y_scale = 1.0
        self.camera.ground_x_skew = 0.0
        self.camera.focus_screen_x = SCREEN_WIDTH / 2
        self.camera.focus_screen_y = SCREEN_HEIGHT / 2
        self.camera.set_world_size(self.match.game_map.bounds.width, self.match.game_map.bounds.height)
        self.camera.snap_to(self.match.player.position)
        self.debug_visible = False
        self.debug_geometry_visible = False
        self.mouse_world = Vector2()
        self.hud = HUDRenderer(game, self.match)
        self.player_locator_timer = 7.0
        self.held_movement_keys: set[int] = set()
        if self.match.theme_id == "cyber_city_tmx":
            self.match.particles.enable_rain(SCREEN_WIDTH, SCREEN_HEIGHT, 220)
            self.game.audio.play_ambient("rain")
        else:
            self.game.audio.play_ambient("city")

    def _play_audio_event(self, event_name: str, fallback: str | None = None) -> None:
        audio = self.game.audio
        if hasattr(audio, "play_event"):
            audio.play_event(event_name)
            return
        if fallback is not None:
            audio.play_sfx(fallback)

    def handle_events(self, events: list[pygame.event.Event]) -> None:
        for event in events:
            self._track_movement_key_event(event)
            if event.type == pygame.QUIT:
                self.game.running = False
            elif event.type == MATCH_END:
                if event.summary.get("advance_to_next_map"):
                    from .map_transition_scene import MapTransitionScene

                    self.game.change_scene(MapTransitionScene(self.game, event.summary))
                else:
                    from .result_scene import ResultScene

                    self.game.change_scene(ResultScene(self.game, event.summary))
            elif event.type == RESPAWN_PLAYER:
                self.match.respawn_player(event.anchor)
                self.camera.snap_to(self.match.player.position)
                self.player_locator_timer = max(self.player_locator_timer, 4.5)
                self._play_audio_event("map_arrive", "mechanism")
                self.match.announcements.append(Banner("中继重生已触发。", (170, 236, 255), ttl=1.6))
            elif event.type == CAPTURE_POINT:
                self._play_audio_event("mechanism", "killfeed")
                if event.reward == "respawn":
                    self.match.announcements.append(Banner(f"已占领 {event.label}，获得一次重生机会。", (170, 236, 255), ttl=1.8))
                else:
                    self.match.announcements.append(Banner(f"已占领 {event.label}，补给与护甲已刷新。", (255, 220, 148), ttl=1.6))
            elif event.type == SHOW_KILLFEED:
                self._play_audio_event("killfeed", "killfeed")
                self.match.killfeed.insert(0, Banner(event.text, event.color, ttl=event.ttl))
                self.match.killfeed = self.match.killfeed[:5]
            elif event.type == SHAKE_CAMERA:
                self.camera.add_shake(event.amplitude, event.duration)
            elif event.type == RELOAD_COMPLETE and event.is_player:
                self._play_audio_event("reload_complete", "reload_complete")
                self.match.announcements.append(Banner(f"{event.weapon_label} 换弹完成。", (200, 232, 255), ttl=1.0))
            elif event.type == SKILL_COOLDOWN_END:
                self.match.announcements.append(Banner(f"{event.skill_name} 冷却结束。", (170, 232, 255), ttl=1.0))
            elif event.type == PLAYER_ENTER_TRIGGER:
                label = event.label
                if event.kind == "danger":
                    self._play_audio_event("danger", "danger")
                    self.match.announcements.append(Banner(f"进入危险区：{label}", (238, 132, 132), ttl=1.4))
                elif event.kind == "mechanism":
                    self._play_audio_event("mechanism", "mechanism")
                    self.match.announcements.append(Banner(f"机关已启动：{label}", (255, 216, 126), ttl=1.4))
                elif event.kind == "supply":
                    self._play_audio_event("pickup_item", "killfeed")
                    self.match.announcements.append(Banner(f"补给区已激活：{label}", (144, 230, 188), ttl=1.3))
                elif event.kind == "capture":
                    self.match.announcements.append(Banner(f"开始占领：{label}", (168, 214, 255), ttl=1.0))
                else:
                    self.match.announcements.append(Banner(f"已进入区域：{label}", (199, 230, 186), ttl=1.2))
            elif event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    from .menu_scene import MenuScene

                    self.game.change_scene(MenuScene(self.game))
                elif event.key == pygame.K_r and self.match.player.alive:
                    self.match.player.active_weapon.begin_reload(self.match.player)
                elif event.key == pygame.K_q and self.match.player.alive:
                    self.match.player.switch_weapon()
                elif event.key == pygame.K_f and self.match.player.alive:
                    self.match.player_pickup()
                elif event.key == pygame.K_e and self.match.player.alive:
                    if self.match.player_throw_grenade(self.mouse_world):
                        self._play_audio_event("grenade_throw", "grenade_throw")
                        self.match.announcements.append(Banner("已投掷手雷。", (246, 178, 90), ttl=1.2))
                    else:
                        self.match.announcements.append(Banner("没有可用手雷。", (210, 130, 130), ttl=1.0))
                elif event.key == pygame.K_SPACE and self.match.player.alive:
                    keys = pygame.key.get_pressed()
                    move = self.match.player.read_move_input(keys, self.held_movement_keys)
                    if self.match.player.use_mobility_skill(self.match.game_map, move):
                        self._play_audio_event("dash", "mechanism")
                        self.camera.add_shake(4.0, 0.12)
                        self.match.announcements.append(Banner("位移冲刺已释放。", (164, 228, 255), ttl=1.0))
                elif event.key == pygame.K_g and self.match.player.alive:
                    if self.match.player.try_begin_heal():
                        self._play_audio_event("heal_start", "reload_complete")
                        self.match.announcements.append(Banner("正在使用医疗包...", (139, 226, 190), ttl=1.6))
                elif event.key == pygame.K_TAB:
                    self.match.controls_visible = not self.match.controls_visible
                elif event.key == pygame.K_F3:
                    self.debug_visible = not self.debug_visible
                elif event.key == pygame.K_F4:
                    self.debug_geometry_visible = not self.debug_geometry_visible
                elif event.key == pygame.K_F6:
                    self.match.spawn_supply_drop(self.match.player.position + Vector2(0, 30))
                    self.match.announcements.append(Banner("调试：已在玩家附近投放补给。", (247, 213, 116), ttl=2.0))
                elif event.key == pygame.K_F7:
                    self.match.safe_zone.force_advance()
                    self.match.announcements.append(Banner("调试：缩圈阶段已快速推进。", (92, 172, 255), ttl=2.0))

    def update(self, dt: float) -> None:
        keys = pygame.key.get_pressed()
        mouse_buttons = pygame.mouse.get_pressed(3)
        self.mouse_world = self.camera.screen_to_world(Vector2(pygame.mouse.get_pos()))
        self.player_locator_timer = max(0.0, self.player_locator_timer - dt)
        self.match.update(dt, keys, self.mouse_world, bool(mouse_buttons[0]), movement_held_keys=self.held_movement_keys)
        self.match.particles.update(dt, (SCREEN_WIDTH, SCREEN_HEIGHT))
        focus = self.match.player.position if self.match.player.alive else self.match.safe_zone.current_center
        self.camera.update(focus, dt)

    def _track_movement_key_event(self, event: pygame.event.Event) -> None:
        movement_keys = (
            *self.match.player.MOVE_LEFT_KEYS,
            *self.match.player.MOVE_RIGHT_KEYS,
            *self.match.player.MOVE_UP_KEYS,
            *self.match.player.MOVE_DOWN_KEYS,
            *self.match.player.SPRINT_KEYS,
        )
        if event.type == pygame.KEYDOWN and event.key in movement_keys:
            self.held_movement_keys.add(event.key)
        elif event.type == pygame.KEYUP and event.key in movement_keys:
            self.held_movement_keys.discard(event.key)
        elif event.type in (pygame.WINDOWFOCUSLOST, pygame.WINDOWMINIMIZED):
            self.held_movement_keys.clear()

    def draw(self, screen: pygame.Surface) -> None:
        self.match.game_map.draw_parallax(screen, self.camera.position)
        self.match.game_map.draw_ground(screen, self.camera)
        self._draw_puddle_reflections(screen)
        self.match.game_map.draw_decorations(screen, self.camera)
        self.match.game_map.draw_obstacles(screen, self.camera)
        self.match.sync_render_group(self.camera)
        self.match.render_group.draw(screen)
        self._draw_player_locator(screen)
        self.match.particles.draw(screen, self.camera, self.game.fonts["small"])
        self._draw_zone(screen)
        self._draw_local_lighting(screen)
        self.match.particles.draw_weather(screen)
        self.hud.draw(screen, self.camera, self.mouse_world, self.debug_visible, self.debug_geometry_visible)

    def _draw_player_locator(self, screen: pygame.Surface) -> None:
        if self.player_locator_timer <= 0.0 or not self.match.player.alive:
            return
        pos = self.camera.world_to_screen(self.match.player.position)
        phase = (pygame.time.get_ticks() % 900) / 900.0
        if phase > 0.5:
            phase = 1.0 - phase
        pulse = phase * 2.0
        ring_radius = 34 + int(18 * pulse)
        overlay = pygame.Surface((SCREEN_WIDTH, SCREEN_HEIGHT), pygame.SRCALPHA)
        alpha = 110 if self.player_locator_timer > 2.0 else 74
        pygame.draw.circle(overlay, (*self.match.player.accent_color, alpha), pos, ring_radius, width=3)
        pygame.draw.circle(overlay, (*self.match.player.marker_color, alpha + 24), pos, ring_radius + 12, width=1)
        arrow = [(pos[0], pos[1] - 48), (pos[0] - 10, pos[1] - 26), (pos[0] + 10, pos[1] - 26)]
        pygame.draw.polygon(overlay, (*self.match.player.marker_color, 220), arrow)
        screen.blit(overlay, (0, 0))
        if self.player_locator_timer > 2.8:
            draw_outlined_text(screen, self.game.fonts["small"], "你在这里", (pos[0], pos[1] - 68), self.match.player.marker_color, center=True)

    def _draw_zone(self, screen: pygame.Surface) -> None:
        fog = pygame.Surface((SCREEN_WIDTH, SCREEN_HEIGHT), pygame.SRCALPHA)
        fog.fill((8, 13, 19, 86))
        center = self.camera.world_to_screen(self.match.safe_zone.current_center)
        radius_x = int(self.match.safe_zone.current_radius)
        radius_y = self.camera.project_vertical_distance(self.match.safe_zone.current_radius)
        zone_rect = pygame.Rect(center[0] - radius_x, center[1] - radius_y, radius_x * 2, radius_y * 2)
        pygame.draw.ellipse(fog, (0, 0, 0, 0), zone_rect)
        screen.blit(fog, (0, 0))
        pygame.draw.ellipse(screen, (92, 172, 255), zone_rect, width=3)
        if self.match.safe_zone.state == "shrink":
            target_center = self.camera.world_to_screen(self.match.safe_zone.target_center)
            target_radius_x = int(self.match.safe_zone.target_radius)
            target_radius_y = self.camera.project_vertical_distance(self.match.safe_zone.target_radius)
            target_rect = pygame.Rect(
                target_center[0] - target_radius_x,
                target_center[1] - target_radius_y,
                target_radius_x * 2,
                target_radius_y * 2,
            )
            pygame.draw.ellipse(screen, (92, 172, 255), target_rect, width=1)
            pygame.draw.line(screen, (92, 172, 255), center, target_center, 1)

    def _draw_local_lighting(self, screen: pygame.Surface) -> None:
        tint = pygame.Surface((SCREEN_WIDTH, SCREEN_HEIGHT), pygame.SRCALPHA)
        tint.fill((8, 12, 18, 84))
        screen.blit(tint, (0, 0))

        lights = pygame.Surface((SCREEN_WIDTH, SCREEN_HEIGHT), pygame.SRCALPHA)
        for grenade in self.match.grenades:
            pos = self.camera.world_to_screen(grenade.position)
            rect = pygame.Rect(0, 0, 86, 54)
            rect.center = pos
            pygame.draw.ellipse(lights, (255, 190, 100, 34), rect)
        for light in self.match.game_map.light_zones:
            center = self.camera.world_to_screen(Vector2(light.rect.center))
            radius = max(light.rect.width, light.rect.height) // 2
            light_rect = pygame.Rect(0, 0, radius * 2, self.camera.project_vertical_distance(radius) * 2)
            light_rect.center = center
            pygame.draw.ellipse(lights, (*light.color, light.intensity), light_rect)
        for character in self.match.characters:
            if character.alive and character.muzzle_flash_timer > 0.0:
                direction = character.aim_direction if character.aim_direction.length_squared() > 0.0 else Vector2(1, 0)
                muzzle_world = character.position + direction.normalize() * (character.radius + 18)
                pos = self.camera.world_to_screen(muzzle_world)
                pygame.draw.circle(lights, (*character.active_weapon.spec.color, 44), pos, 28)
                pygame.draw.circle(lights, (255, 238, 206, 56), pos, 12)
        for trigger in self.match.game_map.triggers[:12]:
            if trigger.kind == "landmark":
                center = self.camera.world_to_screen(Vector2(trigger.rect.center))
                pygame.draw.circle(lights, (120, 168, 255, 12), center, min(120, max(trigger.rect.width, trigger.rect.height) // 2))

        screen.blit(lights, (0, 0), special_flags=pygame.BLEND_ADD)

        if self.match.player.hp <= self.match.player.max_hp * 0.35:
            pulse = int(60 + 40 * (pygame.time.get_ticks() % 800) / 800)
            border = pygame.Surface((SCREEN_WIDTH, SCREEN_HEIGHT), pygame.SRCALPHA)
            pygame.draw.rect(border, (180, 42, 42, pulse), border.get_rect(), width=18, border_radius=28)
            screen.blit(border, (0, 0))

    def _draw_puddle_reflections(self, screen: pygame.Surface) -> None:
        puddles = [region for region in self.match.game_map.regions if region.kind == "puddle"]
        if not puddles:
            return

        reflection = pygame.Surface((SCREEN_WIDTH, SCREEN_HEIGHT), pygame.SRCALPHA)
        actors = [self.match.player, *[bot for bot in self.match.bots if bot.alive]]
        for puddle in puddles:
            screen_rect = self.camera.world_rect_to_screen_bounds(puddle.rect)
            if screen_rect.right < 0 or screen_rect.bottom < 0 or screen_rect.left > SCREEN_WIDTH or screen_rect.top > SCREEN_HEIGHT:
                continue
            pygame.draw.ellipse(reflection, (90, 140, 188, 28), screen_rect)
            for actor in actors:
                actor_pos = self.camera.world_to_screen(actor.position)
                if screen_rect.collidepoint(actor_pos[0], actor_pos[1] + 28):
                    rect = pygame.Rect(actor_pos[0] - actor.radius, actor_pos[1] + actor.radius, actor.radius * 2, actor.radius)
                    pygame.draw.ellipse(reflection, (*actor.color, 44), rect)
            for light in self.match.game_map.light_zones:
                center = self.camera.world_to_screen(Vector2(light.rect.center))
                if screen_rect.collidepoint(center):
                    pygame.draw.ellipse(reflection, (*light.color, 48), screen_rect.inflate(-8, -8))
        screen.blit(reflection, (0, 0), special_flags=pygame.BLEND_ADD)
