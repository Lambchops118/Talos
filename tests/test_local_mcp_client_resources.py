from __future__ import annotations

import asyncio
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from talos.mcp_client import client as local_mcp_client


class Obj:
    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)


class FakeConnection:
    def __init__(self, *, resources=None, templates=None, read_results=None):
        self._resources = Obj(resources=resources or [])
        self._templates = Obj(resourceTemplates=templates or [])
        self._read_results = read_results or {}
        self.last_tool_call = None

    async def list_resources(self):
        return self._resources

    async def list_resource_templates(self):
        return self._templates

    async def read_resource(self, uri: str):
        return self._read_results[uri]

    async def list_tools(self):
        return Obj(tools=[])

    async def call_tool(self, name: str, arguments):
        self.last_tool_call = (name, arguments)
        return Obj(content=[Obj(type="text", text="ok")], isError=False)


class TestableLocalMcpClient(local_mcp_client.LocalMcpClient):
    def start(self) -> None:
        return None

    def _run_coro(self, coro):
        return asyncio.run(coro)


class LocalMcpClientResourceTests(unittest.TestCase):
    def test_list_resources_and_templates_include_server_metadata(self) -> None:
        configs = [local_mcp_client.McpServerConfig(name="kicad", transport="stdio", command="node")]
        client = TestableLocalMcpClient(configs)
        client._connections = {
            "kicad": FakeConnection(
                resources=[
                    Obj(
                        uri="kicad://project/current/info",
                        name="Project Info",
                        description="Current KiCad project metadata",
                        mimeType="application/json",
                        size=128,
                    )
                ],
                templates=[
                    Obj(
                        uriTemplate="kicad://project/{project_id}/snapshot",
                        name="Project Snapshot",
                        description="Read a named snapshot",
                        mimeType="application/json",
                    )
                ],
            )
        }

        resources = client.list_resources()
        templates = client.list_resource_templates()

        self.assertEqual(resources[0]["server"], "kicad")
        self.assertEqual(resources[0]["uri"], "kicad://project/current/info")
        self.assertEqual(resources[0]["mimeType"], "application/json")
        self.assertEqual(resources[0]["size"], 128)
        self.assertEqual(templates[0]["server"], "kicad")
        self.assertEqual(templates[0]["uriTemplate"], "kicad://project/{project_id}/snapshot")

    def test_read_resource_requires_server_when_uri_is_duplicated(self) -> None:
        configs = [
            local_mcp_client.McpServerConfig(name="kicad-a", transport="stdio", command="node"),
            local_mcp_client.McpServerConfig(name="kicad-b", transport="stdio", command="node"),
        ]
        shared_uri = "kicad://project/current/info"
        read_result = Obj(contents=[Obj(uri=shared_uri, mimeType="application/json", text='{"name":"demo"}')])
        client = TestableLocalMcpClient(configs)
        client._connections = {
            "kicad-a": FakeConnection(
                resources=[Obj(uri=shared_uri, name="Project Info")],
                read_results={shared_uri: read_result},
            ),
            "kicad-b": FakeConnection(
                resources=[Obj(uri=shared_uri, name="Project Info")],
                read_results={shared_uri: read_result},
            ),
        }

        client.list_resources()
        with self.assertRaises(ValueError):
            client.read_resource(shared_uri)

        payload = json.loads(client.read_resource(shared_uri, server="kicad-a"))
        self.assertEqual(payload["server"], "kicad-a")
        self.assertEqual(payload["contents"][0]["kind"], "text")
        self.assertEqual(payload["contents"][0]["text"], '{"name":"demo"}')

    def test_load_mcp_server_configs_appends_optional_kicad_server(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            env = {
                "TALOS_MCP_SERVERS": "",
                "KICAD_MCP_SERVER_PATH": tmpdir,
                "KICAD_PYTHONPATH": "/Applications/KiCad/site-packages",
                "KICAD_MCP_TOOL_PREFIX": "kicad_",
            }
            with patch.dict(os.environ, env, clear=False):
                configs = local_mcp_client._load_mcp_server_configs()

        self.assertEqual([config.name for config in configs], ["talos-local", "kicad"])
        self.assertEqual(configs[1].command, "node")
        self.assertTrue(configs[1].args[0].endswith("dist/index.js"))
        self.assertEqual(configs[1].env["PYTHONPATH"], "/Applications/KiCad/site-packages")
        self.assertEqual(configs[1].tool_prefix, "kicad_")

    def test_kicad_tool_call_normalizes_missing_root_paths(self) -> None:
        configs = [local_mcp_client.McpServerConfig(name="kicad", transport="stdio", command="node")]
        client = TestableLocalMcpClient(configs)
        connection = FakeConnection()
        client._connections = {"kicad": connection}
        client._tool_routes = {"kicad_open_project": ("kicad", "open_project")}

        result = client.call_tool(
            "kicad_open_project",
            {"filename": "Users/jacksal1/Desktop/KiCADProjects/demo.kicad_pro"},
        )

        self.assertEqual(result, "ok")
        self.assertEqual(
            connection.last_tool_call,
            ("open_project", {"filename": "/Users/jacksal1/Desktop/KiCADProjects/demo.kicad_pro"}),
        )

    def test_non_kicad_tool_call_does_not_rewrite_path_arguments(self) -> None:
        configs = [local_mcp_client.McpServerConfig(name="other", transport="stdio", command="node")]
        client = TestableLocalMcpClient(configs)
        connection = FakeConnection()
        client._connections = {"other": connection}
        client._tool_routes = {"open_project": ("other", "open_project")}

        result = client.call_tool("open_project", {"filename": "Users/jacksal1/Desktop/demo.txt"})

        self.assertEqual(result, "ok")
        self.assertEqual(
            connection.last_tool_call,
            ("open_project", {"filename": "Users/jacksal1/Desktop/demo.txt"}),
        )


if __name__ == "__main__":
    unittest.main()
