from __future__ import annotations

import os

import paho.mqtt.client as mqtt


BROKER = os.getenv("MQTT_BROKER", "192.168.1.160")
PORT = int(os.getenv("MQTT_PORT", "1883"))


def _publish(topic: str, message: str | int) -> None:
    client = mqtt.Client()
    client.connect(BROKER, PORT, keepalive=60)
    client.publish(topic, message)
    client.disconnect()


def water_plants(pot_number: int) -> str:
    topic_prefix = "quad_pump"

    if pot_number == 1:
        topic = f"{topic_prefix}/17"
    elif pot_number == 2:
        topic = f"{topic_prefix}/19"
    else:
        raise ValueError("pot_number must be 1 or 2")

    _publish(topic, "1")
    return f"Watering {pot_number}."


def turn_on_lights(room: str) -> str:
    return f"Turning on lights in the {room}."


def toggle_fan(status: int) -> str:
    _publish("fan/16", status)
    return f"Fan set to {status}."
