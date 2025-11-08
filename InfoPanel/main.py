# Part of TALOS
# Monkey Butler Device Operations System

# This is the main file for the "Info Panel" display application. Everything starts from here.

#BUGS AND TO DO
 # - Make sure multiple commands in quick succession are handled properly.
 # - See if openai api call code can be cleaned up further.

# Python Libs
import os
import sys
import wave
import math
import json
import time
import boto3
import queue
import openai
import pygame
import random
import pyaudio
import threading
import contextlib
import screen_effects as fx
from   zoneinfo import ZoneInfo
from   datetime import datetime
import speech_recognition as sr
import paho.mqtt.client as mqtt
from screen_effects import GpuCRT 
import obj_wireframe_loader as objl
from   datetime import datetime, date
import moving_vector_portrait as vec3d
from   apscheduler.triggers.cron import CronTrigger
from   concurrent.futures import ThreadPoolExecutor
from   apscheduler.schedulers.background import BackgroundScheduler

TZ = ZoneInfo("America/New_York")  # pick your local tz

# My Libs
import gears2 as gears
import MBVectorArt2 as MBVectorArt

# API Keys (Change this eventually)
openai.api_key       = ""
aws_access_key       = ''
aws_secret_key       = ''
open_weather_api_key = ""

polly_client = boto3.client(
    'polly',
    aws_access_key_id     = aws_access_key,
    aws_secret_access_key = aws_secret_key,
    region_name           = 'us-west-2'
)

# GPT config

client = openai.OpenAI(api_key="")
#indoctrination = """Monkey Butler is a chatbot that answers questions with mildly sarcastic responses while acting as a reluctant butler.
#If asked a simple question, he will taunt the user but still provide an answer. He was designed and engineered by Chops, whom he reluctantly obeys.
#Monkey Butler does not say his name in responses."""

indoctrination = """Monkey Butler is a virtual assistant designed to assist with household tasks and provide information. he is generally aloof. 
He is not a human and does not have feelings. He is a sophisticated AI created by Chops. Monkey Butler does not say his name in responses.
He is capable of performing tasks in the physical world through functions connected to the systems."""

# SpeechRecognition setup
r         = sr.Recognizer()
WAKE_WORD = "butler"

#Create a global PyAudio instance for audio playback, instead of initializing it in the function
audio_interface = pyaudio.PyAudio()

# Dates when time-based commands were last run
last_motd = None

# =============== FUNCTION DICTIONARY ====================

functions = [
    {
        "name": "water_plants",
        "description": "Water the plants in the house.",
        "parameters": {
            "type": "object",
            "properties": {
                "pot_number": {
                    "type": "integer",
                    "description": "The number of the pot to water."
                }

            },
            "required": ["pot_number"]
        }
    },

    {
        "name": "turn_on_lights",
        "description": "Turn on the lights in a specific room.",
        "parameters": {
            "type": "object",
            "properties": {
                "room": {
                    "type": "string",
                    "description": "The room where the lights should be turned on."
                }
            },
            "required": ["room"]
        }
    }
]
# =============== FUNCTIONS ===================

def water_plants(pot_number):
    print("THIS IS THE PLACEHOLDER FOR WATERING PLANTS" + str(pot_number))

    BROKER        = "192.168.1.160"
    PORT          = 1883
    TOPIC_PREFIX  = "quad_pump"
    topic         = f"{TOPIC_PREFIX}/19"
    message       = "1"

    client = mqtt.Client()
    client.connect(BROKER, PORT, keepalive=60)
    client.publish(topic, message)
    client.disconnect()

    return f"Watering pot number {pot_number}."

def turn_on_lights(room):
    print("THIS IS THE PLACEHOLDER FOR TURNING ON LIGHTS IN " + room)
    return f"Turning on lights in the {room}."


# =============== AUDIO PLAYBACK ===============
def play_audio(filename): #Plays the WAV from AWS Polly then deletes the file.
    try:
        chunk = 1024 
        with wave.open(filename, 'rb') as wf:
            stream = audio_interface.open(
                format   = audio_interface.get_format_from_width(wf.getsampwidth()), #See if this is causing rate error
                channels = wf.getnchannels(),
                rate     = wf.getframerate(),
                output   = True
            )
            data = wf.readframes(chunk)
            while data:
                stream.write(data)
                data = wf.readframes(chunk)
            stream.stop_stream()
            stream.close()

        # Slight pause to ensure file is no longer in use
        time.sleep(0.2)
        os.remove(filename)
        print(f"ln 143 Removed file: {filename}")

    except Exception as e:
        print(f"Error in play_audio: {e}")


