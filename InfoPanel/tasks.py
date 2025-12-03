from datetime import datetime
from   zoneinfo import ZoneInfo
import paho.mqtt.client as mqtt
from   apscheduler.triggers.cron import CronTrigger
from   apscheduler.schedulers.background import BackgroundScheduler

TZ = ZoneInfo("America/New_York")  # pick your local tz
BROKER = "192.168.1.160"
PORT   = 1883

# =============== FUNCTION DICTIONARY ====================
functions = [
    {
        "name": "water_plants",
        "description": "Send a signal to the pump circuit to water either pot 1 (monstera), or pot 2 (Dusty Miller, Trailing red, and Senaw)",
        "parameters": {
            "type": "object",
            "properties": {
                "pot_number": {
                    "type": "number",
                    "description": "The pot number to water (1 or 2)."
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
    },

    {
        "name": "morning_motd",
        "description": "Return the morning message of the day including weather and time.",
        "parameters": {
            "type": "object",
            "properties": {
                "weather": {
                    "type": "string",
                    "description": "The current weather summary."
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

def search_web(query):
    None

def print_directions():
    None

def water_plants(pot_number):
    print("THIS IS THE PLACEHOLDER FOR WATERING PLANTS" + str(pot_number))
    TOPIC_PREFIX  = "quad_pump"

    if pot_number   == 1:
        topic = f"{TOPIC_PREFIX}/17"
    elif pot_number == 2:
        topic = f"{TOPIC_PREFIX}/19"
    else:
        raise ValueError("pot_number must be 1 or 2")

    message = "1"
    client  = mqtt.Client()
    client.connect(BROKER, PORT, keepalive=60)
    client.publish(topic, message)
    client.disconnect()

    return f"Watering {pot_number}."

def turn_on_lights(room):
    print("THIS IS THE PLACEHOLDER FOR TURNING ON LIGHTS IN " + room)
    return f"Turning on lights in the {room}."


# ==== DAILY TIME BASED FUNCTIONS ==================================================================================

#Define Time based jobs
def daily_forecast_job(gui_queue): # We can probably replace qui_queue with processing_queue if we want TTS playback too.
    today = datetime.now(TZ).strftime("%Y-%m-%d")
    msg   = f"Forecast for {today}: (placeholder) sunny with a chance of bananas."

    print(msg)
    gui_queue.put(("VOICE_CMD", "daily forecast", msg)) #Bypass pygame in this thread and send to GUI via already established queue. 
    
def wake_display(): #This will require a script on the PI to listen on this MQTT port and then send the CEC signal to the TV
    print("Waking Display.")
    TOPIC_PREFIX = "tv_display"
    topic        = f"{TOPIC_PREFIX}/wake_status"
    message      = "1"
    client  = mqtt.Client()
    client.connect(BROKER, PORT, keepalive=60)
    client.publish(topic, message)
    client.disconnect()

def dim_display(): #This will require a script on the PI to listen on this MQTT port and then send the CEC signal to the TV
    print("Dimming Display.")
    TOPIC_PREFIX = "tv_display"
    topic        = f"{TOPIC_PREFIX}/wake_status"
    message      = "0"
    client  = mqtt.Client()
    client.connect(BROKER, PORT, keepalive=60)
    client.publish(topic, message)
    client.disconnect()

# Start the chron job scheduler
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

    scheduler.add_job(
        wake_display,
        trigger  = CronTrigger(hour=7, minute=25), # Daily at 7:25 AM, to ensure this happens well before morning MOTD
        args     = None,
        id       = "wake_display",
        replace_existing = True,
    )

    scheduler.add_job(
        dim_display,
        trigger  = CronTrigger(hour=23, minute=0), # Daily at 11:00 PM
        args     = None,
        id       = "dim_display",
        replace_existing = True,
    )

    #More jobs can be added here.

    scheduler.start()
    return scheduler

wake_display()
#dim_display()