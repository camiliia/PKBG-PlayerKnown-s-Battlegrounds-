from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


SCREEN_WIDTH = 1440
SCREEN_HEIGHT = 900
FPS = 60
TITLE = "圈地突围"
WORKSPACE_ROOT = Path(__file__).resolve().parents[3]
RESOURCE_ROOT = WORKSPACE_ROOT / "resource"
TMX_ROOT = RESOURCE_ROOT / "tmx"

WORLD_WIDTH = 2800
WORLD_HEIGHT = 2400
WORLD_BOUNDS = (0, 0, WORLD_WIDTH, WORLD_HEIGHT)

PLAYER_RADIUS = 18
BOT_RADIUS = 18
ELITE_BOT_RADIUS = 20
INTERACT_DISTANCE = 68
MELEE_BUFFER = 16

BACKGROUND = (23, 42, 33)
UI_PANEL = (14, 22, 28)
UI_ACCENT = (239, 185, 74)
TEXT_LIGHT = (232, 237, 240)
TEXT_MUTED = (156, 168, 176)
HEALTH_GREEN = (78, 194, 118)
ZONE_BLUE = (92, 172, 255)
ZONE_DANGER = (235, 116, 116)
ZONE_INITIAL_MARGIN = 220.0
ZONE_INITIAL_HOLD_BONUS = 18.0
ZONE_INITIAL_SHRINK_BONUS = 5.0
SPAWN_MIN_SEPARATION = 420.0
STARTUP_GEAR_OFFSET_MIN = 108.0
STARTUP_GEAR_OFFSET_MAX = 168.0

PLAYER_SPEED = 215
SPRINT_MULTIPLIER = 1.4
BOT_SPEED = 190
BOT_SPRINT_MULTIPLIER = 1.25
ELITE_BOT_SPEED = 184
ELITE_BOT_SPRINT_MULTIPLIER = 1.18
HEAL_TIME = 2.7
HEAL_AMOUNT = 42
MAX_MEDKITS = 3
MAX_GRENADES = 3
STARTING_GRENADES = 2
GRENADE_FUSE_TIME = 1.15
GRENADE_THROW_SPEED = 560.0
GRENADE_BLAST_RADIUS = 136.0
GRENADE_DAMAGE = 58
GRENADE_COLOR = (246, 178, 90)

STARTING_AMMO = {
    "5.56": 120,
    "9mm": 120,
    "12g": 36,
    "7.62": 48,
}

AMMO_LABELS = {
    "5.56": "5.56 毫米",
    "9mm": "9 毫米",
    "12g": "12 号霰弹",
    "7.62": "7.62 毫米",
    "none": "未装备",
}


@dataclass(frozen=True)
class WeaponData:
    identifier: str
    label: str
    ammo_type: str
    damage: int
    projectile_speed: float
    fire_interval: float
    reload_time: float
    magazine_size: int
    spread: float
    move_spread: float
    projectile_radius: int
    range_limit: float
    color: tuple[int, int, int]
    pellets: int = 1
    desired_distance: float = 260
    pickup_ammo_bonus: int = 36
    score: int = 10


@dataclass(frozen=True)
class ZonePhase:
    hold_time: float
    shrink_time: float
    radius_scale: float
    dps: float


@dataclass(frozen=True)
class CharacterStats:
    radius: int
    max_hp: int
    max_armor: int
    move_speed: float
    sprint_multiplier: float
    jump_height: float = 0.0
    dodge_speed: float = 0.0


@dataclass(frozen=True)
class GameConfig:
    screen_width: int
    screen_height: int
    target_fps: int
    master_volume: float
    music_volume: float
    effects_volume: float
    mouse_sensitivity: float = 1.0


@dataclass(frozen=True)
class MatchConfig:
    mode: str
    match_time_limit: float
    kill_target: int
    respawn_time: float
    player_count: int
    allow_respawn: bool


@dataclass(frozen=True)
class MapData:
    identifier: str
    label: str
    subtitle: str
    description: tuple[str, ...]
    accent: tuple[int, int, int]
    width: int = WORLD_WIDTH
    height: int = WORLD_HEIGHT
    target_player_count: int = 12
    tmx_path: str | None = None
    preview_image_path: str | None = None


@dataclass(frozen=True)
class PlayerSkin:
    identifier: str
    label: str
    primary_color: tuple[int, int, int]
    accent_color: tuple[int, int, int]
    marker_color: tuple[int, int, int]
    secondary_color: tuple[int, int, int]


@dataclass(frozen=True)
class PlayerProfile:
    callsign: str
    skin_id: str


WeaponSpec = WeaponData
ArenaThemeMeta = MapData