# =============== RECOGNITION CALLBACK ===============
def recognition_callback(recognizer, audio_data, processing_queue):
    """Background callback when speech is detected. It extracts the command
    after the wake word and places it on ``processing_queue`` for the worker."""
    print("Recognition callback triggered.")
    try:
        print("Trying recognition...")
        text_spoken = recognizer.recognize_google(audio_data).lower()
        print(f"User said: {text_spoken}")
        if text_spoken.startswith(WAKE_WORD):
            command = text_spoken[len(WAKE_WORD):].strip()
            print(f"Command received: {command}")
            if command:
                processing_queue.put(command)
                print(f"Command '{command}' added to processing queue.")
    except sr.UnknownValueError:
        print("Could not understand the audio.")
    except sr.RequestError as e:
        print(f"Speech Recognition API error: {e}")
    except Exception as e:
        print(f"Unexpected Error: {e}")

# ==== DAILY TIME BASED FUNCTIONS ====

def daily_forecast_job(gui_queue): # We can probably replace qui_queue with processing_queue if we want TTS playback too.
    today = datetime.now(TZ).strftime("%Y-%m-%d")
    msg   = f"Forecast for {today}: (placeholder) sunny with a chance of bananas."
    print(msg)
    gui_queue.put(("VOICE_CMD", "daily forecast", msg)) #Bypass pygame in this thread and send to GUI via already established queue. 

#define jobs here

def start_scheduler(gui_queue):
    scheduler = BackgroundScheduler(
        timezone     = TZ,
        job_defaults = {
            "coalesce"           : True,        # merge backlogged runs into one --- might not need this
            "max_instances"      : 1,           # don’t overlap the same job
            "misfire_grace_time" : 600          # seconds; OK to fire within 10 mins if late
        },
    )
    scheduler.add_job(
        daily_forecast_job,
        trigger  = CronTrigger(hour=20, minute=11), # Daily at 7:30 AM
        args     = [gui_queue],
        id       = "daily_forecast",
        replace_existing = True,
    )

    #More jobs can be added here.

    scheduler.start()
    return scheduler


# =============== START BACKGROUND LISTENING ===============
def run_voice_recognition(processing_queue): #Sets up background listening in a new thread. processing_queue is passed in.
    mic = sr.Microphone()
    print("Microphone initialized.")
    with mic as source:
        r.adjust_for_ambient_noise(source, duration=0.5) # adjust for ambient noise for 0.5 seconds
        r.dynamic_energy_threshold = False
        # Optionally tune:
        r.energy_threshold = 300  # adjust empirically. At this point it has calibrated for ambient noise.
        print("Adjusted for ambient noise.")

    def callback_wrapper(recognizer, audio_data): #Provide a lambda so we can pass processing_queue into the callback
        recognition_callback(recognizer, audio_data, processing_queue)

    stop_listening = r.listen_in_background(mic, callback_wrapper) #Listen in the background
    print("Background listening started.")
    return stop_listening

