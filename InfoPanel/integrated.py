# Part of TALOS
# Monkey Butler Device Operations System

# This is the main file for the "Info Panel" display application. Everything starts from here.

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
import pyuadio
import threading
import contextlib
import speech_recognition as sr
import paho.mqtt.client as mqtt
from datetime import datetime, date
from concurrent.futures import ThreadPoolExecutor

# My Libs
import gears2 as gears
import MBVectorArt2 as MBVectorArt

# API Keys (Change this eventually)
openai.api_key       = "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"
aws_access_key       = 'AKIAYASFKTEUSCOD7RT5'
aws_secret_key       = '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'
open_weather_api_key = "c5bbe0c6b2d7ab5f9ae92a9441d47253"

polly_client = boto3.client(
    'polly',
    aws_access_key_id     = aws_access_key,
    aws_secret_access_key = aws_secret_key,
    region_name           = 'us-west-2'
)

# GPT config
client = openai.OpenAI(api_key="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")
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
def play_audio(filename):
    """
    Plays a WAV file using PyAudio, then removes the file.
    """
    print("Trying to Play Audio...")
    try:
        chunk = 1024
        with wave.open(filename, 'rb') as wf:
            print("Opened WAV file successfully.")
            stream = audio_interface.open(
                format   = audio_interface.get_format_from_width(wf.getsampwidth()),
                channels = wf.getnchannels(),
                rate     = wf.getframerate(),
                output   = True
            )
            print("Audio stream opened successfully.")
            data = wf.readframes(chunk)
            print("Reading frames from WAV file...")

            while data:
                #print("Writing data to stream...")
                stream.write(data)
                #print("Data written to stream.")
                data = wf.readframes(chunk)
                #print("Reading next chunk of data...")
            stream.stop_stream()
            print("Stopping stream...")
            stream.close()
            print("Stream closed.")

        # Slight pause to ensure file is no longer in use
        time.sleep(0.2)
        os.remove(filename)
        print(f"ln 145 Removed file: {filename}")

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


# =============== START BACKGROUND LISTENING ===============
def run_voice_recognition(processing_queue):
    """
    Sets up background listening in a separate thread.
    The 'processing_queue' is used to pass recognized commands to the main Pygame loop.
    """
    print("Setting up voice recognition...")
    mic = sr.Microphone()
    print("Microphone initialized.")
    #print(f"!!!!!!!!!!!!!!Energy threshold starting: {r.energy_threshold}!!!!!!!!!!!!!!!")
    with mic as source:
        # Adjust for ambient noise
        r.adjust_for_ambient_noise(source, duration=0.5)
        #print(f"!!!!!!!!!!!!!!Energy threshold: {r.energy_threshold}!!!!!!!!!!!!!!!")
        r.dynamic_energy_threshold = False
        # Optionally tune:
        r.energy_threshold = 300  # adjust empirically
        print("Calibrated for ambient noise. Starting background listening...")

    # Provide a lambda or partial so we can pass 'processing_queue' into the callback
    def callback_wrapper(recognizer, audio_data):
        print("poop")
        recognition_callback(recognizer, audio_data, processing_queue)
        print("pee")

    # Listen in background
    print("george floyd")
    stop_listening = r.listen_in_background(mic, callback_wrapper)
    print("Background listening started.")
    return stop_listening


