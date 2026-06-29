from __future__ import annotations

from dataclasses import dataclass

DEFAULT_AUDIO_SCHEME = "cinematic"


@dataclass(frozen=True)
class SoundEvent:
    candidates: tuple[str, ...]
    channel: str = "effects"
    volume: float = 1.0
    cooldown: float = 0.0


def _event(
    scheme: str,
    name: str,
    fallback: tuple[str, ...] = (),
    channel: str = "effects",
    volume: float = 1.0,
    cooldown: float = 0.0,
) -> SoundEvent:
    candidates = (f"{scheme}.{name}", name, *fallback)
    return SoundEvent(tuple(dict.fromkeys(candidates)), channel, volume, cooldown)


def _build_scheme(scheme: str, volume_scale: float) -> dict[str, SoundEvent]:
    return {
        "weapon_fire": _event(scheme, "weapon_fire", ("mechanism",), "combat", 0.72 * volume_scale, 0.025),
        "weapon_fire_smg": _event(scheme, "weapon_fire_smg", (f"{scheme}.weapon_fire", "weapon_fire"), "combat", 0.70 * volume_scale, 0.020),
        "weapon_fire_carbine": _event(scheme, "weapon_fire_carbine", (f"{scheme}.weapon_fire", "weapon_fire"), "combat", 0.76 * volume_scale, 0.035),
        "weapon_fire_shotgun": _event(scheme, "weapon_fire_shotgun", (f"{scheme}.weapon_fire", "weapon_fire"), "combat", 0.92 * volume_scale, 0.080),
        "weapon_fire_dmr": _event(scheme, "weapon_fire_dmr", (f"{scheme}.weapon_fire", "weapon_fire"), "combat", 0.86 * volume_scale, 0.075),
        "bullet_impact": _event(scheme, "bullet_impact", ("mechanism",), "effects", 0.44 * volume_scale, 0.025),
        "body_hit": _event(scheme, "body_hit", ("danger",), "combat", 0.54 * volume_scale, 0.035),
        "enemy_hurt": _event(scheme, "enemy_hurt", (f"{scheme}.body_hit", "body_hit"), "combat", 0.56 * volume_scale, 0.060),
        "enemy_down": _event(scheme, "enemy_down", ("killfeed",), "combat", 0.74 * volume_scale, 0.120),
        "player_hurt": _event(scheme, "player_hurt", ("danger",), "combat", 0.86 * volume_scale, 0.150),
        "player_down": _event(scheme, "player_down", ("danger", "killfeed"), "combat", 0.96 * volume_scale, 0.300),
        "boss_hurt": _event(scheme, "boss_hurt", (f"{scheme}.body_hit", "body_hit"), "combat", 0.72 * volume_scale, 0.080),
        "boss_alert": _event(scheme, "boss_alert", ("danger",), "combat", 0.90 * volume_scale, 0.400),
        "boss_defeated": _event(scheme, "boss_defeated", ("killfeed",), "objective", 1.00 * volume_scale, 0.150),
        "pickup_weapon": _event(scheme, "pickup_weapon", (f"{scheme}.pickup_item", "pickup_item", "reload_complete"), "ui", 0.82 * volume_scale, 0.050),
        "pickup_ammo": _event(scheme, "pickup_ammo", (f"{scheme}.pickup_item", "pickup_item", "reload_complete"), "ui", 0.70 * volume_scale, 0.050),
        "pickup_medkit": _event(scheme, "pickup_medkit", (f"{scheme}.pickup_item", "pickup_item", "reload_complete"), "ui", 0.76 * volume_scale, 0.050),
        "teleport_charge": _event(scheme, "teleport_charge", ("mechanism",), "objective", 0.90 * volume_scale, 0.20),
        "teleport_burst": _event(scheme, "teleport_burst", ("killfeed", "mechanism"), "objective", 1.00 * volume_scale, 0.20),
        "map_arrive": _event(scheme, "map_arrive", ("mechanism",), "objective", 0.92 * volume_scale, 0.20),
        "pickup_item": _event(scheme, "pickup_item", ("reload_complete",), "ui", 0.78 * volume_scale, 0.05),
        "map_pickup": _event(scheme, "map_pickup", ("killfeed", "reload_complete"), "objective", 0.88 * volume_scale, 0.10),
        "map_locked": _event(scheme, "map_locked", ("danger",), "objective", 0.74 * volume_scale, 0.18),
        "reload_complete": _event(scheme, "reload_complete", ("reload_complete",), "ui", 0.82 * volume_scale, 0.08),
        "grenade_throw": _event(scheme, "grenade_throw", ("grenade_throw",), "combat", 0.82 * volume_scale, 0.08),
        "grenade_blast": _event(scheme, "grenade_blast", ("grenade_blast",), "combat", 1.00 * volume_scale, 0.12),
        "dash": _event(scheme, "dash", ("mechanism",), "effects", 0.72 * volume_scale, 0.18),
        "heal_start": _event(scheme, "heal_start", (f"{scheme}.pickup_medkit", "pickup_medkit"), "ui", 0.64 * volume_scale, 0.22),
        "danger": _event(scheme, "danger", ("danger",), "combat", 0.86 * volume_scale, 0.20),
        "mechanism": _event(scheme, "mechanism", ("mechanism",), "objective", 0.80 * volume_scale, 0.10),
        "killfeed": _event(scheme, "killfeed", ("killfeed",), "ui", 0.78 * volume_scale, 0.08),
    }


AUDIO_SCHEMES: dict[str, dict[str, SoundEvent]] = {
    "cinematic": _build_scheme("cinematic", 1.00),
    "tactical": _build_scheme("tactical", 0.86),
    "arcade": _build_scheme("arcade", 0.95),
}


def normalize_scheme(name: str | None) -> str:
    if name in AUDIO_SCHEMES:
        return name
    return DEFAULT_AUDIO_SCHEME


def list_audio_schemes() -> tuple[str, ...]:
    return tuple(AUDIO_SCHEMES)


def get_event_definition(scheme: str | None, event_name: str) -> SoundEvent | None:
    return AUDIO_SCHEMES.get(normalize_scheme(scheme), {}).get(event_name)
