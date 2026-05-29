from __future__ import annotations

import importlib.util
import os
import sys
import unittest
from pathlib import Path


INFO_PANEL_DIR = Path(__file__).resolve().parents[1] / "InfoPanel"
MODULE_PATH = INFO_PANEL_DIR / "agent_runtime.py"
if str(INFO_PANEL_DIR) not in sys.path:
    sys.path.insert(0, str(INFO_PANEL_DIR))

os.environ.setdefault("OPENAI_API_KEY", "test-key")

SPEC = importlib.util.spec_from_file_location("talos_agent_runtime", MODULE_PATH)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError(f"Unable to load module spec for {MODULE_PATH}")
agent_runtime = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = agent_runtime
SPEC.loader.exec_module(agent_runtime)


class AgentRuntimeRecoveryTests(unittest.TestCase):
    def test_reduce_tool_surface_keeps_direct_symbol_search_tools(self) -> None:
        tool_defs = [
            {"name": "kicad_list_symbol_libraries"},
            {"name": "kicad_list_library_symbols"},
            {"name": "kicad_search_symbols"},
            {"name": "kicad_get_symbol_info"},
            {"name": "kicad_add_schematic_component"},
            {"name": "other_tool"},
        ]

        reduced = agent_runtime._reduce_tool_surface(tool_defs)
        kept_names = {tool["name"] for tool in reduced}

        self.assertIn("kicad_list_symbol_libraries", kept_names)
        self.assertIn("kicad_list_library_symbols", kept_names)
        self.assertIn("kicad_search_symbols", kept_names)
        self.assertIn("kicad_get_symbol_info", kept_names)
        self.assertIn("kicad_add_schematic_component", kept_names)
        self.assertIn("other_tool", kept_names)

    def test_tool_result_failure_detection_handles_success_and_failure_json(self) -> None:
        self.assertFalse(
            agent_runtime._tool_result_indicates_failure('{"success": true, "message": "ok"}')
        )
        self.assertTrue(
            agent_runtime._tool_result_indicates_failure('{"success": false, "message": "bad"}')
        )
        self.assertTrue(
            agent_runtime._tool_result_indicates_failure("Error calling kicad_add: broken")
        )

    def test_fallback_message_distinguishes_successful_tool_from_failed_tool(self) -> None:
        success_events = [
            {
                "name": "kicad_create_project",
                "raw_result": '{"success": true, "message": "Created project"}',
                "failed": False,
            }
        ]
        failure_events = [
            {
                "name": "kicad_add_schematic_component",
                "raw_result": "Failed to add component: Symbol not found",
                "failed": True,
            }
        ]

        success_message = agent_runtime._fallback_response_from_tool_error(
            "make a kicad circuit", success_events, RuntimeError("HTTP 500")
        )
        failure_message = agent_runtime._fallback_response_from_tool_error(
            "make a kicad circuit", failure_events, RuntimeError("HTTP 500")
        )

        self.assertIn("completed in kicad_create_project", success_message)
        self.assertIn("failed in kicad_add_schematic_component", failure_message)

    def test_recovery_input_mentions_resume_and_recent_tools(self) -> None:
        tool_events = [
            {
                "name": "kicad_create_project",
                "raw_result": '{"success": true, "message": "Created project"}',
                "failed": False,
            }
        ]

        items = agent_runtime._build_recovery_input_items(
            "make a simple LED circuit",
            "no recent status",
            mcp_client=object(),
            tool_defs=[],
            tool_events=tool_events,
            recovery_attempt=1,
        )

        combined = " ".join(str(item.get("content", "")) for item in items)
        self.assertIn("Recovery attempt 1", combined)
        self.assertIn("kicad_create_project completed", combined)
        self.assertEqual(items[-1]["content"], "make a simple LED circuit")


if __name__ == "__main__":
    unittest.main()