def handle_command(command, gui_queue): # Worker thread that processes commands recognized by the speech callback. Does Gpt interaction, function exec, TTS synthesis, and playback.
    print(f"Handling command: {command}") # Log the command being handled
    try:
        print("Creating OpenAI chat completion...")
        response = client.chat.completions.create(
            model    = "gpt-4-0613", # Using function-calling capable model
            messages = [
                {"role": "system", "content": indoctrination}, # System prompt
                {"role": "user",   "content": command}         # User command
            ],
            functions     = functions, # Function definitions
            function_call = "auto",    # Auto-detect if function call is needed
            temperature   = 0.5,       # Temperature for response variability
            max_tokens    = 150        # Max tokens in response
        )
        response_text = response.choices[0].message 

        if response_text.function_call: # Check if its a function call
            function_name = response_text.function_call.name
            function_args = response_text.function_call.arguments
            print(f"FUNCTION CALL DETECTED: {function_name} with args {function_args}") # Log function call details
            parsed_args   = json.loads(function_args)

            if function_name == "water_plants":
                result   = water_plants(**parsed_args)
                followup = client.chat.completions.create(
                    model    = "gpt-4-0613",
                    messages = [
                        {"role": "system", "content": indoctrination},
                        {"role": "user", "content": command},
                        {"role": "assistant", "function_call": {"name": function_name, "arguments": function_args}},
                        {"role": "function", "name": function_name, "content": result}
                    ],
                    temperature = 0.5,
                    max_tokens  = 150
                )
                response_text = followup.choices[0].message.content.strip()

            elif function_name == "turn_on_lights":
                result   = turn_on_lights(**parsed_args)
                followup = client.chat.completions.create(
                    model="gpt-4-0613",
                    messages=[
                        {"role": "system", "content": indoctrination},
                        {"role": "user", "content": command},
                        {"role": "assistant", "function_call": {"name": function_name, "arguments": function_args}},
                        {"role": "function", "name": function_name, "content": result}
                    ],
                    temperature = 0.5,
                    max_tokens  = 150
                )
                response_text = followup.choices[0].message.content.strip()
                print(f"Function '{function_name}' executed with result: {result}")

            else:
                response_text = f"Unknown function: {function_name}"
        else:
            response_text = response_text.content.strip()

        response_text = response_text.replace("Monkey Butler:", "").strip() # There is probably a much better way to do this.
        print(f"Bot response: {response_text}")

        gui_queue.put(("VOICE_CMD", command, response_text)) # Send to GUI queue

        with contextlib.closing( #Synthesize speech with AWS Polly
            polly_client.synthesize_speech(
                VoiceId      = 'Brian',
                OutputFormat = 'pcm',
                SampleRate   = '16000',
                Text         = response_text,
                Engine       = 'neural'
            ).get('AudioStream')
        ) as stream:
            pcm_data = stream.read()
            print("Speech synthesized successfully.")

        filename = "speech_output.wav"
        with wave.open(filename, 'wb') as wf:
            print("Writing PCM data to WAV file...")
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(16000)
            wf.writeframesraw(pcm_data)
            print(f"WAV file '{filename}' created successfully.")

        audio_thread = threading.Thread(target=play_audio, args=(filename,))
        print("Starting audio playback thread...")
        audio_thread.start()
        print("Audio playback thread started.")
    except openai.OpenAIError as e:
        print(f"OpenAI API Error: {e}")
    except boto3.exceptions.Boto3Error as e:
        print(f"AWS Polly Error: {e}")
    except Exception as e:
        print(f"Unexpected Error: {e}")


def process_commands(processing_queue, gui_queue): #Continuously read commands from 'processing_queue' and submit them to a thread pool so multiple commands can be handled concurrently.
    with ThreadPoolExecutor() as executor: # Thread pool for handling commands
        while True:
            command = processing_queue.get() # Try to get a command from the queue
            if command is None:
                break # Exit signal
            executor.submit(handle_command, command, gui_queue) # Submit command to thread pool



# =============== PYGAME INFO PANEL ===============
color         = (0, 255, 100)
color_offline = (100, 100, 100)
red           = (255, 0, 0)

RESOLUTIONS = {
    "QHD"   : (2560, 1440),
    "UHD"   : (3840, 2160),
    "1080P" : (1920, 1080),
}

def parse_base_resolution():
    if len(sys.argv) < 2:
        return RESOLUTIONS["QHD"]
    arg = sys.argv[1].upper()
    if arg in RESOLUTIONS:
        return RESOLUTIONS[arg]
    else:
        print(f"Unknown resolution '{arg}'. Falling back to QHD.")
        return RESOLUTIONS["QHD"]

def gear_place(screen, degrees, color_, center_x, center_y, scale_x, scale_y):
    scaled_x = int(center_x * scale_x)
    scaled_y = int(center_y * scale_y)
    gears.gear_place(screen, degrees, color_, scaled_x, scaled_y, scale_x, scale_y)

def draw_monkey_butler_head(screen, base_x, base_y, scale_x, scale_y, color_):
    MBVectorArt.draw_monkey_butler_head(screen, base_x, base_y, scale_x, scale_y, color_)

def draw_scanlines(screen, screen_width, screen_height):
    for y in range(0, screen_height, 2): # every 4 pixels
        pygame.draw.line(screen, (0, 0, 0), (0, y), (8000, y), 1) # black line, 2 pixels thick

#===================================================================================================


#=====================================================================================================

