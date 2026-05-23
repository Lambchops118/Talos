from __future__ import annotations

from mcp_servers.tv_control_server import create_tv_control_server


def main() -> int:
    server = create_tv_control_server()
    server.run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
