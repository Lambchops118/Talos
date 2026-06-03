from __future__ import annotations

from talos.mcp_servers.aggregate import create_aggregate_server


def main() -> int:
    server = create_aggregate_server()
    server.run(transport="stdio")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
