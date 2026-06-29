from __future__ import annotations

import argparse
import os
import sys
from dataclasses import dataclass
from pathlib import Path

os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import pygame

from circle_siege.core.config import ARENA_THEMES, DEFAULT_THEME_ID, THEME_BY_ID, WORKSPACE_ROOT
from circle_siege.maps.grid_map_loader import GridMapDocument, load_grid_map_document, save_grid_map_document


WINDOW_SIZE = (1600, 940)
SIDEBAR_WIDTH = 350
MIN_ZOOM = 0.12
MAX_ZOOM = 3.5
BACKGROUND = (10, 13, 18)
CANVAS_BG = (14, 18, 24)
SIDEBAR_BG = (18, 24, 31)
PANEL_BG = (25, 32, 42)
BORDER = (62, 76, 90)
TEXT = (232, 238, 244)
TEXT_MUTED = (154, 166, 178)
TEXT_ACTIVE = (255, 221, 132)
OK = (110, 224, 168)
WARN = (255, 190, 92)


def load_ui_font(size: int, *, bold: bool = False) -> pygame.font.Font:
    font_paths = (
        Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts" / "msyh.ttc",
        Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts" / "simhei.ttf",
        Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts" / "simsun.ttc",
    )
    for path in font_paths:
        if path.exists():
            font = pygame.font.Font(str(path), size)
            font.set_bold(bold)
            return font
    font = pygame.font.Font(None, size)
    font.set_bold(bold)
    return font


@dataclass(frozen=True)
class LayerSpec:
    key: str
    label: str
    color: tuple[int, int, int]
    max_value: int


LAYERS = (
    LayerSpec("collision", "障碍碰撞", (238, 86, 86), 1),
    LayerSpec("player_spawn", "玩家出生点", (96, 218, 255), 1),
    LayerSpec("enemy_spawn", "怪物出生点", (255, 146, 82), 4),
    LayerSpec("loot_spawn", "物品掉落点", (245, 214, 96), 4),
)


