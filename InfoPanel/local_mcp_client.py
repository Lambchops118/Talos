from __future__ import annotations

import asyncio
import base64
import json
import os
import re
import sys
import threading
from contextlib import AsyncExitStack
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


class McpProtocolError(RuntimeError):
    pass


@dataclass(slots=True)
class McpServerConfig:
    name: str
    transport: str
    command: str | None = None
    args: list[str] = field(default_factory=list)
    url: str | None = None
    headers: dict[str, str] = field(default_factory=dict)
    auth_token: str | None = None
    auth_token_env: str | None = None
    tool_prefix: str = ""
    cwd: str | None = None
    env: dict[str, str] = field(default_factory=dict)
    timeout_seconds: float = 30.0

    def normalized_transport(self) -> str:
        transport = self.transport.strip().lower().replace("-", "_")
        if transport == "http":
            return "streamable_http"
        return transport

    def exposed_tool_name(self, raw_name: str) -> str:
        return f"{self.tool_prefix}{raw_name}" if self.tool_prefix else raw_name


class _ServerConnection:
    def __init__(self, config: McpServerConfig) -> None:
        self.config = config
        self._exit_stack: AsyncExitStack | None = None
        self._session: Any = None

    async def start(self) -> None:
        if self._session is not None:
            return

        try:
            from mcp import ClientSession, StdioServerParameters
        except ImportError as exc:  # pragma: no cover - depends on local environment
            raise RuntimeError(
                "The MCP Python SDK is required for TALOS MCP clients. "
                'Install it with: pip install "mcp[cli]"'
            ) from exc

        stack = AsyncExitStack()
        try:
            transport = self.config.normalized_transport()
            if transport == "stdio":
                if not self.config.command:
                    raise ValueError(f"stdio MCP server '{self.config.name}' is missing 'command'.")
                from mcp.client.stdio import stdio_client

                stdio_kwargs: dict[str, Any] = {
                    "command": self.config.command,
                    "args": list(self.config.args),
                }
                if self.config.env:
                    stdio_kwargs["env"] = self._merged_env()
                if self.config.cwd:
                    stdio_kwargs["cwd"] = self.config.cwd
                server_params = StdioServerParameters(**stdio_kwargs)
                read_stream, write_stream = await stack.enter_async_context(stdio_client(server_params))
            elif transport == "streamable_http":
                if not self.config.url:
                    raise ValueError(
                        f"streamable_http MCP server '{self.config.name}' is missing 'url'."
                    )
                try:
                    import httpx
                    from mcp.client.streamable_http import streamable_http_client
                except ImportError as exc:  # pragma: no cover - depends on SDK version/env
                    raise RuntimeError(
                        "Remote MCP over Streamable HTTP requires the MCP SDK's "
                        "'streamable_http_client' transport and httpx."
                    ) from exc

                http_client = httpx.AsyncClient(
                    headers=self._resolved_headers(),
                    follow_redirects=True,
                    timeout=self.config.timeout_seconds,
                )
                managed_http_client = await stack.enter_async_context(http_client)
                streams = await stack.enter_async_context(
                    streamable_http_client(
                        self.config.url,
                        http_client=managed_http_client,
                    )
                )
                read_stream, write_stream = streams[0], streams[1]
            else:
                raise ValueError(
                    f"Unsupported MCP transport '{self.config.transport}' for server '{self.config.name}'."
                )

            self._session = await stack.enter_async_context(ClientSession(read_stream, write_stream))
            await self._session.initialize()
            self._exit_stack = stack
        except Exception:
            await stack.aclose()
            raise

    async def stop(self) -> None:
        if self._exit_stack is not None:
            await self._exit_stack.aclose()
        self._exit_stack = None
        self._session = None

    async def list_tools(self) -> Any:
        session = self._require_session()
        return await session.list_tools()

    async def call_tool(self, name: str, arguments: dict[str, Any]) -> Any:
        session = self._require_session()
        return await session.call_tool(name, arguments)

    async def list_resources(self) -> Any:
        session = self._require_session()
        method = getattr(session, "list_resources", None)
        if method is None:
            raise RuntimeError(f"MCP server '{self.config.name}' does not support resources/list.")
        return await method()

    async def list_resource_templates(self) -> Any:
        session = self._require_session()
        method = getattr(session, "list_resource_templates", None)
        if method is None:
            raise RuntimeError(
                f"MCP server '{self.config.name}' does not support resources/templates/list."
            )
        return await method()

    async def read_resource(self, uri: str) -> Any:
        session = self._require_session()
        method = getattr(session, "read_resource", None)
        if method is None:
            raise RuntimeError(f"MCP server '{self.config.name}' does not support resources/read.")
        return await method(uri)

    def _require_session(self) -> Any:
        if self._session is None:
            raise RuntimeError(f"MCP server '{self.config.name}' is not running.")
        return self._session

    def _resolved_headers(self) -> dict[str, str]:
        headers = dict(self.config.headers)

        auth_token = self.config.auth_token
        if not auth_token and self.config.auth_token_env:
            auth_token = os.getenv(self.config.auth_token_env, "").strip()
            if not auth_token:
                raise ValueError(
                    f"MCP server '{self.config.name}' expects auth token env "
                    f"'{self.config.auth_token_env}', but it is not set."
                )
        if auth_token:
            headers.setdefault("Authorization", f"Bearer {auth_token}")
        return headers

    def _merged_env(self) -> dict[str, str]:
        merged = dict(os.environ)
        for key, value in self.config.env.items():
            merged[str(key)] = str(value)
        return merged


