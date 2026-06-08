from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path
from unittest import mock

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from talos.services import kitchen_recipe_screen as screen


class KitchenRecipeScreenServiceTests(unittest.TestCase):
    def test_replace_recipe_content_formats_lists_for_display(self) -> None:
        captured_patch: dict[str, object] = {}

        def fake_update_state(patch: dict[str, object]) -> dict[str, object]:
            captured_patch.update(patch)
            return {
                "title": patch.get("title", ""),
                "servings": patch.get("servings", screen.DEFAULT_SERVINGS),
                "link_status": screen.DEFAULT_LINK_STATUS,
                "ingredients": patch.get("ingredients", []),
                "steps": patch.get("steps", []),
                "notes": patch.get("notes", []),
                "timer": {"label": screen.DEFAULT_TIMER_LABEL, "remaining_seconds": 0, "running": False, "finished": False},
            }

        with mock.patch.object(screen, "_update_state", side_effect=fake_update_state):
            result = screen.replace_recipe_content(
                title="Tomato Soup",
                subtitle="Low simmer",
                servings="3 bowls",
                ingredients=["2 tomatoes", "1 onion"],
                steps=["Roast vegetables", "Blend until smooth"],
                notes=["Add basil"],
            )

        self.assertEqual(captured_patch["title"], "Tomato Soup")
        self.assertEqual(captured_patch["subtitle"], "Low simmer")
        self.assertEqual(captured_patch["servings"], "3 bowls")
        self.assertEqual(
            captured_patch["ingredients"],
            [
                {"text": "2 tomatoes", "checked": False},
                {"text": "1 onion", "checked": False},
            ],
        )
        self.assertEqual(
            captured_patch["steps"],
            [
                {"text": "Roast vegetables", "done": False},
                {"text": "Blend until smooth", "done": False},
            ],
        )
        self.assertEqual(captured_patch["notes"], ["Add basil"])
        self.assertIn("Tomato Soup", result)

    def test_remove_steps_supports_indices_and_matching_text(self) -> None:
        starting_state = {
            "steps": [
                {"text": "Prep ingredients", "done": False},
                {"text": "Boil water", "done": False},
                {"text": "Serve", "done": False},
            ]
        }
        saved_patches: list[dict[str, object]] = []

        with (
            mock.patch.object(screen, "_fetch_state", return_value=starting_state),
            mock.patch.object(
                screen,
                "_update_state",
                side_effect=lambda patch: saved_patches.append(patch) or {
                    "title": "",
                    "servings": screen.DEFAULT_SERVINGS,
                    "link_status": screen.DEFAULT_LINK_STATUS,
                    "ingredients": [],
                    "steps": patch["steps"],
                    "notes": [],
                    "timer": {"label": screen.DEFAULT_TIMER_LABEL, "remaining_seconds": 0, "running": False, "finished": False},
                },
            ),
        ):
            screen.remove_steps(indices=[2], matching_texts=["Serve"])

        self.assertEqual(
            saved_patches[-1]["steps"],
            [{"text": "Prep ingredients", "done": False}],
        )

    def test_read_link_status_returns_json_string(self) -> None:
        with mock.patch.object(screen, "_fetch_state", return_value={"link_status": "LINK DEGRADED"}):
            payload = json.loads(screen.read_link_status())

        self.assertEqual(payload["link_status"], "LINK DEGRADED")

    def test_clear_recipe_screen_resets_content_and_timer(self) -> None:
        updated_states: list[dict[str, object]] = []
        timer_states: list[dict[str, object]] = []

        with (
            mock.patch.object(
                screen,
                "_update_state",
                side_effect=lambda patch: updated_states.append(patch) or {
                    "title": patch.get("title", ""),
                    "servings": patch.get("servings", screen.DEFAULT_SERVINGS),
                    "link_status": patch.get("link_status", screen.DEFAULT_LINK_STATUS),
                    "ingredients": patch.get("ingredients", []),
                    "steps": patch.get("steps", []),
                    "notes": patch.get("notes", []),
                    "timer": {"label": screen.DEFAULT_TIMER_LABEL, "remaining_seconds": 0, "running": False, "finished": False},
                },
            ),
            mock.patch.object(
                screen,
                "_timer_action",
                side_effect=lambda action, payload=None: timer_states.append({"action": action, "payload": payload or {}}) or {
                    "title": "",
                    "servings": screen.DEFAULT_SERVINGS,
                    "link_status": screen.DEFAULT_LINK_STATUS,
                    "ingredients": [],
                    "steps": [],
                    "notes": [],
                    "timer": {"label": screen.DEFAULT_TIMER_LABEL, "remaining_seconds": 0, "running": False, "finished": False},
                },
            ),
        ):
            screen.clear_recipe_screen()

        self.assertEqual(updated_states[-1]["link_status"], screen.DEFAULT_LINK_STATUS)
        self.assertEqual(updated_states[-1]["servings"], screen.DEFAULT_SERVINGS)
        self.assertEqual(updated_states[-1]["ingredients"], [])
        self.assertEqual(timer_states[-1]["action"], "set")
        self.assertEqual(timer_states[-1]["payload"]["duration_seconds"], 0)


if __name__ == "__main__":
    unittest.main()
