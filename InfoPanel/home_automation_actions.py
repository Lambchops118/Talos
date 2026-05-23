from __future__ import annotations

import os
import re
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import paho.mqtt.client as mqtt
import requests
from dotenv import load_dotenv


ENV_PATH = Path(__file__).resolve().parent.parent / ".env"
load_dotenv(dotenv_path=ENV_PATH)


BROKER = os.getenv("MQTT_BROKER", "192.168.1.160")
PORT = int(os.getenv("MQTT_PORT", "1883"))
TIMEZONE_NAME = os.getenv("TALOS_TIMEZONE", "").strip()
OPEN_WEATHER_API_KEY = os.getenv("OPEN_WEATHER_API_KEY", "").strip()
WEATHER_LOCATION = os.getenv("TALOS_WEATHER_LOCATION", "").strip()
WEATHER_UNITS = os.getenv("TALOS_WEATHER_UNITS", "imperial").strip().lower()
OPENWEATHER_GEOCODE_URL = "https://api.openweathermap.org/geo/1.0/direct"
OPENWEATHER_ONECALL_URL = "https://api.openweathermap.org/data/3.0/onecall"


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


def get_current_weather(location: str = "") -> str:
    requested_location = _normalize_location_query(location) or _normalize_location_query(WEATHER_LOCATION)
    if not requested_location:
        raise ValueError("No weather location configured. Set TALOS_WEATHER_LOCATION or pass a location.")
    if not OPEN_WEATHER_API_KEY:
        raise ValueError("OPEN_WEATHER_API_KEY is not configured.")

    try:
        latitude, longitude, resolved_location = _geocode_location(requested_location)
        weather_data = _fetch_weather(latitude, longitude)
    except requests.HTTPError as exc:
        response = exc.response
        status_code = response.status_code if response is not None else "unknown"
        if status_code == 401:
            raise RuntimeError(
                "OpenWeather rejected the request. Check OPEN_WEATHER_API_KEY and One Call API access."
            ) from exc
        raise RuntimeError(f"Weather request failed with HTTP {status_code}.") from exc
    except requests.RequestException as exc:
        raise RuntimeError(f"Weather request failed: {exc}") from exc

    current = weather_data["current"]
    daily = weather_data.get("daily", [])
    today = daily[0] if daily else {}
    timezone_name = weather_data.get("timezone", "unknown")
    units_label = _units_label()

    lines = [
        f"Location: {resolved_location}",
        f"Observation time: {_format_unix_time(current.get('dt'), timezone_name)}",
        f"Timezone: {timezone_name}",
        f"Weather: {_weather_summary(current)}",
        f"Temperature: {current.get('temp')} {units_label['temperature']}",
        f"Feels like: {current.get('feels_like')} {units_label['temperature']}",
        f"Humidity: {current.get('humidity')}%",
        f"UV index: {current.get('uvi', 'unknown')}",
        f"Wind: {current.get('wind_speed')} {units_label['wind_speed']}",
        f"Cloud cover: {current.get('clouds', 'unknown')}%",
    ]

    if "dew_point" in current:
        lines.append(f"Dew point: {current['dew_point']} {units_label['temperature']}")
    if "pressure" in current:
        lines.append(f"Pressure: {current['pressure']} hPa")
    if "visibility" in current:
        lines.append(f"Visibility: {_format_visibility(current['visibility'])}")
    if "pop" in today:
        lines.append(f"Chance of precipitation today: {round(float(today['pop']) * 100)}%")
    if "temp" in today:
        day_temp = today["temp"]
        if "max" in day_temp:
            lines.append(f"Today's high: {day_temp['max']} {units_label['temperature']}")
        if "min" in day_temp:
            lines.append(f"Today's low: {day_temp['min']} {units_label['temperature']}")
    if "sunrise" in current:
        lines.append(f"Sunrise: {_format_unix_time(current['sunrise'], timezone_name, time_only=True)}")
    if "sunset" in current:
        lines.append(f"Sunset: {_format_unix_time(current['sunset'], timezone_name, time_only=True)}")

    return "\n".join(lines)


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


def _geocode_location(location: str) -> tuple[float, float, str]:
    response = requests.get(
        OPENWEATHER_GEOCODE_URL,
        params={
            "q": location,
            "limit": 1,
            "appid": OPEN_WEATHER_API_KEY,
        },
        timeout=10,
    )
    response.raise_for_status()

    matches = response.json()
    if not matches:
        raise ValueError(f"Could not find weather location: {location}")

    match = matches[0]
    resolved_location = _format_location(match)
    return float(match["lat"]), float(match["lon"]), resolved_location


def _normalize_location_query(location: str) -> str:
    normalized = " ".join(str(location).split())
    normalized = re.sub(r"\s*,\s*", ", ", normalized)
    return normalized.strip(" ,")


def _fetch_weather(latitude: float, longitude: float) -> dict:
    response = requests.get(
        OPENWEATHER_ONECALL_URL,
        params={
            "lat": latitude,
            "lon": longitude,
            "appid": OPEN_WEATHER_API_KEY,
            "units": _weather_units(),
            "exclude": "minutely,alerts",
        },
        timeout=10,
    )
    response.raise_for_status()
    return response.json()


def _format_location(match: dict) -> str:
    parts = [match.get("name", "").strip()]
    state = str(match.get("state", "")).strip()
    country = str(match.get("country", "")).strip()
    if state:
        parts.append(state)
    if country:
        parts.append(country)
    return ", ".join(part for part in parts if part)


def _format_unix_time(timestamp: int | None, timezone_name: str, *, time_only: bool = False) -> str:
    if not timestamp:
        return "unknown"

    try:
        moment = datetime.fromtimestamp(timestamp, ZoneInfo(timezone_name))
    except ZoneInfoNotFoundError:
        moment = datetime.fromtimestamp(timestamp).astimezone()

    return moment.strftime("%H:%M:%S") if time_only else moment.isoformat(timespec="seconds")


def _weather_summary(current: dict) -> str:
    weather = current.get("weather") or []
    if not weather:
        return "unknown"

    primary = weather[0]
    description = str(primary.get("description", "unknown"))
    main = str(primary.get("main", "")).strip()
    if main and main.lower() not in description.lower():
        return f"{main} ({description})"
    return description


def _weather_units() -> str:
    if WEATHER_UNITS in {"standard", "metric", "imperial"}:
        return WEATHER_UNITS
    return "imperial"


def _units_label() -> dict[str, str]:
    units = _weather_units()
    if units == "metric":
        return {"temperature": "C", "wind_speed": "m/s"}
    if units == "standard":
        return {"temperature": "K", "wind_speed": "m/s"}
    return {"temperature": "F", "wind_speed": "mph"}


def _format_visibility(visibility_meters: int | float) -> str:
    units = _weather_units()
    if units == "imperial":
        miles = float(visibility_meters) / 1609.344
        return f"{miles:.1f} miles"
    kilometers = float(visibility_meters) / 1000
    return f"{kilometers:.1f} km"
