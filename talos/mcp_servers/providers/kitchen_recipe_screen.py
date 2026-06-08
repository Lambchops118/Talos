from __future__ import annotations

from mcp.server.fastmcp import FastMCP

from talos.services import kitchen_recipe_screen as screen


def register(server: FastMCP) -> None:
    """Register kitchen recipe screen tools on a FastMCP server."""

    @server.tool()
    def kitchen_screen_health() -> str:
        """Check whether the kitchen recipe screen HTTP app is reachable and healthy."""
        return screen.get_screen_health()

    @server.tool()
    def kitchen_screen_get_state() -> str:
        """Read the full current kitchen recipe screen state as JSON."""
        return screen.get_screen_state()

    @server.tool()
    def kitchen_screen_set_recipe_header(title: str = "", subtitle: str = "") -> str:
        """Set the visible recipe title and subtitle shown on the kitchen recipe screen."""
        return screen.set_recipe_header(title=title, subtitle=subtitle)

    @server.tool()
    def kitchen_screen_clear_recipe_header() -> str:
        """Clear the visible recipe title and subtitle on the kitchen recipe screen."""
        return screen.clear_recipe_header()

    @server.tool()
    def kitchen_screen_replace_recipe_content(
        title: str = "",
        subtitle: str = "",
        servings: str = "",
        ingredients: list[str] | None = None,
        steps: list[str] | None = None,
        notes: list[str] | None = None,
    ) -> str:
        """Replace the main recipe content in one call: title, subtitle, servings, ingredients, steps, and notes."""
        return screen.replace_recipe_content(
            title=title,
            subtitle=subtitle,
            servings=servings,
            ingredients=ingredients,
            steps=steps,
            notes=notes,
        )

    @server.tool()
    def kitchen_screen_read_ingredients() -> str:
        """Read the current ingredient list from the kitchen recipe screen as JSON."""
        return screen.read_ingredients()

    @server.tool()
    def kitchen_screen_replace_ingredients(ingredients: list[str]) -> str:
        """Replace the full ingredient list shown on the kitchen recipe screen."""
        return screen.replace_ingredients(ingredients)

    @server.tool()
    def kitchen_screen_remove_ingredients(
        indices: list[int] | None = None,
        matching_texts: list[str] | None = None,
        clear_all: bool = False,
    ) -> str:
        """Remove ingredients by 1-based index, exact text match, or clear them all."""
        return screen.remove_ingredients(indices=indices, matching_texts=matching_texts, clear_all=clear_all)

    @server.tool()
    def kitchen_screen_clear_ingredients() -> str:
        """Clear all ingredients from the kitchen recipe screen."""
        return screen.clear_ingredients()

    @server.tool()
    def kitchen_screen_read_steps() -> str:
        """Read the current recipe step list from the kitchen recipe screen as JSON."""
        return screen.read_steps()

    @server.tool()
    def kitchen_screen_replace_steps(steps: list[str]) -> str:
        """Replace the full recipe step list shown on the kitchen recipe screen."""
        return screen.replace_steps(steps)

    @server.tool()
    def kitchen_screen_remove_steps(
        indices: list[int] | None = None,
        matching_texts: list[str] | None = None,
        clear_all: bool = False,
    ) -> str:
        """Remove recipe steps by 1-based index, exact text match, or clear them all."""
        return screen.remove_steps(indices=indices, matching_texts=matching_texts, clear_all=clear_all)

    @server.tool()
    def kitchen_screen_clear_steps() -> str:
        """Clear all recipe steps from the kitchen recipe screen."""
        return screen.clear_steps()

    @server.tool()
    def kitchen_screen_read_notes() -> str:
        """Read the current note list from the kitchen recipe screen as JSON."""
        return screen.read_notes()

    @server.tool()
    def kitchen_screen_add_notes(notes: list[str]) -> str:
        """Append one or more notes to the kitchen recipe screen."""
        return screen.add_notes(notes)

    @server.tool()
    def kitchen_screen_replace_notes(notes: list[str]) -> str:
        """Replace the full note list shown on the kitchen recipe screen."""
        return screen.replace_notes(notes)

    @server.tool()
    def kitchen_screen_remove_notes(
        indices: list[int] | None = None,
        matching_texts: list[str] | None = None,
        clear_all: bool = False,
    ) -> str:
        """Remove notes by 1-based index, exact text match, or clear them all."""
        return screen.remove_notes(indices=indices, matching_texts=matching_texts, clear_all=clear_all)

    @server.tool()
    def kitchen_screen_clear_notes() -> str:
        """Clear all notes from the kitchen recipe screen."""
        return screen.clear_notes()

    @server.tool()
    def kitchen_screen_set_timer(duration_seconds: int, label: str = "Recipe timer", auto_start: bool = False) -> str:
        """Set the kitchen recipe screen timer duration and label, optionally starting it immediately."""
        return screen.set_timer(duration_seconds=duration_seconds, label=label, auto_start=auto_start)

    @server.tool()
    def kitchen_screen_read_timer() -> str:
        """Read the current timer state from the kitchen recipe screen as JSON."""
        return screen.read_timer()

    @server.tool()
    def kitchen_screen_start_timer() -> str:
        """Start or resume the kitchen recipe screen timer."""
        return screen.start_timer()

    @server.tool()
    def kitchen_screen_stop_timer() -> str:
        """Stop or pause the kitchen recipe screen timer without resetting it."""
        return screen.stop_timer()

    @server.tool()
    def kitchen_screen_reset_timer() -> str:
        """Reset the kitchen recipe screen timer back to its configured duration."""
        return screen.reset_timer()

    @server.tool()
    def kitchen_screen_set_link_status(link_status: str) -> str:
        """Set the top-row link indicator text, for example LINK NOMINAL or LINK DEGRADED."""
        return screen.set_link_status(link_status)

    @server.tool()
    def kitchen_screen_read_link_status() -> str:
        """Read the current top-row link indicator text as JSON."""
        return screen.read_link_status()

    @server.tool()
    def kitchen_screen_set_servings(servings: str) -> str:
        """Set the servings text shown on the kitchen recipe screen."""
        return screen.set_servings(servings)

    @server.tool()
    def kitchen_screen_reset_servings() -> str:
        """Reset the servings text to the default kitchen recipe screen value."""
        return screen.reset_servings()

    @server.tool()
    def kitchen_screen_clear_recipe_screen() -> str:
        """Clear title, subtitle, ingredients, steps, notes, servings, link status, and timer back to defaults."""
        return screen.clear_recipe_screen()
