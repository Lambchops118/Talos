from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

os.environ.setdefault("OPENAI_API_KEY", "test-key")

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from talos.agent import runtime as agent_runtime
from talos.memory import MemoryStore


class FakeMcpClient:
    def __init__(self) -> None:
        self.inventory_refresh = None
        self.retry_server_name = None

    def list_tool_inventory(self, *, refresh: bool = False):
        self.inventory_refresh = refresh
        return {
            "tools": [{"name": "local_ping"}],
            "servers": [{"name": "talos-local", "status": "healthy"}],
        }

    def retry_server(self, server=None):
        self.retry_server_name = server
        return [{"name": server or "all", "status": "starting"}]


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

    def test_host_tool_lists_mcp_tools_separately_from_resources(self) -> None:
        mcp_client = FakeMcpClient()

        result = agent_runtime._invoke_host_tool(
            mcp_client,
            "list_mcp_tools",
            '{"refresh": true}',
        )

        self.assertTrue(mcp_client.inventory_refresh)
        self.assertIn("local_ping", result)
        self.assertIn("talos-local", result)

    def test_host_tool_retries_mcp_server_explicitly(self) -> None:
        mcp_client = FakeMcpClient()

        result = agent_runtime._invoke_host_tool(
            mcp_client,
            "retry_mcp_server",
            '{"server": "kicad"}',
        )

        self.assertEqual(mcp_client.retry_server_name, "kicad")
        self.assertIn("starting", result)

    def test_host_tool_remembers_memory_fact(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            store = MemoryStore(Path(tmpdir) / "memory.sqlite3")
            with mock.patch.object(agent_runtime, "get_default_memory_store", return_value=store):
                result = agent_runtime._invoke_host_tool(
                    FakeMcpClient(),
                    "remember_memory_fact",
                    '{"scope": "session", "key": "tone", "value": "Keep replies compact.", "salience": 8}',
                    session_id="text-session",
                )

            memory = store.get_prompt_memory("text-session", "tone", max_chars=2000)
            store.close()

        self.assertIn("Memory fact stored", result)
        self.assertIn("[session:text-session] tone: Keep replies compact.", memory)

    def test_runtime_prompt_instructions_include_mode_domain_and_memory(self) -> None:
        instructions = agent_runtime._build_prompt_instructions(
            "Place the KiCad LED on the board.",
            "voice",
            [{"name": "kicad_get_backend_state"}],
            memory_block="User prefers concise KiCad updates.",
            interaction_mode="voice",
        )

        self.assertIn("Base Soul Document", instructions)
        self.assertIn("Voice Mode Overlay", instructions)
        self.assertIn("KiCad Domain Overlay", instructions)
        self.assertIn("Memory Context (Runtime Injected)", instructions)
        self.assertIn("concise KiCad updates", instructions)


if __name__ == "__main__":
    unittest.main()
