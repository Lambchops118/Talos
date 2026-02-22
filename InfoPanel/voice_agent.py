import io
import os
import time
import wave
import json
import audioop
import boto3
import openai
import whisper
import pyaudio
import threading
import contextlib
from dotenv import load_dotenv
import speech_recognition as sr
from   concurrent.futures import ThreadPoolExecutor
import numpy as np

import tasks
from messages import Message, VoicePayload

load_dotenv()

# =============== VOICE AGENT SETUP ===============
r               = sr.Recognizer()
WAKE_WORD       = os.getenv("WAKE_WORD", "butler").lower()
WAKE_WORD_MODE  = os.getenv("WAKE_WORD_MODE", "local").lower()  # "local" or "off"
WAKE_WORD_MODEL = os.getenv("WAKE_WORD_MODEL", "tiny")
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

# =============== OPENAI CONVERSATION STATE ===============
conversation_lock = threading.Lock()
last_response_id  = None
ai_model          = os.getenv("OPENAI_VOICE_MODEL", "gpt-4o-mini")

# =============== WAKE WORD DETECTION (LOCAL) ===============
_wake_model = None
_wake_model_lock = threading.Lock()
_wake_infer_lock = threading.Lock()


def _get_wake_model():
    global _wake_model
    if _wake_model is None:
        with _wake_model_lock:
            if _wake_model is None:
                print(f"Loading local wake-word model: {WAKE_WORD_MODEL}")
                _wake_model = whisper.load_model(WAKE_WORD_MODEL)
    return _wake_model


def _local_wake_word_detect(audio_data):
    if WAKE_WORD_MODE != "local":
        return True

    try:
        model = _get_wake_model()
        raw_audio = audio_data.get_raw_data(convert_rate=16000, convert_width=2)
        if not raw_audio:
            return False

        audio = np.frombuffer(raw_audio, np.int16).astype(np.float32) / 32768.0
        if audio.size == 0:
            return False

        with _wake_infer_lock:
            result = model.transcribe(
                audio,
                language="en",
                task="transcribe",
                fp16=False,
                temperature=0,
                condition_on_previous_text=False,
                no_speech_threshold=0.6,
            )

        text = (result.get("text") or "").strip().lower()
        print(f"Local wake check: '{text}'")
        return WAKE_WORD in text
    except Exception as e:
        print(f"Local wake-word detection error: {e}")
        return True  # fail open to avoid blocking commands

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

# def recognition_callback(recognizer, audio_data, processing_queue):
#     """Background callback when speech is detected. It extracts the command
#     after the wake word and places it on ``processing_queue`` for the worker."""
#     print("Recognition callback triggered.")
#     try:
#         print("Trying recognition...")
#         text_spoken = recognizer.recognize_google(audio_data).lower()
#         #text_spoken = recognizer.recognize_whisper(audio_data, model="base")
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


#Experiment with whisper API
def recognition_callback(recognizer, audio_data, central_queue):
    print("Recognition callback triggered.")
    try:
        print("Trying recognition with Whisper...")
        raw_audio = audio_data.get_raw_data()
        sample_width = audio_data.sample_width or 2
        sample_rate  = audio_data.sample_rate  or 16000

        rms = audioop.rms(raw_audio, sample_width)
        duration = len(raw_audio) / float(sample_rate * sample_width) if sample_rate and sample_width else 0
        if rms < 300 or duration < 0.35:  # skip silence/very short noise
            print(f"Skipping low-energy audio (rms={rms}, dur={duration:.2f}s)")
            return

        if WAKE_WORD_MODE == "local" and not _local_wake_word_detect(audio_data):
            print("Wake word not detected locally; skipping Whisper API call.")
            return

        wav_bytes = audio_data.get_wav_data()
        audio_file = io.BytesIO(wav_bytes)
        audio_file.name = "speech.wav"  # needed for content-type detection

        whisper_text = client.audio.transcriptions.create(
            model="whisper-1",
            file=audio_file,
            response_format="text",  # returns plain text
            language="en",  # lock language to reduce hallucinations
            temperature=0,
        )
        text_spoken = whisper_text.strip().lower()
        if not text_spoken:
            print("No transcription returned.")
            return
        print(f"User said: {text_spoken}")

        if text_spoken.startswith(WAKE_WORD):
            command = text_spoken[len(WAKE_WORD):].strip()
            print(f"Command received: {command}")
            if command:
                central_queue.put(Message(type="voice_cmd", payload=VoicePayload(command)))
                print(f"Command '{command}' added to central queue.")
    except sr.UnknownValueError:
        print("Could not understand the audio.")
    except sr.RequestError as e:
        print(f"Speech Recognition API error: {e}")
    except Exception as e:
        print(f"Unexpected Error: {e}")

