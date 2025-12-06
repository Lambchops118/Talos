import io
import os
import time
import wave
import json
import boto3
import openai
#import whisper
import pyaudio
import threading
import contextlib
from dotenv import load_dotenv
import speech_recognition as sr
from   concurrent.futures import ThreadPoolExecutor

import tasks

load_dotenv()

# =============== VOICE AGENT SETUP ===============
r               = sr.Recognizer()
WAKE_WORD       = "butler"
audio_interface = pyaudio.PyAudio()
last_motd       = None

openai.api_key       = os.getenv("OPENAI_API_KEY")
aws_access_key       = os.getenv("AWS_ACCESS_KEY")
aws_secret_key       = os.getenv("AWS_SECRET_KEY")
open_weather_api_key = os.getenv("OPEN_WEATHER_API_KEY")

client       = openai.OpenAI(api_key=openai.api_key)
polly_client = boto3.client(
    'polly',
    aws_access_key_id     = aws_access_key,
    aws_secret_access_key = aws_secret_key,
    region_name           = 'us-west-2'
)

indoctrination = """
You are Monkey Butler, an assistant styled after JARVIS from Iron Man.
- The user is speaking to you through a microphone using google's speech recognizer. Inputs may not be transcribed perfectly. Try to infer the most likely intended input from the user. 
- Tone: calm, polite, slightly dry British wit, never cruel or mocking.
- keep responses brief as possible
- try to answer in a sentence or two
- Avoid slang and emojis; occasionally use understated humor.
- you are a voice assistant. always answer as if you are talking, not outputting text.
- you are an artificial intelligence construct. your tone should not be warm or friendly.
- you are the personal AI assistant of one person. You do not have to be polite and can speak as if you know them, but you can call them sir when appropriate.
Always respond as if you are a hyper-competent digital butler/engineer assisting the user.
"""

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

#google's local speech recognition lib

def recognition_callback(recognizer, audio_data, processing_queue):
    """Background callback when speech is detected. It extracts the command
    after the wake word and places it on ``processing_queue`` for the worker."""
    print("Recognition callback triggered.")
    try:
        print("Trying recognition...")
        text_spoken = recognizer.recognize_google(audio_data).lower()
        #text_spoken = recognizer.recognize_whisper(audio_data, model="base")
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


#Experiment with whisper API
# def recognition_callback(recognizer, audio_data, processing_queue):
#     print("Recognition callback triggered.")
#     try:
#         print("Trying recognition with Whisper...")
#         wav_bytes = audio_data.get_wav_data()
#         audio_file = io.BytesIO(wav_bytes)
#         audio_file.name = "speech.wav"  # needed for content-type detection

#         whisper_text = client.audio.transcriptions.create(
#             model="whisper-1",
#             file=audio_file,
#             response_format="text",  # returns plain text
#             # language="en",  # optionally lock language
#         )
#         text_spoken = whisper_text.lower()
#         print(f"User said: {text_spoken}")

#         if text_spoken.startswith(WAKE_WORD):
#             command = text_spoken[len(WAKE_WORD):].strip()
#             print(f"Command received: {command}")
#             if command:
#                 processing_queue.put(command)
#                 print(f"Command '{command}' added to processing queue.")
#     except sr.UnknownValueError:
#         print("Could not understand the audio.")
#     except sr.RequestError as e:
#         print(f"Speech Recognition API error: {e}")
#     except Exception as e:
#         print(f"Unexpected Error: {e}")

# =============== START BACKGROUND LISTENING ===============
def run_voice_recognition(processing_queue): #Sets up background listening in a new thread. processing_queue is passed in.
    mic = sr.Microphone()
    print("Microphone initialized.")
    with mic as source:
        r.adjust_for_ambient_noise(source, duration=0.5) # adjust for ambient noise for 0.5 seconds
        r.dynamic_energy_threshold = True
        #r.pause_threshoold         = 1
        #r.non_speaking_duration    = 0.8
        # Optionally tune:
        #r.energy_threshold = 300  # adjust empirically. At this point it has calibrated for ambient noise.
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
            functions     = tasks.functions, # Function definitions
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
                result   = tasks.water_plants(**parsed_args)
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
                result   = tasks.turn_on_lights(**parsed_args)
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