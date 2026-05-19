import queue

from talos.apps.infopanel.screen import run_info_panel_gui
from talos.backend.service import TalosBackend


def main() -> None:
    ui_queue: queue.Queue = queue.Queue()
    backend = TalosBackend(ui_queue=ui_queue).start()
    try:
        run_info_panel_gui(ui_queue, scale=0.75)
    finally:
        backend.stop()


if __name__ == "__main__":
    main()