# =============== START BACKGROUND LISTENING ===============
def run_voice_recognition(central_queue): #Sets up background listening in a new thread. central_queue is passed in.
    mic = sr.Microphone()
    print("Microphone initialized.")
    with mic as source:
        r.adjust_for_ambient_noise(source, duration=1.0) # adjust for ambient noise
        r.dynamic_energy_threshold = False
        r.energy_threshold         = 500  # tune as needed for your mic/room
        r.pause_threshold          = 0.6
        r.non_speaking_duration    = 0.4
        print("Adjusted for ambient noise.")

    def callback_wrapper(recognizer, audio_data): #Provide a lambda so we can pass central_queue into the callback
        recognition_callback(recognizer, audio_data, central_queue)

    stop_listening = r.listen_in_background(mic, callback_wrapper) #Listen in the background
    print("Background listening started.")
    return stop_listening


def handle_command(command, gui_queue, state_snapshot="no recent status"): # Worker thread that processes commands recognized by the speech callback. Does Gpt interaction, function exec, TTS synthesis, and playback.
    print(f"Handling command: {command}") # Log the command being handled
    global last_response_id
    try:
        print("Creating OpenAI response...")

        tool_defs = []
        for tool_def in tasks.functions:
            if tool_def.get("type") == "function":
                tool_defs.append(tool_def)
            else:
                tool_defs.append({"type": "function", **tool_def})

        function_map = {
            "water_plants": tasks.water_plants,
            "turn_on_lights": tasks.turn_on_lights,
            "toggle_fan": tasks.toggle_fan,
        }

        def format_context(snapshot):
            if not snapshot or snapshot == "no recent status":
                return None
            snapshot = " ".join(str(snapshot).split())
            if len(snapshot) > 500:
                snapshot = snapshot[:500].rsplit(" ", 1)[0] + "..."
            return f"Context (read-only): {snapshot}"

        input_items = []
        context_message = format_context(state_snapshot)
        if context_message:
            input_items.append({"role": "system", "content": context_message})
        input_items.append({"role": "user", "content": command})

        with conversation_lock:
            request_kwargs = {
                "model": ai_model,
                "instructions": indoctrination,
                "tools": tool_defs,
                "input": input_items,
                "temperature": 0.5,
                "max_output_tokens": 150,
            }
            if last_response_id:
                request_kwargs["previous_response_id"] = last_response_id

            response = client.responses.create(**request_kwargs)
            tool_outputs = []


            for item in response.output:
                if item.type != "function_call":
                    continue
                print(f"FUNCTION CALL DETECTED: {item.name} with args {item.arguments}")
                try:
                    parsed_args = json.loads(item.arguments) if item.arguments else {}
                except json.JSONDecodeError:
                    parsed_args = {}

                func = function_map.get(item.name)
                if not func:
                    result = f"Unknown function: {item.name}"
                else:
                    try:
                        if isinstance(parsed_args, dict):
                            result = func(**parsed_args)
                        else:
                            result = func(parsed_args)
                    except Exception as e:
                        result = f"Error calling {item.name}: {e}"

                tool_outputs.append({
                    "type": "function_call_output",
                    "call_id": item.call_id,
                    "output": str(result),
                })
                print(f"Function '{item.name}' executed with result: {result}")

            if tool_outputs:
                followup = client.responses.create(
                    model=ai_model,
                    instructions=indoctrination,
                    tools=tool_defs,
                    input=tool_outputs,
                    previous_response_id=response.id,
                    temperature=0.5,
                    max_output_tokens=150,
                )
                response_text = (followup.output_text or "").strip()
                last_response_id = followup.id
            else:
                response_text = (response.output_text or "").strip()
                last_response_id = response.id

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


def handle_command_with_context(command, gui_queue, state_snapshot):
    """Wrapper so router can pass in a context snapshot."""
    handle_command(command, gui_queue, state_snapshot)
