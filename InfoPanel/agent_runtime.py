from __future__ import annotations

import json
import os
import threading
import time
from pathlib import Path
from typing import Any

import openai
from dotenv import load_dotenv

from local_mcp_client import get_local_mcp_client, shutdown_local_mcp_client


ENV_PATH = Path(__file__).resolve().parent.parent / ".env"
load_dotenv(dotenv_path=ENV_PATH)

openai.api_key = os.getenv("OPENAI_API_KEY")

if not ENV_PATH.exists():
    raise RuntimeError(
        f"Missing environment file: {ENV_PATH}. "
        "Create it from .env.example and add OPENAI_API_KEY."
    )

if not openai.api_key:
    raise RuntimeError(
        f"OPENAI_API_KEY is not set in {ENV_PATH}. "
        "Add your key to that file and restart the app."
    )

client = openai.OpenAI(api_key=openai.api_key)

indoctrination = """
You are Monkey Butler, an assistant styled after JARVIS from Iron Man.
- The user is speaking to you through a microphone using google's speech recognizer. Inputs may not be transcribed perfectly. Try to infer the most likely intended input from the user.
- Tone: calm, polite, slightly dry British wit, never cruel or mocking.
- keep responses brief as possible
- try to answer in a sentence or two
- Avoid slang and emojis; occasionally use understated humor.
- you are a voice assistant. always answer as if you are talking, not outputting text.
- you are an artificial intelligence construct. your tone should not be warm or friendly.
- you are the personal AI assistant of one person. You do not have to be polite and can speak as if you know them, but you can call them sir when appropriate.
Always respond as if you are a hyper-competent digital butler/engineer assisting the user.
"""

ai_model = os.getenv("OPENAI_VOICE_MODEL", "gpt-4o-mini")
MAX_TOOL_CALL_ROUNDS = max(1, int(os.getenv("TALOS_MAX_TOOL_CALL_ROUNDS", "8")))
OPENAI_SERVER_ERROR_RETRIES = max(0, int(os.getenv("TALOS_OPENAI_SERVER_ERROR_RETRIES", "2")))
OPENAI_SERVER_ERROR_RETRY_DELAY = max(
    0.0, float(os.getenv("TALOS_OPENAI_SERVER_ERROR_RETRY_DELAY", "1.5"))
)
KICAD_TOOL_PREFIX = os.getenv("KICAD_MCP_TOOL_PREFIX", "kicad_").strip() or "kicad_"
TOOL_OUTPUT_CHAR_LIMIT = max(256, int(os.getenv("TALOS_TOOL_OUTPUT_CHAR_LIMIT", "4000")))
TOOL_OUTPUT_SUMMARY_ENABLED = (
    os.getenv("TALOS_SUMMARIZE_TOOL_OUTPUTS", "1").strip().lower() not in {"0", "false", "no", "off"}
)
TOOL_OUTPUT_SUMMARY_PREVIEW_ITEMS = max(
    1, int(os.getenv("TALOS_TOOL_OUTPUT_SUMMARY_PREVIEW_ITEMS", "5"))
)
TOOL_OUTPUT_SUMMARY_PREVIEW_KEYS = max(
    1, int(os.getenv("TALOS_TOOL_OUTPUT_SUMMARY_PREVIEW_KEYS", "12"))
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
    ]


def _is_server_error(exc: Exception) -> bool:
    lowered = str(exc).lower()
    return "server_error" in lowered or "error code: 500" in lowered or "http 500" in lowered


def _responses_create_with_retry(**kwargs):
    attempt = 0
    while True:
        try:
            return client.responses.create(**kwargs)
        except Exception as exc:
            if attempt >= OPENAI_SERVER_ERROR_RETRIES or not _is_server_error(exc):
                raise
            attempt += 1
            print(
                f"OpenAI server error on attempt {attempt}; retrying in "
                f"{OPENAI_SERVER_ERROR_RETRY_DELAY:.1f}s..."
            )
            time.sleep(OPENAI_SERVER_ERROR_RETRY_DELAY)


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
    raise KeyError(name)


def _collect_tool_outputs(response: Any, mcp_client: Any) -> list[dict[str, Any]]:
    tool_outputs = []
    for item in response.output:
        if item.type != "function_call":
            continue

        print(f"FUNCTION CALL DETECTED: {item.name} with args {item.arguments}")
        try:
            if item.name in {"list_mcp_resources", "list_mcp_resource_templates", "read_mcp_resource"}:
                result = _invoke_host_tool(mcp_client, item.name, item.arguments)
            else:
                result = mcp_client.call_tool(item.name, item.arguments)
        except KeyError:
            result = f"Unknown function: {item.name}"
        except Exception as exc:
            result = f"Error calling {item.name}: {exc}"

        shaped_output = _shape_tool_output(item.name, result)
        tool_outputs.append(
            {
                "type": "function_call_output",
                "call_id": item.call_id,
                "output": shaped_output,
            }
        )
        print(f"Function '{item.name}' executed with result: {_truncate_text(str(result), 600)}")
    return tool_outputs


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
            while True:
                tool_outputs = _collect_tool_outputs(response, mcp_client)
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
                response = _responses_create_with_retry(
                    model=ai_model,
                    instructions=indoctrination,
                    tools=tool_defs,
                    input=tool_outputs,
                    previous_response_id=response.id,
                    temperature=0.5,
                    max_output_tokens=150,
                )
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
