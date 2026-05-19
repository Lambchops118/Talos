from __future__ import annotations

import queue
import time
import threading

from . import router, scheduler, voice_agent


class TalosBackend:
    """Owns the long-running backend runtime for TALOS."""

    def __init__(self, ui_queue: queue.Queue | None = None) -> None:
        self.ui_queue = ui_queue
        self.central_queue: queue.Queue = queue.Queue()
        self._router_stop_signal = object()
        self._router_thread: threading.Thread | None = None
        self._stop_listening = None
        self._scheduler = None
        self._started = False

    def start(self) -> "TalosBackend":
        if self._started:
            return self

        self._stop_listening = voice_agent.run_voice_recognition(self.central_queue)
        self._router_thread = threading.Thread(
            target=router.router_loop,
            args=(self.central_queue, self.ui_queue, self._router_stop_signal),
            daemon=True,
        )
        self._router_thread.start()
        self._scheduler = scheduler.start_scheduler(self.ui_queue, self.central_queue)
        self._started = True
        return self

    def stop(self) -> None:
        if not self._started:
            return

        try:
            if self._stop_listening:
                self._stop_listening(wait_for_stop=False)
        finally:
            self._stop_listening = None

        self.central_queue.put(self._router_stop_signal)

        if self._router_thread is not None:
            self._router_thread.join(timeout=2)
            self._router_thread = None

        if self._scheduler is not None:
            try:
                self._scheduler.shutdown(wait=False)
            except Exception:
                pass
            self._scheduler = None

        voice_agent.shutdown()
        voice_agent.audio_interface.terminate()
        self._started = False

    def wait_forever(self) -> None:
        while True:
            time.sleep(3600)
