from __future__ import annotations

import os
import sys
from pathlib import Path

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pygame


def main() -> None:
    pygame.init()
    pygame.display.set_mode((1, 1))

    root = Path(__file__).resolve().parents[1]
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))
    from circle_siege.entities.animation_controller import AnimationController
    from tools.build_direction_sheet import build_sheet

    asset_dir = root.parent / "resource" / "img" / "characters"
    sheet_dir = asset_dir / "sheets"
    sheet_dir.mkdir(parents=True, exist_ok=True)

    configs = [
        ("hero", "hero_dir8_sheet.png", "hero_sprite96_v2.png"),
        ("bot", "bot_dir8_sheet.png", "bot_sprite96_v2.png"),
        ("elite", "elite_dir8_sheet.png", "elite_sprite96_v2.png"),
    ]
    for prefix, dir8_name, fallback_name in configs:
        dir8_path = asset_dir / dir8_name
        fallback_path = asset_dir / fallback_name
        if dir8_path.exists():
            surface = pygame.image.load(str(dir8_path)).convert_alpha()
            controller = AnimationController.from_direction_sheet(surface, scale=1.0, default_angle=45.0)
        else:
            surface = pygame.image.load(str(fallback_path)).convert_alpha()
            controller = AnimationController(surface, scale=1.0, default_angle=45.0)
        for state in ("idle", "move", "fire", "dead"):
            frame_count = AnimationController.FRAME_COUNTS[state]
            authored_variants = (
                (
                    asset_dir / "source" / f"{prefix}_{state}_alpha_v2.png",
                    sheet_dir / f"{prefix}_{state}_sheet_v2.png",
                ),
                (
                    asset_dir / "source" / f"{prefix}_{state}_alpha.png",
                    sheet_dir / f"{prefix}_{state}_sheet.png",
                ),
            )
            authored_source = None
            target_path = None
            for candidate_source, candidate_target in authored_variants:
                if candidate_source.exists():
                    authored_source = candidate_source
                    target_path = candidate_target
                    break
            if authored_source is not None and target_path is not None:
                if target_path.exists() and target_path.stat().st_mtime >= authored_source.stat().st_mtime:
                    print(f"kept authored {target_path.name}")
                    continue
                build_sheet(
                    authored_source,
                    target_path,
                    columns=frame_count,
                    rows=len(AnimationController.DIRECTION_ORDER),
                    cell_size=128,
                    layout="bands" if state == "move" else "grid",
                )
                print(f"built authored {target_path.name} from {authored_source.name}")
                continue
            target_path = sheet_dir / f"{prefix}_{state}_sheet.png"
            sheet = controller.export_sheet(state)
            pygame.image.save(sheet, str(target_path))
            print(f"exported {prefix}_{state}_sheet.png -> {sheet.get_size()}")

    pygame.quit()


if __name__ == "__main__":
    main()