WEAPON_LIBRARY = {
    "unarmed": WeaponData(
        identifier="unarmed",
        label="未装备",
        ammo_type="none",
        damage=0,
        projectile_speed=0.0,
        fire_interval=0.25,
        reload_time=0.0,
        magazine_size=0,
        spread=0.0,
        move_spread=0.0,
        projectile_radius=0,
        range_limit=0.0,
        color=(160, 174, 188),
        desired_distance=0,
        pickup_ammo_bonus=0,
        score=0,
    ),
    "carbine": WeaponData(
        identifier="carbine",
        label="飓风卡宾枪",
        ammo_type="5.56",
        damage=19,
        projectile_speed=1240.0,
        fire_interval=0.11,
        reload_time=1.9,
        magazine_size=30,
        spread=0.018,
        move_spread=0.024,
        projectile_radius=4,
        range_limit=980.0,
        color=(240, 211, 104),
        desired_distance=330,
        pickup_ammo_bonus=48,
        score=18,
    ),
    "smg": WeaponData(
        identifier="smg",
        label="獠牙冲锋枪",
        ammo_type="9mm",
        damage=13,
        projectile_speed=1100.0,
        fire_interval=0.075,
        reload_time=1.5,
        magazine_size=34,
        spread=0.03,
        move_spread=0.042,
        projectile_radius=4,
        range_limit=760.0,
        color=(248, 144, 86),
        desired_distance=220,
        pickup_ammo_bonus=54,
        score=14,
    ),
    "shotgun": WeaponData(
        identifier="shotgun",
        label="先锋霰弹枪",
        ammo_type="12g",
        damage=8,
        projectile_speed=930.0,
        fire_interval=0.72,
        reload_time=2.35,
        magazine_size=6,
        spread=0.16,
        move_spread=0.08,
        projectile_radius=5,
        range_limit=330.0,
        color=(146, 226, 199),
        pellets=6,
        desired_distance=135,
        pickup_ammo_bonus=18,
        score=15,
    ),
    "dmr": WeaponData(
        identifier="dmr",
        label="山脊射手步枪",
        ammo_type="7.62",
        damage=34,
        projectile_speed=1400.0,
        fire_interval=0.32,
        reload_time=2.1,
        magazine_size=12,
        spread=0.01,
        move_spread=0.028,
        projectile_radius=4,
        range_limit=1320.0,
        color=(143, 187, 255),
        desired_distance=520,
        pickup_ammo_bonus=30,
        score=22,
    ),
}


ZONE_PHASES = (
    ZonePhase(hold_time=28.0, shrink_time=18.0, radius_scale=0.78, dps=5.0),
    ZonePhase(hold_time=23.0, shrink_time=17.0, radius_scale=0.58, dps=7.0),
    ZonePhase(hold_time=19.0, shrink_time=15.0, radius_scale=0.41, dps=9.0),
    ZonePhase(hold_time=15.0, shrink_time=13.0, radius_scale=0.27, dps=12.0),
    ZonePhase(hold_time=12.0, shrink_time=11.0, radius_scale=0.16, dps=16.0),
)

ARENA_THEMES = (
    MapData(
        identifier="cyber_city_tmx",
        label="赛博都市雨夜竞技场",
        subtitle="霓虹街区、高台天桥与地下通道",
        description=(
            "中路主街风险最高，视野最强，也是最适合正面对枪的区域。",
            "左侧近战巷道与右侧压制高台会形成明确的战术分流。",
            "补给区、危险区和机关区都由 TMX trigger 直接驱动。",
        ),
        accent=(104, 214, 255),
        width=3840,
        height=2560,
        tmx_path=str(TMX_ROOT / "cyber_city.tmx"),
        preview_image_path=str(RESOURCE_ROOT / "img" / "cyber_city_bg_v4.png"),
    ),
    MapData(
        identifier="village_tmx",
        label="山村聚落",
        subtitle="开阔村道与密集房区",
        description=(
            "整张地图由手工 TMX 障碍数据驱动，房区和街道边界清晰。",
            "村口与主路适合中距离压制，房屋转角适合近身绕后。",
            "物件密度高，适合练掩体拉扯和多方向推进。",
        ),
        accent=(236, 188, 92),
        width=3780,
        height=2395,
        tmx_path=str(TMX_ROOT / "village1.tmx"),
        preview_image_path=str(RESOURCE_ROOT / "img" / "village.jpg"),
    ),
    MapData(
        identifier="temple_tmx",
        label="古寺遗址",
        subtitle="高低阶梯与神殿庭院",
        description=(
            "地形起伏和障碍线密，适合压缩战线和卡视角推进。",
            "寺前通道风险高，但回报也高，是必争对枪区。",
            "边缘地带适合绕侧，中心台阶更适合中近距离交战。",
        ),
        accent=(230, 154, 90),
        width=1999,
        height=1495,
        tmx_path=str(TMX_ROOT / "temple1.tmx"),
        preview_image_path=str(RESOURCE_ROOT / "img" / "temple.jpg"),
    ),
    MapData(
        identifier="courtyard_tmx",
        label="庭院迷阵",
        subtitle="瓦屋、林地与小路交错",
        description=(
            "基于多层瓦屋与树木图块拼装，场景细节明显多于纯程序地形。",
            "房屋与林带共同形成复杂视线切割，适合小队式拉扯。",
            "路径层天然构成推进路线，适合做更细致的碰撞和巡逻。",
        ),
        accent=(111, 205, 169),
        width=1376,
        height=768,
        tmx_path=str(TMX_ROOT / "scene.tmx"),
        preview_image_path=str(RESOURCE_ROOT / "img" / "古色地图.png"),
    ),
)

