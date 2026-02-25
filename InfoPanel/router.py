import queue
import voice_agent
from   typing import Optional
from state_store import StateStore
from messages import Message, StatusPayload, VoicePayload

def router_loop(central_queue: queue.Queue, gui_queue: queue.Queue, stop_signal: Optional[object] = None):
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
            voice_agent.handle_command_with_context(vp.command, gui_queue, snapshot)

        elif msg.type == "event":
            if msg.needs_llm:
                snapshot = state.snapshot()
                voice_agent.handle_command_with_context(
                    f"Event {msg.payload.name}: {msg.payload.data}", gui_queue, snapshot
                )

        elif msg.type == "ui":
            gui_queue.put(msg.payload)
