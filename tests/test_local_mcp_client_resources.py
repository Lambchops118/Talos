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
    def __init__(
        self,
        *,
        name: str = "fake",
        resources=None,
        templates=None,
        read_results=None,
        tools=None,
        fail_start: bool = False,
        fail_first_tool_call: bool = False,
        enforce_same_task: bool = False,
    ):
        self.config = local_mcp_client.McpServerConfig(
            name=name, transport="stdio", command="python", reconnect_attempts=1
        )
        self._resources = Obj(resources=resources or [])
        self._templates = Obj(resourceTemplates=templates or [])
        self._read_results = read_results or {}
        self._tools = Obj(tools=tools or [])
        self.last_tool_call = None
        self.health = local_mcp_client.McpServerHealth(name=name)
        self.is_running = not fail_start
        self.start_count = 0
        self.fail_start = fail_start
        self.fail_first_tool_call = fail_first_tool_call
        self.enforce_same_task = enforce_same_task
        self.owner_task_id = None
        self.task_records = []

    def should_attempt_reconnect(self):
        return True

    def _record_task(self, operation: str) -> None:
        task = asyncio.current_task()
        task_id = id(task) if task is not None else None
        self.task_records.append((operation, task_id))
        if not self.enforce_same_task:
            return
        if self.owner_task_id is None:
            self.owner_task_id = task_id
            return
        if task_id != self.owner_task_id:
            raise RuntimeError(
                f"{operation} ran in task {task_id}, expected task {self.owner_task_id}"
            )

    async def start(self):
        self._record_task("start")
        self.start_count += 1
        if self.fail_start:
            self.health.state = "failed"
            self.health.last_error = "boom"
            self.is_running = False
            raise RuntimeError("boom")
        self.health.state = "running"
        self.is_running = True

    async def stop(self):
        self._record_task("stop")
        self.is_running = False

    async def list_resources(self):
        self._record_task("list_resources")
        return self._resources

    async def list_resource_templates(self):
        self._record_task("list_resource_templates")
        return self._templates

    async def read_resource(self, uri: str):
        self._record_task("read_resource")
        return self._read_results[uri]

    async def list_tools(self):
        self._record_task("list_tools")
        return self._tools

    async def call_tool(self, name: str, arguments):
        self._record_task("call_tool")
        self.last_tool_call = (name, arguments)
        if self.fail_first_tool_call:
            self.fail_first_tool_call = False
            raise RuntimeError("transient")
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

    def test_start_keeps_working_servers_when_one_server_fails(self) -> None:
        configs = [
            local_mcp_client.McpServerConfig(name="good", transport="stdio", command="python"),
            local_mcp_client.McpServerConfig(name="bad", transport="stdio", command="python"),
        ]
        client = TestableLocalMcpClient(configs)
        client._connections = {
            "good": FakeConnection(tools=[Obj(name="ping", description="Ping", inputSchema={})]),
            "bad": FakeConnection(fail_start=True),
        }

        tools = client.list_tools(refresh=True)

        self.assertEqual([tool["name"] for tool in tools], ["ping"])
        self.assertEqual(client._connections["bad"].health.state, "failed")

    def test_tool_call_retries_after_transient_connection_failure(self) -> None:
        configs = [
            local_mcp_client.McpServerConfig(
                name="kicad", transport="stdio", command="node", reconnect_attempts=1
            )
        ]
        client = TestableLocalMcpClient(configs)
        connection = FakeConnection(fail_first_tool_call=True)
        client._connections = {"kicad": connection}
        client._tool_routes = {"kicad_open_project": ("kicad", "open_project")}

        result = client.call_tool("kicad_open_project", {"filename": "demo.kicad_pro"})

        self.assertEqual(result, "ok")
        self.assertEqual(connection.start_count, 1)
        self.assertEqual(connection.last_tool_call, ("open_project", {"filename": "demo.kicad_pro"}))

    def test_real_client_runs_start_and_resource_refresh_in_same_task(self) -> None:
        configs = [local_mcp_client.McpServerConfig(name="kicad", transport="stdio", command="python")]
        client = local_mcp_client.LocalMcpClient(configs)
        connection = FakeConnection(
            name="kicad",
            tools=[Obj(name="ping", description="Ping", inputSchema={})],
            resources=[Obj(uri="kicad://project/current/info", name="Project Info")],
            enforce_same_task=True,
        )
        client._connections = {"kicad": connection}

        try:
            tools = client.list_tools(refresh=True)
            resources = client.list_resources(refresh=True)
        finally:
            client.stop()

        self.assertEqual([tool["name"] for tool in tools], ["ping"])
        self.assertEqual(resources[0]["uri"], "kicad://project/current/info")
        self.assertEqual(connection.start_count, 1)
        self.assertEqual(
            [operation for operation, _task_id in connection.task_records],
            ["start", "list_tools", "list_resources", "stop"],
        )

    def test_load_mcp_server_configs_reads_timeout_and_reconnect_settings(self) -> None:
        raw_config = json.dumps(
            {
                "name": "remote",
                "transport": "streamable_http",
                "url": "https://example.com/mcp",
                "timeout_seconds": 15,
                "startup_timeout_seconds": 5,
                "tool_timeout_seconds": 10,
                "reconnect_initial_delay_seconds": 2,
                "reconnect_max_delay_seconds": 8,
                "reconnect_attempts": 3,
            }
        )
        with patch.dict(os.environ, {"TALOS_MCP_SERVERS": raw_config, "KICAD_MCP_SERVER_PATH": ""}):
            configs = local_mcp_client._load_mcp_server_configs()

        self.assertEqual(configs[0].startup_timeout, 5)
        self.assertEqual(configs[0].tool_timeout, 10)
        self.assertEqual(configs[0].reconnect_initial_delay_seconds, 2)
        self.assertEqual(configs[0].reconnect_max_delay_seconds, 8)
        self.assertEqual(configs[0].reconnect_attempts, 3)

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
