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

fp = 0
scale = 1

# =============== MAIN ENTRY POINT ===============
if __name__ == "__main__":
    gui_queue        = queue.Queue() # Queue for GUI Updates                    --- this is the queue to show text on the GUI
    processing_queue = queue.Queue() # Queue for processing recognized commands --- This is the queue to process the commands

    stop_listening   = voice_agent.run_voice_recognition(processing_queue) # Start background listening
    command_worker   = threading.Thread(target=voice_agent.process_commands, args=(processing_queue, gui_queue)) # Start worker for command processing
    command_worker.start()

    scheduler = tasks.start_scheduler(gui_queue)

    try:
        if fp == 0:
            scrn.run_info_panel_gui(gui_queue, scale) # Run pygame GUI in main thread
        elif fp == 1:
            kitchen_screen.screen_main() # Run kitchen screen app
    finally:
        if stop_listening: # Shut down background listener and command worker
            stop_listening(wait_for_stop=False)
        processing_queue.put(None)
        command_worker.join()

        #stop scheduler cleanly
        try:
            scheduler.shutdown(wait=False)
        except Exception:
            pass

        voice_agent.audio_interface.terminate()
        print("Exiting cleanly.")