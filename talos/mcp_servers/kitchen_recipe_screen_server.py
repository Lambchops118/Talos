from __future__ import annotations

from .base import create_server, register_all
from .providers import register_kitchen_recipe_screen_tools


def create_kitchen_recipe_screen_server():
    server = create_server("talos-kitchen-recipe-screen")
    return register_all(
        server,
        [
            register_kitchen_recipe_screen_tools,
        ],
    )
