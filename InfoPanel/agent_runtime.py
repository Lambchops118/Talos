from __future__ import annotations

import os
import threading
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

_conversation_lock = threading.Lock()
_last_response_ids: dict[str, str] = {}


def _format_context(snapshot: str) -> str | None:
    if not snapshot or snapshot == "no recent status":
        return None
    snapshot = " ".join(str(snapshot).split())
    if len(snapshot) > 500:
        snapshot = snapshot[:500].rsplit(" ", 1)[0] + "..."
    return f"Context (read-only): {snapshot}"


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
    tool_defs = mcp_client.openai_tool_definitions()

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
            response = client.responses.create(**request_kwargs)
            if benchmark:
                benchmark.mark_stage("llm_first_done")

            tool_outputs = []
            for item in response.output:
                if item.type != "function_call":
                    continue
                print(f"FUNCTION CALL DETECTED: {item.name} with args {item.arguments}")
                try:
                    result = mcp_client.call_tool(item.name, item.arguments)
                except KeyError:
                    result = f"Unknown function: {item.name}"
                except Exception as exc:
                    result = f"Error calling {item.name}: {exc}"

                tool_outputs.append(
                    {
                        "type": "function_call_output",
                        "call_id": item.call_id,
                        "output": str(result),
                    }
                )
                print(f"Function '{item.name}' executed with result: {result}")

            if tool_outputs:
                if benchmark:
                    benchmark.mark_stage("llm_followup_send")
                followup = client.responses.create(
                    model=ai_model,
                    instructions=indoctrination,
                    tools=tool_defs,
                    input=tool_outputs,
                    previous_response_id=response.id,
                    temperature=0.5,
                    max_output_tokens=150,
                )
                if benchmark:
                    benchmark.mark_stage("llm_done")
                response_text = (followup.output_text or "").strip()
                _last_response_ids[session_id] = followup.id
            else:
                if benchmark:
                    benchmark.mark_stage("llm_done")
                response_text = (response.output_text or "").strip()
                _last_response_ids[session_id] = response.id
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
