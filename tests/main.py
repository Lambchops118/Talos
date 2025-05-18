import os
import openai
import speech_recognition as sr
import boto3
import time
from playsound import playsound
import threading

# Secure API Keys (Use Environment Variables)

openai.api_key = "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"
client = openai.OpenAI(api_key="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")

aws_access_key = 'AKIAYASFKTEUSCOD7RT5'
aws_secret_key = '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'

# Initialize AWS Polly Client
polly_client = boto3.client('polly',
    aws_access_key_id=aws_access_key,
    aws_secret_access_key=aws_secret_key,
    region_name='us-west-2'
)

# Speech Recognizer
r = sr.Recognizer()

# Assistant Personality
indoctrination = """Monkey Butler is a chatbot that answers questions with mildly sarcastic responses while acting as a reluctant butler. 
If asked a simple question, he will taunt the user but still provide an answer. He was designed and engineered by Chops, whom he reluctantly obeys.
Monkey Butler does not say his name in responses."""

# Set Wake Word
WAKE_WORD = "butler"

# Function to play audio in a separate thread and remove file afterward
def play_audio(filename):
    playsound(filename)  # Play the speech file
    time.sleep(0.5)  # Small delay to ensure file is not in use
    try:
        os.remove(filename)  # Delete the file after playing
    except PermissionError:
        print("Warning: Unable to delete file, it may still be in use.")

# Main Loop
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
                command = MyText[len(WAKE_WORD):].strip()  # Extract the command after wake word
                print(f"Command received: {command}")

                if command:  # Ensure there is a command after the wake word
                    # Generate AI response
                    response = client.chat.completions.create(
                        model="gpt-4o",
                        messages=[
                            {"role": "system", "content": indoctrination},
                            {"role": "user", "content": command}
                        ],
                        temperature=0.5,
                        max_tokens=200
                    )

                    response_text = response.choices[0].message.content.strip()
                    response_text = response_text.replace("Monkey Butler:", "").strip()
                    print(f"Bot response: {response_text}")

                    # Convert AI response to speech using AWS Polly
                    polly_response = polly_client.synthesize_speech(
                        VoiceId='Brian',
                        OutputFormat='mp3',
                        Text=response_text,
                        Engine='neural'
                    )

                    filename = "speech_output.mp3"
                    with open(filename, 'wb') as file:
                        file.write(polly_response['AudioStream'].read())

                    # Play the audio in a separate thread and then delete it
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