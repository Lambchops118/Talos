from datetime import datetime
from   zoneinfo import ZoneInfo
import paho.mqtt.client as mqtt
from   apscheduler.triggers.cron import CronTrigger
from   apscheduler.schedulers.background import BackgroundScheduler

TZ = ZoneInfo("America/New_York")  # pick your local tz


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

    {
        "name": "morning_motd",
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

# =============== FUNCTIONS ========================================================================================

def get_weather():
    None

def get_time():
    None



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


# ==== DAILY TIME BASED FUNCTIONS ==================================================================================

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
        trigger  = CronTrigger(hour=20, minute=36), # Daily at 7:30 AM
        args     = [gui_queue],
        id       = "daily_forecast",
        replace_existing = True,
    )

    #More jobs can be added here.

    scheduler.start()
    return scheduler