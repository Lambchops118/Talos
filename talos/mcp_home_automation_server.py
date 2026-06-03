from __future__ import annotations

from talos.mcp_servers.home_automation_server import create_home_automation_server


def main() -> int:
    server = create_home_automation_server()
    server.run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