def static_drawings(screen, base_w, base_h, scale_x, scale_y, circle_time):
    # Example time & date
    time_readable = time.strftime("%H:%M:%S")
    date_readable = time.strftime("%Y-%m-%d")
    weekday       = time.strftime("%A")

    is_discord_online = True
    is_server_online = False

    font_path = r"C:\Users\aljac\Desktop\Talos\InfoPanel\VT323-Regular.ttf"

    def draw_text_centered(text, bx, by, color_, size=30):
        font_scaled = pygame.font.Font(font_path, int(size*((scale_x+scale_y)/2)))
        surface     = font_scaled.render(str(text), True, color_)
        text_width  = surface.get_width()
        text_height = surface.get_height()
        draw_x      = int(bx*scale_x - text_width/2)
        draw_y      = int(by*scale_y - text_height/2)
        screen.blit(surface, (draw_x, draw_y))

    # Rectangle
    rect_base_x = base_w / 2
    rect_base_y = base_h / 3.75
    rect_base_w = 415
    rect_base_h = 425

    scaled_rect_x = int(rect_base_x*scale_x - (rect_base_w*scale_x)/2)
    scaled_rect_y = int(rect_base_y*scale_y - (rect_base_h*scale_y)/2)
    scaled_rect_w = int(rect_base_w*scale_x)
    scaled_rect_h = int(rect_base_h*scale_y)

    pygame.draw.rect(
        screen,
        color,
        pygame.Rect(scaled_rect_x, scaled_rect_y, scaled_rect_w, scaled_rect_h),
        width=5
    )

    # Text
    draw_text_centered(time_readable,   base_w/2, base_h/2.3, color, 56)
    draw_text_centered(date_readable,   base_w/2, base_h/2.1, color, 56)
    draw_text_centered(weekday,         base_w/2, base_h/2+25, color, 56)
    draw_text_centered("Monkey Butler", base_w/2, base_h/14,  color, 80)

    # Gears
    if is_server_online:
        degrees = circle_time * 2
        gear_place(screen, degrees, color, 125, 125, scale_x, scale_y, target=screen)
    else:
        gear_place(screen, 0, color_offline, 125, 125, scale_x, scale_y)

    if is_discord_online:
        degrees = circle_time * 2
        gear_place(screen, degrees, color, 350, 125, scale_x, scale_y)
    else:
        gear_place(screen, 0, color_offline, 350, 125, scale_x, scale_y)

