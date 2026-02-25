#import poll_apis
import os
import tv_control
from   pyowm import OWM
from   datetime import datetime
from   zoneinfo import ZoneInfo
import paho.mqtt.client as mqtt
from   pycoingecko import CoinGeckoAPI
from   messages import Message, VoicePayload
from   apscheduler.triggers.cron import CronTrigger
from   apscheduler.schedulers.background import BackgroundScheduler

TZ       = ZoneInfo("America/New_York")  # pick your local tz
BROKER   = "192.168.1.160"
PORT     = 1883
cg       = CoinGeckoAPI()
coins    = ["bitcoin", "ethereum", "solana"]
currency = "usd"
city     = "Ellicott City,MD,US"
open_weather_api_key = os.getenv("OPEN_WEATHER_API_KEY")

def degrees_to_compass(deg):
    directions = [
        "N","NNE","NE","ENE","E","ESE","SE","SSE",
        "S","SSW","SW","WSW","W","WNW","NW","NNW"
    ]
    idx = int((deg + 11.25) / 22.5) % 16
    return directions[idx]

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

    # {
    #     "name": "morning_motd",
    #     "description": "Return the morning message of the day including weather and time.",
    #     "parameters": {
    #         "type": "object",
    #         "properties": {
    #             "weather": {
    #                 "type": "string",
    #                 "description": "The current weather summary."
    #             }
    #         },
    #         "required": ["room"]
    #     }
    # },

    {
        "name": "toggle_fan",
        "description": "Toggle the fan on (1) or off (0)",
        "parameters": {
            "type": "object",
            "properties": {
                "status": {
                    "type": "number",
                    "description": "The number to send to the MQTT broker to toggle the fan on (1) or off (0)"
                }
            },
            "required": ["status"]
        }
    }
]

# =============== FUNCTIONS ========================================================================================


def search_web(query):
    None

def print_directions():
    None

#def morning_motd():
    #None
    

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

def toggle_fan(status):
    print(f"Toggling fan {status}")
    topic   = "fan/16"
    message = status
    client  = mqtt.Client()
    client.connect(BROKER, PORT, keepalive=60)
    client.publish(topic, message)
    client.disconnect()


# ==== SPECIFIC TIME BASED FUNCTIONS ==================================================================================

#Define Time based jobs
def debug_job(gui_queue, central_queue=None):
    print("DEBUG JOB ACTIVATED")

def daily_forecast_job(gui_queue, central_queue=None): # We can probably replace qui_queue with processing_queue if we want TTS playback too.
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
    #tv_control.FireTvController.morning_turn_on() #This wont work because by morning tv is hard resting

def dim_display(): #This will require a script on the PI to listen on this MQTT port and then send the CEC signal to the TV
    print("Dimming Display.")
    # TOPIC_PREFIX = "tv_display"
    # topic        = f"{TOPIC_PREFIX}/wake_status"
    # message      = "0"
    # client  = mqtt.Client()
    # client.connect(BROKER, PORT, keepalive=60)
    # client.publish(topic, message)
    # client.disconnect()
    tv_control.night_sleep()

def update_infopanel_information(gui_queue, central_queue=None):
    # fetch data here
    # This will NOT BLOCK infopanel GUI or voice commands because its in a separate thread
    price_data  = cg.get_price(ids=coins, vs_currencies=currency)
    owm         = OWM(open_weather_api_key)
    mgr         = owm.weather_manager()
    observation = mgr.weather_at_place(city)
    weather     = observation.weather

    temp_data = weather.temperature("fahrenheit")
    wind_data = weather.wind(unit="miles_hour")

    push_status(
        central_queue,
        btc_price = price_data["bitcoin"][currency],
        eth_price = price_data["ethereum"][currency],
        sol_price = price_data["solana"][currency],

        temp      = round(temp_data["temp"]),
        feelslike = round(temp_data["feels_like"]),
        humidity  = round(weather.humidity),
        wind      = round(wind_data.get("speed")),
        wind_dir  = degrees_to_compass(wind_data.get("deg")),
        weather   = weather.detailed_status,

        uptime = "ERR"
    )

def update_dynamo_information(gui_queue, central_queue=None):
    None


# VOICE FUNCTIONS #####################################################################################################################################
def morning_report_job(gui_queue, central_queue=None):
    owm         = OWM(open_weather_api_key)
    mgr         = owm.weather_manager()
    observation = mgr.weather_at_place(city)
    weather     = observation.weather
    temp_data   = weather.temperature("fahrenheit")

    temp        = round(temp_data["temp"])
    feelslike   = round(temp_data["feels_like"])
    weather     = weather.detailed_status

    now         = datetime.now()
    time_str    = now.strftime("%I:%M %p").lstrip("0")
    day_str     = now.strftime("%A")
    date_str    = now.strftime("%m-%d-%y")

    if central_queue is None:
        return
    central_queue.put(
        Message(
            type="voice_cmd",
            payload=VoicePayload(
            f"[Generate a morning report for the following data. This is not a spoken input, this is a system prompt]" \
            
            f"time: {time_str}" \
            f"day: {day_str}" \
            f"Temperature: {temp} deg F" \
            f"feels like: {feelslike} deg F" \
            f"weather: {weather}" \
            f"calendar: None" \
            f"Date: {date_str}" \
            )
        )
    )



# Start the chron job scheduler ########################################################################################################################
def push_status(central_queue, **values):
    if central_queue is None:
        return
    central_queue.put(Message(type="ui", payload=("STATUS", values)))


def start_scheduler(gui_queue, central_queue=None):
    scheduler = BackgroundScheduler(
        timezone     = TZ,
        job_defaults = {
            "coalesce"           : True,        # merge backlogged runs into one --- might not need this
            "max_instances"      : 1,           # don’t overlap the same job
            "misfire_grace_time" : 600          # seconds; OK to fire within 10 mins if late
        },
    )

    #Debug Job
    scheduler.add_job( 
        debug_job,
        trigger  = CronTrigger(hour=13, minute=31), # Daily at 7:30 AM
        args     = [gui_queue, central_queue],
        id       = "debug_task",
        replace_existing = True,
    )

    scheduler.add_job(
        daily_forecast_job,
        trigger  = CronTrigger(hour=20, minute=36), # Daily at 7:30 AM
        args     = [gui_queue, central_queue],
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

    scheduler.add_job(
        update_infopanel_information,
        trigger  = CronTrigger(minute="*/1"), # Every 1 Minute
        args     = [gui_queue, central_queue],
        id       = "update_infopane_information",
        replace_existing = True,
    )

    scheduler.add_job(
        morning_report_job,
        trigger  = CronTrigger(hour=7, minute=30), 
        args     = [gui_queue, central_queue],
        id       = "morning_report_job",
        replace_existing = True,
    )

    #scheduler.add_job(
    #    get_crypto_prices,
    #    trigger  = CronTrigger(minute="*/15"), # Every 15 Minutes
    #    args     = None,
    #    id       = "get_crypto_prices",
    #    replace_existing = True,
    #)

    #More jobs can be added here.

    scheduler.start()
    return scheduler

#wake_display()
#dim_display()
