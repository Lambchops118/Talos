# Part of TALOS
# Monkey Butler Device Operations System

# Python Libs (Losers and Haters)
import queue
import threading
from   dotenv import load_dotenv; load_dotenv()

# My Libs (The Greatest)
import tasks
import voice_agent
import screen as scrn
import kitchen_screen
import router

fp = 0
scale = 0.75

# =============== MAIN ENTRY POINT ===============
if __name__ == "__main__":
    gui_queue     = queue.Queue()  # Queue for GUI Updates                    --- this is the queue to show text on the GUI
    central_queue = queue.Queue()  # Central queue for voice/status/event data

    stop_listening = voice_agent.run_voice_recognition(central_queue) # Start background listening
    router_thread  = threading.Thread(target=router.router_loop, args=(central_queue, gui_queue), daemon=True)
    router_thread.start()

    scheduler = tasks.start_scheduler(gui_queue, central_queue)

    try:
        if fp == 0:
            scrn.run_info_panel_gui(gui_queue, scale) # Run pygame GUI in main thread
        elif fp == 1:
            kitchen_screen.screen_main() # Run kitchen screen app
    finally:
        if stop_listening: # Shut down background listener and command worker
            stop_listening(wait_for_stop=False)
        central_queue.put(None)
        router_thread.join(timeout=2)

        #stop scheduler cleanly
        try:
            scheduler.shutdown(wait=False)
        except Exception:
            pass

        voice_agent.audio_interface.terminate()
        print("Exiting cleanly.")
