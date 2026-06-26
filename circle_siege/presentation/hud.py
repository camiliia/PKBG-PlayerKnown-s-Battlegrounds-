from __future__ import annotations

import math

import pygame

from ..core.config import AMMO_LABELS, HEALTH_GREEN, SCREEN_HEIGHT, SCREEN_WIDTH, TEXT_LIGHT, TEXT_MUTED, UI_PANEL, ZONE_BLUE
from ..helpers import draw_outlined_text, draw_progress_bar, draw_text_block, format_time, truncate_text


class HUDRenderer:
    def __init__(self, game, match) -> None:
        self.game = game
        self.match = match

    def draw(self, screen: pygame.Surface, camera, mouse_world, debug_visible: bool, debug_geometry_visible: bool) -> None:
        self._draw_pickup_prompt(screen)
        self._draw_top_panel(screen)
        self._draw_weapon_panel(screen)
        self._draw_minimap(screen)
        self._draw_killfeed(screen)
        self._draw_announcements(screen)
        self._draw_player_identity(screen, camera)
        self._draw_crosshair(screen)
        if self.match.countdown > 0.0:
            self._draw_countdown(screen)
        if self.match.controls_visible:
            self._draw_controls(screen)
        if debug_visible:
            self._draw_debug_panel(screen, camera)
        if debug_geometry_visible:
            self._draw_debug_geometry(screen, camera, mouse_world)

    def _draw_pickup_prompt(self, screen: pygame.Surface) -> None:
        pickup = self.match.nearest_pickup_for_player() if self.match.player.alive else None
        if pickup is None:
            return
        panel = pygame.Rect(SCREEN_WIDTH // 2 - 250, SCREEN_HEIGHT - 86, 500, 48)
        pygame.draw.rect(screen, (*UI_PANEL, 235), panel, border_radius=12)
        pygame.draw.rect(screen, (232, 236, 239), panel, width=2, border_radius=12)
        label = truncate_text(self.game.fonts["medium"], f"按 F 拾取：{pickup.label}", panel.width - 40)
        text = self.game.fonts["medium"].render(label, True, TEXT_LIGHT)
        screen.blit(text, text.get_rect(center=panel.center))

    def _draw_top_panel(self, screen: pygame.Surface) -> None:
        panel = pygame.Rect(18, 16, 420, 300)
        pygame.draw.rect(screen, (*UI_PANEL, 235), panel, border_radius=16)
        pygame.draw.rect(screen, self.match.player.accent_color, panel, width=2, border_radius=16)

        zone_label = "收缩中" if self.match.safe_zone.state == "shrink" else "等待中"
        current_region = truncate_text(
            self.game.fonts["small"],
            self.match.game_map.nearest_landmark_name(self.match.player.position),
            panel.width - 104,
        )
        rows = (
            f"呼号：{truncate_text(self.game.fonts['small'], self.match.player.name, panel.width - 96)}",
            f"地图：{truncate_text(self.game.fonts['small'], self.match.theme.label, panel.width - 96)}",
            f"区域：{current_region}",
            f"剩余单位：{self.match.alive_count()}    精英：{self.match.elite_alive_count()}",
            f"藏宝图：{self.match.treasure_maps_found}/{self.match.treasure_map_target}    生存：{format_time(self.match.elapsed)}",
            f"缩圈：{zone_label}  {format_time(self.match.safe_zone.time_to_next())}",
        )
        y = panel.top + 14
        for row in rows:
            text = self.game.fonts["small"].render(row, True, TEXT_LIGHT)
            screen.blit(text, (panel.left + 16, y))
            y += 21

        objective_rect = pygame.Rect(panel.left + 16, y + 4, panel.width - 32, 18)
        draw_text_block(
            screen,
            self.game.fonts["small"],
            self.match.mission_objective_text(),
            objective_rect,
            self.match.player.marker_color,
            line_spacing=0,
            max_lines=1,
        )
        progress_rect = pygame.Rect(panel.left + 16, objective_rect.bottom + 4, panel.width - 32, 18)
        draw_text_block(
            screen,
            self.game.fonts["tiny"],
            self.match.mission_progress_text(),
            progress_rect,
            TEXT_LIGHT,
            line_spacing=0,
            max_lines=1,
        )
        alert_rect = pygame.Rect(panel.left + 16, progress_rect.bottom + 6, panel.width - 32, 18)
        alert_color = (255, 214, 150) if self.match.player_has_agro else TEXT_MUTED
        draw_text_block(
            screen,
            self.game.fonts["tiny"],
            self.match.local_alert_status_text(),
            alert_rect,
            alert_color,
            line_spacing=0,
            max_lines=1,
        )
        guidance_rect = pygame.Rect(panel.left + 16, alert_rect.bottom + 4, panel.width - 32, 18)
        guidance_color = self.match.theme.accent if self.match.player.combat_enabled else (255, 214, 150)
        draw_text_block(
            screen,
            self.game.fonts["tiny"],
            self.match.mission_guidance_text(),
            guidance_rect,
            guidance_color,
            line_spacing=0,
            max_lines=1,
        )

        health_rect = pygame.Rect(panel.left + 16, panel.bottom - 42, panel.width - 32, 14)
        draw_progress_bar(screen, health_rect, self.match.player.hp / self.match.player.max_hp, HEALTH_GREEN)
        armor_rect = pygame.Rect(panel.left + 16, panel.bottom - 20, panel.width - 32, 11)
        draw_progress_bar(screen, armor_rect, self.match.player.armor / max(1, self.match.player.max_armor), ZONE_BLUE)

    def _draw_weapon_panel(self, screen: pygame.Surface) -> None:
        panel = pygame.Rect(18, SCREEN_HEIGHT - 166, 470, 142)
        pygame.draw.rect(screen, (*UI_PANEL, 235), panel, border_radius=16)
        pygame.draw.rect(screen, (230, 234, 236), panel, width=2, border_radius=16)

        weapon = self.match.player.active_weapon
        label = truncate_text(self.game.fonts["title"], weapon.spec.label, 210)
        weapon_title = self.game.fonts["title"].render(label, True, weapon.spec.color)
        screen.blit(weapon_title, (panel.left + 16, panel.top + 12))

        ammo_value = "--" if not self.match.player.combat_enabled else f"{weapon.magazine:02d}"
        ammo_text = self.game.fonts["hero_small"].render(ammo_value, True, TEXT_LIGHT)
        reserve = self.match.player.ammo.get(weapon.spec.ammo_type, 0)
        reserve_text = self.game.fonts["medium"].render(f"/ {reserve:03d}", True, TEXT_MUTED)
        screen.blit(ammo_text, (panel.left + 16, panel.top + 34))
        screen.blit(reserve_text, (panel.left + 110, panel.top + 62))

        status_line = f"状态：{weapon.state_label(self.match.player)}"
        if not self.match.player.combat_enabled:
            status_line += "（拾取武器后可攻击）"
        draw_text_block(
            screen,
            self.game.fonts["tiny"],
            truncate_text(self.game.fonts["tiny"], status_line, panel.width - 210),
            pygame.Rect(panel.left + 16, panel.top + 76, panel.width - 210, 18),
            self.match.player.marker_color if self.match.player.combat_enabled else (255, 214, 150),
            line_spacing=0,
            max_lines=1,
        )

        ammo_line = f"弹药：{AMMO_LABELS[weapon.spec.ammo_type]}    医疗包：{self.match.player.medkits}"
        draw_text_block(
            screen,
            self.game.fonts["small"],
            ammo_line,
            pygame.Rect(panel.left + 16, panel.bottom - 46, panel.width - 210, 22),
            TEXT_LIGHT,
            line_spacing=0,
            max_lines=1,
        )

        slot_line = (
            f"武器位 {self.match.player.active_weapon_index + 1}/{len(self.match.player.weapons)}"
            f"  手雷 {self.match.player.grenade_count}"
            f"  技能 {max(0, self.match.player.skill_cooldown_timer):.1f}s"
        )
        draw_text_block(
            screen,
            self.game.fonts["tiny"],
            slot_line,
            pygame.Rect(panel.left + 16, panel.bottom - 24, panel.width - 210, 18),
            TEXT_MUTED,
            line_spacing=0,
            max_lines=1,
        )

        if weapon.is_reloading:
            progress = 1.0 - (weapon.reload_timer / weapon.spec.reload_time)
            draw_progress_bar(screen, pygame.Rect(panel.right - 154, panel.top + 18, 124, 16), progress, self.match.theme.accent)
        if self.match.player.heal_timer > 0.0:
            progress = 1.0 - (self.match.player.heal_timer / 2.7)
            draw_progress_bar(screen, pygame.Rect(panel.right - 154, panel.top + 48, 124, 16), progress, (110, 205, 170))
        if self.match.active_capture_label:
            cap_rect = pygame.Rect(panel.right - 184, panel.top + 84, 152, 12)
            draw_progress_bar(screen, cap_rect, self.match.active_capture_progress, (124, 220, 255))
            cap_label = truncate_text(self.game.fonts["tiny"], f"占领中：{self.match.active_capture_label}", 152)
            cap_text = self.game.fonts["tiny"].render(cap_label, True, TEXT_LIGHT)
            screen.blit(cap_text, (panel.right - 184, panel.top + 64))

    def _draw_minimap(self, screen: pygame.Surface) -> None:
        minimap = self.match.game_map.minimap_base.copy()
        scale_x = minimap.get_width() / max(1, self.match.game_map.bounds.width)
        scale_y = minimap.get_height() / max(1, self.match.game_map.bounds.height)
        zone_center = (int(self.match.safe_zone.current_center.x * scale_x), int(self.match.safe_zone.current_center.y * scale_y))
        zone_radius = int(self.match.safe_zone.current_radius * scale_x)
        pygame.draw.circle(minimap, (34, 61, 84), zone_center, zone_radius, width=2)

        for pickup in self.match.pickups:
            if pickup.is_supply:
                pygame.draw.circle(minimap, (247, 213, 116), (int(pickup.position.x * scale_x), int(pickup.position.y * scale_y)), 3)

        for bot in self.match.bots:
            if not bot.alive:
                continue
            center = (int(bot.position.x * scale_x), int(bot.position.y * scale_y))
            radius = 5 if bot.is_elite else 3
            color = bot.accent_color if bot.is_elite else bot.color
            pygame.draw.circle(minimap, color, center, radius)
            if bot.is_elite:
                pygame.draw.circle(minimap, bot.marker_color, center, radius + 2, width=1)

        player_center = (int(self.match.player.position.x * scale_x), int(self.match.player.position.y * scale_y))
        pygame.draw.circle(minimap, self.match.player.color, player_center, 5)
        pygame.draw.circle(minimap, self.match.player.marker_color, player_center, 7, width=2)

        frame = pygame.Rect(SCREEN_WIDTH - minimap.get_width() - 24, 18, minimap.get_width() + 12, minimap.get_height() + 40)
        pygame.draw.rect(screen, (*UI_PANEL, 235), frame, border_radius=14)
        pygame.draw.rect(screen, (230, 234, 236), frame, width=2, border_radius=14)
        title = self.game.fonts["small"].render("战术地图", True, TEXT_LIGHT)
        screen.blit(title, (frame.left + 10, frame.top + 8))
        screen.blit(minimap, (frame.left + 6, frame.top + 28))

    def _draw_killfeed(self, screen: pygame.Surface) -> None:
        y = 320
        for banner in self.match.killfeed:
            box = pygame.Rect(18, y, 380, 30)
            pygame.draw.rect(screen, (*UI_PANEL, 220), box, border_radius=10)
            text = self.game.fonts["tiny"].render(truncate_text(self.game.fonts["tiny"], banner.text, box.width - 24), True, banner.color)
            screen.blit(text, (box.left + 12, box.top + 6))
            y += 36

    def _draw_announcements(self, screen: pygame.Surface) -> None:
        y = 18
        for banner in self.match.announcements[:2]:
            text = self.game.fonts["small"].render(banner.text, True, banner.color)
            box = text.get_rect(center=(SCREEN_WIDTH // 2, y + 16))
            pad = box.inflate(30, 14)
            pygame.draw.rect(screen, (*UI_PANEL, 218), pad, border_radius=14)
            pygame.draw.rect(screen, banner.color, pad, width=2, border_radius=14)
            screen.blit(text, box)
            y += 42

    def _draw_player_identity(self, screen: pygame.Surface, camera) -> None:
        if not self.match.player.alive:
            return
        pos = camera.world_to_screen(self.match.player.position)
        label = self.game.fonts["small"].render(self.match.player.name, True, self.match.player.marker_color)
        label_rect = label.get_rect(center=(pos[0], pos[1] - self.match.player.radius - 30))
        tag_rect = label_rect.inflate(16, 8)
        pygame.draw.rect(screen, (*UI_PANEL, 220), tag_rect, border_radius=10)
        pygame.draw.rect(screen, self.match.player.accent_color, tag_rect, width=2, border_radius=10)
        screen.blit(label, label_rect)

    def _draw_crosshair(self, screen: pygame.Surface) -> None:
        if not self.match.player.alive:
            return
        weapon = self.match.player.active_weapon
        spread = 16 + int((weapon.spec.spread + weapon.spec.move_spread * self.match.player.movement_ratio()) * 360)
        mx, my = pygame.mouse.get_pos()
        pygame.draw.circle(screen, (0, 0, 0), (mx, my), 12, width=2)
        color = weapon.spec.color if self.match.player.combat_enabled else TEXT_MUTED
        pygame.draw.line(screen, color, (mx - spread, my), (mx - 6, my), 2)
        pygame.draw.line(screen, color, (mx + 6, my), (mx + spread, my), 2)
        pygame.draw.line(screen, color, (mx, my - spread), (mx, my - 6), 2)
        pygame.draw.line(screen, color, (mx, my + 6), (mx, my + spread), 2)

    def _draw_countdown(self, screen: pygame.Surface) -> None:
        value = max(1, math.ceil(self.match.countdown))
        draw_outlined_text(screen, self.game.fonts["hero"], str(value), (SCREEN_WIDTH // 2, SCREEN_HEIGHT // 2 - 30), TEXT_LIGHT, center=True)
        sub = self.game.fonts["medium"].render("战斗准备中...", True, TEXT_MUTED)
        screen.blit(sub, sub.get_rect(center=(SCREEN_WIDTH // 2, SCREEN_HEIGHT // 2 + 40)))

    def _draw_controls(self, screen: pygame.Surface) -> None:
        panel = pygame.Rect(SCREEN_WIDTH - 386, SCREEN_HEIGHT - 244, 364, 220)
        pygame.draw.rect(screen, (*UI_PANEL, 236), panel, border_radius=16)
        pygame.draw.rect(screen, (232, 236, 239), panel, width=2, border_radius=16)

        title = self.game.fonts["medium"].render("操作说明", True, TEXT_LIGHT)
        screen.blit(title, (panel.left + 16, panel.top + 12))
        tip = self.game.fonts["tiny"].render("先拿武器，再搜图；枪声和爆炸只会惊动附近守卫", True, TEXT_LIGHT)
        screen.blit(tip, (panel.left + 16, panel.top + 34))

        lines = (
            "WASD 移动    Shift 冲刺",
            "鼠标瞄准    左键开火",
            "R 换弹      Q 切枪",
            "F 拾取      E 投掷手雷",
            "Space 位移技能",
            "G 使用医疗包   Esc 返回菜单",
            "Tab 帮助    F3 调试面板",
            "F4 几何叠层  F6 空投调试",
            "F7 快速推进缩圈",
        )
        y = panel.top + 58
        for line in lines:
            text = self.game.fonts["tiny"].render(line, True, TEXT_MUTED)
            screen.blit(text, (panel.left + 16, y))
            y += 18

    def _draw_debug_panel(self, screen: pygame.Surface, camera) -> None:
        panel = pygame.Rect(SCREEN_WIDTH - 352, 250, 330, 332)
        pygame.draw.rect(screen, (12, 18, 23), panel, border_radius=16)
        pygame.draw.rect(screen, (106, 196, 248), panel, width=2, border_radius=16)
        title = self.game.fonts["medium"].render("调试面板", True, TEXT_LIGHT)
        screen.blit(title, (panel.left + 16, panel.top + 12))

        player_pos = f"{int(self.match.player.position.x)}, {int(self.match.player.position.y)}"
        camera_pos = f"{int(camera.position.x)}, {int(camera.position.y)}"
        zone_center = f"{int(self.match.safe_zone.current_center.x)}, {int(self.match.safe_zone.current_center.y)}"
        zone_state = {"hold": "等待", "shrink": "收缩", "final": "决赛"}[self.match.safe_zone.state]
        lines = (
            f"呼号: {self.match.player.name}",
            f"FPS: {self.game.current_fps:5.1f}    dt: {self.game.delta_time * 1000:4.1f}ms",
            f"地图主题: {self.match.theme.label}",
            f"玩家坐标: {player_pos}",
            f"镜头坐标: {camera_pos}",
            f"当前区域: {self.match.game_map.nearest_landmark_name(self.match.player.position)}",
            f"血量/护甲: {self.match.player.hp}/{self.match.player.max_hp}  护甲 {self.match.player.armor}",
            f"弹体/掉落: {len(self.match.projectiles) + len(self.match.grenades)} / {len(self.match.pickups)}",
            f"存活/精英: {self.match.alive_count()} / {self.match.elite_alive_count()}",
            f"特效数量: {len(self.match.particles.effects)}",
            f"毒圈阶段: {zone_state}  半径 {int(self.match.safe_zone.current_radius)}",
            f"毒圈中心: {zone_center}",
        )
        y = panel.top + 42
        for line in lines:
            text = self.game.fonts["debug"].render(line, True, TEXT_LIGHT)
            screen.blit(text, (panel.left + 16, y))
            y += 20

        for bot in [bot for bot in self.match.bots if bot.alive][:3]:
            info = self.game.fonts["debug"].render(f"{bot.name}: {bot.debug_state} -> {bot.debug_target_name}", True, bot.accent_color if bot.is_elite else bot.color)
            screen.blit(info, (panel.left + 16, y))
            y += 18

    def _draw_debug_geometry(self, screen: pygame.Surface, camera, mouse_world) -> None:
        view = camera.view_rect().inflate(120, 120)
        for obstacle in self.match.game_map.obstacles:
            if view.colliderect(obstacle.rect):
                rect = obstacle.rect.move(-camera.position.x, -camera.position.y)
                pygame.draw.rect(screen, (90, 232, 199), rect, width=1, border_radius=obstacle.border_radius)

        state_colors = {
            "交战": (236, 118, 118),
            "进圈": (92, 172, 255),
            "搜刮": (247, 213, 116),
            "追击": (181, 153, 255),
            "治疗": (110, 205, 170),
            "掩护": (120, 220, 200),
            "巡逻": (170, 170, 170),
        }
        for bot in self.match.bots:
            if not bot.alive or not view.collidepoint(bot.position):
                continue
            start = camera.world_to_screen(bot.position)
            end = camera.world_to_screen(bot.debug_focus)
            color = state_colors.get(bot.debug_state, (170, 170, 170))
            if bot.is_elite:
                color = (255, 128, 128)
            pygame.draw.line(screen, color, start, end, 2)
            pygame.draw.circle(screen, color, end, 5, width=1)

        player_rect = self.match.player.rect().move(-camera.position.x, -camera.position.y)
        pygame.draw.rect(screen, self.match.player.marker_color, player_rect, width=1, border_radius=8)
        aim_end = camera.world_to_screen(mouse_world)
        pygame.draw.line(screen, self.match.player.marker_color, camera.world_to_screen(self.match.player.position), aim_end, 1)