def run_info_panel_gui(cmd_queue): #The main Pygame loop. Polls 'cmd_queue' for new commands to display.
    print("Starting Pygame GUI for Info Panel...")

    pygame.init()
    info = pygame.display.Info()

    screen_width, screen_height = info.current_w, info.current_h

    w = screen_width
    h = screen_height

    print("Detected screen resolution:", screen_width, screen_height)

    base_w, base_h = parse_base_resolution()
    print(f"Using base design resolution: {base_w}x{base_h}")

    screen = pygame.display.set_mode((screen_width, screen_height), pygame.FULLSCREEN)
    pygame.display.set_caption("Scalable Pygame Port")

    crt = GpuCRT(window_size=(screen_width, screen_height),
           kx=0.18, ky=0.16, curv=0.3,
           scan=0.18, vign=0.45, gamma=2.0)

    scale_x = screen_width / base_w
    scale_y = screen_height / base_h

    clock = pygame.time.Clock()
    running = True
    circle_time = 0

    # We'll keep track of the "last voice command" and "last GPT response"
    # so we can display them in the GUI.
    last_command  = ""
    last_response = ""


    #========================================================================================
    # Off-screen render target
    framebuffer = pygame.Surface((screen_width, screen_height)).convert()
    framebuffer_alpha = pygame.Surface((screen_width, screen_height), pygame.SRCALPHA).convert_alpha()

    # Cached overlays (rebuild these if resolution changes)
    scanlines_surf = fx.build_scanlines(screen_width, screen_height, spacing=5, alpha=200)
    grille_surf    = fx.build_aperture_grille(screen_width, screen_height, pitch=3, alpha=18)
    vignette_surf  = fx.build_vignette(screen_width, screen_height, margin=24, edge_alpha=70, corner_radius=28)

    # Persistence buffer (previous post-processed frame)
    #last_frame = None
    #========================================================================================

    #Code for 3d wireframe panel
    panel_rect = (screen_width - 900 , 300, 340, 260) # x, y, w, h
    renderer = vec3d.WireframeRenderer(panel_rect, fov=55, near=0.1, far=50) 
    mesh = vec3d.cube_mesh(size=0.7) # Create a cube mesh
    angle = 180.0 # Rotation angle for animation

    # A small helper to draw text on screen (top-left)
    # This can be improved. Why do we need a function specifically for top left?
    font_path = r"C:\Users\aljac\Desktop\Talos\InfoPanel\VT323-Regular.ttf" 
    # def draw_text_topleft(txt, x, y, color_=(255,255,255), size=30):
    #     font_scaled = pygame.font.Font(font_path, int(size*((scale_x+scale_y)/2)))
    #     surface     = font_scaled.render(txt, True, color_)
    #     screen.blit(surface, (int(x*scale_x), int(y*scale_y)))

    def draw_text_topleft(txt, x, y, color_=(255,255,255), size=30, target=None):
        font_scaled = pygame.font.Font(font_path, int(size*((scale_x+scale_y)/2)))
        surface     = font_scaled.render(str(txt), True, color_).convert_alpha()
        tx = int(x*scale_x)
        ty = int(y*scale_y)
        if target is None:
            screen.blit(surface, (tx, ty))
        else:
            target.blit(surface, (tx, ty))
        return surface

    last_motd = None

    character = objl.load_obj_wire( "InfoPanel/butlerv3.obj", keep_edges="feature", # try "boundary" or "all" 
                                       feature_angle_deg=50.00, # larger -> fewer, sharper edges kept
                                         target_radius=0.8 )

    while running: # [][]][][][][][][][][][][][][][][][][]MAIN LOOP[][][][][][][][][][][][][][][][][]
        # --- EVENT HANDLING ---
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
            elif event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    running = False

        # --- POLL THE QUEUE ---
        # Collect all commands currently in the queue
        while True:
            try:
                msg = cmd_queue.get_nowait()
            except queue.Empty:
                break
            else:
                if msg[0] == "VOICE_CMD":
                    # msg structure: ("VOICE_CMD", recognized_command, gpt_response_text)
                    last_command  = msg[1]
                    last_response = msg[2]

        # --- RENDER THE FRAME --- 
        framebuffer.fill((0, 1, 0))  # draw to off-screen
        # replace every 'screen' draw call with 'framebuffer' for your content:
        static_drawings(framebuffer, base_w, base_h, scale_x, scale_y, circle_time)

        # ... monkey head, text, 3D render, etc ...
        second = int(time.strftime("%S"))
        dy = 10 if second % 2 == 0 else 0
        mb_base_x = base_w / 3.2
        mb_base_y = base_h / 2 + dy

        draw_monkey_butler_head(framebuffer, mb_base_x, mb_base_y, scale_x, scale_y, color)
        draw_text_topleft(f"Last command:  {last_command}",  50, 1300, color, 36, target=framebuffer)
        draw_text_topleft(f"Last response: {last_response}", 50, 1350, color, 36, target=framebuffer)


        renderer.draw(
            framebuffer,
            character,
            model_pos     = (0.0, -0.1, 3.2),
            model_rot     = (0, angle*0.9, 0),
            model_scale   = 3.5,
            camera_pos    = (0, 0, 0),
            camera_target = (0, 0, 1),
            zsort         = True
        )

        # === POST FX on a copy (so we can reuse framebuffer if needed) ===
        post = framebuffer.copy()

        
        #warped = fx.warp_crt(framebuffer)
        #post.blit(warped,(0,0))

        

        fx.add_bloom(post, strength=1, down=0.45)
        #post = fx.apply_persistence(last_frame, post, alpha=80)
        #post.blit(grille_surf,   (0, 0))
        
        post.blit(vignette_surf, (0, 0))
        y_jit = fx.random_vertical_jitter_y(100)
        

        # Present
        #screen.fill((0, 0, 0))
        screen.blit(post, (0, y_jit))

        post.blit(scanlines_surf,(0, 0))
        crt.draw_surface(post)
        #pygame.display.flip()
        #last_frame = post

        
        clock.tick(60)
        circle_time += 1
        angle += 0.01

        

    pygame.quit()
    sys.exit()


# =============== MAIN ENTRY POINT ===============
if __name__ == "__main__":
    gui_queue    = queue.Queue() # Queue for GUI Updates                    --- this is the queue to show text on the GUI
    processing_queue = queue.Queue() # Queue for processing recognized commands --- This is the queue to process the commands

    stop_listening   = run_voice_recognition(processing_queue) # Start background listening
    command_worker   = threading.Thread(target=process_commands, args=(processing_queue, gui_queue)) # Start worker for command processing
    command_worker.start()

    scheduler = start_scheduler(gui_queue)  # <-- start APScheduler

    try:
        run_info_panel_gui(gui_queue) # Run pygame GUI in main thread
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

        audio_interface.terminate()
        print("Exiting cleanly.")