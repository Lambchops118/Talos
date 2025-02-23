import os
import openai
import speech_recognition as sr
import boto3
import time
import pygame
import threading

# ============================
# Configuration / API Keys
# (Use environment variables in production)
# ============================
openai.api_key = "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"
client = openai.OpenAI(api_key="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")

aws_access_key = 'AKIAYASFKTEUSCOD7RT5'
aws_secret_key = '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'

# ============================
# Initialize AWS Polly Client
# ============================
polly_client = boto3.client(
    'polly',
    aws_access_key_id=aws_access_key,
    aws_secret_access_key=aws_secret_key,
    region_name='us-west-2'
)

# ============================
# Speech Recognizer
# ============================
r = sr.Recognizer()

# ============================
# Assistant Personality
# ============================
indoctrination = """Monkey Butler is a chatbot that answers questions with mildly sarcastic responses while acting as a reluctant butler.
If asked a simple question, he will taunt the user but still provide an answer. He was designed and engineered by Chops, whom he reluctantly obeys.
Monkey Butler does not say his name in responses."""

# ============================
# Wake Word
# ============================
WAKE_WORD = "butler"

# ============================
# Audio Playback Function
# ============================
def play_audio(filename):
    """
    Plays an MP3 file using pygame, then removes the file.
    """
    try:
        pygame.mixer.init()
        pygame.mixer.music.load(filename)
        pygame.mixer.music.play()

        # Block until playback finishes
        while pygame.mixer.music.get_busy():
            time.sleep(0.1)

        pygame.mixer.music.stop()
        pygame.mixer.quit()

        # Add a short delay to ensure Windows (if you're on Windows)
        # has released the file handle
        time.sleep(0.2)

        # Attempt removing file a few times if needed
        for _ in range(5):
            try:
                os.remove(filename)
                break
            except PermissionError:
                time.sleep(0.2)

    except Exception as e:
        print(f"Error in play_audio: {e}")

# ============================
# Speech Recognition Callback
# ============================
def recognition_callback(recognizer, audio_data):
    """
    This function is called from a background thread whenever speech is detected.
    """
    try:
        # Convert speech to text using Google
        MyText = recognizer.recognize_google(audio_data).lower()
        print(f"User said: {MyText}")

        # Check wake word
        if MyText.startswith(WAKE_WORD):
            command = MyText[len(WAKE_WORD):].strip()
            print(f"Command received: {command}")

            if command:
                # Generate AI response using GPT-3.5-Turbo
                response = client.chat.completions.create(
                    model="gpt-3.5-turbo",
                    messages=[
                        {"role": "system", "content": indoctrination},
                        {"role": "user", "content": command}
                    ],
                    temperature=0.5,
                    max_tokens=150
                )

                response_text = response.choices[0].message.content.strip()
                # Clean up any "Monkey Butler:" references
                response_text = response_text.replace("Monkey Butler:", "").strip()
                print(f"Bot response: {response_text}")

                # Convert response to speech with AWS Polly
                polly_response = polly_client.synthesize_speech(
                    VoiceId='Brian',
                    OutputFormat='mp3',
                    Text=response_text,
                    Engine='neural'
                )

                filename = "speech_output.mp3"
                with open(filename, 'wb') as file:
                    file.write(polly_response['AudioStream'].read())

                # Play the audio in a separate thread
                audio_thread = threading.Thread(target=play_audio, args=(filename,))
                audio_thread.start()

    except sr.UnknownValueError:
        # No blocking pause—just a quick note or pass silently.
        print("Could not understand the audio.")
    except sr.RequestError as e:
        print(f"Speech Recognition API error: {e}")
    except openai.OpenAIError as e:
        print(f"OpenAI API Error: {e}")
    except boto3.exceptions.Boto3Error as e:
        print(f"AWS Polly Error: {e}")
    except Exception as e:
        print(f"Unexpected Error: {e}")

# ============================
# Main Entry Point
# ============================
def main():
    # Use the default microphone as our source
    mic = sr.Microphone()

    # Adjust for ambient noise once at startup (optional)
    with mic as source:
        r.adjust_for_ambient_noise(source, duration=1.0)
        print("Calibrated for ambient noise. Starting background listening...")

    # Start background listening
    stop_listening = r.listen_in_background(mic, recognition_callback)

    print("Background listening started. Press Ctrl+C to stop.")

    try:
        while True:
            time.sleep(0.1)
            # You can do other tasks here if needed
    except KeyboardInterrupt:
        # Stop background listening when the user terminates
        stop_listening(wait_for_stop=False)
        print("Stopped listening in background.")

if __name__ == "__main__":
    main()