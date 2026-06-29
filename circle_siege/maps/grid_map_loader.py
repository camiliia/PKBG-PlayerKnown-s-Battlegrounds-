from __future__ import annotations

import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ..core.config import GRID_MAP_ROOT


GRID_LAYER_NAMES = ("collision", "player_spawn", "enemy_spawn", "loot_spawn")
DEFAULT_CELL_SIZE = 64


@dataclass
class GridMapDocument:
    path: Path
    identifier: str
    label: str
    cell_size: int
    cols: int
    rows: int
    background_image: str | None
    layers: dict[str, list[list[int]]]


def grid_map_path_for_theme(theme_id: str) -> Path:
    return GRID_MAP_ROOT / f"{theme_id}.json"


def load_grid_map_document(theme) -> GridMapDocument:
    path = grid_map_path_for_theme(theme.identifier)
    if not path.exists():
        document = create_default_grid_map_document(theme, path)
        save_grid_map_document(document)
        return document

    with path.open("r", encoding="utf-8") as handle:
        payload = json.load(handle)
    return _document_from_payload(payload, path, theme)


def save_grid_map_document(document: GridMapDocument) -> None:
    document.path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "meta": {
            "id": document.identifier,
            "label": document.label,
            "cell_size": document.cell_size,
            "cols": document.cols,
            "rows": document.rows,
            "background_image": document.background_image,
        },
        "layers": document.layers,
    }
    with document.path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)
        handle.write("\n")


def create_default_grid_map_document(theme, path: Path | None = None) -> GridMapDocument:
    path = path or grid_map_path_for_theme(theme.identifier)
    cell_size = DEFAULT_CELL_SIZE
    cols = max(32, int(math.ceil(theme.width / cell_size)))
    rows = max(22, int(math.ceil(theme.height / cell_size)))
    background_image = getattr(theme, "preview_image_path", None)

    collision = [[0 for _ in range(cols)] for _ in range(rows)]
    for x in range(cols):
        collision[0][x] = 1
        collision[rows - 1][x] = 1
    for y in range(rows):
        collision[y][0] = 1
        collision[y][cols - 1] = 1

    _stamp_default_obstacles(collision, cols, rows)

    player_spawn = [[0 for _ in range(cols)] for _ in range(rows)]
    enemy_spawn = [[0 for _ in range(cols)] for _ in range(rows)]
    loot_spawn = [[0 for _ in range(cols)] for _ in range(rows)]

    _mark_first_open(player_spawn, collision, cols // 2, rows // 2, value=1)
    for index, (x, y) in enumerate(_default_enemy_spawn_cells(cols, rows)):
        _mark_first_open(enemy_spawn, collision, x, y, value=2 if index < 2 else 1)
    for index, (x, y) in enumerate(_default_loot_cells(cols, rows)):
        _mark_first_open(loot_spawn, collision, x, y, value=(index % 4) + 1)

    return GridMapDocument(
        path=path,
        identifier=theme.identifier,
        label=theme.label,
        cell_size=cell_size,
        cols=cols,
        rows=rows,
        background_image=background_image,
        layers={
            "collision": collision,
            "player_spawn": player_spawn,
            "enemy_spawn": enemy_spawn,
            "loot_spawn": loot_spawn,
        },
    )


def _document_from_payload(payload: dict[str, Any], path: Path, theme) -> GridMapDocument:
    meta = payload.get("meta", {}) if isinstance(payload, dict) else {}
    layers = payload.get("layers", {}) if isinstance(payload, dict) else {}
    cell_size = int(meta.get("cell_size") or DEFAULT_CELL_SIZE)
    cols = int(meta.get("cols") or max(32, math.ceil(theme.width / cell_size)))
    rows = int(meta.get("rows") or max(22, math.ceil(theme.height / cell_size)))
    normalized_layers = {
        name: _normalize_matrix(layers.get(name), rows, cols)
        for name in GRID_LAYER_NAMES
    }
    return GridMapDocument(
        path=path,
        identifier=str(meta.get("id") or theme.identifier),
        label=str(meta.get("label") or theme.label),
        cell_size=max(16, cell_size),
        cols=max(1, cols),
        rows=max(1, rows),
        background_image=meta.get("background_image") or getattr(theme, "preview_image_path", None),
        layers=normalized_layers,
    )


def _normalize_matrix(raw: Any, rows: int, cols: int) -> list[list[int]]:
    matrix: list[list[int]] = []
    source_rows = raw if isinstance(raw, list) else []
    for y in range(rows):
        source_row = source_rows[y] if y < len(source_rows) and isinstance(source_rows[y], list) else []
        row = []
        for x in range(cols):
            value = source_row[x] if x < len(source_row) else 0
            try:
                row.append(int(value))
            except (TypeError, ValueError):
                row.append(0)
        matrix.append(row)
    return matrix


def _stamp_default_obstacles(collision: list[list[int]], cols: int, rows: int) -> None:
    segments = (
        (rows // 4, cols // 8, cols // 2 - 3),
        (rows // 4, cols // 2 + 4, cols - cols // 8),
        (rows // 2, cols // 6, cols // 2 - 5),
        (rows // 2, cols // 2 + 5, cols - cols // 6),
        (rows * 3 // 4, cols // 8, cols // 2 - 4),
        (rows * 3 // 4, cols // 2 + 6, cols - cols // 8),
    )
    for y, x1, x2 in segments:
        if 1 <= y < rows - 1:
            for x in range(max(1, x1), min(cols - 1, x2)):
                collision[y][x] = 1

    for x in (cols // 3, cols * 2 // 3):
        gap_y = rows // 2
        for y in range(rows // 6, rows * 5 // 6):
            if abs(y - gap_y) <= 2:
                continue
            if 1 <= x < cols - 1 and 1 <= y < rows - 1:
                collision[y][x] = 1


def _default_enemy_spawn_cells(cols: int, rows: int) -> list[tuple[int, int]]:
    return [
        (3, 3),
        (cols - 4, 3),
        (3, rows - 4),
        (cols - 4, rows - 4),
        (cols // 2, 3),
        (cols // 2, rows - 4),
        (3, rows // 2),
        (cols - 4, rows // 2),
        (cols // 4, rows // 4),
        (cols * 3 // 4, rows * 3 // 4),
    ]


def _default_loot_cells(cols: int, rows: int) -> list[tuple[int, int]]:
    cells: list[tuple[int, int]] = []
    for y in range(3, rows - 3, max(3, rows // 7)):
        for x in range(4, cols - 4, max(5, cols // 8)):
            cells.append((x, y))
    return cells[:64]


def _mark_first_open(matrix: list[list[int]], collision: list[list[int]], x: int, y: int, *, value: int) -> None:
    rows = len(matrix)
    cols = len(matrix[0]) if rows else 0
    for radius in range(max(rows, cols)):
        for dy in range(-radius, radius + 1):
            for dx in range(-radius, radius + 1):
                if abs(dx) != radius and abs(dy) != radius:
                    continue
                cx = x + dx
                cy = y + dy
                if 0 <= cx < cols and 0 <= cy < rows and not collision[cy][cx]:
                    matrix[cy][cx] = value
                    return
