from __future__ import annotations

import importlib
import os
import sys
import types
from pathlib import Path

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pygame


def _iter_authored_variants(asset_dir: Path, prefix: str, state: str) -> tuple[tuple[Path, Path], ...]:
    source_dir = asset_dir / "source"
    return (
        (
            source_dir / f"{prefix}_{state}_sheet_alpha_v2.png",
            asset_dir / "sheets" / f"{prefix}_{state}_sheet_v2.png",
        ),
        (
            source_dir / f"{prefix}_{state}_alpha_v2.png",
            asset_dir / "sheets" / f"{prefix}_{state}_sheet_v2.png",
        ),
        (
            source_dir / f"{prefix}_{state}_alpha.png",
            asset_dir / "sheets" / f"{prefix}_{state}_sheet.png",
        ),
    )


def _find_authored_variant(asset_dir: Path, prefix: str, state: str) -> tuple[Path, Path] | None:
    for candidate_source, candidate_target in _iter_authored_variants(asset_dir, prefix, state):
        if candidate_source.exists():
            return candidate_source, candidate_target
    return None


def _should_rebuild(source_path: Path, target_path: Path) -> bool:
    return not target_path.exists() or target_path.stat().st_mtime < source_path.stat().st_mtime


def _layout_for_state(state: str) -> str:
    return "bands" if state == "move" else "grid"


def _load_animation_controller(root: Path):
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))

    import circle_siege

    package_name = "circle_siege.entities"
    if package_name not in sys.modules:
        entities_package = types.ModuleType(package_name)
        entities_package.__path__ = [str(root / "circle_siege" / "entities")]
        entities_package.__package__ = package_name
        sys.modules[package_name] = entities_package

    module = importlib.import_module(f"{package_name}.animation_controller")
    return module.AnimationController


def main() -> None:
    pygame.init()
    pygame.display.set_mode((1, 1))

    root = Path(__file__).resolve().parents[1]
    AnimationController = _load_animation_controller(root)
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
            authored_variant = _find_authored_variant(asset_dir, prefix, state)
            if authored_variant is not None:
                authored_source, target_path = authored_variant
                if not _should_rebuild(authored_source, target_path):
                    print(f"kept authored {target_path.name}")
                    continue
                build_sheet(
                    authored_source,
                    target_path,
                    columns=frame_count,
                    rows=len(AnimationController.DIRECTION_ORDER),
                    cell_size=128,
                    layout=_layout_for_state(state),
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
