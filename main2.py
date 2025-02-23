import os
import openai
import speech_recognition as sr
import boto3
import time
import pygame
import threading

# -- Secure API Keys (placeholder) --
openai.api_key = "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"
client = openai.OpenAI(api_key="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")

aws_access_key = 'AKIAYASFKTEUSCOD7RT5'
aws_secret_key = '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'

# -- Initialize AWS Polly Client --
polly_client = boto3.client(
    'polly',
    aws_access_key_id=aws_access_key,
    aws_secret_access_key=aws_secret_key,
    region_name='us-west-2'
)

# -- Speech Recognizer --
r = sr.Recognizer()

# -- Assistant Personality --
indoctrination = """Monkey Butler is a chatbot that answers questions with mildly sarcastic responses while acting as a reluctant butler.
If asked a simple question, he will taunt the user but still provide an answer. He was designed and engineered by Chops, whom he reluctantly obeys.
Monkey Butler does not say his name in responses."""

# -- Wake Word --
WAKE_WORD = "butler"

# -- Function: Play audio with pygame and remove file afterward --
def play_audio(filename):
    try:
        pygame.mixer.init()
        pygame.mixer.music.load(filename)
        pygame.mixer.music.play()
        
        # Block until playback finishes
        while pygame.mixer.music.get_busy():
            time.sleep(0.1)
        
        # Explicitly stop and quit the mixer to release the file on Windows
        pygame.mixer.music.stop()
        pygame.mixer.quit()

        # Small delay or retry loop to ensure Windows releases the file
        time.sleep(0.2)  # short delay; can adjust if necessary

        # Retry removing the file a few times in case of a slight delay
        for _ in range(5):
            try:
                os.remove(filename)
                break
            except PermissionError:
                time.sleep(0.2)

    except Exception as e:
        print(f"Error in play_audio: {e}")

# -- Main Loop --
while True:
    try:
        with sr.Microphone() as source:
            r.adjust_for_ambient_noise(source, duration=1.0)
            r.pause_threshold = 0.6

            print("Listening for command...")
            audio = r.listen(source)

            MyText = r.recognize_google(audio).lower()
            print(f"User said: {MyText}")

            # Check if the wake word is at the start
            if MyText.startswith(WAKE_WORD):
                command = MyText[len(WAKE_WORD):].strip()
                print(f"Command received: {command}")

                if command:
                    # -- Generate AI response with GPT-3.5-Turbo --
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
                    response_text = response_text.replace("Monkey Butler:", "").strip()
                    print(f"Bot response: {response_text}")

                    # -- Convert AI response to speech using AWS Polly --
                    polly_response = polly_client.synthesize_speech(
                        VoiceId='Brian',
                        OutputFormat='mp3',
                        Text=response_text,
                        Engine='neural'
                    )

                    filename = "speech_output.mp3"
                    with open(filename, 'wb') as file:
                        file.write(polly_response['AudioStream'].read())

                    # -- Play the audio in a separate thread --
                    audio_thread = threading.Thread(target=play_audio, args=(filename,))
                    audio_thread.start()

    except sr.RequestError as e:
        print(f"Speech Recognition API error: {e}")
    except sr.UnknownValueError:
        print("Could not understand the audio.")
    except openai.OpenAIError as e:
        print(f"OpenAI API Error: {e}")
    except boto3.exceptions.Boto3Error as e:
        print(f"AWS Polly Error: {e}")
    except Exception as e:
        print(f"Unexpected Error: {e}")