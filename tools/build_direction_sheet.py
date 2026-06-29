from __future__ import annotations

import argparse
from pathlib import Path

from PIL import Image

ROW_BAND_MAX_GAP = 12
COLUMN_BAND_MAX_GAP = 48


def trim_alpha(image: Image.Image) -> Image.Image:
    alpha = image.getchannel("A")
    bbox = alpha.getbbox()
    if bbox is None:
        return image
    return image.crop(bbox)


def fit_to_cell(image: Image.Image, cell_size: int, bottom_padding: int = 4) -> Image.Image:
    trimmed = trim_alpha(image)
    canvas = Image.new("RGBA", (cell_size, cell_size), (0, 0, 0, 0))
    if trimmed.getbbox() is None:
        return canvas
    scale = min((cell_size - 16) / max(1, trimmed.width), (cell_size - 12) / max(1, trimmed.height))
    resized = trimmed.resize((max(1, int(trimmed.width * scale)), max(1, int(trimmed.height * scale))), Image.LANCZOS)
    x = (cell_size - resized.width) // 2
    y = cell_size - resized.height - bottom_padding
    canvas.alpha_composite(resized, (x, y))
    return canvas


def _build_projection(alpha: Image.Image, axis: str, threshold: int = 20) -> list[int]:
    width, height = alpha.size
    projection: list[int] = []
    if axis == "x":
        for x in range(width):
            projection.append(sum(1 for y in range(height) if alpha.getpixel((x, y)) > threshold))
    else:
        for y in range(height):
            projection.append(sum(1 for x in range(width) if alpha.getpixel((x, y)) > threshold))
    return projection


def _find_peak_centers(projection: list[int], expected_count: int) -> list[int]:
    length = len(projection)
    min_distance = max(8, int(length / max(1, expected_count) * 0.6))
    ranked = sorted(range(length), key=lambda index: projection[index], reverse=True)
    peaks: list[int] = []
    for index in ranked:
        if projection[index] <= 0:
            break
        if all(abs(index - peak) >= min_distance for peak in peaks):
            peaks.append(index)
            if len(peaks) == expected_count:
                break
    if len(peaks) != expected_count:
        return []
    peaks.sort()
    return peaks


