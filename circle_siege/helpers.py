from __future__ import annotations

import math
from typing import Iterable

import pygame


Vector2 = pygame.Vector2


def clamp(value: float, minimum: float, maximum: float) -> float:
    return max(minimum, min(maximum, value))


def lerp(a: float, b: float, amount: float) -> float:
    return a + (b - a) * amount


def lerp_vec(a: Vector2, b: Vector2, amount: float) -> Vector2:
    return a.lerp(b, amount)


def safe_normalize(vector: Vector2) -> Vector2:
    if vector.length_squared() <= 1e-9:
        return Vector2()
    return vector.normalize()


def distance_to_segment(point: Vector2, start: Vector2, end: Vector2) -> float:
    segment = end - start
    length_sq = segment.length_squared()
    if length_sq <= 1e-9:
        return point.distance_to(start)
    projection = clamp((point - start).dot(segment) / length_sq, 0.0, 1.0)
    closest = start + segment * projection
    return point.distance_to(closest)


def circle_rect_collision(center: Vector2, radius: float, rect: pygame.Rect) -> bool:
    closest_x = clamp(center.x, rect.left, rect.right)
    closest_y = clamp(center.y, rect.top, rect.bottom)
    dx = center.x - closest_x
    dy = center.y - closest_y
    return dx * dx + dy * dy <= radius * radius


def has_line_of_sight(start: Vector2, end: Vector2, obstacles: Iterable) -> bool:
    for obstacle in obstacles:
        if obstacle.blocks_sight and obstacle.rect.clipline(start, end):
            return False
    return True


def format_time(seconds: float) -> str:
    seconds = max(0, int(seconds))
    return f"{seconds // 60:02d}:{seconds % 60:02d}"


def draw_outlined_text(
    surface: pygame.Surface,
    font: pygame.font.Font,
    text: str,
    position: tuple[int, int],
    color: tuple[int, int, int],
    outline: tuple[int, int, int] = (8, 10, 12),
    center: bool = False,
) -> pygame.Rect:
    base = font.render(text, True, color)
    rect = base.get_rect(center=position) if center else base.get_rect(topleft=position)
    offsets = ((-2, 0), (2, 0), (0, -2), (0, 2))
    for dx, dy in offsets:
        shadow = font.render(text, True, outline)
        shadow_rect = shadow.get_rect(center=rect.center) if center else shadow.get_rect(topleft=rect.topleft)
        shadow_rect.move_ip(dx, dy)
        surface.blit(shadow, shadow_rect)
    surface.blit(base, rect)
    return rect


def truncate_text(font: pygame.font.Font, text: str, max_width: int, suffix: str = "...") -> str:
    if font.size(text)[0] <= max_width:
        return text
    clipped = text.rstrip()
    while clipped and font.size(clipped + suffix)[0] > max_width:
        clipped = clipped[:-1]
    return (clipped + suffix) if clipped else suffix


def _tokenize_wrap_units(text: str) -> list[str]:
    tokens: list[str] = []
    ascii_buffer = ""
    for char in text:
        if char == "\n":
            if ascii_buffer:
                tokens.append(ascii_buffer)
                ascii_buffer = ""
            tokens.append("\n")
            continue
        if char.isspace():
            if ascii_buffer:
                tokens.append(ascii_buffer)
                ascii_buffer = ""
            tokens.append(char)
            continue
        if char.isascii() and (char.isalnum() or char in "._-/%:+#&()[]{}<>"):
            ascii_buffer += char
            continue
        if ascii_buffer:
            tokens.append(ascii_buffer)
            ascii_buffer = ""
        tokens.append(char)
    if ascii_buffer:
        tokens.append(ascii_buffer)
    return tokens


def wrap_text(font: pygame.font.Font, text: str, max_width: int, max_lines: int | None = None) -> list[str]:
    if not text:
        return [""]

    lines: list[str] = []
    current = ""
    truncated = False

    for token in _tokenize_wrap_units(text):
        if token == "\n":
            lines.append(current.rstrip())
            current = ""
            if max_lines is not None and len(lines) >= max_lines:
                truncated = True
                break
            continue

        if not current and token.isspace():
            continue

        trial = current + token
        if font.size(trial)[0] <= max_width:
            current = trial
            continue

        if current:
            lines.append(current.rstrip())
            if max_lines is not None and len(lines) >= max_lines:
                truncated = True
                break
            current = ""
            if token.isspace():
                continue

        if font.size(token)[0] <= max_width:
            current = token.lstrip()
            continue

        for char in token:
            trial = current + char
            if font.size(trial)[0] <= max_width or not current:
                current = trial
            else:
                lines.append(current.rstrip())
                if max_lines is not None and len(lines) >= max_lines:
                    truncated = True
                    current = ""
                    break
                current = char
        if truncated:
            break

    if current and (max_lines is None or len(lines) < max_lines):
        lines.append(current.rstrip())
    elif current:
        truncated = True

    if max_lines is not None and len(lines) > max_lines:
        lines = lines[:max_lines]
        truncated = True

    if truncated and lines:
        lines[-1] = truncate_text(font, lines[-1], max_width)

    return lines


def draw_text_block(
    surface: pygame.Surface,
    font: pygame.font.Font,
    text: str,
    rect: pygame.Rect,
    color: tuple[int, int, int],
    line_spacing: int = 6,
    max_lines: int | None = None,
    center: bool = False,
) -> pygame.Rect:
    lines = wrap_text(font, text, rect.width, max_lines=max_lines)
    rendered_rects: list[pygame.Rect] = []
    y = rect.top
    for line in lines:
        rendered = font.render(line, True, color)
        line_rect = rendered.get_rect(centerx=rect.centerx, y=y) if center else rendered.get_rect(x=rect.x, y=y)
        surface.blit(rendered, line_rect)
        rendered_rects.append(line_rect)
        y += rendered.get_height() + line_spacing
    if not rendered_rects:
        return pygame.Rect(rect.x, rect.y, 0, 0)
    result = rendered_rects[0].copy()
    for item in rendered_rects[1:]:
        result.union_ip(item)
    return result


def draw_progress_bar(
    surface: pygame.Surface,
    rect: pygame.Rect,
    ratio: float,
    fill_color: tuple[int, int, int],
    back_color: tuple[int, int, int] = (25, 31, 37),
    border_color: tuple[int, int, int] = (214, 219, 223),
) -> None:
    pygame.draw.rect(surface, back_color, rect, border_radius=8)
    inner = rect.inflate(-4, -4)
    if ratio > 0:
        fill = inner.copy()
        fill.width = max(0, int(inner.width * clamp(ratio, 0.0, 1.0)))
        pygame.draw.rect(surface, fill_color, fill, border_radius=6)
    pygame.draw.rect(surface, border_color, rect, width=2, border_radius=8)


def screen_clamp_rect(rect: pygame.Rect, width: int, height: int) -> pygame.Rect:
    if rect.left < 0:
        rect.left = 0
    if rect.top < 0:
        rect.top = 0
    if rect.right > width:
        rect.right = width
    if rect.bottom > height:
        rect.bottom = height
    return rect


def radians_from_vector(vector: Vector2) -> float:
    return math.atan2(vector.y, vector.x)
