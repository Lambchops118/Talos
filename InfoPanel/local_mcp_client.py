from __future__ import annotations

import json
import subprocess
import sys
import threading
from collections import deque
from pathlib import Path
from typing import Any


class McpProtocolError(RuntimeError):
    pass


class LocalMcpClient:
    def __init__(self, server_path: Path) -> None:
        self.server_path = server_path
        self._process: subprocess.Popen[bytes] | None = None
        self._lock = threading.Lock()
        self._next_id = 1
        self._tool_cache: list[dict[str, Any]] | None = None
        self._stderr_lines: deque[str] = deque(maxlen=20)

    def start(self) -> None:
        if self._process and self._process.poll() is None:
            return

        self._process = subprocess.Popen(
            [sys.executable, str(self.server_path)],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        self._stderr_lines.clear()
        self._start_stderr_drain()
        self._initialize()

    def stop(self) -> None:
        process = self._process
        if process is None:
            return

        try:
            if process.stdin and not process.stdin.closed:
                process.stdin.close()
        except Exception:
            pass

        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=2)

        self._process = None
        self._tool_cache = None

    def list_tools(self, refresh: bool = False) -> list[dict[str, Any]]:
        self.start()
        if self._tool_cache is not None and not refresh:
            return list(self._tool_cache)

        result = self._send_request("tools/list", {})
        tools = result.get("tools", [])
        if not isinstance(tools, list):
            raise McpProtocolError("MCP server returned an invalid tools/list payload.")

        self._tool_cache = tools
        return list(tools)

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
        result = self._send_request(
            "tools/call",
            {"name": name, "arguments": parsed_arguments},
        )

        is_error = bool(result.get("isError"))
        text = self._extract_text(result)
        if is_error:
            raise RuntimeError(text)
        return text

    def _initialize(self) -> None:
        result = self._send_request(
            "initialize",
            {
                "protocolVersion": "2025-03-26",
                "capabilities": {},
                "clientInfo": {"name": "talos-voice-agent", "version": "0.1.0"},
            },
        )
        if not isinstance(result, dict):
            raise McpProtocolError("MCP initialize response was not an object.")
        self._send_notification("notifications/initialized", {})

    def _send_request(self, method: str, params: dict[str, Any]) -> dict[str, Any]:
        with self._lock:
            request_id = self._next_id
            self._next_id += 1
            self._write_message(
                {
                    "jsonrpc": "2.0",
                    "id": request_id,
                    "method": method,
                    "params": params,
                }
            )
            response = self._read_message()

        if response.get("id") != request_id:
            raise McpProtocolError(
                f"MCP response ID mismatch. Expected {request_id}, got {response.get('id')}."
            )

        if "error" in response:
            error = response["error"] or {}
            message = error.get("message", "Unknown MCP error")
            raise RuntimeError(message)

        result = response.get("result")
        if not isinstance(result, dict):
            raise McpProtocolError(f"Unexpected MCP result payload for method {method}.")
        return result

    def _send_notification(self, method: str, params: dict[str, Any]) -> None:
        with self._lock:
            self._write_message(
                {
                    "jsonrpc": "2.0",
                    "method": method,
                    "params": params,
                }
            )

    def _write_message(self, message: dict[str, Any]) -> None:
        process = self._require_process()
        payload = json.dumps(message).encode("utf-8")
        header = f"Content-Length: {len(payload)}\r\n\r\n".encode("ascii")
        assert process.stdin is not None
        process.stdin.write(header)
        process.stdin.write(payload)
        process.stdin.flush()

    def _read_message(self) -> dict[str, Any]:
        process = self._require_process()
        assert process.stdout is not None

        content_length: int | None = None
        while True:
            line = process.stdout.readline()
            if not line:
                raise RuntimeError(self._server_crash_context())
            if line == b"\r\n":
                break
            decoded = line.decode("ascii").strip()
            if decoded.lower().startswith("content-length:"):
                _, value = decoded.split(":", 1)
                content_length = int(value.strip())

        if content_length is None:
            raise McpProtocolError("Missing Content-Length header from local MCP server.")

        payload = process.stdout.read(content_length)
        if len(payload) != content_length:
            raise RuntimeError(self._server_crash_context())

        message = json.loads(payload.decode("utf-8"))
        if not isinstance(message, dict):
            raise McpProtocolError("MCP message payload was not an object.")
        return message

    def _require_process(self) -> subprocess.Popen[bytes]:
        if self._process is None or self._process.poll() is not None:
            raise RuntimeError(self._server_crash_context())
        return self._process

    def _start_stderr_drain(self) -> None:
        process = self._require_process()
        if process.stderr is None:
            return

        def drain() -> None:
            assert process.stderr is not None
            for raw_line in process.stderr:
                try:
                    line = raw_line.decode("utf-8", errors="replace").rstrip()
                except Exception:
                    continue
                if line:
                    self._stderr_lines.append(line)
                    print(f"[talos-mcp] {line}")

        thread = threading.Thread(target=drain, daemon=True)
        thread.start()

    @staticmethod
    def _parse_arguments(arguments: str | dict[str, Any] | None) -> dict[str, Any]:
        if arguments in (None, ""):
            return {}
        if isinstance(arguments, dict):
            return arguments
        if isinstance(arguments, str):
            parsed = json.loads(arguments)
            if not isinstance(parsed, dict):
                raise ValueError("Tool arguments must decode to a JSON object.")
            return parsed
        raise TypeError("Tool arguments must be a dict, JSON string, or None.")

    @staticmethod
    def _extract_text(result: dict[str, Any]) -> str:
        content = result.get("content", [])
        if isinstance(content, list):
            chunks: list[str] = []
            for item in content:
                if isinstance(item, dict) and item.get("type") == "text":
                    text = item.get("text", "")
                    if text:
                        chunks.append(str(text))
            if chunks:
                return "\n".join(chunks)
        structured = result.get("structuredContent")
        if structured is not None:
            return json.dumps(structured)
        return ""

    def _server_crash_context(self) -> str:
        if not self._stderr_lines:
            return "Local MCP server closed unexpectedly."
        return "Local MCP server closed unexpectedly. Recent stderr:\n" + "\n".join(self._stderr_lines)


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
