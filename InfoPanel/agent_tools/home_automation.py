from __future__ import annotations

import os

import paho.mqtt.client as mqtt

from .registry import tool


BROKER = os.getenv("MQTT_BROKER", "192.168.1.160")
PORT = int(os.getenv("MQTT_PORT", "1883"))


def _publish(topic: str, message: str | int) -> None:
    client = mqtt.Client()
    client.connect(BROKER, PORT, keepalive=60)
    client.publish(topic, message)
    client.disconnect()


@tool(
    name="water_plants",
    description="Send a signal to the pump circuit to water either pot 1 (monstera), or pot 2 (Dusty Miller, Trailing red, and Senaw).",
    parameters={
        "type": "object",
        "properties": {
            "pot_number": {
                "type": "number",
                "description": "The pot number to water (1 or 2).",
            }
        },
        "required": ["pot_number"],
    },
)
def water_plants(pot_number: int) -> str:
    print("THIS IS THE PLACEHOLDER FOR WATERING PLANTS" + str(pot_number))
    topic_prefix = "quad_pump"

    if pot_number == 1:
        topic = f"{topic_prefix}/17"
    elif pot_number == 2:
        topic = f"{topic_prefix}/19"
    else:
        raise ValueError("pot_number must be 1 or 2")

    _publish(topic, "1")
    return f"Watering {pot_number}."


@tool(
    name="turn_on_lights",
    description="Turn on the lights in a specific room.",
    parameters={
        "type": "object",
        "properties": {
            "room": {
                "type": "string",
                "description": "The room where the lights should be turned on.",
            }
        },
        "required": ["room"],
    },
)
def turn_on_lights(room: str) -> str:
    print("THIS IS THE PLACEHOLDER FOR TURNING ON LIGHTS IN " + room)
    return f"Turning on lights in the {room}."


@tool(
    name="toggle_fan",
    description="Toggle the fan on (1) or off (0).",
    parameters={
        "type": "object",
        "properties": {
            "status": {
                "type": "number",
                "description": "The number to send to the MQTT broker to toggle the fan on (1) or off (0).",
            }
        },
        "required": ["status"],
    },
)
def toggle_fan(status: int) -> str:
    print(f"Toggling fan {status}")
    _publish("fan/16", status)
    return f"Fan set to {status}."