class LocalMcpClient:
    def __init__(self, configs: list[McpServerConfig]) -> None:
        if not configs:
            raise ValueError("At least one MCP server config is required.")

        self._configs = list(configs)
        self._connections = {config.name: _ServerConnection(config) for config in self._configs}

        self._lock = threading.Lock()
        self._tool_cache: list[dict[str, Any]] | None = None
        self._tool_routes: dict[str, tuple[str, str]] = {}
        self._resource_cache: list[dict[str, Any]] | None = None
        self._resource_template_cache: list[dict[str, Any]] | None = None
        self._resource_routes: dict[str, list[str]] = {}

        self._loop: asyncio.AbstractEventLoop | None = None
        self._loop_thread: threading.Thread | None = None

    def start(self) -> None:
        with self._lock:
            if self._loop is not None:
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
                self._tool_routes = {}
                self._resource_cache = None
                self._resource_template_cache = None
                self._resource_routes = {}

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
            description = tool.get("description", "")
            parameters = tool.get("inputSchema", {"type": "object", "properties": {}})
            description, parameters = self._decorate_openai_tool_schema(
                tool["name"], description, parameters
            )
            definitions.append(
                {
                    "type": "function",
                    "name": tool["name"],
                    "description": description,
                    "parameters": parameters,
                }
            )
        return definitions

    def call_tool(self, name: str, arguments: str | dict[str, Any] | None = None) -> str:
        self.start()
        if not self._tool_routes:
            self.list_tools()
        parsed_arguments = self._parse_arguments(arguments)
        return self._run_coro(self._async_call_tool(name, parsed_arguments))

    def list_resources(self, refresh: bool = False) -> list[dict[str, Any]]:
        self.start()
        if self._resource_cache is not None and not refresh:
            return list(self._resource_cache)

        result = self._run_coro(self._async_list_resources())
        if not isinstance(result, list):
            raise McpProtocolError("MCP server returned an invalid resources/list payload.")

        self._resource_cache = result
        return list(result)

    def list_resource_templates(self, refresh: bool = False) -> list[dict[str, Any]]:
        self.start()
        if self._resource_template_cache is not None and not refresh:
            return list(self._resource_template_cache)

        result = self._run_coro(self._async_list_resource_templates())
        if not isinstance(result, list):
            raise McpProtocolError(
                "MCP server returned an invalid resources/templates/list payload."
            )

        self._resource_template_cache = result
        return list(result)

    def read_resource(self, uri: str, server: str | None = None) -> str:
        self.start()
        return self._run_coro(self._async_read_resource(uri, server))

    async def _async_start(self) -> None:
        started_connections: list[_ServerConnection] = []
        try:
            for config in self._configs:
                connection = self._connections[config.name]
                await connection.start()
                started_connections.append(connection)
        except Exception:
            for connection in reversed(started_connections):
                try:
                    await connection.stop()
                except Exception:
                    pass
            raise

    async def _async_stop(self) -> None:
        for connection in reversed(list(self._connections.values())):
            try:
                await connection.stop()
            except Exception:
                pass

    async def _async_list_tools(self) -> list[dict[str, Any]]:
        tools: list[dict[str, Any]] = []
        routes: dict[str, tuple[str, str]] = {}

        for config in self._configs:
            connection = self._connections[config.name]
            result = await connection.list_tools()

            for tool in getattr(result, "tools", []):
                raw_name = getattr(tool, "name")
                if not raw_name:
                    raise McpProtocolError(f"MCP server '{config.name}' returned a tool without a name.")

                exposed_name = config.exposed_tool_name(raw_name)
                existing = routes.get(exposed_name)
                if existing is not None:
                    raise McpProtocolError(
                        "Duplicate MCP tool name detected for "
                        f"'{exposed_name}' from servers '{existing[0]}' and '{config.name}'. "
                        "Set a unique 'tool_prefix' on one of those servers."
                    )

                input_schema = getattr(tool, "inputSchema", None)
                if input_schema is None and hasattr(tool, "model_dump"):
                    dumped = tool.model_dump()
                    input_schema = dumped.get("inputSchema")

                description = getattr(tool, "description", "") or ""
                description = self._decorate_description(config.name, description)

                routes[exposed_name] = (config.name, raw_name)
                tools.append(
                    {
                        "name": exposed_name,
                        "description": description,
                        "inputSchema": input_schema or {"type": "object", "properties": {}},
                    }
                )

        self._tool_routes = routes
        return tools

    async def _async_call_tool(self, name: str, arguments: dict[str, Any]) -> str:
        route = self._tool_routes.get(name)
        if route is None:
            await self._async_list_tools()
            route = self._tool_routes.get(name)
        if route is None:
            raise KeyError(name)

        server_name, raw_name = route
        connection = self._connections[server_name]
        arguments = self._normalize_tool_arguments(name, server_name, arguments)
        result = await connection.call_tool(raw_name, arguments)

        is_error = bool(getattr(result, "isError", False))
        text = self._extract_text(result)
        if is_error:
            raise RuntimeError(text)
        return text

    async def _async_list_resources(self) -> list[dict[str, Any]]:
        resources: list[dict[str, Any]] = []
        routes: dict[str, list[str]] = {}

        for config in self._configs:
            connection = self._connections[config.name]
            try:
                result = await connection.list_resources()
            except Exception:
                continue

            for resource in getattr(result, "resources", []):
                resource_data = self._asdict(resource)
                uri = self._first_value(resource, resource_data, "uri")
                if not uri:
                    continue

                routes.setdefault(str(uri), []).append(config.name)
                resources.append(
                    {
                        "server": config.name,
                        "uri": str(uri),
                        "name": self._optional_text(resource, resource_data, "name"),
                        "description": self._optional_text(resource, resource_data, "description"),
                        "mimeType": self._optional_text(resource, resource_data, "mimeType"),
                        "size": self._optional_number(resource, resource_data, "size"),
                    }
                )

        self._resource_routes = routes
        return resources

    async def _async_list_resource_templates(self) -> list[dict[str, Any]]:
        templates: list[dict[str, Any]] = []

        for config in self._configs:
            connection = self._connections[config.name]
            try:
                result = await connection.list_resource_templates()
            except Exception:
                continue

            for template in getattr(result, "resourceTemplates", []):
                template_data = self._asdict(template)
                uri_template = self._first_value(template, template_data, "uriTemplate", "uri_template")
                if not uri_template:
                    continue

                templates.append(
                    {
                        "server": config.name,
                        "uriTemplate": str(uri_template),
                        "name": self._optional_text(template, template_data, "name"),
                        "description": self._optional_text(template, template_data, "description"),
                        "mimeType": self._optional_text(template, template_data, "mimeType"),
                    }
                )

        return templates

    async def _async_read_resource(self, uri: str, server: str | None = None) -> str:
        resolved_server = server.strip() if isinstance(server, str) else None
        if not resolved_server:
            if not self._resource_routes:
                await self._async_list_resources()
            routes = self._resource_routes.get(uri)
            if not routes:
                await self._async_list_resources()
                routes = self._resource_routes.get(uri)
            if not routes:
                raise KeyError(uri)

            unique_routes = list(dict.fromkeys(routes))
            if len(unique_routes) > 1:
                raise ValueError(
                    f"Multiple MCP servers expose resource '{uri}'. Specify the server name."
                )
            resolved_server = unique_routes[0]

        connection = self._connections.get(resolved_server)
        if connection is None:
            raise KeyError(resolved_server)

        result = await connection.read_resource(uri)
        return json.dumps(
            {
                "server": resolved_server,
                "uri": uri,
                "contents": self._extract_resource_contents(result),
            }
        )

    @staticmethod
    def _asdict(item: Any) -> dict[str, Any]:
        if hasattr(item, "model_dump"):
            dumped = item.model_dump()
            if isinstance(dumped, dict):
                return dumped
        if isinstance(item, dict):
            return item
        return {}

    @staticmethod
    def _first_value(item: Any, dumped: dict[str, Any], *keys: str) -> Any:
        for key in keys:
            value = getattr(item, key, None)
            if value not in (None, ""):
                return value
            value = dumped.get(key)
            if value not in (None, ""):
                return value
        return None

    @classmethod
    def _optional_text(cls, item: Any, dumped: dict[str, Any], *keys: str) -> str | None:
        value = cls._first_value(item, dumped, *keys)
        if value in (None, ""):
            return None
        return str(value)

    @classmethod
    def _optional_number(cls, item: Any, dumped: dict[str, Any], *keys: str) -> int | float | None:
        value = cls._first_value(item, dumped, *keys)
        if isinstance(value, (int, float)):
            return value
        return None

    @classmethod
    def _extract_resource_contents(cls, result: Any) -> list[dict[str, Any]]:
        contents = getattr(result, "contents", None)
        if contents is None and isinstance(result, dict):
            contents = result.get("contents")
        if not isinstance(contents, list):
            return []

        extracted: list[dict[str, Any]] = []
        for item in contents:
            extracted.append(cls._resource_content_to_dict(item))
        return extracted

    @classmethod
    def _resource_content_to_dict(cls, item: Any) -> dict[str, Any]:
        dumped = cls._asdict(item)
        uri = cls._optional_text(item, dumped, "uri")
        mime_type = cls._optional_text(item, dumped, "mimeType", "mime_type")
        text = cls._optional_text(item, dumped, "text")
        if text is not None:
            max_chars = 20000
            return {
                "kind": "text",
                "uri": uri,
                "mimeType": mime_type,
                "text": text[:max_chars],
                "truncated": len(text) > max_chars,
            }

        blob = cls._first_value(item, dumped, "blob")
        if isinstance(blob, bytes):
            encoded = base64.b64encode(blob).decode("ascii")
            size_bytes = len(blob)
        elif isinstance(blob, str):
            encoded = blob
            try:
                size_bytes = len(base64.b64decode(blob, validate=False))
            except Exception:
                size_bytes = len(blob)
        else:
            encoded = ""
            size_bytes = 0

        max_blob_chars = 8192
        payload: dict[str, Any] = {
            "kind": "blob",
            "uri": uri,
            "mimeType": mime_type,
            "sizeBytes": size_bytes,
            "truncated": len(encoded) > max_blob_chars,
        }
        if encoded:
            payload["blobBase64"] = encoded[:max_blob_chars]
        return payload

    def _decorate_description(self, server_name: str, description: str) -> str:
        if len(self._configs) == 1:
            return description.strip()
        base_description = description.strip()
        if base_description:
            return f"[Server: {server_name}] {base_description}"
        return f"[Server: {server_name}]"

    @classmethod
    def _decorate_openai_tool_schema(
        cls, name: str, description: str, parameters: dict[str, Any]
    ) -> tuple[str, dict[str, Any]]:
        description_text = str(description or "").strip()
        schema = json.loads(json.dumps(parameters or {"type": "object", "properties": {}}))

        if not name.startswith("kicad_"):
            return description_text, schema

        notes: list[str] = []
        properties = schema.get("properties")
        if isinstance(properties, dict):
            path_note_added = False
            for field_name in cls._PATH_ARGUMENT_FIELDS:
                field = properties.get(field_name)
                if not isinstance(field, dict):
                    continue
                base = str(field.get("description") or "").strip()
                suffix = "Use an absolute filesystem path."
                if suffix not in base:
                    field["description"] = f"{base} {suffix}".strip()
                path_note_added = True
            if path_note_added:
                notes.append(
                    "Use absolute filesystem paths for filename/path/schematicPath/boardPath/projectPath fields."
                )

        if name == "kicad_add_schematic_component":
            notes.append(
                "Use canonical KiCad library symbols; for power rails prefer power:+5V and power:GND instead of inventing Device:V."
            )

        if notes:
            if description_text:
                description_text = f"{description_text} {' '.join(notes)}"
            else:
                description_text = " ".join(notes)
        return description_text, schema

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
            return json.dumps(structured)
        return ""

    _PATH_ARGUMENT_FIELDS = {
        "path",
        "filename",
        "schematicPath",
        "boardPath",
        "projectPath",
        "template",
    }
    _MISSING_ROOT_PATH_RE = re.compile(r"^(Users|private|Applications|Volumes)/")

    @classmethod
    def _normalize_tool_arguments(
        cls, name: str, server_name: str, arguments: dict[str, Any]
    ) -> dict[str, Any]:
        if not arguments:
            return arguments
        if "kicad" not in server_name.lower() and not name.startswith("kicad_"):
            return arguments
        return cls._normalize_kicad_argument_value(arguments)

    @classmethod
    def _normalize_kicad_argument_value(cls, value: Any, *, key: str | None = None) -> Any:
        if isinstance(value, dict):
            return {
                dict_key: cls._normalize_kicad_argument_value(dict_value, key=str(dict_key))
                for dict_key, dict_value in value.items()
            }
        if isinstance(value, list):
            return [cls._normalize_kicad_argument_value(item) for item in value]
        if isinstance(value, str) and key in cls._PATH_ARGUMENT_FIELDS:
            return cls._normalize_path_string(value)
        return value

    @classmethod
    def _normalize_path_string(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            return value
        if normalized.startswith("~"):
            return str(Path(normalized).expanduser())
        if cls._MISSING_ROOT_PATH_RE.match(normalized):
            return f"/{normalized}"
        return normalized


def _default_local_server_config() -> McpServerConfig:
    server_path = Path(__file__).resolve().parent / "mcp_server.py"
    return McpServerConfig(
        name="talos-local",
        transport="stdio",
        command=sys.executable,
        args=[str(server_path)],
    )


def _optional_kicad_server_config() -> McpServerConfig | None:
    raw_path = os.getenv("KICAD_MCP_SERVER_PATH", "").strip()
    if not raw_path:
        return None

    repo_root = Path(__file__).resolve().parent.parent
    server_path = Path(raw_path).expanduser()
    if not server_path.is_absolute():
        server_path = (repo_root / server_path).resolve()

    if server_path.is_dir():
        entrypoint = server_path / "dist" / "index.js"
        cwd = server_path
    else:
        entrypoint = server_path
        cwd = (
            server_path.parent.parent
            if server_path.parent.name == "dist" and server_path.parent.parent.exists()
            else server_path.parent
        )

    env: dict[str, str] = {
        "NODE_ENV": os.getenv("KICAD_MCP_NODE_ENV", "production").strip() or "production",
        "LOG_LEVEL": os.getenv("KICAD_MCP_LOG_LEVEL", "info").strip() or "info",
        "KICAD_AUTO_LAUNCH": os.getenv("KICAD_AUTO_LAUNCH", "false").strip() or "false",
    }
    for source_key, target_key in (
        ("KICAD_PYTHONPATH", "PYTHONPATH"),
        ("KICAD_PYTHON", "KICAD_PYTHON"),
        ("KICAD_MCP_DEV", "KICAD_MCP_DEV"),
    ):
        value = os.getenv(source_key, "").strip()
        if value:
            env[target_key] = value

    return McpServerConfig(
        name=os.getenv("KICAD_MCP_SERVER_NAME", "kicad").strip() or "kicad",
        transport="stdio",
        command=os.getenv("KICAD_MCP_COMMAND", "node").strip() or "node",
        args=[str(entrypoint)],
        cwd=str(cwd),
        env=env,
        tool_prefix=os.getenv("KICAD_MCP_TOOL_PREFIX", "kicad_").strip(),
        timeout_seconds=float(os.getenv("KICAD_MCP_TIMEOUT", "60")),
    )


def _load_mcp_server_configs() -> list[McpServerConfig]:
    raw_config = os.getenv("TALOS_MCP_SERVERS", "").strip()
    if not raw_config:
        configs = [_default_local_server_config()]
        kicad_config = _optional_kicad_server_config()
        if kicad_config is not None:
            configs.append(kicad_config)
        return configs

    try:
        parsed = json.loads(raw_config)
    except json.JSONDecodeError as exc:
        raise ValueError(
            "TALOS_MCP_SERVERS must be valid JSON. "
            "Expected a JSON array of MCP server config objects."
        ) from exc

    if isinstance(parsed, dict):
        parsed = [parsed]
    if not isinstance(parsed, list):
        raise ValueError("TALOS_MCP_SERVERS must decode to a JSON array or object.")

    configs: list[McpServerConfig] = []
    seen_names: set[str] = set()
    for index, item in enumerate(parsed):
        if not isinstance(item, dict):
            raise ValueError(f"TALOS_MCP_SERVERS entry {index} must be an object.")

        name = str(item.get("name") or "").strip()
        transport = str(item.get("transport") or "").strip()
        if not name:
            raise ValueError(f"TALOS_MCP_SERVERS entry {index} is missing 'name'.")
        if not transport:
            raise ValueError(f"TALOS_MCP_SERVERS entry {index} is missing 'transport'.")
        if name in seen_names:
            raise ValueError(f"TALOS_MCP_SERVERS contains duplicate server name '{name}'.")
        seen_names.add(name)

        args = item.get("args", [])
        if args is None:
            args = []
        if not isinstance(args, list):
            raise ValueError(f"TALOS_MCP_SERVERS entry '{name}' has non-list 'args'.")

        headers = item.get("headers", {})
        if headers is None:
            headers = {}
        if not isinstance(headers, dict):
            raise ValueError(f"TALOS_MCP_SERVERS entry '{name}' has non-object 'headers'.")

        env = item.get("env", {})
        if env is None:
            env = {}
        if not isinstance(env, dict):
            raise ValueError(f"TALOS_MCP_SERVERS entry '{name}' has non-object 'env'.")

        timeout_seconds = item.get("timeout_seconds", 30.0)
        configs.append(
            McpServerConfig(
                name=name,
                transport=transport,
                command=_optional_str(item.get("command")),
                args=[str(arg) for arg in args],
                url=_optional_str(item.get("url")),
                headers={str(key): str(value) for key, value in headers.items()},
                auth_token=_optional_str(item.get("auth_token")),
                auth_token_env=_optional_str(item.get("auth_token_env")),
                tool_prefix=str(item.get("tool_prefix") or ""),
                cwd=_optional_str(item.get("cwd")),
                env={str(key): str(value) for key, value in env.items()},
                timeout_seconds=float(timeout_seconds),
            )
        )

    kicad_config = _optional_kicad_server_config()
    if kicad_config is not None and kicad_config.name not in seen_names:
        configs.append(kicad_config)

    return configs


def _optional_str(value: Any) -> str | None:
    if value in (None, ""):
        return None
    return str(value)


_shared_client: LocalMcpClient | None = None
_shared_lock = threading.Lock()


def get_local_mcp_client() -> LocalMcpClient:
    global _shared_client
    with _shared_lock:
        if _shared_client is None:
            _shared_client = LocalMcpClient(_load_mcp_server_configs())
        return _shared_client


def shutdown_local_mcp_client() -> None:
    global _shared_client
    with _shared_lock:
        if _shared_client is not None:
            _shared_client.stop()
            _shared_client = None