THEME_BY_ID = {theme.identifier: theme for theme in ARENA_THEMES}
DEFAULT_THEME_ID = ARENA_THEMES[0].identifier

DEFAULT_GAME_CONFIG = GameConfig(
    screen_width=SCREEN_WIDTH,
    screen_height=SCREEN_HEIGHT,
    target_fps=FPS,
    master_volume=1.0,
    music_volume=0.8,
    effects_volume=1.0,
    mouse_sensitivity=1.0,
)

DEFAULT_MATCH_CONFIG = MatchConfig(
    mode="寻宝模式",
    match_time_limit=540.0,
    kill_target=1,
    respawn_time=0.0,
    player_count=10,
    allow_respawn=False,
)

PLAYER_STATS = CharacterStats(
    radius=PLAYER_RADIUS,
    max_hp=100,
    max_armor=55,
    move_speed=PLAYER_SPEED,
    sprint_multiplier=SPRINT_MULTIPLIER,
    jump_height=0.0,
    dodge_speed=430.0,
)

BOT_STATS = CharacterStats(
    radius=BOT_RADIUS,
    max_hp=100,
    max_armor=20,
    move_speed=BOT_SPEED,
    sprint_multiplier=BOT_SPRINT_MULTIPLIER,
    jump_height=0.0,
    dodge_speed=380.0,
)

ELITE_BOT_STATS = CharacterStats(
    radius=ELITE_BOT_RADIUS,
    max_hp=150,
    max_armor=60,
    move_speed=ELITE_BOT_SPEED,
    sprint_multiplier=ELITE_BOT_SPRINT_MULTIPLIER,
    jump_height=0.0,
    dodge_speed=350.0,
)

PLAYER_SKINS = (
    PlayerSkin(
        identifier="azure",
        label="深空蓝",
        primary_color=(86, 181, 236),
        accent_color=(116, 224, 255),
        marker_color=(220, 246, 255),
        secondary_color=(24, 38, 58),
    ),
    PlayerSkin(
        identifier="ember",
        label="余烬红",
        primary_color=(232, 108, 92),
        accent_color=(255, 212, 170),
        marker_color=(255, 236, 204),
        secondary_color=(61, 28, 24),
    ),
    PlayerSkin(
        identifier="volt",
        label="霓虹绿",
        primary_color=(118, 220, 144),
        accent_color=(229, 255, 188),
        marker_color=(245, 255, 210),
        secondary_color=(23, 52, 33),
    ),
    PlayerSkin(
        identifier="violet",
        label="风暴紫",
        primary_color=(168, 136, 238),
        accent_color=(238, 226, 255),
        marker_color=(248, 240, 255),
        secondary_color=(38, 29, 64),
    ),
    PlayerSkin(
        identifier="gold",
        label="曜金黄",
        primary_color=(238, 192, 84),
        accent_color=(255, 242, 188),
        marker_color=(255, 249, 220),
        secondary_color=(65, 48, 20),
    ),
)

PLAYER_SKIN_BY_ID = {skin.identifier: skin for skin in PLAYER_SKINS}

DEFAULT_CALLSIGN_OPTIONS = (
    "玩家一号",
    "夜行者",
    "极光",
    "赤电",
    "潜流",
    "流火",
    "回声",
)

DEFAULT_PLAYER_PROFILE = PlayerProfile(
    callsign=DEFAULT_CALLSIGN_OPTIONS[0],
    skin_id=PLAYER_SKINS[0].identifier,
)

BOT_NAMES = (
    "赤狐",
    "猎隼",
    "玄刃",
    "霜狼",
    "流火",
    "惊蛰",
    "断潮",
    "夜隼",
    "铁翼",
    "白栎",
    "狂砂",
    "迅矛",
    "苍弓",
    "惊雷",
    "寒潮",
    "孤礁",
)
