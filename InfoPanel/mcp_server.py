from __future__ import annotations

import json
import sys
import traceback
from dataclasses import dataclass
from typing import Any, Callable

import home_automation_actions as actions


@dataclass(frozen=True)
class ToolSpec:
    name: str
    description: str
    input_schema: dict[str, Any]
    handler: Callable[..., Any]


TOOLS: dict[str, ToolSpec] = {
    "water_plants": ToolSpec(
        name="water_plants",
        description="Send a signal to the pump circuit to water either pot 1 or pot 2.",
        input_schema={
            "type": "object",
            "properties": {
                "pot_number": {
                    "type": "number",
                    "description": "The pot number to water (1 or 2).",
                }
            },
            "required": ["pot_number"],
            "additionalProperties": False,
        },
        handler=actions.water_plants,
    ),
    "turn_on_lights": ToolSpec(
        name="turn_on_lights",
        description="Turn on the lights in a specific room.",
        input_schema={
            "type": "object",
            "properties": {
                "room": {
                    "type": "string",
                    "description": "The room where the lights should be turned on.",
                }
            },
            "required": ["room"],
            "additionalProperties": False,
        },
        handler=actions.turn_on_lights,
    ),
    "toggle_fan": ToolSpec(
        name="toggle_fan",
        description="Toggle the fan on (1) or off (0).",
        input_schema={
            "type": "object",
            "properties": {
                "status": {
                    "type": "number",
                    "description": "The number to send to the MQTT broker to toggle the fan on (1 or 0).",
                }
            },
            "required": ["status"],
            "additionalProperties": False,
        },
        handler=actions.toggle_fan,
    ),
}


def read_message() -> dict[str, Any] | None:
    content_length: int | None = None
    while True:
        line = sys.stdin.buffer.readline()
        if not line:
            return None
        if line == b"\r\n":
            break
        decoded = line.decode("ascii").strip()
        if decoded.lower().startswith("content-length:"):
            _, value = decoded.split(":", 1)
            content_length = int(value.strip())

    if content_length is None:
        raise RuntimeError("Missing Content-Length header.")

    payload = sys.stdin.buffer.read(content_length)
    if len(payload) != content_length:
        raise RuntimeError("Incomplete payload received.")

    message = json.loads(payload.decode("utf-8"))
    if not isinstance(message, dict):
        raise RuntimeError("MCP message must be an object.")
    return message


def write_message(message: dict[str, Any]) -> None:
    payload = json.dumps(message).encode("utf-8")
    header = f"Content-Length: {len(payload)}\r\n\r\n".encode("ascii")
    sys.stdout.buffer.write(header)
    sys.stdout.buffer.write(payload)
    sys.stdout.buffer.flush()


def jsonrpc_result(request_id: Any, result: dict[str, Any]) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": request_id, "result": result}


def jsonrpc_error(request_id: Any, code: int, message: str) -> dict[str, Any]:
    return {
        "jsonrpc": "2.0",
        "id": request_id,
        "error": {"code": code, "message": message},
    }


def coerce_value(value: Any, schema: dict[str, Any]) -> Any:
    schema_type = schema.get("type")
    if schema_type == "number":
        if isinstance(value, (int, float)):
            return value
        if isinstance(value, str):
            numeric = float(value)
            return int(numeric) if numeric.is_integer() else numeric
        raise ValueError(f"Expected a number, got {type(value).__name__}.")
    if schema_type == "integer":
        if isinstance(value, bool):
            raise ValueError("Booleans are not valid integers.")
        return int(value)
    if schema_type == "string":
        if isinstance(value, str):
            return value
        raise ValueError(f"Expected a string, got {type(value).__name__}.")
    if schema_type == "boolean":
        if isinstance(value, bool):
            return value
        raise ValueError(f"Expected a boolean, got {value!r}.")
    return value


def validate_arguments(spec: ToolSpec, arguments: dict[str, Any]) -> dict[str, Any]:
    schema = spec.input_schema or {}
    properties = schema.get("properties", {})
    required = schema.get("required", [])
    additional_properties = schema.get("additionalProperties", True)

    missing = [name for name in required if name not in arguments]
    if missing:
        raise ValueError(f"Missing required arguments: {', '.join(missing)}")

    if not additional_properties:
        unknown = [name for name in arguments if name not in properties]
        if unknown:
            raise ValueError(f"Unknown arguments: {', '.join(unknown)}")

    validated: dict[str, Any] = {}
    for key, value in arguments.items():
        validated[key] = coerce_value(value, properties.get(key, {}))
    return validated


def handle_initialize(_: dict[str, Any]) -> dict[str, Any]:
    return {
        "protocolVersion": "2025-03-26",
        "capabilities": {"tools": {"listChanged": False}},
        "serverInfo": {"name": "talos-local-mcp", "version": "0.1.0"},
    }


def handle_list_tools() -> dict[str, Any]:
    return {
        "tools": [
            {
                "name": spec.name,
                "description": spec.description,
                "inputSchema": spec.input_schema,
            }
            for spec in TOOLS.values()
        ]
    }


def handle_call_tool(params: dict[str, Any]) -> dict[str, Any]:
    tool_name = params.get("name")
    tool_arguments = params.get("arguments", {})

    if tool_name not in TOOLS:
        return {
            "content": [{"type": "text", "text": f"Unknown tool: {tool_name}"}],
            "isError": True,
        }
    if not isinstance(tool_arguments, dict):
        return {
            "content": [{"type": "text", "text": "Tool arguments must be a JSON object."}],
            "isError": True,
        }

    spec = TOOLS[tool_name]
    try:
        validated = validate_arguments(spec, tool_arguments)
        result = spec.handler(**validated)
        return {
            "content": [{"type": "text", "text": str(result)}],
            "isError": False,
        }
    except Exception as exc:
        return {
            "content": [{"type": "text", "text": f"Error calling {tool_name}: {exc}"}],
            "isError": True,
        }


def handle_request(message: dict[str, Any]) -> dict[str, Any] | None:
    method = message.get("method")
    request_id = message.get("id")
    params = message.get("params", {})

    if not isinstance(params, dict):
        params = {}

    if request_id is None:
        if method == "notifications/initialized":
            return None
        return None

    if method == "initialize":
        return jsonrpc_result(request_id, handle_initialize(params))
    if method == "tools/list":
        return jsonrpc_result(request_id, handle_list_tools())
    if method == "tools/call":
        return jsonrpc_result(request_id, handle_call_tool(params))
    return jsonrpc_error(request_id, -32601, f"Method not found: {method}")


def main() -> int:
    while True:
        try:
            message = read_message()
            if message is None:
                return 0
            response = handle_request(message)
            if response is not None:
                write_message(response)
        except Exception as exc:
            traceback.print_exc(file=sys.stderr)
            request_id = None
            if "message" in locals():
                request_id = message.get("id")
            write_message(jsonrpc_error(request_id, -32000, str(exc)))


if __name__ == "__main__":
    raise SystemExit(main())
