from __future__ import annotations

import os
from datetime import datetime
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import paho.mqtt.client as mqtt


BROKER = os.getenv("MQTT_BROKER", "192.168.1.160")
PORT = int(os.getenv("MQTT_PORT", "1883"))
TIMEZONE_NAME = os.getenv("TALOS_TIMEZONE", "").strip()


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


def get_current_datetime() -> str:
    now = _get_now()
    timezone_name = _get_timezone_name(now)
    utc_offset = now.strftime("%z")
    utc_offset = f"{utc_offset[:3]}:{utc_offset[3:]}" if utc_offset else "unknown"

    return "\n".join(
        [
            f"Current local datetime: {now.isoformat(timespec='seconds')}",
            f"Date: {now.date().isoformat()}",
            f"Time: {now.strftime('%H:%M:%S')}",
            f"Day of week: {now.strftime('%A')}",
            f"Month: {now.strftime('%B')}",
            f"Year: {now.year}",
            f"Timezone: {timezone_name}",
            f"UTC offset: {utc_offset}",
        ]
    )


def _get_now() -> datetime:
    if TIMEZONE_NAME:
        try:
            return datetime.now(ZoneInfo(TIMEZONE_NAME))
        except ZoneInfoNotFoundError:
            pass
    return datetime.now().astimezone()


def _get_timezone_name(now: datetime) -> str:
    configured_timezone = TIMEZONE_NAME
    if configured_timezone:
        return configured_timezone

    tzinfo = now.tzinfo
    if tzinfo is None:
        return "local"

    key = getattr(tzinfo, "key", None)
    if key:
        return str(key)

    name = tzinfo.tzname(now)
    return str(name) if name else "local"
