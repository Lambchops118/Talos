from __future__ import annotations

import json
import os
import random
import threading
import time
from typing import Any

import openai

from talos.agent.prompts import MONKEY_BUTLER_PROMPT
from talos.config import env_bool, env_float, env_int, load_environment, require_env
from talos.mcp_client import get_local_mcp_client, shutdown_local_mcp_client


load_environment()

_client: openai.OpenAI | None = None
indoctrination = MONKEY_BUTLER_PROMPT

ai_model = os.getenv("OPENAI_VOICE_MODEL", "gpt-4o-mini")
MAX_TOOL_CALL_ROUNDS = max(1, env_int("TALOS_MAX_TOOL_CALL_ROUNDS", 8))
OPENAI_SERVER_ERROR_RETRIES = max(0, env_int("TALOS_OPENAI_SERVER_ERROR_RETRIES", 2))
OPENAI_SERVER_ERROR_RETRY_DELAY = max(
    0.0, env_float("TALOS_OPENAI_SERVER_ERROR_RETRY_DELAY", 1.5)
)
OPENAI_SERVER_ERROR_RETRY_MAX_DELAY = max(
    OPENAI_SERVER_ERROR_RETRY_DELAY,
    env_float("TALOS_OPENAI_SERVER_ERROR_RETRY_MAX_DELAY", 20.0),
)
OPENAI_SERVER_ERROR_RETRY_JITTER = max(
    0.0, env_float("TALOS_OPENAI_SERVER_ERROR_RETRY_JITTER", 0.25)
)
OPENAI_SERVER_ERROR_RECOVERY_ATTEMPTS = max(
    0, env_int("TALOS_OPENAI_SERVER_ERROR_RECOVERY_ATTEMPTS", 1)
)
KICAD_TOOL_PREFIX = os.getenv("KICAD_MCP_TOOL_PREFIX", "kicad_").strip() or "kicad_"
TOOL_OUTPUT_CHAR_LIMIT = max(256, env_int("TALOS_TOOL_OUTPUT_CHAR_LIMIT", 4000))
TOOL_OUTPUT_SUMMARY_ENABLED = env_bool("TALOS_SUMMARIZE_TOOL_OUTPUTS", True)
TOOL_OUTPUT_SUMMARY_PREVIEW_ITEMS = max(
    1, env_int("TALOS_TOOL_OUTPUT_SUMMARY_PREVIEW_ITEMS", 5)
)
TOOL_OUTPUT_SUMMARY_PREVIEW_KEYS = max(
    1, env_int("TALOS_TOOL_OUTPUT_SUMMARY_PREVIEW_KEYS", 12)
)

_conversation_lock = threading.Lock()
_last_response_ids: dict[str, str] = {}

KICAD_PREFERRED_TOOL_SUFFIXES = {
    "list_tool_categories",
    "get_category_tools",
    "search_tools",
    "execute_tool",
    "create_project",
    "open_project",
    "save_project",
    "snapshot_project",
    "get_project_info",
    "set_board_size",
    "add_board_outline",
    "get_board_info",
    "check_kicad_ui",
    "launch_kicad_ui",
    "get_backend_state",
    "list_symbol_libraries",
    "list_library_symbols",
    "search_symbols",
    "get_symbol_info",
    "add_schematic_component",
    "list_schematic_components",
    "annotate_schematic",
    "connect_passthrough",
    "connect_to_net",
    "add_schematic_net_label",
    "sync_schematic_to_board",
    "place_component",
    "move_component",
    "add_net",
    "route_trace",
}
KICAD_BACKEND_STATE_TOOL = f"{KICAD_TOOL_PREFIX}get_backend_state"
KICAD_UI_CHECK_TOOL = f"{KICAD_TOOL_PREFIX}check_kicad_ui"
KICAD_UI_LAUNCH_TOOL = f"{KICAD_TOOL_PREFIX}launch_kicad_ui"
KICAD_SYNC_TOOL = f"{KICAD_TOOL_PREFIX}sync_schematic_to_board"
KICAD_RELEVANT_TERMS = {
    "kicad",
    "pcb",
    "board",
    "schematic",
    "footprint",
    "trace",
    "routing",
    "route",
    "net",
    "component",
    "components",
    "place",
    "placement",
    "populate",
    "layout",
}
KICAD_BOARD_EDIT_TERMS = {
    "board",
    "footprint",
    "trace",
    "route",
    "routing",
    "net",
    "place",
    "placement",
    "populate",
    "layout",
    "move",
    "rotate",
}
KICAD_SCHEMATIC_TO_BOARD_TERMS = {
    "schematic",
    "sync",
    "footprint",
    "place",
    "placement",
    "populate",
    "route",
    "routing",
}


