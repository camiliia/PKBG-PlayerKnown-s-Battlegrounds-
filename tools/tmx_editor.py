from __future__ import annotations

import argparse
import copy
import os
import shutil
import sys
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path

os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import pygame

from circle_siege.core.config import TMX_ROOT
from circle_siege.core.resource_manager import load_font_from_candidates
from circle_siege.maps.map_loader import load_tmx_bundle


WINDOW_SIZE = (1600, 940)
SIDEBAR_WIDTH = 340
MIN_ZOOM = 0.08
MAX_ZOOM = 4.5
POINT_RADIUS = 7
POINT_PICK_PADDING = 10
RECT_MIN_SIZE = 6
HANDLE_SIZE = 10
BACKGROUND = (14, 18, 24)
CANVAS_BG = (10, 12, 16)
SIDEBAR_BG = (18, 24, 31)
PANEL_BG = (24, 31, 40)
TEXT_MAIN = (232, 238, 244)
TEXT_MUTED = (149, 162, 176)
TEXT_ACTIVE = (255, 222, 138)
BORDER = (58, 71, 84)
STATUS_OK = (108, 224, 168)
STATUS_WARN = (255, 194, 96)
STATUS_ERR = (255, 122, 122)


@dataclass(frozen=True)
class LayerSpec:
    group_name: str
    label: str
    shape: str
    color: tuple[int, int, int]
    hotkey: str


@dataclass
class FloatRect:
    x: float
    y: float
    width: float
    height: float

    @property
    def left(self) -> float:
        return self.x

    @property
    def top(self) -> float:
        return self.y

    @property
    def right(self) -> float:
        return self.x + self.width

    @property
    def bottom(self) -> float:
        return self.y + self.height

    def inflate(self, dx: float, dy: float) -> "FloatRect":
        return FloatRect(
            self.x - dx / 2,
            self.y - dy / 2,
            self.width + dx,
            self.height + dy,
        )

    def collidepoint(self, point: tuple[float, float]) -> bool:
        px, py = point
        return self.left <= px <= self.right and self.top <= py <= self.bottom


LAYER_SPECS: tuple[LayerSpec, ...] = (
    LayerSpec("obstacle", "障碍矩形", "rect", (250, 104, 104), "1"),
    LayerSpec("loot", "掉落点", "point", (255, 210, 104), "2"),
    LayerSpec("spawn", "出生点", "point", (100, 214, 255), "3"),
    LayerSpec("cover", "掩体点", "point", (116, 245, 186), "4"),
    LayerSpec("landmark", "地标点", "point", (214, 168, 255), "5"),
    LayerSpec("trigger_supply", "补给触发区", "rect", (255, 184, 94), "6"),
    LayerSpec("trigger_danger", "危险触发区", "rect", (255, 118, 148), "7"),
    LayerSpec("trigger_mechanism", "机关触发区", "rect", (182, 244, 112), "8"),
)
LAYER_BY_NAME = {spec.group_name: spec for spec in LAYER_SPECS}
LAYER_ORDER = [spec.group_name for spec in LAYER_SPECS]


@dataclass
class EditorObject:
    object_id: int
    group_name: str
    shape: str
    x: float
    y: float
    width: float = 0.0
    height: float = 0.0
    name: str = ""
    extra_attributes: dict[str, str] = field(default_factory=dict)
    extra_children: list[ET.Element] = field(default_factory=list)

    def copy(self) -> "EditorObject":
        return EditorObject(
            object_id=self.object_id,
            group_name=self.group_name,
            shape=self.shape,
            x=self.x,
            y=self.y,
            width=self.width,
            height=self.height,
            name=self.name,
            extra_attributes=self.extra_attributes.copy(),
            extra_children=[copy.deepcopy(child) for child in self.extra_children],
        )


