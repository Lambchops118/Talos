from __future__ import annotations

import asyncio
import sys
import threading
from pathlib import Path
from typing import Any

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


class McpProtocolError(RuntimeError):
    pass


class LocalMcpClient:
    def __init__(self, server_path: Path) -> None:
        self.server_path = server_path
        self._lock = threading.Lock()
        self._tool_cache: list[dict[str, Any]] | None = None

        self._loop: asyncio.AbstractEventLoop | None = None
        self._loop_thread: threading.Thread | None = None
        self._stdio_ctx = None
        self._session_ctx = None
        self._session: ClientSession | None = None

    def start(self) -> None:
        with self._lock:
            if self._session is not None:
                return

            loop = asyncio.new_event_loop()
            thread = threading.Thread(target=self._run_loop, args=(loop,), daemon=True)
            thread.start()

            self._loop = loop
            self._loop_thread = thread
            try:
                self._run_coro(self._async_start())
            except Exception:
                self._shutdown_loop()
                raise

    def stop(self) -> None:
        with self._lock:
            if self._loop is None:
                return
            try:
                self._run_coro(self._async_stop())
            finally:
                self._shutdown_loop()
                self._tool_cache = None

    def list_tools(self, refresh: bool = False) -> list[dict[str, Any]]:
        self.start()
        if self._tool_cache is not None and not refresh:
            return list(self._tool_cache)

        result = self._run_coro(self._async_list_tools())
        if not isinstance(result, list):
            raise McpProtocolError("MCP server returned an invalid tools/list payload.")

        self._tool_cache = result
        return list(result)

    def openai_tool_definitions(self) -> list[dict[str, Any]]:
        definitions = []
        for tool in self.list_tools():
            definitions.append(
                {
                    "type": "function",
                    "name": tool["name"],
                    "description": tool.get("description", ""),
                    "parameters": tool.get("inputSchema", {"type": "object", "properties": {}}),
                }
            )
        return definitions

    def call_tool(self, name: str, arguments: str | dict[str, Any] | None = None) -> str:
        self.start()
        parsed_arguments = self._parse_arguments(arguments)
        return self._run_coro(self._async_call_tool(name, parsed_arguments))

    async def _async_start(self) -> None:
        server_params = StdioServerParameters(
            command=sys.executable,
            args=[str(self.server_path)],
        )

        self._stdio_ctx = stdio_client(server_params)
        read_stream, write_stream = await self._stdio_ctx.__aenter__()
        self._session_ctx = ClientSession(read_stream, write_stream)
        self._session = await self._session_ctx.__aenter__()
        await self._session.initialize()

    async def _async_stop(self) -> None:
        if self._session_ctx is not None:
            await self._session_ctx.__aexit__(None, None, None)
        self._session_ctx = None
        self._session = None

        if self._stdio_ctx is not None:
            await self._stdio_ctx.__aexit__(None, None, None)
        self._stdio_ctx = None

    async def _async_list_tools(self) -> list[dict[str, Any]]:
        session = self._require_session()
        result = await session.list_tools()

        tools: list[dict[str, Any]] = []
        for tool in getattr(result, "tools", []):
            input_schema = getattr(tool, "inputSchema", None)
            if input_schema is None and hasattr(tool, "model_dump"):
                dumped = tool.model_dump()
                input_schema = dumped.get("inputSchema")
            tools.append(
                {
                    "name": getattr(tool, "name"),
                    "description": getattr(tool, "description", "") or "",
                    "inputSchema": input_schema or {"type": "object", "properties": {}},
                }
            )
        return tools

    async def _async_call_tool(self, name: str, arguments: dict[str, Any]) -> str:
        session = self._require_session()
        result = await session.call_tool(name, arguments)

        is_error = bool(getattr(result, "isError", False))
        text = self._extract_text(result)
        if is_error:
            raise RuntimeError(text)
        return text

    def _require_session(self) -> ClientSession:
        if self._session is None:
            raise RuntimeError("Local MCP session is not running.")
        return self._session

    def _run_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        asyncio.set_event_loop(loop)
        loop.run_forever()

    def _run_coro(self, coro):
        if self._loop is None:
            raise RuntimeError("Local MCP loop is not running.")
        future = asyncio.run_coroutine_threadsafe(coro, self._loop)
        return future.result()

    def _shutdown_loop(self) -> None:
        if self._loop is not None:
            self._loop.call_soon_threadsafe(self._loop.stop)
        if self._loop_thread is not None:
            self._loop_thread.join(timeout=2)
        if self._loop is not None:
            self._loop.close()
        self._loop = None
        self._loop_thread = None

    @staticmethod
    def _parse_arguments(arguments: str | dict[str, Any] | None) -> dict[str, Any]:
        if arguments in (None, ""):
            return {}
        if isinstance(arguments, dict):
            return arguments
        if isinstance(arguments, str):
            import json

            parsed = json.loads(arguments)
            if not isinstance(parsed, dict):
                raise ValueError("Tool arguments must decode to a JSON object.")
            return parsed
        raise TypeError("Tool arguments must be a dict, JSON string, or None.")

    @staticmethod
    def _extract_text(result: Any) -> str:
        content = getattr(result, "content", [])
        if isinstance(content, list):
            chunks: list[str] = []
            for item in content:
                item_type = getattr(item, "type", None)
                text = getattr(item, "text", None)
                if item_type == "text" and text:
                    chunks.append(str(text))
            if chunks:
                return "\n".join(chunks)

        structured = getattr(result, "structuredContent", None)
        if structured is not None:
            import json

            return json.dumps(structured)
        return ""


_shared_client: LocalMcpClient | None = None
_shared_lock = threading.Lock()


def get_local_mcp_client() -> LocalMcpClient:
    global _shared_client
    with _shared_lock:
        if _shared_client is None:
            server_path = Path(__file__).resolve().parent / "mcp_server.py"
            _shared_client = LocalMcpClient(server_path)
        return _shared_client


def shutdown_local_mcp_client() -> None:
    global _shared_client
    with _shared_lock:
        if _shared_client is not None:
            _shared_client.stop()
            _shared_client = None
