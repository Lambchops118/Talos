from __future__ import annotations

from talos.mcp_servers.kitchen_recipe_screen_server import create_kitchen_recipe_screen_server


def main() -> int:
    server = create_kitchen_recipe_screen_server()
    server.run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
