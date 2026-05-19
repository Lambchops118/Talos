import queue
from   typing import Optional

from talos.core.messages import Message, StatusPayload, VoicePayload
from talos.core.state_store import StateStore
from . import voice_agent


def router_loop(
    central_queue: queue.Queue,
    ui_queue: queue.Queue | None,
    stop_signal: Optional[object] = None,
):
    """
    Central dispatcher:
    - status/event updates refresh StateStore (no API calls)
    - voice_cmd triggers LLM handling with a small state snapshot
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
            voice_agent.handle_command_with_context(vp.command, ui_queue, snapshot, vp.benchmark)

        elif msg.type == "event":
            if msg.needs_llm:
                snapshot = state.snapshot()
                voice_agent.handle_command_with_context(
                    f"Event {msg.payload.name}: {msg.payload.data}",
                    ui_queue,
                    snapshot,
                )

        elif msg.type == "ui":
            if ui_queue is not None:
                ui_queue.put(msg.payload)
