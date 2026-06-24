from __future__ import annotations

import pygame


RELOAD_COMPLETE = pygame.event.custom_type()
RESPAWN_PLAYER = pygame.event.custom_type()
MATCH_END = pygame.event.custom_type()
SHAKE_CAMERA = pygame.event.custom_type()
SHOW_KILLFEED = pygame.event.custom_type()
PLAYER_ENTER_TRIGGER = pygame.event.custom_type()
CAPTURE_POINT = pygame.event.custom_type()
SKILL_COOLDOWN_END = pygame.event.custom_type()


def post_reload_complete(owner_name: str, weapon_label: str, is_player: bool) -> None:
    pygame.event.post(
        pygame.event.Event(
            RELOAD_COMPLETE,
            owner_name=owner_name,
            weapon_label=weapon_label,
            is_player=is_player,
        )
    )


def post_match_end(summary: dict[str, object]) -> None:
    pygame.event.post(pygame.event.Event(MATCH_END, summary=summary))


def post_respawn_player(anchor: tuple[float, float] | None = None) -> None:
    pygame.event.post(pygame.event.Event(RESPAWN_PLAYER, anchor=anchor))


def post_killfeed(text: str, color: tuple[int, int, int], ttl: float = 4.0) -> None:
    pygame.event.post(pygame.event.Event(SHOW_KILLFEED, text=text, color=color, ttl=ttl))


def post_camera_shake(amplitude: float, duration: float) -> None:
    pygame.event.post(pygame.event.Event(SHAKE_CAMERA, amplitude=amplitude, duration=duration))


def post_player_enter_trigger(label: str, kind: str) -> None:
    pygame.event.post(pygame.event.Event(PLAYER_ENTER_TRIGGER, label=label, kind=kind))


def post_capture_point(label: str, reward: str) -> None:
    pygame.event.post(pygame.event.Event(CAPTURE_POINT, label=label, reward=reward))


def post_skill_cooldown_end(skill_name: str) -> None:
    pygame.event.post(pygame.event.Event(SKILL_COOLDOWN_END, skill_name=skill_name))
