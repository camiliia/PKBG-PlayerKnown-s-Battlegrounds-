# Audio And Transition Structure

## Teleport transition

- `circle_siege/scenes/map_transition_scene.py` keeps only timing, skip handling, scene switching, and audio event triggers.
- `circle_siege/presentation/transition_effects.py` owns portal, particle, gate, flash, and progress-panel rendering.
- The win/progression condition remains in the battle scene and is not changed by this refactor.

## Audio schemes

- `circle_siege/systems/audio_events.py` defines gameplay event names, channel routing, cooldowns, volume scaling, and fallback order.
- `circle_siege/systems/audio.py` loads legacy fixed files and recursively loads scheme-specific assets under `resource/sound`.

Available schemes:

- `cinematic`
- `tactical`
- `arcade`

Asset examples:

```text
D:\软件项目开发\resource\sound\cinematic\teleport_charge.wav
D:\软件项目开发\resource\sound\tactical\boss_alert.ogg
D:\软件项目开发\resource\sound\arcade\pickup_item.wav
```

The recursive loader maps `resource/sound/cinematic/teleport_charge.wav` to `cinematic.teleport_charge`.
If no scheme asset exists, event playback falls back to the current files such as `swk.wav`, `aigei.mp3`, and `nmw.mp3`.

## Generated local audio

Pygame does not ship commercial-ready gunshot or music assets, so this project now keeps a deterministic local generator at `tools/generate_audio_assets.py`.

Run it after cloning or after deleting generated assets:

```powershell
& .\.venv\Scripts\python.exe tools\generate_audio_assets.py
```

It writes royalty-free placeholder WAV files under `resource/sound/generated`:

- `generated/music/menu_theme.wav`, `battle_theme.wav`, `combat_theme.wav`, `boss_theme.wav`
- `generated/ambient/rain_loop.wav`, `city_loop.wav`
- `generated/cinematic/*.wav`, `generated/tactical/*.wav`, `generated/arcade/*.wav`

The generated scheme folders are aliased by `AudioManager`, so `resource/sound/generated/cinematic/weapon_fire_smg.wav` is loaded as `cinematic.weapon_fire_smg`.

To replace with downloaded assets, keep the same event filename and put the file under `resource/sound/<scheme>/` or `resource/sound/generated/<scheme>/`. Use only CC0, self-made, or explicitly licensed files.
