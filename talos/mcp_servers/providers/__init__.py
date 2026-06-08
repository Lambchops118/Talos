from .home_automation import register as register_home_automation_tools
from .kitchen_recipe_screen import register as register_kitchen_recipe_screen_tools
from .tv_control import register as register_tv_control_tools

__all__ = [
    "register_home_automation_tools",
    "register_kitchen_recipe_screen_tools",
    "register_tv_control_tools",
]
