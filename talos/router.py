import queue
from typing import Optional

from talos.agent import runtime as agent_runtime
from talos.messages import Message, StatusPayload, TextPayload, VoicePayload
from talos.state_store import StateStore


def _run_agent_command(
    command: str,
    gui_queue: queue.Queue,
    snapshot: str,
    *,
    session_id: str,
    interaction_mode: str = "text",
) -> str:
    response_text = agent_runtime.run_command(
        command,
        snapshot,
        session_id=session_id,
        interaction_mode=interaction_mode,
    )
    gui_queue.put(("VOICE_CMD", command, response_text))
    return response_text

def router_loop(central_queue: queue.Queue, gui_queue: queue.Queue, stop_signal: Optional[object] = None):
    """
    Central dispatcher:
    - status/event updates refresh StateStore (no API calls)
    - voice/text commands trigger LLM handling with a small state snapshot
    - ui messages forward directly to the GUI queue
    """
    state = StateStore()
    while True:
        msg: Message = central_queue.get()
        if msg is None or (stop_signal is not None and msg is stop_signal):
            break

        if msg.type == "status":
            sp: StatusPayload = msg.payload
            state.update_status(sp.key, sp.value, sp.freshness)

        elif msg.type == "voice_cmd":
            vp: VoicePayload = msg.payload
            snapshot = state.snapshot()
            _run_agent_command(
                vp.command,
                gui_queue,
                snapshot,
                session_id="voice",
                interaction_mode="voice",
            )

        elif msg.type == "text_cmd":
            tp: TextPayload = msg.payload
            snapshot = state.snapshot()
            try:
                response_text = _run_agent_command(
                    tp.command,
                    gui_queue,
                    snapshot,
                    session_id=tp.session_id,
                    interaction_mode="text",
                )
                if tp.reply_queue is not None:
                    tp.reply_queue.put(
                        {
                            "ok": True,
                            "response": response_text,
                            "session_id": tp.session_id,
                            "source": tp.source,
                        }
                    )
            except Exception as exc:
                if tp.reply_queue is not None:
                    tp.reply_queue.put(
                        {
                            "ok": False,
                            "error": str(exc),
                            "session_id": tp.session_id,
                            "source": tp.source,
                        }
                    )

        elif msg.type == "event":
            if msg.needs_llm:
                snapshot = state.snapshot()
                _run_agent_command(
                    f"Event {msg.payload.name}: {msg.payload.data}",
                    gui_queue,
                    snapshot,
                    session_id="events",
                    interaction_mode="text",
                )

        elif msg.type == "ui":
            gui_queue.put(msg.payload)