def _resource_tool_definitions() -> list[dict[str, Any]]:
    return [
        {
            "type": "function",
            "name": "list_mcp_resources",
            "description": "List read-only MCP resources exposed by connected servers.",
            "parameters": {
                "type": "object",
                "properties": {
                    "refresh": {
                        "type": "boolean",
                        "description": "Refresh the cached MCP resource list before returning it.",
                    }
                },
                "additionalProperties": False,
            },
        },
        {
            "type": "function",
            "name": "list_mcp_resource_templates",
            "description": "List MCP resource templates exposed by connected servers.",
            "parameters": {
                "type": "object",
                "properties": {
                    "refresh": {
                        "type": "boolean",
                        "description": "Refresh the cached MCP resource template list before returning it.",
                    }
                },
                "additionalProperties": False,
            },
        },
        {
            "type": "function",
            "name": "read_mcp_resource",
            "description": "Read a specific MCP resource URI. Use the server field when more than one server exposes the same URI.",
            "parameters": {
                "type": "object",
                "properties": {
                    "uri": {
                        "type": "string",
                        "description": "The MCP resource URI to read.",
                    },
                    "server": {
                        "type": "string",
                        "description": "Optional server name for disambiguation when duplicate URIs exist.",
                    },
                },
                "required": ["uri"],
                "additionalProperties": False,
            },
        },
        {
            "type": "function",
            "name": "list_mcp_server_status",
            "description": "List configured MCP servers and their current health, failure, and retry state. This is read-only and does not retry degraded servers.",
            "parameters": {
                "type": "object",
                "properties": {},
                "additionalProperties": False,
            },
        },
        {
            "type": "function",
            "name": "list_mcp_tools",
            "description": "List currently available MCP tools and configured server health. Use this when asked what tools are available. This does not retry degraded servers.",
            "parameters": {
                "type": "object",
                "properties": {
                    "refresh": {
                        "type": "boolean",
                        "description": "Refresh the available tool list from currently healthy servers without retrying degraded servers.",
                    }
                },
                "additionalProperties": False,
            },
        },
        {
            "type": "function",
            "name": "retry_mcp_server",
            "description": "Explicitly retry starting one degraded MCP server, or all degraded servers when server is omitted.",
            "parameters": {
                "type": "object",
                "properties": {
                    "server": {
                        "type": "string",
                        "description": "Optional MCP server name to retry, such as kicad.",
                    }
                },
                "additionalProperties": False,
            },
        },
    ]


def _is_server_error(exc: Exception) -> bool:
    lowered = str(exc).lower()
    return "server_error" in lowered or "error code: 500" in lowered or "http 500" in lowered


def _get_openai_client() -> openai.OpenAI:
    global _client
    if _client is None:
        api_key = require_env("OPENAI_API_KEY")
        openai.api_key = api_key
        _client = openai.OpenAI(api_key=api_key)
    return _client