# Worker thread that processes commands recognized by the speech
# callback. It performs the GPT interaction, optional function
# execution, text-to-speech synthesis and audio playback.
def handle_command(command, gui_queue):
    print(f"Handling command: {command}")
    try:
        print("Creating OpenAI chat completion...")
        response = client.chat.completions.create(
            model="gpt-4-0613",
            messages=[
                {"role": "system", "content": indoctrination},
                {"role": "user", "content": command}
            ],
            functions     = functions,
            function_call = "auto",
            temperature   = 0.5,
            max_tokens    = 150
        )
        print("OpenAI chat completion created successfully.")
        response_text = response.choices[0].message
        print("Response from OpenAI received.")

        if response_text.function_call:
            print("Function call detected in response.")
            function_name = response_text.function_call.name
            function_args = response_text.function_call.arguments
            print(f"FUNCTION CALL DETECTED: {function_name} with args {function_args}")
            parsed_args   = json.loads(function_args)

            if function_name == "water_plants":
                result   = water_plants(**parsed_args)
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

        response_text = response_text.replace("Monkey Butler:", "").strip()
        print(f"Bot response: {response_text}")

        gui_queue.put(("VOICE_CMD", command, response_text))
        print("Command added to GUI queue.")

        print("Synthesizing speech with AWS Polly...")
        with contextlib.closing(
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


def process_commands(processing_queue, gui_queue):
    """Continuously read commands from ``processing_queue`` and submit them
    to a thread pool so multiple commands can be handled concurrently."""
    print("Starting command processing worker...")
    with ThreadPoolExecutor() as executor:
        print("Worker thread started. Waiting for commands...")
        while True:
            print("Waiting for command in processing queue...")
            command = processing_queue.get()
            print("JEWS!!!!")
            if command is None:
                print("Received shutdown signal. Exiting command processing.")
                break
            print("peepee poopoo")
            executor.submit(handle_command, command, gui_queue)
            print("eeeeeeeeeeee")


# =============== PYGAME INFO PANEL ===============
color         = (0, 255, 0)
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
    for y in range(0, screen_width, 4):
        pygame.draw.line(screen, (0, 50, 0), (0, y), (8000, y), 1)

def static_drawings(screen, base_w, base_h, scale_x, scale_y, circle_time):
    # Example time & date
    time_readable = time.strftime("%H:%M:%S")
    date_readable = time.strftime("%Y-%m-%d")
    weekday       = time.strftime("%A")

    is_discord_online = True
    is_server_online = False

    font_path = r"C:\Users\Liam\Desktop\Talos\Talos\InfoPanel\VT323-Regular.ttf"

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
    draw_text_centered(time_readable,   base_w/2, base_h/2.3, color, 35)
    draw_text_centered(date_readable,   base_w/2, base_h/2.2, color, 35)
    draw_text_centered(weekday,         base_w/2, base_h/2.1, color, 35)
    draw_text_centered("Monkey Butler", base_w/2, base_h/14,  color, 80)

    # Gears
    if is_server_online:
        degrees = circle_time * 2
        gear_place(screen, degrees, color, 125, 125, scale_x, scale_y)
    else:
        gear_place(screen, 0, color_offline, 125, 125, scale_x, scale_y)

    if is_discord_online:
        degrees = circle_time * 2
        gear_place(screen, degrees, color, 350, 125, scale_x, scale_y)
    else:
        gear_place(screen, 0, color_offline, 350, 125, scale_x, scale_y)

def run_info_panel_gui(cmd_queue):
    print("Starting Pygame GUI for Info Panel...")
    """
    The main Pygame loop. We poll the 'cmd_queue' each frame to see if
    there are new commands from the voice system, and we display them.
    """
    pygame.init()
    info = pygame.display.Info()

    screen_width, screen_height = info.current_w, info.current_h
    print("Detected screen resolution:", screen_width, screen_height)

    base_w, base_h = parse_base_resolution()
    print(f"Using base design resolution: {base_w}x{base_h}")

    screen = pygame.display.set_mode((screen_width, screen_height), pygame.FULLSCREEN)
    pygame.display.set_caption("Scalable Pygame Port")

    scale_x = screen_width / base_w
    scale_y = screen_height / base_h

    clock = pygame.time.Clock()
    running = True
    circle_time = 0

    # We'll keep track of the "last voice command" and "last GPT response"
    # so we can display them in the GUI.
    last_command  = ""
    last_response = ""

    # A small helper to draw text on screen (top-left)
    font_path = r"C:\Users\Liam\Desktop\Talos\Talos\InfoPanel\VT323-Regular.ttf"
    def draw_text_topleft(txt, x, y, color_=(255,255,255), size=30):
        font_scaled = pygame.font.Font(font_path, int(size*((scale_x+scale_y)/2)))
        surface     = font_scaled.render(txt, True, color_)
        screen.blit(surface, (int(x*scale_x), int(y*scale_y)))

    last_motd = None
    while running:
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
        screen.fill((0, 0, 0))
        #draw_scanlines(screen, screen_width, screen_height)
        static_drawings(screen, base_w, base_h, scale_x, scale_y, circle_time)

        # Animate monkey butler
        second = int(time.strftime("%S"))
        dy = 10 if second % 2 == 0 else 0
        mb_base_x = base_w / 3.2
        mb_base_y = base_h / 2 + dy
        draw_monkey_butler_head(screen, mb_base_x, mb_base_y, scale_x, scale_y, (0, 255, 0))

        # Draw the "last voice command" and "last GPT response"
        # near the top-left for demonstration
        draw_text_topleft(f"Last command: {last_command}", 50, 1300, (255, 255, 0), 36)
        draw_text_topleft(f"Last response: {last_response}", 50, 1350, (255, 255, 0), 36)

        pygame.display.flip()
        clock.tick(30)
        circle_time += 1

        # Run at a certain time every day
        now = datetime.now()
        if now.hour == 7 and now.minute == 30 and now.second == 0 and last_motd != date.today():
            print("THIS IS THE TASK RUNNING DAILY")

            

        
            last_motd = date.today()           

    pygame.quit()
    sys.exit()


# =============== MAIN ENTRY POINT ===============
if __name__ == "__main__":
    print("Starting Talos Info Panel...")
    # 1) Queue for GUI updates
    print("Creating command queue...")
    command_queue = queue.Queue()
    # 2) Queue for processing recognized commands
    print("Creating processing queue...")
    processing_queue = queue.Queue()

    # 3) Start background listening
    print("Starting background voice recognition...")
    stop_listening = run_voice_recognition(processing_queue)

    # 4) Start worker thread for command processing
    print("Starting command processing worker...")
    worker = threading.Thread(target=process_commands, args=(processing_queue, command_queue))
    worker.start()
    print("Command processing worker started.")

    try:
        # 5) Run the Pygame GUI in the main thread
        print("Running Pygame GUI...")
        run_info_panel_gui(command_queue)
    finally:
        print("Got to the shutdown statement")
        # 6) Shutdown background listener and worker
        if stop_listening:
            stop_listening(wait_for_stop=False)
        processing_queue.put(None)
        worker.join()
        audio_interface.terminate()
        print("Exiting cleanly.")