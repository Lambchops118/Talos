from __future__ import annotations

import home_automation_actions as actions
from mcp.server.fastmcp import FastMCP


def register(server: FastMCP) -> None:
    """Register the existing home automation tools on a FastMCP server."""

    @server.tool()
    def get_current_datetime() -> str:
        """Get the current local date, time, year, and timezone for TALOS."""
        return actions.get_current_datetime()

    @server.tool()
    def get_current_weather(location: str = "") -> str:
        """Get the current weather, temperature, humidity, UV index, and related details."""
        return actions.get_current_weather(location)

    @server.tool()
    def water_plants(pot_number: int) -> str:
        """Send a signal to the pump circuit to water either pot 1 or pot 2."""
        return actions.water_plants(pot_number)

    @server.tool()
    def turn_on_lights(room: str) -> str:
        """Turn on the lights in a specific room."""
        return actions.turn_on_lights(room)

    @server.tool()
    def toggle_fan(status: int) -> str:
        """Toggle the fan on (1) or off (0)."""
        return actions.toggle_fan(status)
