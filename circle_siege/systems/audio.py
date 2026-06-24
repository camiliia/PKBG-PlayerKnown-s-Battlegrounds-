from __future__ import annotations

from pathlib import Path

import pygame

from ..core.config import RESOURCE_ROOT


class AudioManager:
    def __init__(self) -> None:
        self.master_volume = 1.0
        self.music_volume = 1.0
        self.effects_volume = 1.0
        self.available = False
        self.current_music = None
        self.sounds: dict[str, pygame.mixer.Sound] = {}
        self.channels: dict[str, pygame.mixer.Channel] = {}
        try:
            if not pygame.mixer.get_init():
                pygame.mixer.init()
            pygame.mixer.set_num_channels(8)
            self.channels = {
                "music": pygame.mixer.Channel(0),
                "ambient": pygame.mixer.Channel(1),
                "effects": pygame.mixer.Channel(2),
                "ui": pygame.mixer.Channel(3),
            }
            self.available = True
            self._load_default_sounds()
            self._apply_channel_volumes()
        except pygame.error:
            self.available = False

    def _load_default_sounds(self) -> None:
        sound_root = RESOURCE_ROOT / "sound"
        mapping = {
            "menu_music": sound_root / "aigei.mp3",
            "battle_music": sound_root / "nmw.mp3",
            "reload_complete": sound_root / "swk.wav",
            "killfeed": sound_root / "swk.wav",
            "danger": sound_root / "swk.wav",
            "mechanism": sound_root / "swk.wav",
            "grenade_throw": sound_root / "swk.wav",
            "grenade_blast": sound_root / "swk.wav",
        }
        for key, path in mapping.items():
            if path.exists():
                try:
                    self.sounds[key] = pygame.mixer.Sound(str(path))
                except pygame.error:
                    continue

    def _apply_channel_volumes(self) -> None:
        if not self.available:
            return
        if "music" in self.channels:
            self.channels["music"].set_volume(self.master_volume * self.music_volume * 0.55)
        if "ambient" in self.channels:
            self.channels["ambient"].set_volume(self.master_volume * self.music_volume * 0.32)
        if "effects" in self.channels:
            self.channels["effects"].set_volume(self.master_volume * self.effects_volume * 0.42)
        if "ui" in self.channels:
            self.channels["ui"].set_volume(self.master_volume * self.effects_volume * 0.26)

    def set_master_volume(self, value: float) -> None:
        self.master_volume = max(0.0, min(1.0, value))
        self._apply_channel_volumes()

    def set_music_volume(self, value: float) -> None:
        self.music_volume = max(0.0, min(1.0, value))
        self._apply_channel_volumes()

    def set_effects_volume(self, value: float) -> None:
        self.effects_volume = max(0.0, min(1.0, value))
        self._apply_channel_volumes()

    def play_sfx(self, event_name: str) -> None:
        if not self.available:
            return
        sound = self.sounds.get(event_name)
        if sound is None:
            return
        channel_name = "effects"
        if event_name in {"reload_complete", "killfeed"}:
            channel_name = "ui"
        self.channels[channel_name].play(sound)

    def play_music(self, track_name: str) -> None:
        if not self.available:
            return
        music_key = f"{track_name}_music"
        if self.current_music == music_key:
            return
        sound = self.sounds.get(music_key)
        if sound is None:
            return
        self.current_music = music_key
        self.channels["music"].play(sound, loops=-1)

    def stop_music(self) -> None:
        if self.available and "music" in self.channels:
            self.channels["music"].stop()
            self.current_music = None

    def update(self, dt: float) -> None:
        return None
