"""Entity layer."""

from .bot_player import BotPlayer
from .character import CharacterBase
from .item import Pickup
from .map import Arena, Decoration, Map, Obstacle
from .player import Player
from .projectile import Bullet, Projectile
from .weapon import Weapon

EnemyBot = BotPlayer
Character = CharacterBase

__all__ = [
    "Arena",
    "BotPlayer",
    "Bullet",
    "Character",
    "CharacterBase",
    "Decoration",
    "EnemyBot",
    "Map",
    "Obstacle",
    "Pickup",
    "Player",
    "Projectile",
    "Weapon",
]
