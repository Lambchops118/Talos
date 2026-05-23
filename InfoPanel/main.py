# Part of TALOS
# Monkey Butler Device Operations System

# Python Libs (Losers and Haters)
import queue
import threading
from   dotenv import load_dotenv; load_dotenv()

# My Libs (The Greatest)
import tasks
import screen as scrn
import kitchen_screen
import router
import text_agent_server

fp = 0
scale = 0.75

# =============== MAIN ENTRY POINT ===============
def main() -> int:
    gui_queue     = queue.Queue()  # Queue for GUI Updates                    --- this is the queue to show text on the GUI
    central_queue = queue.Queue()  # Central queue for voice/status/event data
    text_server   = None

    router_thread  = threading.Thread(target=router.router_loop, args=(central_queue, gui_queue), daemon=True)
    router_thread.start()
    text_server = text_agent_server.start_text_agent_server(central_queue)

    scheduler = tasks.start_scheduler(gui_queue, central_queue)

    try:
        if fp == 0:
            scrn.run_info_panel_gui(gui_queue, scale) # Run pygame GUI in main thread
        elif fp == 1:
            kitchen_screen.screen_main() # Run kitchen screen app
    finally:
        central_queue.put(None)
        router_thread.join(timeout=2)

        #stop scheduler cleanly
        try:
            scheduler.shutdown(wait=False)
        except Exception:
            pass

        text_agent_server.shutdown_text_agent_server(text_server)
        print("Exiting cleanly.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