class GridMapEditor:
    def __init__(self, screen: pygame.Surface, theme_id: str) -> None:
        self.screen = screen
        self.canvas_width = WINDOW_SIZE[0] - SIDEBAR_WIDTH
        self.canvas_height = WINDOW_SIZE[1]
        self.themes = list(ARENA_THEMES)
        self.theme_index = self._theme_index(theme_id)
        self.theme = self.themes[self.theme_index]
        self.document: GridMapDocument = load_grid_map_document(self.theme)
        self.background = self._load_background()

        self.font = load_ui_font(22)
        self.small_font = load_ui_font(18)
        self.title_font = load_ui_font(30, bold=True)
        self.value_font = load_ui_font(17, bold=True)

        self.zoom = self._initial_zoom()
        self.camera = pygame.Vector2(0, 0)
        self.current_layer = 0
        self.selected_value = 1
        self.brush_size = 1
        self.show_grid = True
        self.painting = False
        self.erasing = False
        self.panning = False
        self.pan_last = pygame.Vector2()
        self.dirty = False
        self.status = "就绪"
        self.status_color = OK
        self.layer_button_rects: list[tuple[pygame.Rect, int]] = []
        self.value_button_rects: list[tuple[pygame.Rect, int]] = []
        self.command_button_rects: list[tuple[pygame.Rect, str]] = []

        self._clamp_camera()

    @property
    def layer(self) -> LayerSpec:
        return LAYERS[self.current_layer]

    @property
    def world_size(self) -> tuple[int, int]:
        return self.document.cols * self.document.cell_size, self.document.rows * self.document.cell_size

    @staticmethod
    def _theme_index(theme_id: str) -> int:
        for index, theme in enumerate(ARENA_THEMES):
            if theme.identifier == theme_id:
                return index
        return 0

    def _initial_zoom(self) -> float:
        width, height = self.world_size
        return max(MIN_ZOOM, min(self.canvas_width / width, self.canvas_height / height, MAX_ZOOM))

    def _load_background(self) -> pygame.Surface | None:
        background = self.document.background_image
        if not background:
            return None
        path = Path(background)
        if not path.is_absolute():
            path = WORKSPACE_ROOT / path
        if not path.exists():
            return None
        try:
            image = pygame.image.load(str(path)).convert()
        except pygame.error:
            return None
        return pygame.transform.smoothscale(image, self.world_size)

    def run(self) -> None:
        clock = pygame.time.Clock()
        running = True
        while running:
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    running = False
                else:
                    self._handle_event(event)

            self._draw()
            pygame.display.flip()
            clock.tick(60)

        if self.dirty:
            self._save()

    def _handle_event(self, event: pygame.event.Event) -> None:
        if event.type == pygame.KEYDOWN:
            self._handle_key(event)
            return

        if event.type == pygame.MOUSEWHEEL:
            mouse = pygame.mouse.get_pos()
            if self._in_canvas(mouse):
                self._zoom_at(mouse, event.y)
            return

        if event.type == pygame.MOUSEBUTTONDOWN:
            if event.button == 1 and self._in_sidebar(event.pos):
                self._handle_sidebar_click(event.pos)
                return
            if event.button in (4, 5) and self._in_canvas(event.pos):
                self._zoom_at(event.pos, 1 if event.button == 4 else -1)
                return
            if event.button == 2 and self._in_canvas(event.pos):
                self.panning = True
                self.pan_last = pygame.Vector2(event.pos)
                return
            if event.button in (1, 3) and self._in_canvas(event.pos):
                self.painting = True
                self.erasing = event.button == 3
                self._paint_at(event.pos)
                return

        if event.type == pygame.MOUSEBUTTONUP:
            if event.button in (1, 3):
                self.painting = False
            if event.button == 2:
                self.panning = False
            return

        if event.type == pygame.MOUSEMOTION:
            if self.panning:
                current = pygame.Vector2(event.pos)
                delta = current - self.pan_last
                self.pan_last = current
                self.camera -= delta / self.zoom
                self._clamp_camera()
            elif self.painting:
                self._paint_at(event.pos)

    def _handle_key(self, event: pygame.event.Event) -> None:
        ctrl = bool(event.mod & pygame.KMOD_CTRL)
        shift = bool(event.mod & pygame.KMOD_SHIFT)
        if ctrl and event.key == pygame.K_s:
            self._save()
            return
        if event.key == pygame.K_ESCAPE:
            pygame.event.post(pygame.event.Event(pygame.QUIT))
            return
        if event.key in (pygame.K_1, pygame.K_2, pygame.K_3, pygame.K_4):
            self._select_layer(event.key - pygame.K_1)
            return
        if event.key == pygame.K_g:
            self.show_grid = not self.show_grid
            return
        if event.key == pygame.K_q:
            self.selected_value = max(1, self.selected_value - 1)
            return
        if event.key == pygame.K_e:
            self.selected_value = min(self.layer.max_value, self.selected_value + 1)
            return
        if event.key == pygame.K_LEFTBRACKET:
            self.brush_size = max(1, self.brush_size - 1)
            return
        if event.key == pygame.K_RIGHTBRACKET:
            self.brush_size = min(9, self.brush_size + 1)
            return
        if event.key == pygame.K_TAB:
            self._switch_theme(-1 if shift else 1)
            return
        if event.key == pygame.K_r:
            self._reload()

    def _switch_theme(self, step: int) -> None:
        if self.dirty:
            self._save()
        self.theme_index = (self.theme_index + step) % len(self.themes)
        self.theme = self.themes[self.theme_index]
        self.document = load_grid_map_document(self.theme)
        self.background = self._load_background()
        self.zoom = self._initial_zoom()
        self.camera.update(0, 0)
        self._clamp_camera()
        self.dirty = False
        self.status = f"已载入 {self.theme.identifier}"
        self.status_color = OK

    def _reload(self) -> None:
        self.document = load_grid_map_document(self.theme)
        self.background = self._load_background()
        self.dirty = False
        self.status = "已从磁盘重新载入"
        self.status_color = OK

    def _save(self) -> None:
        save_grid_map_document(self.document)
        self.dirty = False
        self.status = f"已保存 {self.document.path.name}"
        self.status_color = OK

    def _in_canvas(self, pos: tuple[int, int]) -> bool:
        return 0 <= pos[0] < self.canvas_width and 0 <= pos[1] < self.canvas_height

    def _in_sidebar(self, pos: tuple[int, int]) -> bool:
        return self.canvas_width <= pos[0] < WINDOW_SIZE[0] and 0 <= pos[1] < WINDOW_SIZE[1]

    def _select_layer(self, index: int) -> None:
        if not 0 <= index < len(LAYERS):
            return
        self.current_layer = index
        self.selected_value = min(self.selected_value, self.layer.max_value)
        self.status = f"当前图层：{self.layer.label}"
        self.status_color = OK

    def _handle_sidebar_click(self, pos: tuple[int, int]) -> None:
        for rect, index in self.layer_button_rects:
            if rect.collidepoint(pos):
                self._select_layer(index)
                return
        for rect, value in self.value_button_rects:
            if rect.collidepoint(pos):
                self.selected_value = value
                self.status = f"当前数值：{value}"
                self.status_color = OK
                return
        for rect, command in self.command_button_rects:
            if not rect.collidepoint(pos):
                continue
            if command == "save":
                self._save()
            elif command == "reload":
                self._reload()
            elif command == "grid":
                self.show_grid = not self.show_grid
                self.status = "已显示网格" if self.show_grid else "已隐藏网格"
                self.status_color = OK
            elif command == "next_theme":
                self._switch_theme(1)
            elif command == "prev_theme":
                self._switch_theme(-1)
            return

    def _zoom_at(self, screen_pos: tuple[int, int], wheel_y: int) -> None:
        before = self._screen_to_world(screen_pos)
        factor = 1.12 ** wheel_y
        self.zoom = max(MIN_ZOOM, min(MAX_ZOOM, self.zoom * factor))
        self.camera = before - pygame.Vector2(screen_pos) / self.zoom
        self._clamp_camera()

    def _screen_to_world(self, pos: tuple[int, int]) -> pygame.Vector2:
        return pygame.Vector2(pos[0] / self.zoom + self.camera.x, pos[1] / self.zoom + self.camera.y)

    def _screen_rect_for_cell(self, col: int, row: int) -> pygame.Rect:
        size = max(1, int(round(self.document.cell_size * self.zoom)))
        return pygame.Rect(
            int(round((col * self.document.cell_size - self.camera.x) * self.zoom)),
            int(round((row * self.document.cell_size - self.camera.y) * self.zoom)),
            size,
            size,
        )

    def _cell_at(self, pos: tuple[int, int]) -> tuple[int, int] | None:
        world = self._screen_to_world(pos)
        col = int(world.x // self.document.cell_size)
        row = int(world.y // self.document.cell_size)
        if 0 <= col < self.document.cols and 0 <= row < self.document.rows:
            return col, row
        return None

    def _paint_at(self, pos: tuple[int, int]) -> None:
        cell = self._cell_at(pos)
        if cell is None:
            return
        col, row = cell
        radius = self.brush_size // 2
        changed = False
        for y in range(row - radius, row + radius + 1):
            for x in range(col - radius, col + radius + 1):
                if not (0 <= x < self.document.cols and 0 <= y < self.document.rows):
                    continue
                if self._paint_cell(x, y):
                    changed = True
        if changed:
            self.dirty = True
            self.status = "有未保存修改"
            self.status_color = WARN

    def _paint_cell(self, col: int, row: int) -> bool:
        layer = self.layer.key
        matrix = self.document.layers[layer]
        old_value = matrix[row][col]
        value = 0 if self.erasing else min(self.selected_value, self.layer.max_value)

        if layer != "collision" and value > 0 and self.document.layers["collision"][row][col] > 0:
            return False

        if old_value == value:
            return False
        matrix[row][col] = value

        if layer == "collision" and value > 0:
            for marker_layer in ("player_spawn", "enemy_spawn", "loot_spawn"):
                self.document.layers[marker_layer][row][col] = 0
        return True

    def _clamp_camera(self) -> None:
        width, height = self.world_size
        max_x = max(0.0, width - self.canvas_width / self.zoom)
        max_y = max(0.0, height - self.canvas_height / self.zoom)
        self.camera.x = max(0.0, min(max_x, self.camera.x))
        self.camera.y = max(0.0, min(max_y, self.camera.y))

    def _visible_cell_range(self) -> tuple[range, range]:
        cell_size = self.document.cell_size
        start_col = max(0, int(self.camera.x // cell_size) - 1)
        end_col = min(self.document.cols, int((self.camera.x + self.canvas_width / self.zoom) // cell_size) + 2)
        start_row = max(0, int(self.camera.y // cell_size) - 1)
        end_row = min(self.document.rows, int((self.camera.y + self.canvas_height / self.zoom) // cell_size) + 2)
        return range(start_col, end_col), range(start_row, end_row)

    def _draw(self) -> None:
        self.screen.fill(BACKGROUND)
        self._draw_canvas()
        self._draw_sidebar()

    def _draw_canvas(self) -> None:
        canvas = pygame.Rect(0, 0, self.canvas_width, self.canvas_height)
        self.screen.fill(CANVAS_BG, canvas)
        previous_clip = self.screen.get_clip()
        self.screen.set_clip(canvas)
        self._draw_background()
        self._draw_layers()
        if self.show_grid:
            self._draw_grid()
        self.screen.set_clip(previous_clip)
        pygame.draw.line(self.screen, BORDER, (self.canvas_width, 0), (self.canvas_width, self.canvas_height), 2)

    def _draw_background(self) -> None:
        if self.background is None:
            return
        world_width = self.canvas_width / self.zoom
        world_height = self.canvas_height / self.zoom
        visible = pygame.Rect(int(self.camera.x), int(self.camera.y), int(world_width) + 2, int(world_height) + 2)
        visible = visible.clip(self.background.get_rect())
        if visible.width <= 0 or visible.height <= 0:
            return
        view = self.background.subsurface(visible)
        scaled_size = (max(1, int(round(visible.width * self.zoom))), max(1, int(round(visible.height * self.zoom))))
        scaled = pygame.transform.smoothscale(view, scaled_size)
        target = ((visible.x - self.camera.x) * self.zoom, (visible.y - self.camera.y) * self.zoom)
        self.screen.blit(scaled, target)

    def _draw_layers(self) -> None:
        cols, rows = self._visible_cell_range()
        overlay = pygame.Surface((self.canvas_width, self.canvas_height), pygame.SRCALPHA)
        for row in rows:
            for col in cols:
                rect = self._screen_rect_for_cell(col, row)
                if self.document.layers["collision"][row][col] > 0:
                    pygame.draw.rect(overlay, (238, 86, 86, 112), rect)
                    pygame.draw.rect(overlay, (255, 120, 120, 170), rect, 1)
                for spec in LAYERS[1:]:
                    value = self.document.layers[spec.key][row][col]
                    if value > 0:
                        self._draw_marker(overlay, rect, spec, value, spec.key == self.layer.key)
        self.screen.blit(overlay, (0, 0))

    def _draw_marker(self, surface: pygame.Surface, rect: pygame.Rect, spec: LayerSpec, value: int, active: bool) -> None:
        color = spec.color
        alpha = 230 if active else 145
        center = rect.center
        radius = max(4, min(18, rect.width // 3))
        if spec.key == "player_spawn":
            pygame.draw.circle(surface, (*color, alpha), center, radius)
            pygame.draw.circle(surface, (255, 255, 255, alpha), center, radius, 2)
        elif spec.key == "enemy_spawn":
            points = [(center[0], center[1] - radius), (center[0] - radius, center[1] + radius), (center[0] + radius, center[1] + radius)]
            pygame.draw.polygon(surface, (*color, alpha), points)
            pygame.draw.polygon(surface, (255, 255, 255, alpha), points, 2)
        else:
            points = [(center[0], center[1] - radius), (center[0] - radius, center[1]), (center[0], center[1] + radius), (center[0] + radius, center[1])]
            pygame.draw.polygon(surface, (*color, alpha), points)
            pygame.draw.polygon(surface, (255, 255, 255, alpha), points, 2)
        if rect.width >= 28 and value > 1:
            text = self.value_font.render(str(value), True, (15, 18, 22))
            surface.blit(text, text.get_rect(center=center))

    def _draw_grid(self) -> None:
        cell = self.document.cell_size
        scaled = cell * self.zoom
        if scaled < 7:
            return
        color = (255, 255, 255, 42)
        start_col = int(self.camera.x // cell)
        end_col = int((self.camera.x + self.canvas_width / self.zoom) // cell) + 2
        start_row = int(self.camera.y // cell)
        end_row = int((self.camera.y + self.canvas_height / self.zoom) // cell) + 2
        for col in range(max(0, start_col), min(self.document.cols + 1, end_col)):
            x = int(round((col * cell - self.camera.x) * self.zoom))
            pygame.draw.line(self.screen, color, (x, 0), (x, self.canvas_height))
        for row in range(max(0, start_row), min(self.document.rows + 1, end_row)):
            y = int(round((row * cell - self.camera.y) * self.zoom))
            pygame.draw.line(self.screen, color, (0, y), (self.canvas_width, y))

    def _draw_sidebar(self) -> None:
        x = self.canvas_width
        sidebar = pygame.Rect(x, 0, SIDEBAR_WIDTH, WINDOW_SIZE[1])
        self.layer_button_rects.clear()
        self.value_button_rects.clear()
        self.command_button_rects.clear()
        pygame.draw.rect(self.screen, SIDEBAR_BG, sidebar)
        y = 22
        y = self._text("二维地图标点工具", x + 22, y, self.title_font, TEXT_ACTIVE) + 14
        y = self._text(f"地图：{self.theme.identifier}", x + 22, y, self.font, TEXT) + 6
        y = self._text(f"尺寸：{self.document.cols} x {self.document.rows} 格", x + 22, y, self.small_font, TEXT_MUTED) + 4
        y = self._text(f"文件：{self.document.path.name}", x + 22, y, self.small_font, TEXT_MUTED) + 18

        y = self._panel_title("图层", x + 18, y)
        for index, spec in enumerate(LAYERS):
            active = index == self.current_layer
            rect = pygame.Rect(x + 22, y, SIDEBAR_WIDTH - 44, 34)
            self.layer_button_rects.append((rect, index))
            pygame.draw.rect(self.screen, PANEL_BG if active else SIDEBAR_BG, rect, border_radius=6)
            pygame.draw.rect(self.screen, spec.color if active else BORDER, rect, 1, border_radius=6)
            pygame.draw.rect(self.screen, spec.color, pygame.Rect(rect.x + 10, rect.y + 9, 16, 16), border_radius=3)
            self._text(f"{index + 1}. {spec.label}", rect.x + 34, rect.y + 8, self.small_font, TEXT_ACTIVE if active else TEXT)
            y += 40
        y += 10

        y = self._panel_title("画笔", x + 18, y)
        y = self._text(f"当前图层：{self.layer.label}", x + 22, y, self.font, TEXT) + 8
        y = self._text("标记数值：", x + 22, y, self.small_font, TEXT_MUTED) + 6
        value_y = y
        button_size = 34
        for value in range(1, self.layer.max_value + 1):
            rect = pygame.Rect(x + 22 + (value - 1) * 42, value_y, button_size, button_size)
            self.value_button_rects.append((rect, value))
            active = value == self.selected_value
            pygame.draw.rect(self.screen, PANEL_BG if active else SIDEBAR_BG, rect, border_radius=6)
            pygame.draw.rect(self.screen, self.layer.color if active else BORDER, rect, 2 if active else 1, border_radius=6)
            text_color = TEXT_ACTIVE if active else TEXT_MUTED
            label = self.value_font.render(str(value), True, text_color)
            self.screen.blit(label, label.get_rect(center=rect.center))
        y = value_y + button_size + 10
        y = self._text(f"画笔大小：{self.brush_size}  （[ / ] 调整）", x + 22, y, self.small_font, TEXT_MUTED) + 18

        y = self._panel_title("操作", x + 18, y)
        controls = (
            "左键拖动：标记当前图层",
            "右键拖动：擦除当前图层",
            "中键拖动：移动视野",
            "滚轮：缩放地图",
            "1-4：切换图层",
            "Q/E：减少/增加标记数值",
            "Ctrl+S：保存",
            "G：显示/隐藏网格",
            "Tab / Shift+Tab：切换地图",
            "R：重新载入当前文件",
        )
        for line in controls:
            y = self._text(line, x + 22, y, self.small_font, TEXT_MUTED) + 4
        y += 14

        y = self._panel_title("快捷按钮", x + 18, y)
        buttons = (
            ("保存", "save"),
            ("重载", "reload"),
            ("网格", "grid"),
            ("上一张", "prev_theme"),
            ("下一张", "next_theme"),
        )
        for index, (label, command) in enumerate(buttons):
            rect = pygame.Rect(x + 22 + (index % 2) * 148, y + (index // 2) * 38, 132, 30)
            self.command_button_rects.append((rect, command))
            pygame.draw.rect(self.screen, PANEL_BG, rect, border_radius=6)
            pygame.draw.rect(self.screen, BORDER, rect, 1, border_radius=6)
            text = self.small_font.render(label, True, TEXT)
            self.screen.blit(text, text.get_rect(center=rect.center))
        y += ((len(buttons) + 1) // 2) * 38 + 12

        y = self._panel_title("状态", x + 18, y)
        self._text(self.status, x + 22, y, self.small_font, self.status_color)
        dirty = "未保存：是" if self.dirty else "未保存：否"
        self._text(dirty, x + 22, y + 24, self.small_font, WARN if self.dirty else OK)

    def _panel_title(self, text: str, x: int, y: int) -> int:
        pygame.draw.line(self.screen, BORDER, (x, y), (x + SIDEBAR_WIDTH - 36, y))
        return self._text(text, x + 4, y + 10, self.font, TEXT_ACTIVE) + 8

    def _text(self, text: str, x: int, y: int, font: pygame.font.Font, color: tuple[int, int, int]) -> int:
        image = font.render(text, True, color)
        self.screen.blit(image, (x, y))
        return y + image.get_height()


def resolve_theme_id(value: str | None) -> str:
    if not value:
        return DEFAULT_THEME_ID
    normalized = Path(value).stem.lower()
    aliases = {
        "cyber_city": "cyber_city_tmx",
        "village": "village_tmx",
        "village1": "village_tmx",
        "temple": "temple_tmx",
        "temple1": "temple_tmx",
        "scene": "courtyard_tmx",
        "courtyard": "courtyard_tmx",
    }
    if value in THEME_BY_ID:
        return value
    if normalized in aliases:
        return aliases[normalized]
    for theme in ARENA_THEMES:
        if theme.identifier.lower() == normalized:
            return theme.identifier
        if normalized in theme.identifier.lower():
            return theme.identifier
        if theme.tmx_path and Path(theme.tmx_path).stem.lower() == normalized:
            return theme.identifier
    return DEFAULT_THEME_ID


def main() -> None:
    parser = argparse.ArgumentParser(description="编辑二维矩阵地图的碰撞、出生点和掉落点数据。")
    parser.add_argument("--theme", default=None, help="地图主题 ID，例如 cyber_city_tmx。")
    parser.add_argument("--map", default=None, help="兼容旧 TMX 名称，会自动匹配对应主题。")
    args = parser.parse_args()

    pygame.init()
    pygame.display.set_caption("二维地图标点工具")
    screen = pygame.display.set_mode(WINDOW_SIZE)
    theme_id = resolve_theme_id(args.theme or args.map)
    editor = GridMapEditor(screen, theme_id)
    editor.run()
    pygame.quit()


if __name__ == "__main__":
    main()