def _bands_from_centers(centers: list[int], max_length: int) -> list[tuple[int, int]]:
    if not centers:
        return []
    bounds: list[int] = [0]
    for left, right in zip(centers, centers[1:]):
        bounds.append((left + right) // 2)
    bounds.append(max_length)
    bands: list[tuple[int, int]] = []
    for index in range(len(centers)):
        start = max(0, bounds[index])
        end = min(max_length, bounds[index + 1])
        bands.append((start, end))
    return bands


def _nonzero_bands(projection: list[int], threshold: int = 10, max_gap: int = 0) -> list[tuple[int, int]]:
    bands: list[tuple[int, int]] = []
    start: int | None = None
    for index, value in enumerate(projection):
        if value > threshold:
            if start is None:
                start = index
        elif start is not None:
            bands.append((start, index))
            start = None
    if start is not None:
        bands.append((start, len(projection)))
    if max_gap <= 0 or not bands:
        return bands
    merged = [bands[0]]
    for start, end in bands[1:]:
        previous_start, previous_end = merged[-1]
        if start - previous_end <= max_gap:
            merged[-1] = (previous_start, end)
        else:
            merged.append((start, end))
    return merged


def _detect_row_bands(alpha: Image.Image, rows: int) -> list[tuple[int, int]]:
    projection = _build_projection(alpha, "y")
    row_bands = _nonzero_bands(projection, max_gap=ROW_BAND_MAX_GAP)
    if len(row_bands) == rows:
        return row_bands

    # Some authored move sheets let adjacent stances overlap vertically.
    # In that case, row peaks are more stable than raw nonzero spans.
    row_centers = _find_peak_centers(projection, rows)
    if not row_centers:
        return row_bands
    return _bands_from_centers(row_centers, alpha.height)


def _component_center(box: tuple[int, int, int, int], axis: str) -> float:
    left, top, right, bottom = box
    if axis == "x":
        return (left + right) / 2
    return (top + bottom) / 2


def _find_component_boxes(alpha: Image.Image, threshold: int = 20, min_pixels: int = 96) -> list[tuple[int, int, int, int]]:
    width, height = alpha.size
    pixels = alpha.load()
    visited = bytearray(width * height)
    boxes: list[tuple[int, int, int, int]] = []

    for y in range(height):
        row_offset = y * width
        for x in range(width):
            index = row_offset + x
            if visited[index] or pixels[x, y] <= threshold:
                continue
            stack = [(x, y)]
            visited[index] = 1
            left = right = x
            top = bottom = y
            count = 0

            while stack:
                current_x, current_y = stack.pop()
                count += 1
                left = min(left, current_x)
                right = max(right, current_x)
                top = min(top, current_y)
                bottom = max(bottom, current_y)
                for next_y in range(max(0, current_y - 1), min(height, current_y + 2)):
                    next_row_offset = next_y * width
                    for next_x in range(max(0, current_x - 1), min(width, current_x + 2)):
                        next_index = next_row_offset + next_x
                        if visited[next_index] or pixels[next_x, next_y] <= threshold:
                            continue
                        visited[next_index] = 1
                        stack.append((next_x, next_y))

            if count >= min_pixels:
                boxes.append((left, top, right + 1, bottom + 1))

    return boxes


def build_sheet(source_path: Path, output_path: Path, columns: int, rows: int, cell_size: int, layout: str = "auto") -> None:
    with Image.open(source_path).convert("RGBA") as image:
        alpha = image.getchannel("A")
        if layout == "bands":
            row_bands = _detect_row_bands(alpha, rows)
            if len(row_bands) != rows:
                raise ValueError(f"Expected {rows} row bands in {source_path.name}, found {len(row_bands)}.")
            sheet = Image.new("RGBA", (cell_size * columns, cell_size * rows), (0, 0, 0, 0))
            for row, (top, bottom) in enumerate(row_bands):
                band_projection = [
                    sum(1 for y in range(top, bottom) if alpha.getpixel((x, y)) > 20)
                    for x in range(image.width)
                ]
                col_bands = _nonzero_bands(band_projection, max_gap=COLUMN_BAND_MAX_GAP)
                if len(col_bands) != columns:
                    raise ValueError(
                        f"Expected {columns} column bands in row {row + 1} of {source_path.name}, found {len(col_bands)}."
                    )
                for col, (left, right) in enumerate(col_bands):
                    rect = (
                        max(0, left - 8),
                        max(0, top - 8),
                        min(image.width, right + 8),
                        min(image.height, bottom + 8),
                    )
                    cell = image.crop(rect)
                    normalized = fit_to_cell(cell, cell_size)
                    sheet.alpha_composite(normalized, (col * cell_size, row * cell_size))
            output_path.parent.mkdir(parents=True, exist_ok=True)
            sheet.save(output_path)
            return
        if layout == "components":
            component_boxes = _find_component_boxes(alpha)
            expected_count = columns * rows
            if len(component_boxes) != expected_count:
                raise ValueError(
                    f"Expected {expected_count} sprite components in {source_path.name}, found {len(component_boxes)}."
                )
            ordered_boxes = sorted(component_boxes, key=lambda box: _component_center(box, "y"))
            sheet = Image.new("RGBA", (cell_size * columns, cell_size * rows), (0, 0, 0, 0))
            for row in range(rows):
                row_boxes = ordered_boxes[row * columns : (row + 1) * columns]
                row_boxes.sort(key=lambda box: _component_center(box, "x"))
                for col, box in enumerate(row_boxes):
                    left, top, right, bottom = box
                    rect = (
                        max(0, left - 8),
                        max(0, top - 8),
                        min(image.width, right + 8),
                        min(image.height, bottom + 8),
                    )
                    cell = image.crop(rect)
                    normalized = fit_to_cell(cell, cell_size)
                    sheet.alpha_composite(normalized, (col * cell_size, row * cell_size))
            output_path.parent.mkdir(parents=True, exist_ok=True)
            sheet.save(output_path)
            return
        row_centers = _find_peak_centers(_build_projection(alpha, "y"), rows)
        col_centers = _find_peak_centers(_build_projection(alpha, "x"), columns)
        row_bands = _bands_from_centers(row_centers, image.height)
        col_bands = _bands_from_centers(col_centers, image.width)
        sheet = Image.new("RGBA", (cell_size * columns, cell_size * rows), (0, 0, 0, 0))
        use_detected_layout = layout == "auto" and bool(row_bands) and bool(col_bands)
        if not use_detected_layout:
            cell_width = image.width // columns
            cell_height = image.height // rows

        for row in range(rows):
            for col in range(columns):
                if use_detected_layout:
                    top, bottom = row_bands[row]
                    left, right = col_bands[col]
                    rect = (
                        max(0, left - 8),
                        max(0, top - 8),
                        min(image.width, right + 8),
                        min(image.height, bottom + 8),
                    )
                else:
                    rect = (
                        col * cell_width,
                        row * cell_height,
                        (col + 1) * cell_width,
                        (row + 1) * cell_height,
                    )
                cell = image.crop(rect)
                normalized = fit_to_cell(cell, cell_size)
                sheet.alpha_composite(normalized, (col * cell_size, row * cell_size))
        output_path.parent.mkdir(parents=True, exist_ok=True)
        sheet.save(output_path)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--columns", type=int, default=4)
    parser.add_argument("--rows", type=int, default=2)
    parser.add_argument("--cell-size", type=int, default=96)
    parser.add_argument("--layout", choices=("auto", "grid", "bands", "components"), default="auto")
    args = parser.parse_args()
    build_sheet(Path(args.input), Path(args.output), args.columns, args.rows, args.cell_size, layout=args.layout)


if __name__ == "__main__":
    main()
