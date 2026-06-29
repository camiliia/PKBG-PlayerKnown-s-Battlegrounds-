from __future__ import annotations

import subprocess
from pathlib import Path


def _ffmpeg_executable() -> str:
    try:
        import imageio_ffmpeg

        return imageio_ffmpeg.get_ffmpeg_exe()
    except ImportError:
        return "ffmpeg"


def extract_audio(source: Path, target: Path) -> None:
    if not source.exists():
        raise FileNotFoundError(source)
    target.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        [
            _ffmpeg_executable(),
            "-y",
            "-i",
            str(source),
            "-vn",
            "-acodec",
            "libvorbis",
            "-q:a",
            "5",
            str(target),
        ],
        check=True,
    )


def main() -> None:
    sound_root = Path(__file__).resolve().parents[2] / "resource" / "sound"
    output_root = sound_root / "extracted"
    jobs = (
        (sound_root / "menuground.mp4", output_root / "menu_music.ogg"),
        (sound_root / "battleground.mp4", output_root / "battle_music.ogg"),
    )
    for source, target in jobs:
        extract_audio(source, target)
        print(f"Extracted {source.name} -> {target.relative_to(sound_root)}")


if __name__ == "__main__":
    main()
