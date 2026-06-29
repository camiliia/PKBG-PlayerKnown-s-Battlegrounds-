from __future__ import annotations

import math
import random
import struct
import wave
from pathlib import Path


SAMPLE_RATE = 44_100
ROOT = Path(__file__).resolve().parents[2] / "resource" / "sound" / "generated"


def clamp(value: float) -> float:
    return max(-1.0, min(1.0, value))


def write_wav(path: Path, samples: list[float]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as wav:
        wav.setnchannels(2)
        wav.setsampwidth(2)
        wav.setframerate(SAMPLE_RATE)
        frames = bytearray()
        for sample in samples:
            value = int(clamp(sample) * 32767)
            frames.extend(struct.pack("<hh", value, value))
        wav.writeframes(frames)


def envelope(progress: float, attack: float = 0.015, release_power: float = 2.0) -> float:
    if progress < attack:
        return progress / max(attack, 1e-6)
    return max(0.0, (1.0 - progress) ** release_power)


def render(duration: float, builder) -> list[float]:
    count = max(1, int(SAMPLE_RATE * duration))
    return [builder(i / SAMPLE_RATE, i / max(1, count - 1)) for i in range(count)]


def noise_burst(duration: float, seed: str, gain: float, decay: float, tone: float = 0.0) -> list[float]:
    rng = random.Random(seed)

    def build(t: float, p: float) -> float:
        amp = math.exp(-p * decay)
        value = rng.uniform(-1.0, 1.0) * amp
        if tone > 0:
            value += math.sin(math.tau * tone * t) * amp * 0.55
        return value * gain

    return render(duration, build)


def tone_sweep(duration: float, start: float, end: float, gain: float, seed: str = "") -> list[float]:
    rng = random.Random(seed)

    def build(t: float, p: float) -> float:
        freq = start + (end - start) * p
        value = math.sin(math.tau * freq * t) * math.sin(math.pi * p)
        value += rng.uniform(-0.12, 0.12) * p * (1.0 - p)
        return value * gain

    return render(duration, build)


def tone_hit(duration: float, freq: float, gain: float, seed: str) -> list[float]:
    rng = random.Random(seed)

    def build(t: float, p: float) -> float:
        amp = envelope(p, attack=0.004, release_power=3.2)
        value = math.sin(math.tau * freq * t) * amp
        value += math.sin(math.tau * freq * 0.48 * t) * amp * 0.45
        value += rng.uniform(-0.5, 0.5) * amp * 0.28
        return value * gain

    return render(duration, build)


def whoosh(duration: float, seed: str, gain: float) -> list[float]:
    rng = random.Random(seed)

    def build(_t: float, p: float) -> float:
        return rng.uniform(-1.0, 1.0) * math.sin(math.pi * p) * gain

    return render(duration, build)


def music_loop(duration: float, root: float, tempo: float, gain: float, boss: bool = False) -> list[float]:
    beat_len = 60.0 / tempo
    notes = (0, 3, 7, 10) if boss else (0, 5, 7, 3)

    def build(t: float, p: float) -> float:
        beat_index = int(t / beat_len)
        beat_phase = (t % beat_len) / beat_len
        note = notes[beat_index % len(notes)]
        freq = root * (2 ** (note / 12.0))
        bass = math.sin(math.tau * freq * t) * 0.55
        pad = math.sin(math.tau * freq * 1.5 * t) * 0.22
        pulse = math.sin(math.tau * 42.0 * t) * math.exp(-beat_phase * (9.0 if boss else 6.5))
        hats = math.sin(math.tau * 680.0 * t) * math.exp(-((beat_phase * 4.0) % 1.0) * 15.0) * 0.06
        loop_fade = math.sin(math.pi * min(p, 1.0)) if p < 0.06 or p > 0.94 else 1.0
        return (bass + pad + pulse + hats) * gain * loop_fade

    return render(duration, build)


def ambient_loop(duration: float, seed: str, rain: bool) -> list[float]:
    rng = random.Random(seed)

    def build(t: float, _p: float) -> float:
        bed = rng.uniform(-1.0, 1.0) * (0.18 if rain else 0.08)
        low = math.sin(math.tau * 46.0 * t) * (0.035 if rain else 0.055)
        if rain and rng.random() < 0.008:
            bed += rng.uniform(-0.8, 0.8)
        if not rain and rng.random() < 0.0015:
            bed += math.sin(math.tau * 280.0 * t) * 0.18
        return (bed + low) * 0.55

    return render(duration, build)


def build_scheme(scheme: str, scale: float, bright: float) -> None:
    base = ROOT / scheme
    assets = {
        "weapon_fire": noise_burst(0.085, f"{scheme}:fire", 0.42 * scale, 12.0, 145 * bright),
        "weapon_fire_smg": noise_burst(0.065, f"{scheme}:smg", 0.35 * scale, 13.0, 180 * bright),
        "weapon_fire_carbine": noise_burst(0.095, f"{scheme}:carbine", 0.42 * scale, 10.0, 130 * bright),
        "weapon_fire_shotgun": noise_burst(0.19, f"{scheme}:shotgun", 0.55 * scale, 7.8, 92 * bright),
        "weapon_fire_dmr": noise_burst(0.145, f"{scheme}:dmr", 0.50 * scale, 8.8, 112 * bright),
        "bullet_impact": tone_hit(0.065, 620 * bright, 0.25 * scale, f"{scheme}:impact"),
        "body_hit": tone_hit(0.12, 96, 0.36 * scale, f"{scheme}:body"),
        "enemy_hurt": tone_hit(0.15, 156, 0.32 * scale, f"{scheme}:enemy_hurt"),
        "enemy_down": tone_sweep(0.28, 170, 62, 0.36 * scale, f"{scheme}:enemy_down"),
        "player_hurt": tone_hit(0.18, 210, 0.38 * scale, f"{scheme}:player_hurt"),
        "player_down": tone_sweep(0.44, 180, 48, 0.45 * scale, f"{scheme}:player_down"),
        "boss_hurt": tone_hit(0.18, 72, 0.46 * scale, f"{scheme}:boss_hurt"),
        "boss_alert": tone_sweep(0.55, 90, 220, 0.42 * scale, f"{scheme}:boss_alert"),
        "boss_defeated": tone_sweep(0.72, 128, 34, 0.48 * scale, f"{scheme}:boss_defeated"),
        "pickup_item": tone_sweep(0.16, 560 * bright, 1040 * bright, 0.30 * scale, f"{scheme}:pickup"),
        "pickup_weapon": tone_sweep(0.20, 380 * bright, 940 * bright, 0.32 * scale, f"{scheme}:pickup_weapon"),
        "pickup_ammo": tone_sweep(0.13, 700 * bright, 1120 * bright, 0.26 * scale, f"{scheme}:pickup_ammo"),
        "pickup_medkit": tone_sweep(0.22, 420 * bright, 760 * bright, 0.28 * scale, f"{scheme}:pickup_medkit"),
        "map_pickup": tone_sweep(0.36, 260 * bright, 980 * bright, 0.38 * scale, f"{scheme}:map_pickup"),
        "map_locked": tone_sweep(0.22, 260, 120, 0.34 * scale, f"{scheme}:map_locked"),
        "reload_complete": tone_hit(0.13, 480 * bright, 0.24 * scale, f"{scheme}:reload"),
        "grenade_throw": whoosh(0.18, f"{scheme}:grenade_throw", 0.26 * scale),
        "grenade_blast": noise_burst(0.52, f"{scheme}:grenade_blast", 0.62 * scale, 4.5, 62),
        "dash": whoosh(0.22, f"{scheme}:dash", 0.34 * scale),
        "heal_start": tone_sweep(0.26, 330 * bright, 640 * bright, 0.24 * scale, f"{scheme}:heal"),
        "teleport_charge": tone_sweep(0.9, 160 * bright, 980 * bright, 0.34 * scale, f"{scheme}:tele_charge"),
        "teleport_burst": noise_burst(0.62, f"{scheme}:tele_burst", 0.52 * scale, 3.8, 88),
        "map_arrive": tone_sweep(0.42, 340 * bright, 780 * bright, 0.34 * scale, f"{scheme}:arrive"),
        "danger": tone_sweep(0.30, 132, 96, 0.34 * scale, f"{scheme}:danger"),
        "mechanism": tone_hit(0.18, 360 * bright, 0.28 * scale, f"{scheme}:mechanism"),
        "killfeed": tone_sweep(0.18, 580 * bright, 720 * bright, 0.24 * scale, f"{scheme}:killfeed"),
    }
    for name, samples in assets.items():
        write_wav(base / f"{name}.wav", samples)


def main() -> None:
    write_wav(ROOT / "music" / "menu_theme.wav", music_loop(6.0, 82.0, 84.0, 0.20))
    write_wav(ROOT / "music" / "battle_theme.wav", music_loop(6.0, 72.0, 92.0, 0.24))
    write_wav(ROOT / "music" / "combat_theme.wav", music_loop(5.0, 86.0, 128.0, 0.27))
    write_wav(ROOT / "music" / "boss_theme.wav", music_loop(5.0, 58.0, 112.0, 0.32, boss=True))
    write_wav(ROOT / "ambient" / "rain_loop.wav", ambient_loop(4.0, "rain", True))
    write_wav(ROOT / "ambient" / "city_loop.wav", ambient_loop(4.0, "city", False))
    build_scheme("cinematic", 1.0, 1.0)
    build_scheme("tactical", 0.84, 0.82)
    build_scheme("arcade", 0.92, 1.24)
    print(f"Generated audio assets under {ROOT}")


if __name__ == "__main__":
    main()