@dataclass
class MapDocument:
    path: Path
    root: ET.Element
    tree: ET.ElementTree
    surface: pygame.Surface
    pixel_size: tuple[int, int]
    tile_size: tuple[int, int]
    tile_count: tuple[int, int]
    editable_objects: dict[str, list[EditorObject]]
    passthrough_objects: dict[str, list[ET.Element]]
    dirty: bool = False

    @classmethod
    def load(cls, path: Path) -> "MapDocument":
        tree = ET.parse(path)
        root = tree.getroot()
        bundle = load_tmx_bundle(path)
        tile_width = int(root.get("tilewidth", "32") or 32)
        tile_height = int(root.get("tileheight", "32") or 32)
        map_width = int(root.get("width", "1") or 1)
        map_height = int(root.get("height", "1") or 1)
        editable_objects = {name: [] for name in LAYER_ORDER}
        passthrough_objects = {name: [] for name in LAYER_ORDER}

        for group_element in root.findall("objectgroup"):
            group_name = (group_element.get("name") or "").strip().lower()
            if group_name not in LAYER_BY_NAME:
                continue
            layer_spec = LAYER_BY_NAME[group_name]
            for object_element in group_element.findall("object"):
                parsed = _parse_object_element(object_element, layer_spec, tile_width, tile_height)
                if parsed is None:
                    passthrough_objects[group_name].append(copy.deepcopy(object_element))
                else:
                    editable_objects[group_name].append(parsed)

        return cls(
            path=path,
            root=root,
            tree=tree,
            surface=bundle.surface,
            pixel_size=bundle.pixel_size,
            tile_size=(tile_width, tile_height),
            tile_count=(map_width, map_height),
            editable_objects=editable_objects,
            passthrough_objects=passthrough_objects,
        )

    @property
    def map_name(self) -> str:
        return self.path.name

    @property
    def next_object_id(self) -> int:
        existing_ids = [
            int(float(object_element.get("id", "0") or 0))
            for object_element in self.root.findall(".//object")
            if object_element.get("id")
        ]
        editable_ids = [
            obj.object_id
            for object_list in self.editable_objects.values()
            for obj in object_list
        ]
        highest = max(existing_ids + editable_ids + [0])
        return highest + 1

    @property
    def next_layer_id(self) -> int:
        layer_ids = [
            int(float(child.get("id", "0") or 0))
            for child in self.root
            if child.get("id")
        ]
        return max(layer_ids + [0]) + 1

    def create_point(self, group_name: str, position: tuple[float, float]) -> EditorObject:
        return EditorObject(
            object_id=self.next_object_id,
            group_name=group_name,
            shape="point",
            x=position[0],
            y=position[1],
        )

    def create_rect(self, group_name: str, rect: FloatRect) -> EditorObject:
        return EditorObject(
            object_id=self.next_object_id,
            group_name=group_name,
            shape="rect",
            x=rect.x,
            y=rect.y,
            width=rect.width,
            height=rect.height,
        )

    def save(self) -> Path:
        backup_path = self.path.with_suffix(f"{self.path.suffix}.bak")
        shutil.copy2(self.path, backup_path)

        group_lookup = {
            (group.get("name") or "").strip().lower(): group
            for group in self.root.findall("objectgroup")
        }
        next_layer_id = self.next_layer_id
        for group_name in LAYER_ORDER:
            editable = self.editable_objects[group_name]
            passthrough = self.passthrough_objects[group_name]
            if group_name not in group_lookup and not editable and not passthrough:
                continue
            group_element = group_lookup.get(group_name)
            if group_element is None:
                group_element = ET.Element(
                    "objectgroup",
                    {
                        "id": str(next_layer_id),
                        "name": group_name,
                    },
                )
                self.root.append(group_element)
                group_lookup[group_name] = group_element
                next_layer_id += 1

            for child in list(group_element):
                if child.tag == "object":
                    group_element.remove(child)

            for passthrough_object in passthrough:
                group_element.append(copy.deepcopy(passthrough_object))
            for editor_object in editable:
                group_element.append(_serialize_object(editor_object))

        highest_object_id = max(
            [
                int(float(object_element.get("id", "0") or 0))
                for object_element in self.root.findall(".//object")
                if object_element.get("id")
            ]
            + [0]
        )
        highest_layer_id = max(
            [
                int(float(child.get("id", "0") or 0))
                for child in self.root
                if child.get("id")
            ]
            + [0]
        )
        self.root.set("nextobjectid", str(highest_object_id + 1))
        self.root.set("nextlayerid", str(highest_layer_id + 1))
        ET.indent(self.tree, space=" ", level=0)
        self.tree.write(self.path, encoding="UTF-8", xml_declaration=True)
        self.dirty = False
        return backup_path