def _responses_create_with_retry(**kwargs):
    attempt = 0
    while True:
        try:
            return _get_openai_client().responses.create(**kwargs)
        except Exception as exc:
            if attempt >= OPENAI_SERVER_ERROR_RETRIES or not _is_server_error(exc):
                raise
            attempt += 1
            retry_delay = min(
                OPENAI_SERVER_ERROR_RETRY_DELAY * (2 ** (attempt - 1)),
                OPENAI_SERVER_ERROR_RETRY_MAX_DELAY,
            )
            if OPENAI_SERVER_ERROR_RETRY_JITTER > 0:
                jitter_window = retry_delay * OPENAI_SERVER_ERROR_RETRY_JITTER
                retry_delay += random.uniform(-jitter_window, jitter_window)
                retry_delay = max(0.0, retry_delay)
            print(
                f"OpenAI server error on attempt {attempt}; retrying in "
                f"{retry_delay:.1f}s..."
            )
            time.sleep(retry_delay)


def _reduce_tool_surface(tool_defs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    reduced: list[dict[str, Any]] = []
    kept_kicad = 0
    skipped_kicad = 0

    for tool in tool_defs:
        name = str(tool.get("name") or "")
        if not name.startswith(KICAD_TOOL_PREFIX):
            reduced.append(tool)
            continue

        suffix = name[len(KICAD_TOOL_PREFIX) :]
        if suffix in KICAD_PREFERRED_TOOL_SUFFIXES:
            reduced.append(tool)
            kept_kicad += 1
        else:
            skipped_kicad += 1

    if skipped_kicad:
        print(
            f"Reduced KiCad tool surface: kept {kept_kicad}, skipped {skipped_kicad} "
            f"for model context."
        )
    return reduced


def _build_tool_definitions(mcp_client: Any) -> list[dict[str, Any]]:
    tool_defs = _resource_tool_definitions() + mcp_client.openai_tool_definitions()
    reduce_kicad = os.getenv("TALOS_REDUCE_KICAD_TOOL_SURFACE", "1").strip().lower()
    if reduce_kicad not in {"0", "false", "no", "off"}:
        tool_defs = _reduce_tool_surface(tool_defs)

    try:
        tool_bytes = len(json.dumps(tool_defs).encode("utf-8"))
    except Exception:
        tool_bytes = 0
    print(f"Tool definitions prepared: {len(tool_defs)} tools, {tool_bytes} bytes")
    return tool_defs


def _format_context(snapshot: str) -> str | None:
    if not snapshot or snapshot == "no recent status":
        return None
    snapshot = " ".join(str(snapshot).split())
    if len(snapshot) > 500:
        snapshot = snapshot[:500].rsplit(" ", 1)[0] + "..."
    return f"Context (read-only): {snapshot}"


def _tokenize_lowered(text: str) -> set[str]:
    normalized = []
    for char in text.lower():
        normalized.append(char if char.isalnum() else " ")
    return {token for token in "".join(normalized).split() if token}


def _is_kicad_request(command: str, tool_defs: list[dict[str, Any]]) -> bool:
    lowered = command.lower()
    if KICAD_TOOL_PREFIX in lowered or "kicad" in lowered:
        return True
    if not any(str(tool.get("name") or "").startswith(KICAD_TOOL_PREFIX) for tool in tool_defs):
        return False
    return bool(_tokenize_lowered(command) & KICAD_RELEVANT_TERMS)


def _format_kicad_backend_context(raw_output: str, command: str) -> str | None:
    stripped = raw_output.strip()
    if not stripped:
        return None

    try:
        payload = json.loads(stripped)
    except Exception:
        return f"KiCad backend preflight (fresh): {_truncate_text(' '.join(stripped.split()), 500)}"

    if not isinstance(payload, dict):
        return None

    status = {
        "backend": payload.get("backend"),
        "realtime": payload.get("realtime_sync", payload.get("realtime")),
        "ipc_connected": payload.get("ipc_connected", payload.get("ipcConnected")),
        "loaded_project": payload.get("loadedProject"),
        "loaded_board": payload.get("loadedBoard"),
        "project_path": payload.get("projectPath"),
        "board_path": payload.get("boardPath"),
        "dirty": payload.get("dirty"),
        "message": payload.get("message"),
    }
    compact_status = json.dumps(status, ensure_ascii=True)

    notes: list[str] = []
    tokens = _tokenize_lowered(command)

    if status["backend"] == "swig":
        notes.append(
            "KiCad is currently in SWIG mode, so board changes are file-based and not guaranteed to appear live in the UI."
        )
    if status["ipc_connected"] is False:
        notes.append(
            "For real-time board placement, KiCad must be running with IPC enabled and a board open."
        )
    if tokens & KICAD_BOARD_EDIT_TERMS and status["loaded_board"] is False:
        notes.append("No PCB board is currently loaded, so board-editing commands may fail or target only files on disk.")
    if tokens & KICAD_SCHEMATIC_TO_BOARD_TERMS:
        notes.append(
            "If the task starts from schematic components, sync the schematic to the board before placement or routing."
        )
    if KICAD_UI_CHECK_TOOL and status["backend"] == "swig":
        notes.append(
            "If the user expects visual updates, prefer checking or launching KiCad UI before claiming the placement is visible."
        )

    if notes:
        return f"KiCad backend preflight (fresh): {compact_status} Guidance: {' '.join(notes)}"
    return f"KiCad backend preflight (fresh): {compact_status}"


def _maybe_add_kicad_preflight(
    input_items: list[dict[str, Any]],
    mcp_client: Any,
    tool_defs: list[dict[str, Any]],
    command: str,
) -> None:
    if not _is_kicad_request(command, tool_defs):
        return

    tool_names = {str(tool.get("name") or "") for tool in tool_defs}
    if KICAD_BACKEND_STATE_TOOL not in tool_names:
        return

    try:
        raw_state = mcp_client.call_tool(KICAD_BACKEND_STATE_TOOL, {})
    except Exception as exc:
        input_items.append(
            {
                "role": "system",
                "content": f"KiCad backend preflight failed: {_truncate_text(str(exc), 300)}",
            }
        )
        return

    preflight_context = _format_kicad_backend_context(raw_state, command)
    if preflight_context:
        input_items.append({"role": "system", "content": preflight_context})


def _parse_function_arguments(arguments: Any) -> dict[str, Any]:
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


def _truncate_text(value: str, limit: int = TOOL_OUTPUT_CHAR_LIMIT) -> str:
    if len(value) <= limit:
        return value
    if limit <= 3:
        return value[:limit]
    return value[: limit - 3] + "..."


def _summarize_jsonish_value(value: Any, *, depth: int = 0) -> Any:
    if depth >= 2:
        if isinstance(value, dict):
            return f"<object with {len(value)} keys>"
        if isinstance(value, list):
            return f"<list with {len(value)} items>"
        return value

    if isinstance(value, dict):
        summary: dict[str, Any] = {}
        preferred_keys = (
            "success",
            "message",
            "error",
            "errorDetails",
            "name",
            "path",
            "project",
            "board",
            "component",
            "components",
            "net",
            "nets",
            "warnings",
        )
        for key in preferred_keys:
            if key not in value:
                continue
            item = value[key]
            if isinstance(item, (dict, list)):
                summary[key] = _summarize_jsonish_value(item, depth=depth + 1)
            else:
                summary[key] = item

        remaining_keys = [key for key in value.keys() if key not in summary]
        for key in remaining_keys[:TOOL_OUTPUT_SUMMARY_PREVIEW_KEYS]:
            item = value[key]
            if isinstance(item, (str, int, float, bool)) or item is None:
                summary[key] = item
            elif isinstance(item, dict):
                summary[key] = f"<object with {len(item)} keys>"
            elif isinstance(item, list):
                summary[key] = f"<list with {len(item)} items>"
            else:
                summary[key] = f"<{type(item).__name__}>"

        if len(remaining_keys) > TOOL_OUTPUT_SUMMARY_PREVIEW_KEYS:
            summary["_remaining_keys"] = len(remaining_keys) - TOOL_OUTPUT_SUMMARY_PREVIEW_KEYS
        return summary

    if isinstance(value, list):
        preview = [
            _summarize_jsonish_value(item, depth=depth + 1)
            for item in value[:TOOL_OUTPUT_SUMMARY_PREVIEW_ITEMS]
        ]
        summary = {
            "item_count": len(value),
            "preview": preview,
        }
        if len(value) > TOOL_OUTPUT_SUMMARY_PREVIEW_ITEMS:
            summary["remaining_items"] = len(value) - TOOL_OUTPUT_SUMMARY_PREVIEW_ITEMS
        return summary

    if isinstance(value, str):
        return _truncate_text(" ".join(value.split()))
    return value


def _summarize_tool_result(name: str, raw_output: str) -> str | None:
    stripped = raw_output.strip()
    if not stripped:
        return raw_output

    try:
        parsed = json.loads(stripped)
    except Exception:
        condensed = " ".join(raw_output.split())
        if len(condensed) >= len(raw_output) or len(raw_output) > TOOL_OUTPUT_CHAR_LIMIT:
            return condensed
        return None

    summary_payload = {
        "tool": name,
        "summary": _summarize_jsonish_value(parsed),
    }
    return json.dumps(summary_payload, ensure_ascii=True)


def _shape_tool_output(name: str, result: Any) -> str:
    raw_output = str(result)
    shaped_output = raw_output
    used_summary = False

    if TOOL_OUTPUT_SUMMARY_ENABLED:
        summary_output = _summarize_tool_result(name, raw_output)
        if summary_output is not None and len(summary_output) < len(raw_output):
            shaped_output = summary_output
            used_summary = True

    truncated = False
    if len(shaped_output) > TOOL_OUTPUT_CHAR_LIMIT:
        shaped_output = _truncate_text(shaped_output)
        truncated = True

    if used_summary or truncated or len(raw_output) > TOOL_OUTPUT_CHAR_LIMIT:
        print(
            f"Tool output shaped for {name}: raw={len(raw_output)} chars, "
            f"sent={len(shaped_output)} chars, summary={used_summary}, truncated={truncated}"
        )

    return shaped_output


def _tool_result_indicates_failure(raw_result: str) -> bool:
    stripped = raw_result.strip()
    if not stripped:
        return False

    lowered = stripped.lower()
    if lowered.startswith("error calling ") or lowered.startswith("unknown function:"):
        return True
    if lowered.startswith("failed ") or lowered.startswith("failed to "):
        return True

    try:
        parsed = json.loads(stripped)
    except Exception:
        return False

    if isinstance(parsed, dict):
        success = parsed.get("success")
        if success is False:
            return True
        if success is True:
            return False
        if parsed.get("error") or parsed.get("errorDetails"):
            return True
    return False


def _fallback_response_from_tool_error(
    command: str,
    tool_events: list[dict[str, Any]],
    exc: Exception,
) -> str:
    if not tool_events:
        return (
            "The model backend failed after the tool call, and I do not have a usable KiCad result to report."
        )

    last_event = tool_events[-1]
    tool_name = last_event.get("name", "the KiCad tool")
    raw_result = " ".join(last_event.get("raw_result", "").split())
    raw_result = _truncate_text(raw_result, 500)
    tool_failed = bool(last_event.get("failed"))

    if command and _is_kicad_request(command, [{"name": tool_name}]):
        if tool_failed:
            return (
                f"The KiCad step failed in {tool_name}: {raw_result} "
                "The follow-up call to OpenAI then hit a server-side 500, so I am surfacing the real tool failure instead. "
                "Please retry with a valid KiCad symbol or path."
            )
        return (
            f"The KiCad step completed in {tool_name}: {raw_result} "
            "The follow-up call to OpenAI then hit a server-side 500 before the agent could continue. "
            "Please retry the request from the current project state."
        )

    if tool_failed:
        return (
            f"The last tool call failed in {tool_name}: {raw_result} "
            f"The follow-up model call then hit a server-side error: {_truncate_text(str(exc), 200)}"
        )
    return (
        f"The last tool call completed in {tool_name}: {raw_result} "
        f"The follow-up model call then hit a server-side error: {_truncate_text(str(exc), 200)}"
    )


def _summarize_recovery_events(tool_events: list[dict[str, Any]], limit: int = 6) -> str:
    if not tool_events:
        return "No prior tool calls were recorded."

    selected = tool_events[-limit:]
    parts: list[str] = []
    for event in selected:
        status = "failed" if event.get("failed") else "completed"
        name = str(event.get("name") or "unknown_tool")
        raw_result = " ".join(str(event.get("raw_result") or "").split())
        raw_result = _truncate_text(raw_result, 240)
        parts.append(f"{name} {status}: {raw_result}")
    return " | ".join(parts)


def _build_recovery_input_items(
    command: str,
    state_snapshot: str,
    mcp_client: Any,
    tool_defs: list[dict[str, Any]],
    tool_events: list[dict[str, Any]],
    recovery_attempt: int,
) -> list[dict[str, Any]]:
    input_items: list[dict[str, Any]] = []

    context_message = _format_context(state_snapshot)
    if context_message:
        input_items.append({"role": "system", "content": context_message})

    recovery_summary = _summarize_recovery_events(tool_events)
    input_items.append(
        {
            "role": "system",
            "content": (
                "A previous OpenAI follow-up call failed with a transient server-side error "
                f"after tool execution. Recovery attempt {recovery_attempt}. "
                "Continue the same user request from the current tool state. "
                "Do not repeat already-successful project creation or placement steps unless the current backend state shows they did not persist. "
                f"Recent tool activity: {recovery_summary}"
            ),
        }
    )
    _maybe_add_kicad_preflight(input_items, mcp_client, tool_defs, command)
    input_items.append({"role": "user", "content": command})
    return input_items


def _invoke_host_tool(mcp_client: Any, name: str, arguments: Any) -> str:
    parsed_arguments = _parse_function_arguments(arguments)
    if name == "list_mcp_resources":
        return json.dumps({"resources": mcp_client.list_resources(refresh=bool(parsed_arguments.get("refresh")))})
    if name == "list_mcp_resource_templates":
        return json.dumps(
            {
                "resourceTemplates": mcp_client.list_resource_templates(
                    refresh=bool(parsed_arguments.get("refresh"))
                )
            }
        )
    if name == "read_mcp_resource":
        uri = str(parsed_arguments.get("uri") or "").strip()
        if not uri:
            raise ValueError("read_mcp_resource requires a non-empty 'uri'.")
        server = parsed_arguments.get("server")
        server_name = str(server).strip() if server not in (None, "") else None
        return mcp_client.read_resource(uri, server=server_name)
    if name == "list_mcp_server_status":
        return json.dumps({"servers": mcp_client.list_server_status()})
    if name == "list_mcp_tools":
        return json.dumps(
            mcp_client.list_tool_inventory(refresh=bool(parsed_arguments.get("refresh")))
        )
    if name == "retry_mcp_server":
        server = parsed_arguments.get("server")
        server_name = str(server).strip() if server not in (None, "") else None
        return json.dumps({"servers": mcp_client.retry_server(server_name)})
    raise KeyError(name)


def _collect_tool_outputs(response: Any, mcp_client: Any) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    tool_outputs = []
    tool_events: list[dict[str, Any]] = []
    for item in response.output:
        if item.type != "function_call":
            continue

        print(f"FUNCTION CALL DETECTED: {item.name} with args {item.arguments}")
        try:
            if item.name in {
                "list_mcp_resources",
                "list_mcp_resource_templates",
                "read_mcp_resource",
                "list_mcp_server_status",
                "list_mcp_tools",
                "retry_mcp_server",
            }:
                result = _invoke_host_tool(mcp_client, item.name, item.arguments)
            else:
                result = mcp_client.call_tool(item.name, item.arguments)
        except KeyError:
            result = f"Unknown function: {item.name}"
        except Exception as exc:
            result = f"Error calling {item.name}: {exc}"

        shaped_output = _shape_tool_output(item.name, result)
        raw_result = str(result)
        tool_outputs.append(
            {
                "type": "function_call_output",
                "call_id": item.call_id,
                "output": shaped_output,
            }
        )
        tool_events.append(
            {
                "name": item.name,
                "raw_result": raw_result,
                "output": shaped_output,
                "failed": _tool_result_indicates_failure(raw_result),
            }
        )
        print(f"Function '{item.name}' executed with result: {_truncate_text(raw_result, 600)}")
    return tool_outputs, tool_events


def run_command(
    command: str,
    state_snapshot: str = "no recent status",
    *,
    session_id: str = "default",
    benchmark: Any = None,
) -> str:
    if benchmark:
        benchmark.set_command(command)

    mcp_client = get_local_mcp_client()
    tool_defs = _build_tool_definitions(mcp_client)

    input_items: list[dict[str, Any]] = []
    context_message = _format_context(state_snapshot)
    if context_message:
        input_items.append({"role": "system", "content": context_message})
    _maybe_add_kicad_preflight(input_items, mcp_client, tool_defs, command)
    input_items.append({"role": "user", "content": command})

    try:
        with _conversation_lock:
            request_kwargs: dict[str, Any] = {
                "model": ai_model,
                "instructions": indoctrination,
                "tools": tool_defs,
                "input": input_items,
                "temperature": 0.5,
                "max_output_tokens": 150,
            }
            previous_response_id = _last_response_ids.get(session_id)
            if previous_response_id:
                request_kwargs["previous_response_id"] = previous_response_id

            if benchmark:
                benchmark.mark_stage("llm_send")
            response = _responses_create_with_retry(**request_kwargs)
            if benchmark:
                benchmark.mark_stage("llm_first_done")

            response_text = ""
            rounds = 0
            tool_events: list[dict[str, Any]] = []
            recovery_attempts = 0
            while True:
                tool_outputs, recent_events = _collect_tool_outputs(response, mcp_client)
                if recent_events:
                    tool_events.extend(recent_events)
                if not tool_outputs:
                    response_text = (response.output_text or "").strip()
                    _last_response_ids[session_id] = response.id
                    break

                if rounds >= MAX_TOOL_CALL_ROUNDS:
                    response_text = "I reached the tool-call limit before finishing that request."
                    _last_response_ids[session_id] = response.id
                    break

                if benchmark:
                    benchmark.mark_stage("llm_followup_send")
                try:
                    response = _responses_create_with_retry(
                        model=ai_model,
                        instructions=indoctrination,
                        tools=tool_defs,
                        input=tool_outputs,
                        previous_response_id=response.id,
                        temperature=0.5,
                        max_output_tokens=150,
                    )
                except Exception as exc:
                    if not _is_server_error(exc):
                        raise
                    if recovery_attempts < OPENAI_SERVER_ERROR_RECOVERY_ATTEMPTS and tool_events:
                        recovery_attempts += 1
                        print(
                            "OpenAI follow-up failed after tool execution; "
                            f"attempting recovery {recovery_attempts}/"
                            f"{OPENAI_SERVER_ERROR_RECOVERY_ATTEMPTS}."
                        )
                        recovery_input_items = _build_recovery_input_items(
                            command,
                            state_snapshot,
                            mcp_client,
                            tool_defs,
                            tool_events,
                            recovery_attempts,
                        )
                        response = _responses_create_with_retry(
                            model=ai_model,
                            instructions=indoctrination,
                            tools=tool_defs,
                            input=recovery_input_items,
                            temperature=0.5,
                            max_output_tokens=150,
                        )
                        continue

                    response_text = _fallback_response_from_tool_error(command, tool_events, exc)
                    _last_response_ids.pop(session_id, None)
                    break
                rounds += 1

            if benchmark:
                benchmark.mark_stage("llm_done")
    except Exception as exc:
        if benchmark:
            benchmark.add_error(f"Agent runtime error: {exc}")
            benchmark.emit_summary_once("agent_runtime_error")
        raise

    response_text = response_text.replace("Monkey Butler:", "").strip()
    if benchmark:
        benchmark.set_response_text(response_text)
    return response_text


def reset_session(session_id: str) -> None:
    with _conversation_lock:
        _last_response_ids.pop(session_id, None)


def shutdown() -> None:
    shutdown_local_mcp_client()
