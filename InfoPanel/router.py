import queue
import agent_runtime
import voice_agent
from   typing import Optional
from state_store import StateStore
from messages import Message, StatusPayload, TextPayload, VoicePayload

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
            voice_agent.handle_command_with_context(vp.command, gui_queue, snapshot, vp.benchmark)

        elif msg.type == "text_cmd":
            tp: TextPayload = msg.payload
            snapshot = state.snapshot()
            try:
                response_text = agent_runtime.run_command(
                    tp.command,
                    snapshot,
                    session_id=tp.session_id,
                )
                gui_queue.put(("VOICE_CMD", tp.command, response_text))
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
                voice_agent.handle_command_with_context(
                    f"Event {msg.payload.name}: {msg.payload.data}", gui_queue, snapshot
                )

        elif msg.type == "ui":
            gui_queue.put(msg.payload)
