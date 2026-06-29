from __future__ import annotations

import array
import math
import random
import time
from pathlib import Path

import pygame

from ..core.config import RESOURCE_ROOT
from .audio_events import DEFAULT_AUDIO_SCHEME, get_event_definition, normalize_scheme


SUPPORTED_SOUND_SUFFIXES = {".wav", ".ogg", ".mp3"}


ONE_SHOT_CHANNELS = {"effects", "combat", "ui", "objective"}


class AudioManager:
    def __init__(self) -> None:
        self.master_volume = 1.0
        self.music_volume = 1.0
        self.effects_volume = 1.0
        self.audio_scheme = DEFAULT_AUDIO_SCHEME
        self.available = False
        self.current_music = None
        self.current_ambient = None
        self.sounds: dict[str, pygame.mixer.Sound] = {}
        self.channels: dict[str, pygame.mixer.Channel] = {}
        self._bus_volumes: dict[str, float] = {}
        self._event_last_played: dict[str, float] = {}
        try:
            if not pygame.mixer.get_init():
                pygame.mixer.init(frequency=44100, size=-16, channels=2, buffer=512)
            pygame.mixer.set_num_channels(24)
            pygame.mixer.set_reserved(4)
            self.channels = {
                "music": pygame.mixer.Channel(0),
                "ambient": pygame.mixer.Channel(1),
                "ui": pygame.mixer.Channel(2),
                "objective": pygame.mixer.Channel(3),
                "effects": pygame.mixer.Channel(4),
                "combat": pygame.mixer.Channel(5),
            }
            self.available = True
            self._load_default_sounds()
            self._build_fallback_sounds()
            self._apply_channel_volumes()
        except pygame.error:
            self.available = False

    def _load_default_sounds(self) -> None:
        sound_root = RESOURCE_ROOT / "sound"
        generated_root = sound_root / "generated"
        extracted_root = sound_root / "extracted"
        mapping = {
            "menu_music": extracted_root / "menu_music.ogg",
            "battle_music": extracted_root / "battle_music.ogg",
            "generated_menu_music": generated_root / "music" / "menu_theme.wav",
            "generated_battle_music": generated_root / "music" / "battle_theme.wav",
            "combat_music": generated_root / "music" / "combat_theme.wav",
            "boss_music": generated_root / "music" / "boss_theme.wav",
            "rain_ambient": generated_root / "ambient" / "rain_loop.wav",
            "city_ambient": generated_root / "ambient" / "city_loop.wav",
            "legacy_menu_music": sound_root / "aigei.mp3",
            "legacy_battle_music": sound_root / "nmw.mp3",
            "reload_complete": sound_root / "swk.wav",
            "killfeed": sound_root / "swk.wav",
            "danger": sound_root / "swk.wav",
            "mechanism": sound_root / "swk.wav",
            "grenade_throw": sound_root / "swk.wav",
            "grenade_blast": sound_root / "swk.wav",
        }
        for key, path in mapping.items():
            self._load_sound(key, path)
        if "menu_music" not in self.sounds:
            self._load_sound("menu_music", generated_root / "music" / "menu_theme.wav")
        if "menu_music" not in self.sounds:
            self._load_sound("menu_music", sound_root / "aigei.mp3")
        if "battle_music" not in self.sounds:
            self._load_sound("battle_music", generated_root / "music" / "battle_theme.wav")
        if "battle_music" not in self.sounds:
            self._load_sound("battle_music", sound_root / "nmw.mp3")
        self._load_sound_assets(sound_root)

    def _load_sound(self, key: str, path: Path) -> None:
        if not path.exists() or path.suffix.lower() not in SUPPORTED_SOUND_SUFFIXES:
            return
        try:
            self.sounds[key] = pygame.mixer.Sound(str(path))
        except pygame.error:
            return

    def _load_sound_assets(self, sound_root: Path) -> None:
        if not sound_root.exists():
            return
        for path in sound_root.rglob("*"):
            if not path.is_file() or path.suffix.lower() not in SUPPORTED_SOUND_SUFFIXES:
                continue
            relative = path.relative_to(sound_root).with_suffix("")
            key = ".".join(relative.parts)
            self._load_sound(key, path)
            if len(relative.parts) >= 3 and relative.parts[0] == "generated":
                self._load_sound(".".join(relative.parts[1:]), path)

    def _apply_channel_volumes(self) -> None:
        if not self.available:
            return
        self._bus_volumes = {
            "music": self.master_volume * self.music_volume * 0.58,
            "ambient": self.master_volume * self.music_volume * 0.34,
            "effects": self.master_volume * self.effects_volume * 0.48,
            "ui": self.master_volume * self.effects_volume * 0.34,
            "combat": self.master_volume * self.effects_volume * 0.58,
            "objective": self.master_volume * self.effects_volume * 0.58,
        }
        for key, channel in self.channels.items():
            channel.set_volume(self._bus_volumes.get(key, self.master_volume))

    def set_master_volume(self, value: float) -> None:
        self.master_volume = max(0.0, min(1.0, value))
        self._apply_channel_volumes()

    def set_music_volume(self, value: float) -> None:
        self.music_volume = max(0.0, min(1.0, value))
        self._apply_channel_volumes()

    def set_effects_volume(self, value: float) -> None:
        self.effects_volume = max(0.0, min(1.0, value))
        self._apply_channel_volumes()

    def set_audio_scheme(self, name: str) -> None:
        self.audio_scheme = normalize_scheme(name)

    def play_sfx(
        self,
        event_name: str,
        volume: float = 1.0,
        channel_name: str | None = None,
        loops: int = 0,
        fade_ms: int = 0,
    ) -> bool:
        if not self.available:
            return False
        sound = self.sounds.get(event_name)
        if sound is None:
            return False
        channel_key = channel_name or self._default_channel_for_event(event_name)
        channel = self._select_channel(channel_key, loops)
        if channel is None:
            return False
        sound.set_volume(max(0.0, min(1.0, volume)))
        channel.set_volume(self._bus_volumes.get(channel_key, self._bus_volumes.get("effects", 1.0)))
        channel.play(sound, loops=loops, fade_ms=max(0, fade_ms))
        return True

    def play_event(self, event_name: str, scheme_name: str | None = None, volume_scale: float = 1.0) -> bool:
        scheme = normalize_scheme(scheme_name or self.audio_scheme)
        event = get_event_definition(scheme, event_name)
        if event is None:
            return self.play_sfx(event_name, volume=max(0.0, min(1.0, volume_scale)))

        cooldown_key = f"{scheme}:{event_name}"
        now = time.monotonic()
        last_played = self._event_last_played.get(cooldown_key, -9999.0)
        if event.cooldown > 0.0 and now - last_played < event.cooldown:
            return False

        for candidate in event.candidates:
            if self.play_sfx(candidate, volume=event.volume * max(0.0, min(1.0, volume_scale)), channel_name=event.channel):
                self._event_last_played[cooldown_key] = now
                return True
        return False

    def _select_channel(self, channel_key: str, loops: int = 0) -> pygame.mixer.Channel | None:
        if loops != 0 or channel_key in {"music", "ambient"}:
            return self.channels.get(channel_key)
        if channel_key in ONE_SHOT_CHANNELS:
            return pygame.mixer.find_channel(False) or self.channels.get(channel_key)
        return self.channels.get(channel_key) or pygame.mixer.find_channel(False)

    def _default_channel_for_event(self, event_name: str) -> str:
        if event_name in {"reload_complete", "killfeed"}:
            return "ui"
        if event_name.startswith(("grenade_", "boss_", "player_")) or event_name in {
            "danger",
            "weapon_fire",
        }:
            return "combat"
        if event_name.startswith(("teleport_", "map_")) or event_name == "mechanism":
            return "objective"
        return "effects"

    def play_music(self, track_name: str, fade_ms: int = 650) -> None:
        if not self.available:
            return
        music_key = f"{track_name}_music"
        if self.current_music == music_key:
            return
        sound = self.sounds.get(music_key) or self.sounds.get("battle_music")
        if sound is None:
            return
        self.current_music = music_key
        self.channels["music"].set_volume(self._bus_volumes.get("music", self.master_volume))
        self.channels["music"].play(sound, loops=-1, fade_ms=max(0, fade_ms))

    def stop_music(self) -> None:
        if self.available and "music" in self.channels:
            self.channels["music"].fadeout(300)
            self.current_music = None

    def play_ambient(self, ambient_name: str, fade_ms: int = 900) -> None:
        if not self.available:
            return
        ambient_key = f"{ambient_name}_ambient"
        if self.current_ambient == ambient_key:
            return
        sound = self.sounds.get(ambient_key)
        if sound is None:
            return
        self.current_ambient = ambient_key
        self.channels["ambient"].set_volume(self._bus_volumes.get("ambient", self.master_volume))
        self.channels["ambient"].play(sound, loops=-1, fade_ms=max(0, fade_ms))

    def stop_ambient(self) -> None:
        if self.available and "ambient" in self.channels:
            self.channels["ambient"].fadeout(350)
            self.current_ambient = None

    def update(self, dt: float) -> None:
        return None

    def _build_fallback_sounds(self) -> None:
        if not self.available:
            return
        specs = {
            "weapon_fire": ("shot", 0.08, 120.0, 0.40),
            "bullet_impact": ("click", 0.06, 620.0, 0.26),
            "body_hit": ("thud", 0.11, 88.0, 0.35),
            "enemy_down": ("down", 0.22, 130.0, 0.42),
            "player_hurt": ("hurt", 0.18, 180.0, 0.40),
            "player_down": ("down", 0.44, 92.0, 0.48),
            "boss_alert": ("alert", 0.44, 82.0, 0.42),
            "boss_defeated": ("down", 0.55, 72.0, 0.48),
            "pickup_item": ("pickup", 0.16, 820.0, 0.34),
            "map_locked": ("deny", 0.18, 240.0, 0.36),
            "teleport_charge": ("rise", 0.72, 220.0, 0.34),
            "teleport_burst": ("burst", 0.52, 96.0, 0.48),
            "map_arrive": ("pickup", 0.36, 520.0, 0.36),
            "danger": ("alert", 0.30, 132.0, 0.36),
            "mechanism": ("click", 0.20, 360.0, 0.32),
            "killfeed": ("pickup", 0.18, 680.0, 0.28),
            "grenade_throw": ("whoosh", 0.18, 260.0, 0.28),
            "grenade_blast": ("burst", 0.48, 70.0, 0.58),
            "reload_complete": ("click", 0.15, 480.0, 0.28),
            "dash": ("whoosh", 0.22, 420.0, 0.34),
            "heal_start": ("pickup", 0.24, 420.0, 0.28),
            "menu_music": ("pad", 3.2, 110.0, 0.18),
            "battle_music": ("pulse", 4.0, 82.0, 0.22),
            "combat_music": ("pulse", 3.2, 98.0, 0.24),
            "boss_music": ("pulse", 3.6, 58.0, 0.30),
            "rain_ambient": ("rain", 2.4, 0.0, 0.20),
            "city_ambient": ("rain", 2.8, 0.0, 0.16),
        }
        for key, spec in specs.items():
            if key in self.sounds:
                continue
            sound = self._synthesize_sound(*spec)
            if sound is not None:
                self.sounds[key] = sound

    def _synthesize_sound(
        self,
        style: str,
        duration: float,
        base_frequency: float,
        gain: float,
    ) -> pygame.mixer.Sound | None:
        init = pygame.mixer.get_init()
        if init is None:
            return None
        frequency, sample_format, channels = init
        if abs(sample_format) != 16:
            return None
        sample_count = max(1, int(frequency * duration))
        rng = random.Random(f"{style}:{duration}:{base_frequency}:{gain}")
        data = array.array("h")
        for index in range(sample_count):
            t = index / frequency
            progress = index / max(1, sample_count - 1)
            envelope = max(0.0, 1.0 - progress)
            value = 0.0
            if style == "shot":
                value = rng.uniform(-1.0, 1.0) * math.exp(-progress * 10.0)
                value += math.sin(math.tau * base_frequency * t) * math.exp(-progress * 6.0)
            elif style == "click":
                value = math.sin(math.tau * base_frequency * t) * math.exp(-progress * 16.0)
                value += rng.uniform(-0.5, 0.5) * math.exp(-progress * 20.0)
            elif style == "thud":
                value = math.sin(math.tau * base_frequency * t) * math.exp(-progress * 7.0)
                value += rng.uniform(-0.5, 0.5) * math.exp(-progress * 10.0)
            elif style == "hurt":
                freq = base_frequency * (1.0 - progress * 0.45)
                value = math.sin(math.tau * freq * t) * envelope
            elif style == "alert":
                freq = base_frequency * (1.0 if int(progress * 6) % 2 == 0 else 1.5)
                value = math.sin(math.tau * freq * t) * (0.45 + 0.55 * envelope)
            elif style == "down":
                freq = base_frequency * (1.0 - progress * 0.62)
                value = math.sin(math.tau * freq * t) * envelope
                value += math.sin(math.tau * freq * 0.5 * t) * envelope * 0.7
            elif style == "pickup":
                freq = base_frequency * (1.0 + progress * 0.75)
                value = math.sin(math.tau * freq * t) * math.sin(math.pi * progress)
            elif style == "deny":
                freq = base_frequency * (1.0 - progress * 0.3)
                value = math.sin(math.tau * freq * t) * envelope
            elif style == "rise":
                freq = base_frequency * (1.0 + progress * 2.4)
                value = math.sin(math.tau * freq * t) * math.sin(math.pi * progress)
                value += rng.uniform(-0.2, 0.2) * progress
            elif style == "burst":
                value = rng.uniform(-1.0, 1.0) * math.exp(-progress * 3.2)
                value += math.sin(math.tau * base_frequency * t) * math.exp(-progress * 2.4)
            elif style == "whoosh":
                value = rng.uniform(-1.0, 1.0) * math.sin(math.pi * progress) * 0.8
            elif style == "pad":
                value = (
                    math.sin(math.tau * base_frequency * t)
                    + 0.5 * math.sin(math.tau * base_frequency * 1.5 * t)
                    + 0.28 * math.sin(math.tau * base_frequency * 2.0 * t)
                ) * 0.45
            elif style == "pulse":
                beat = 1.0 if int(t * 4.0) % 2 == 0 else 0.35
                value = math.sin(math.tau * base_frequency * t) * beat
                value += 0.35 * math.sin(math.tau * base_frequency * 2.0 * t)
            elif style == "rain":
                value = rng.uniform(-1.0, 1.0) * 0.42
                if rng.random() < 0.004:
                    value += rng.uniform(-1.0, 1.0)
            sample = int(max(-1.0, min(1.0, value * gain)) * 32767)
            for _ in range(channels):
                data.append(sample)
        return pygame.mixer.Sound(buffer=data.tobytes())