class TmxEditorApp:
    def __init__(self, initial_map: str | None = None) -> None:
        pygame.init()
        pygame.display.set_caption("TMX 地图编辑器")
        self.screen = pygame.display.set_mode(WINDOW_SIZE, pygame.RESIZABLE)
        self.clock = pygame.time.Clock()
        self.font_small = _load_font(16)
        self.font_medium = _load_font(18)
        self.font_title = _load_font(24, bold=True)

        self.map_paths = sorted(TMX_ROOT.glob("*.tmx"))
        if not self.map_paths:
            raise FileNotFoundError(f"未找到地图目录：{TMX_ROOT}")

        self.current_index = _resolve_initial_index(self.map_paths, initial_map)
        self.document = MapDocument.load(self.map_paths[self.current_index])
        self.current_layer = "obstacle"
        self.selected_object_id: int | None = None
        self.selected_group: str | None = None
        self.drag_mode: str | None = None
        self.drag_origin_world = pygame.Vector2()
        self.drag_origin_screen = pygame.Vector2()
        self.drag_snapshot: EditorObject | None = None
        self.draw_rect_preview: FloatRect | None = None
        self.show_grid = True
        self.status_text = "左侧切图，右侧选层；左键新增/拖动，右键删除。"
        self.status_color = STATUS_OK
        self.sidebar_actions: list[tuple[pygame.Rect, tuple[str, object]]] = []
        self.zoom = 1.0
        self.pan = pygame.Vector2()
        self.cached_surface: pygame.Surface | None = None
        self.cached_surface_key: tuple[int, int] | None = None
        self.fit_to_canvas()
        self._update_title()

    def run(self) -> None:
        running = True
        while running:
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    running = False
                elif event.type == pygame.VIDEORESIZE:
                    self.screen = pygame.display.set_mode((event.w, event.h), pygame.RESIZABLE)
                    self.fit_to_canvas()
                elif event.type == pygame.MOUSEWHEEL:
                    self._handle_zoom(event)
                elif event.type == pygame.MOUSEBUTTONDOWN:
                    self._handle_mouse_down(event)
                elif event.type == pygame.MOUSEBUTTONUP:
                    self._handle_mouse_up(event)
                elif event.type == pygame.MOUSEMOTION:
                    self._handle_mouse_motion(event)
                elif event.type == pygame.KEYDOWN:
                    self._handle_keydown(event)

            self._draw()
            pygame.display.flip()
            self.clock.tick(60)
        pygame.quit()

    def _handle_zoom(self, event: pygame.event.Event) -> None:
        mouse_pos = pygame.mouse.get_pos()
        if not self.canvas_rect.collidepoint(mouse_pos):
            return
        world_before = self.screen_to_world(mouse_pos)
        old_zoom = self.zoom
        factor = 1.12 if event.y > 0 else 1 / 1.12
        self.zoom = max(MIN_ZOOM, min(MAX_ZOOM, self.zoom * factor))
        if abs(self.zoom - old_zoom) < 1e-6:
            return
        self._invalidate_scaled_surface()
        canvas = self.canvas_rect
        self.pan.x = mouse_pos[0] - canvas.x - world_before[0] * self.zoom
        self.pan.y = mouse_pos[1] - canvas.y - world_before[1] * self.zoom

    def _handle_mouse_down(self, event: pygame.event.Event) -> None:
        if event.button == 1 and self.sidebar_rect.collidepoint(event.pos):
            self._handle_sidebar_click(event.pos)
            return
        if not self.canvas_rect.collidepoint(event.pos):
            return

        if event.button == 2 or (event.button == 1 and pygame.key.get_pressed()[pygame.K_SPACE]):
            self.drag_mode = "pan"
            self.drag_origin_screen = pygame.Vector2(event.pos)
            return

        if event.button == 3:
            hit = self._hit_test(event.pos)
            if hit is not None:
                group_name, object_id = hit
                self._select_object(group_name, object_id)
                self._delete_selected()
            return

        if event.button != 1:
            return

        hit = self._hit_test(event.pos)
        if hit is not None:
            group_name, object_id = hit
            self._select_object(group_name, object_id)
            selected = self._selected_object()
            if selected is None:
                return
            handle_rect = self._selected_handle_rect(selected)
            if handle_rect is not None and handle_rect.collidepoint(event.pos):
                self.drag_mode = "resize"
            else:
                self.drag_mode = "move"
            self.drag_origin_world = pygame.Vector2(self.screen_to_world(event.pos))
            self.drag_snapshot = selected.copy()
            return

        self._clear_selection()
        layer_spec = LAYER_BY_NAME[self.current_layer]
        world = self._clamp_point(self.screen_to_world(event.pos))
        if layer_spec.shape == "point":
            new_object = self.document.create_point(self.current_layer, world)
            self.document.editable_objects[self.current_layer].append(new_object)
            self.document.dirty = True
            self._select_object(self.current_layer, new_object.object_id)
            self._set_status(f"已新增 {layer_spec.label}。", STATUS_OK)
            self._update_title()
            return

        self.drag_mode = "draw_rect"
        self.drag_origin_world = pygame.Vector2(world)
        self.draw_rect_preview = FloatRect(world[0], world[1], 0.0, 0.0)

    def _handle_mouse_up(self, event: pygame.event.Event) -> None:
        if event.button not in (1, 2):
            return
        if self.drag_mode == "draw_rect" and self.draw_rect_preview is not None:
            rect = _normalize_rect(self.draw_rect_preview)
            if rect.width >= RECT_MIN_SIZE and rect.height >= RECT_MIN_SIZE:
                rect = self._clamp_rect(rect)
                new_object = self.document.create_rect(self.current_layer, rect)
                self.document.editable_objects[self.current_layer].append(new_object)
                self.document.dirty = True
                self._select_object(self.current_layer, new_object.object_id)
                self._set_status(f"已新增 {LAYER_BY_NAME[self.current_layer].label}。", STATUS_OK)
                self._update_title()
        self.drag_mode = None
        self.drag_snapshot = None
        self.draw_rect_preview = None

    def _handle_mouse_motion(self, event: pygame.event.Event) -> None:
        if self.drag_mode == "pan":
            delta = pygame.Vector2(event.rel)
            self.pan += delta
            return

        selected = self._selected_object()
        if self.drag_mode == "move" and selected is not None and self.drag_snapshot is not None:
            delta = pygame.Vector2(self.screen_to_world(event.pos)) - self.drag_origin_world
            if selected.shape == "point":
                selected.x, selected.y = self._clamp_point(
                    (self.drag_snapshot.x + delta.x, self.drag_snapshot.y + delta.y)
                )
            else:
                rect = FloatRect(
                    self.drag_snapshot.x + delta.x,
                    self.drag_snapshot.y + delta.y,
                    self.drag_snapshot.width,
                    self.drag_snapshot.height,
                )
                rect = self._clamp_rect(rect)
                selected.x = rect.x
                selected.y = rect.y
            self.document.dirty = True
            self._update_title()
            return

        if self.drag_mode == "resize" and selected is not None and self.drag_snapshot is not None:
            world = self._clamp_point(self.screen_to_world(event.pos))
            width = max(RECT_MIN_SIZE, world[0] - self.drag_snapshot.x)
            height = max(RECT_MIN_SIZE, world[1] - self.drag_snapshot.y)
            selected.width = min(width, self.document.pixel_size[0] - self.drag_snapshot.x)
            selected.height = min(height, self.document.pixel_size[1] - self.drag_snapshot.y)
            self.document.dirty = True
            self._update_title()
            return

        if self.drag_mode == "draw_rect" and self.draw_rect_preview is not None:
            world = self._clamp_point(self.screen_to_world(event.pos))
            self.draw_rect_preview.width = world[0] - self.drag_origin_world.x
            self.draw_rect_preview.height = world[1] - self.drag_origin_world.y

    def _handle_keydown(self, event: pygame.event.Event) -> None:
        modifiers = pygame.key.get_mods()
        if event.key == pygame.K_ESCAPE:
            self.drag_mode = None
            self.drag_snapshot = None
            self.draw_rect_preview = None
            return
        if event.key == pygame.K_g:
            self.show_grid = not self.show_grid
            return
        if event.key == pygame.K_f:
            self.fit_to_canvas()
            return
        if event.key == pygame.K_F5:
            self._reload_current_map(force=True)
            return
        if event.key == pygame.K_PAGEUP:
            self._switch_map(-1)
            return
        if event.key == pygame.K_PAGEDOWN:
            self._switch_map(1)
            return
        if event.key in (pygame.K_DELETE, pygame.K_BACKSPACE):
            self._delete_selected()
            return
        if modifiers & pygame.KMOD_CTRL and event.key == pygame.K_s:
            self._save_current_map()
            return
        if modifiers & pygame.KMOD_CTRL and event.key == pygame.K_d:
            self._duplicate_selected()
            return

        keymap = {
            pygame.K_1: "obstacle",
            pygame.K_2: "loot",
            pygame.K_3: "spawn",
            pygame.K_4: "cover",
            pygame.K_5: "landmark",
            pygame.K_6: "trigger_supply",
            pygame.K_7: "trigger_danger",
            pygame.K_8: "trigger_mechanism",
        }
        if event.key in keymap:
            self.current_layer = keymap[event.key]
            self._set_status(f"当前图层：{LAYER_BY_NAME[self.current_layer].label}", STATUS_OK)
            return

        selected = self._selected_object()
        if selected is None:
            return
        step = 10 if modifiers & pygame.KMOD_SHIFT else 1
        resize_mode = bool(modifiers & pygame.KMOD_ALT)
        if event.key == pygame.K_LEFT:
            self._nudge_selected(dx=-step, dy=0, resize=resize_mode)
        elif event.key == pygame.K_RIGHT:
            self._nudge_selected(dx=step, dy=0, resize=resize_mode)
        elif event.key == pygame.K_UP:
            self._nudge_selected(dx=0, dy=-step, resize=resize_mode)
        elif event.key == pygame.K_DOWN:
            self._nudge_selected(dx=0, dy=step, resize=resize_mode)

    @property
    def canvas_rect(self) -> pygame.Rect:
        width = max(240, self.screen.get_width() - SIDEBAR_WIDTH)
        return pygame.Rect(0, 0, width, self.screen.get_height())

    @property
    def sidebar_rect(self) -> pygame.Rect:
        canvas = self.canvas_rect
        return pygame.Rect(canvas.right, 0, self.screen.get_width() - canvas.width, self.screen.get_height())

    def fit_to_canvas(self) -> None:
        canvas = self.canvas_rect.inflate(-40, -40)
        map_width, map_height = self.document.pixel_size
        self.zoom = min(canvas.width / max(1, map_width), canvas.height / max(1, map_height))
        self.zoom = max(MIN_ZOOM, min(MAX_ZOOM, self.zoom))
        draw_width = map_width * self.zoom
        draw_height = map_height * self.zoom
        self.pan = pygame.Vector2(
            canvas.centerx - draw_width / 2,
            canvas.centery - draw_height / 2,
        )
        self._invalidate_scaled_surface()

    def world_to_screen(self, point: tuple[float, float]) -> tuple[int, int]:
        canvas = self.canvas_rect
        return (
            int(round(canvas.x + self.pan.x + point[0] * self.zoom)),
            int(round(canvas.y + self.pan.y + point[1] * self.zoom)),
        )

    def screen_to_world(self, point: tuple[int, int]) -> tuple[float, float]:
        canvas = self.canvas_rect
        return (
            (point[0] - canvas.x - self.pan.x) / self.zoom,
            (point[1] - canvas.y - self.pan.y) / self.zoom,
        )

    def _scaled_map_surface(self) -> pygame.Surface:
        target_size = (
            max(1, int(round(self.document.pixel_size[0] * self.zoom))),
            max(1, int(round(self.document.pixel_size[1] * self.zoom))),
        )
        if self.cached_surface is None or self.cached_surface_key != target_size:
            self.cached_surface = pygame.transform.smoothscale(self.document.surface, target_size)
            self.cached_surface_key = target_size
        return self.cached_surface

    def _invalidate_scaled_surface(self) -> None:
        self.cached_surface = None
        self.cached_surface_key = None

    def _draw(self) -> None:
        self.screen.fill(BACKGROUND)
        self._draw_canvas()
        self._draw_sidebar()

    def _draw_canvas(self) -> None:
        canvas = self.canvas_rect
        pygame.draw.rect(self.screen, CANVAS_BG, canvas)
        pygame.draw.rect(self.screen, BORDER, canvas, width=1)
        self.screen.set_clip(canvas)
        map_surface = self._scaled_map_surface()
        self.screen.blit(map_surface, (canvas.x + self.pan.x, canvas.y + self.pan.y))
        self._draw_grid()
        self._draw_objects()
        if self.draw_rect_preview is not None:
            rect = _normalize_rect(self.draw_rect_preview)
            self._draw_rect_overlay(rect, (255, 255, 255), filled=False)
        self.screen.set_clip(None)

    def _draw_grid(self) -> None:
        if not self.show_grid:
            return
        tile_width, tile_height = self.document.tile_size
        map_tiles_x, map_tiles_y = self.document.tile_count
        if map_tiles_x <= 1 and map_tiles_y <= 1:
            return
        if tile_width * self.zoom < 12 or tile_height * self.zoom < 12:
            return
        canvas = self.canvas_rect
        left_world = max(0, int(self.screen_to_world((canvas.left, canvas.top))[0] // tile_width))
        top_world = max(0, int(self.screen_to_world((canvas.left, canvas.top))[1] // tile_height))
        right_world = min(map_tiles_x, int(self.screen_to_world((canvas.right, canvas.bottom))[0] // tile_width) + 2)
        bottom_world = min(map_tiles_y, int(self.screen_to_world((canvas.right, canvas.bottom))[1] // tile_height) + 2)
        grid_color = (255, 255, 255, 34)
        for tile_x in range(left_world, right_world):
            x = self.world_to_screen((tile_x * tile_width, 0))[0]
            pygame.draw.line(self.screen, grid_color, (x, canvas.top), (x, canvas.bottom), 1)
        for tile_y in range(top_world, bottom_world):
            y = self.world_to_screen((0, tile_y * tile_height))[1]
            pygame.draw.line(self.screen, grid_color, (canvas.left, y), (canvas.right, y), 1)

    def _draw_objects(self) -> None:
        for group_name in LAYER_ORDER:
            spec = LAYER_BY_NAME[group_name]
            for obj in self.document.editable_objects[group_name]:
                if obj.shape == "point":
                    self._draw_point_object(obj, spec.color)
                else:
                    self._draw_rect_overlay(
                        FloatRect(obj.x, obj.y, obj.width, obj.height),
                        spec.color,
                        filled=True,
                    )

        selected = self._selected_object()
        if selected is None:
            return
        if selected.shape == "point":
            center = self.world_to_screen((selected.x, selected.y))
            pygame.draw.circle(self.screen, (255, 255, 255), center, POINT_RADIUS + 6, width=2)
        else:
            rect = FloatRect(selected.x, selected.y, selected.width, selected.height)
            self._draw_rect_overlay(rect, (255, 255, 255), filled=False)
            handle = self._selected_handle_rect(selected)
            if handle is not None:
                pygame.draw.rect(self.screen, (255, 255, 255), handle, border_radius=3)
        self._draw_selected_label(selected)

    def _draw_point_object(self, obj: EditorObject, color: tuple[int, int, int]) -> None:
        center = self.world_to_screen((obj.x, obj.y))
        pygame.draw.circle(self.screen, color, center, POINT_RADIUS)
        pygame.draw.circle(self.screen, (18, 18, 18), center, POINT_RADIUS, width=2)
        pygame.draw.line(self.screen, (18, 18, 18), (center[0] - 10, center[1]), (center[0] + 10, center[1]), 1)
        pygame.draw.line(self.screen, (18, 18, 18), (center[0], center[1] - 10), (center[0], center[1] + 10), 1)

    def _draw_rect_overlay(self, rect: FloatRect, color: tuple[int, int, int], *, filled: bool) -> None:
        screen_rect = pygame.Rect(
            *self.world_to_screen((rect.x, rect.y)),
            max(1, int(round(rect.width * self.zoom))),
            max(1, int(round(rect.height * self.zoom))),
        )
        if filled:
            fill = pygame.Surface(screen_rect.size, pygame.SRCALPHA)
            fill.fill((*color, 58))
            self.screen.blit(fill, screen_rect.topleft)
        pygame.draw.rect(self.screen, color, screen_rect, width=2, border_radius=4)

    def _draw_selected_label(self, obj: EditorObject) -> None:
        spec = LAYER_BY_NAME[obj.group_name]
        label = f"{spec.label} #{obj.object_id}"
        surface = self.font_small.render(label, True, (18, 18, 18))
        panel = pygame.Surface((surface.get_width() + 12, surface.get_height() + 8), pygame.SRCALPHA)
        panel.fill((255, 255, 255, 220))
        panel.blit(surface, (6, 4))
        anchor = (obj.x, obj.y) if obj.shape == "point" else (obj.x, max(0, obj.y - 18))
        screen_pos = self.world_to_screen(anchor)
        self.screen.blit(panel, (screen_pos[0] + 10, screen_pos[1] - panel.get_height() - 6))

    def _draw_sidebar(self) -> None:
        sidebar = self.sidebar_rect
        self.sidebar_actions.clear()
        pygame.draw.rect(self.screen, SIDEBAR_BG, sidebar)
        pygame.draw.line(self.screen, BORDER, sidebar.topleft, sidebar.bottomleft, 1)

        x = sidebar.x + 18
        y = 18
        title = self.font_title.render("TMX 地图编辑器", True, TEXT_MAIN)
        self.screen.blit(title, (x, y))
        y += title.get_height() + 6

        map_label = f"当前地图：{self.document.map_name}{' *' if self.document.dirty else ''}"
        self.screen.blit(self.font_medium.render(map_label, True, TEXT_ACTIVE), (x, y))
        y += 34

        y = self._draw_button_row(
            x,
            y,
            [
                ("保存", ("save", None)),
                ("重载", ("reload", None)),
                ("居中", ("fit", None)),
            ],
        )
        y += 14

        y = self._draw_section_title("地图列表", x, y)
        for index, path in enumerate(self.map_paths):
            button_rect = pygame.Rect(x, y, sidebar.width - 36, 28)
            is_active = index == self.current_index
            bg = (54, 70, 84) if is_active else PANEL_BG
            fg = TEXT_ACTIVE if is_active else TEXT_MAIN
            pygame.draw.rect(self.screen, bg, button_rect, border_radius=6)
            pygame.draw.rect(self.screen, BORDER, button_rect, width=1, border_radius=6)
            label = self.font_small.render(path.name, True, fg)
            self.screen.blit(label, (button_rect.x + 10, button_rect.y + 6))
            self.sidebar_actions.append((button_rect, ("map", index)))
            y += 34

        y += 8
        y = self._draw_section_title("编辑图层", x, y)
        for group_name in LAYER_ORDER:
            spec = LAYER_BY_NAME[group_name]
            count = len(self.document.editable_objects[group_name])
            button_rect = pygame.Rect(x, y, sidebar.width - 36, 30)
            is_active = group_name == self.current_layer
            bg = (*spec.color,) if is_active else PANEL_BG
            pygame.draw.rect(self.screen, bg, button_rect, border_radius=6)
            pygame.draw.rect(self.screen, BORDER, button_rect, width=1, border_radius=6)
            label_text = f"[{spec.hotkey}] {spec.label}  ({count})"
            label_color = (16, 18, 20) if is_active else TEXT_MAIN
            self.screen.blit(self.font_small.render(label_text, True, label_color), (button_rect.x + 10, button_rect.y + 7))
            self.sidebar_actions.append((button_rect, ("layer", group_name)))
            y += 36

        y += 10
        y = self._draw_section_title("操作说明", x, y)
        help_lines = [
            "左键空白处：新增当前图层对象",
            "左键已有对象：选中并拖动",
            "拖矩形句柄：调整障碍/触发区大小",
            "右键对象：删除",
            "中键或空格+左键：拖动画布",
            "滚轮：缩放",
            "Ctrl+S：保存    F5：放弃修改并重载",
            "PageUp/PageDown：切换地图",
            "Delete：删除选中    Ctrl+D：复制",
            "方向键：微调位置    Alt+方向键：调尺寸",
            "G：网格开关    F：重新居中",
        ]
        for line in help_lines:
            text = self.font_small.render(line, True, TEXT_MUTED)
            self.screen.blit(text, (x, y))
            y += 22

        y += 6
        y = self._draw_section_title("状态", x, y)
        status_rect = pygame.Rect(x, y, sidebar.width - 36, 70)
        pygame.draw.rect(self.screen, PANEL_BG, status_rect, border_radius=6)
        pygame.draw.rect(self.screen, BORDER, status_rect, width=1, border_radius=6)
        status_surface = self.font_small.render(self.status_text, True, self.status_color)
        self.screen.blit(status_surface, (status_rect.x + 10, status_rect.y + 10))
        if self.selected_group is not None and self.selected_object_id is not None:
            selected_text = f"选中：{self.selected_group} #{self.selected_object_id}"
            self.screen.blit(self.font_small.render(selected_text, True, TEXT_MAIN), (status_rect.x + 10, status_rect.y + 36))

    def _draw_button_row(
        self,
        x: int,
        y: int,
        buttons: list[tuple[str, tuple[str, object]]],
    ) -> int:
        button_width = 92
        for index, (label, action) in enumerate(buttons):
            rect = pygame.Rect(x + index * (button_width + 10), y, button_width, 34)
            pygame.draw.rect(self.screen, PANEL_BG, rect, border_radius=6)
            pygame.draw.rect(self.screen, BORDER, rect, width=1, border_radius=6)
            text = self.font_small.render(label, True, TEXT_MAIN)
            text_x = rect.centerx - text.get_width() // 2
            text_y = rect.centery - text.get_height() // 2
            self.screen.blit(text, (text_x, text_y))
            self.sidebar_actions.append((rect, action))
        return y + 34

    def _draw_section_title(self, title: str, x: int, y: int) -> int:
        text = self.font_medium.render(title, True, TEXT_MAIN)
        self.screen.blit(text, (x, y))
        return y + 28

    def _handle_sidebar_click(self, position: tuple[int, int]) -> None:
        for rect, action in reversed(self.sidebar_actions):
            if not rect.collidepoint(position):
                continue
            kind, payload = action
            if kind == "save":
                self._save_current_map()
            elif kind == "reload":
                self._reload_current_map(force=True)
            elif kind == "fit":
                self.fit_to_canvas()
            elif kind == "map":
                self._switch_to_index(int(payload))
            elif kind == "layer":
                self.current_layer = str(payload)
                self._set_status(f"当前图层：{LAYER_BY_NAME[self.current_layer].label}", STATUS_OK)
            break

    def _switch_map(self, offset: int) -> None:
        self._switch_to_index((self.current_index + offset) % len(self.map_paths))

    def _switch_to_index(self, index: int) -> None:
        if index == self.current_index:
            return
        if self.document.dirty:
            self._set_status("当前地图有未保存修改，请先保存，或按 F5 放弃后再切图。", STATUS_WARN)
            return
        self.current_index = index
        self.document = MapDocument.load(self.map_paths[self.current_index])
        self.current_layer = "obstacle"
        self._clear_selection()
        self.fit_to_canvas()
        self._set_status(f"已切换到 {self.document.map_name}", STATUS_OK)
        self._update_title()

    def _reload_current_map(self, *, force: bool = False) -> None:
        if self.document.dirty and not force:
            self._set_status("该地图有未保存修改，按 F5 可强制重载并丢弃修改。", STATUS_WARN)
            return
        self.document = MapDocument.load(self.map_paths[self.current_index])
        self._clear_selection()
        self.fit_to_canvas()
        self._set_status("已从磁盘重载当前地图。", STATUS_OK)
        self._update_title()

    def _save_current_map(self) -> None:
        backup_path = self.document.save()
        self._set_status(f"已保存 {self.document.map_name}，备份：{backup_path.name}", STATUS_OK)
        self._update_title()

    def _select_object(self, group_name: str, object_id: int) -> None:
        self.selected_group = group_name
        self.selected_object_id = object_id
        self.current_layer = group_name

    def _clear_selection(self) -> None:
        self.selected_group = None
        self.selected_object_id = None

    def _selected_object(self) -> EditorObject | None:
        if self.selected_group is None or self.selected_object_id is None:
            return None
        for obj in self.document.editable_objects[self.selected_group]:
            if obj.object_id == self.selected_object_id:
                return obj
        return None

    def _selected_handle_rect(self, obj: EditorObject) -> pygame.Rect | None:
        if obj.shape != "rect":
            return None
        rect = pygame.Rect(
            *self.world_to_screen((obj.x, obj.y)),
            max(1, int(round(obj.width * self.zoom))),
            max(1, int(round(obj.height * self.zoom))),
        )
        return pygame.Rect(rect.right - HANDLE_SIZE - 2, rect.bottom - HANDLE_SIZE - 2, HANDLE_SIZE, HANDLE_SIZE)

    def _hit_test(self, screen_pos: tuple[int, int]) -> tuple[str, int] | None:
        world = self.screen_to_world(screen_pos)
        group_order = [self.current_layer] + [name for name in LAYER_ORDER if name != self.current_layer]
        for group_name in group_order:
            for obj in reversed(self.document.editable_objects[group_name]):
                if obj.shape == "point":
                    screen_center = self.world_to_screen((obj.x, obj.y))
                    radius = POINT_RADIUS + POINT_PICK_PADDING
                    if pygame.Vector2(screen_center).distance_to(screen_pos) <= radius:
                        return group_name, obj.object_id
                else:
                    rect = FloatRect(obj.x, obj.y, obj.width, obj.height)
                    world_padding = max(4.0, 10.0 / max(self.zoom, 0.001))
                    hit_rect = rect.inflate(world_padding * 2, world_padding * 2)
                    if hit_rect.collidepoint(world):
                        return group_name, obj.object_id
        return None

    def _delete_selected(self) -> None:
        selected = self._selected_object()
        if selected is None or self.selected_group is None:
            return
        object_list = self.document.editable_objects[self.selected_group]
        self.document.editable_objects[self.selected_group] = [
            obj for obj in object_list if obj.object_id != selected.object_id
        ]
        self.document.dirty = True
        label = LAYER_BY_NAME[self.selected_group].label
        self._clear_selection()
        self._set_status(f"已删除 {label}。", STATUS_OK)
        self._update_title()

    def _duplicate_selected(self) -> None:
        selected = self._selected_object()
        if selected is None or self.selected_group is None:
            return
        clone = selected.copy()
        clone.object_id = self.document.next_object_id
        clone.x += 24
        clone.y += 24
        if clone.shape == "point":
            clone.x, clone.y = self._clamp_point((clone.x, clone.y))
        else:
            rect = self._clamp_rect(FloatRect(clone.x, clone.y, clone.width, clone.height))
            clone.x = rect.x
            clone.y = rect.y
        self.document.editable_objects[self.selected_group].append(clone)
        self.document.dirty = True
        self._select_object(self.selected_group, clone.object_id)
        self._set_status("已复制选中对象。", STATUS_OK)
        self._update_title()

    def _nudge_selected(self, *, dx: int, dy: int, resize: bool) -> None:
        selected = self._selected_object()
        if selected is None:
            return
        if resize and selected.shape == "rect":
            selected.width = max(RECT_MIN_SIZE, min(selected.width + dx, self.document.pixel_size[0] - selected.x))
            selected.height = max(RECT_MIN_SIZE, min(selected.height + dy, self.document.pixel_size[1] - selected.y))
        elif selected.shape == "point":
            selected.x, selected.y = self._clamp_point((selected.x + dx, selected.y + dy))
        else:
            rect = FloatRect(selected.x + dx, selected.y + dy, selected.width, selected.height)
            rect = self._clamp_rect(rect)
            selected.x = rect.x
            selected.y = rect.y
        self.document.dirty = True
        self._update_title()

    def _clamp_point(self, point: tuple[float, float]) -> tuple[float, float]:
        return (
            max(0.0, min(point[0], float(self.document.pixel_size[0]))),
            max(0.0, min(point[1], float(self.document.pixel_size[1]))),
        )

    def _clamp_rect(self, rect: FloatRect) -> FloatRect:
        width = max(RECT_MIN_SIZE, min(rect.width, self.document.pixel_size[0]))
        height = max(RECT_MIN_SIZE, min(rect.height, self.document.pixel_size[1]))
        x = max(0.0, min(rect.x, self.document.pixel_size[0] - width))
        y = max(0.0, min(rect.y, self.document.pixel_size[1] - height))
        return FloatRect(x, y, width, height)

    def _set_status(self, text: str, color: tuple[int, int, int]) -> None:
        self.status_text = text
        self.status_color = color

    def _update_title(self) -> None:
        dirty = " *未保存" if self.document.dirty else ""
        pygame.display.set_caption(f"TMX 地图编辑器 - {self.document.map_name}{dirty}")


def _parse_object_element(
    object_element: ET.Element,
    layer_spec: LayerSpec,
    tile_width: int,
    tile_height: int,
) -> EditorObject | None:
    if any(object_element.find(tag) is not None for tag in ("polygon", "polyline", "ellipse", "text")):
        return None

    object_id = int(float(object_element.get("id", "0") or 0))
    x = float(object_element.get("x", "0") or 0)
    y = float(object_element.get("y", "0") or 0)
    name = object_element.get("name", "") or ""
    extra_attributes = {
        key: value
        for key, value in object_element.attrib.items()
        if key not in {"id", "name", "x", "y", "width", "height"}
    }
    extra_children = [
        copy.deepcopy(child)
        for child in object_element
        if child.tag != "point"
    ]

    if layer_spec.shape == "point":
        if object_element.find("point") is None:
            width = float(object_element.get("width", "0") or 0)
            height = float(object_element.get("height", "0") or 0)
            if width > 0 or height > 0:
                x += width / 2
                y += height / 2
        return EditorObject(
            object_id=object_id,
            group_name=layer_spec.group_name,
            shape="point",
            x=x,
            y=y,
            name=name,
            extra_attributes=extra_attributes,
            extra_children=extra_children,
        )

    width = float(object_element.get("width", "0") or 0)
    height = float(object_element.get("height", "0") or 0)
    fallback_width = max(12.0, tile_width * 0.35)
    fallback_height = max(12.0, tile_height * 0.35)
    if width <= 0:
        width = fallback_width
    if height <= 0:
        height = fallback_height
    return EditorObject(
        object_id=object_id,
        group_name=layer_spec.group_name,
        shape="rect",
        x=x,
        y=y,
        width=width,
        height=height,
        name=name,
        extra_attributes=extra_attributes,
        extra_children=extra_children,
    )


def _serialize_object(editor_object: EditorObject) -> ET.Element:
    attributes = editor_object.extra_attributes.copy()
    attributes["id"] = str(editor_object.object_id)
    if editor_object.name:
        attributes["name"] = editor_object.name
    attributes["x"] = _format_number(editor_object.x)
    attributes["y"] = _format_number(editor_object.y)
    if editor_object.shape == "rect":
        attributes["width"] = _format_number(editor_object.width)
        attributes["height"] = _format_number(editor_object.height)
    object_element = ET.Element("object", attributes)
    if editor_object.shape == "point":
        object_element.append(ET.Element("point"))
    for child in editor_object.extra_children:
        object_element.append(copy.deepcopy(child))
    return object_element


def _format_number(value: float) -> str:
    rounded = round(value)
    if abs(value - rounded) < 1e-4:
        return str(int(rounded))
    return f"{value:.2f}".rstrip("0").rstrip(".")


def _normalize_rect(rect: FloatRect) -> FloatRect:
    x = rect.x + min(0.0, rect.width)
    y = rect.y + min(0.0, rect.height)
    width = abs(rect.width)
    height = abs(rect.height)
    return FloatRect(x, y, width, height)


def _resolve_initial_index(map_paths: list[Path], initial_map: str | None) -> int:
    if not initial_map:
        for index, path in enumerate(map_paths):
            if path.name == "cyber_city.tmx":
                return index
        return 0
    initial_name = Path(initial_map).name.lower()
    for index, path in enumerate(map_paths):
        if path.name.lower() == initial_name:
            return index
    return 0


def _load_font(size: int, *, bold: bool = False) -> pygame.font.Font:
    body_candidates = (
        "C:/Windows/Fonts/msyh.ttc",
        "C:/Windows/Fonts/simsun.ttc",
        "C:/Windows/Fonts/nsimsun.ttc",
        "C:/Windows/Fonts/simhei.ttf",
    )
    title_candidates = (
        "C:/Windows/Fonts/msyhbd.ttc",
        "C:/Windows/Fonts/simhei.ttf",
        "C:/Windows/Fonts/msyh.ttc",
        "C:/Windows/Fonts/simsun.ttc",
    )
    return load_font_from_candidates(title_candidates if bold else body_candidates, size)


def main() -> None:
    parser = argparse.ArgumentParser(description="TMX 地图对象编辑器")
    parser.add_argument("--map", help="启动时优先打开的 TMX 文件名，例如 cyber_city.tmx")
    args = parser.parse_args()
    app = TmxEditorApp(initial_map=args.map)
    app.run()


if __name__ == "__main__":
    main()
