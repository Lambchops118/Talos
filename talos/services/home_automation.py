from __future__ import annotations

import os
from datetime import datetime
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import paho.mqtt.client as mqtt
import requests

from talos.config import load_environment


load_environment()


BROKER = os.getenv("MQTT_BROKER", "192.168.1.160")
PORT = int(os.getenv("MQTT_PORT", "1883"))
TIMEZONE_NAME = os.getenv("TALOS_TIMEZONE", "").strip()
OPEN_WEATHER_API_KEY = os.getenv("OPEN_WEATHER_API_KEY", "").strip()
WEATHER_LOCATION = os.getenv("TALOS_WEATHER_LOCATION", "").strip()
WEATHER_UNITS = os.getenv("TALOS_WEATHER_UNITS", "imperial").strip().lower()
OPENWEATHER_CURRENT_URL = "https://api.openweathermap.org/data/2.5/weather"
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
        current_data = _fetch_current_weather(requested_location)
        onecall_data = _fetch_onecall(current_data)
    except requests.HTTPError as exc:
        response = exc.response
        status_code = response.status_code if response is not None else "unknown"
        if status_code == 401:
            raise RuntimeError(
                "OpenWeather rejected the request. Check OPEN_WEATHER_API_KEY and One Call API access."
            ) from exc
        if status_code == 404:
            raise RuntimeError(f"Could not find weather location: {requested_location}") from exc
        raise RuntimeError(f"Weather request failed with HTTP {status_code}.") from exc
    except requests.RequestException as exc:
        raise RuntimeError(f"Weather request failed: {exc}") from exc

    current = current_data
    onecall_current = onecall_data.get("current", {})
    today = (onecall_data.get("daily") or [{}])[0]
    timezone_name = onecall_data.get("timezone", _format_timezone_name(current.get("timezone")))
    units_label = _units_label()
    resolved_location = _format_current_location(current)

    lines = [
        f"Location: {resolved_location}",
        f"Observation time: {_format_unix_time(current.get('dt'), current.get('timezone'))}",
        f"Timezone: {timezone_name}",
        f"Weather: {_weather_summary(current)}",
        f"Temperature: {current.get('main', {}).get('temp')} {units_label['temperature']}",
        f"Feels like: {current.get('main', {}).get('feels_like')} {units_label['temperature']}",
        f"Humidity: {current.get('main', {}).get('humidity')}%",
        f"UV index: {onecall_current.get('uvi', 'unknown')}",
        f"Wind: {current.get('wind', {}).get('speed')} {units_label['wind_speed']}",
        f"Cloud cover: {current.get('clouds', {}).get('all', 'unknown')}%",
    ]

    main = current.get("main", {})
    wind = current.get("wind", {})
    sys = current.get("sys", {})

    if "temp_min" in main and "temp_max" in main:
        lines.append(
            f"Current range: {main['temp_min']} to {main['temp_max']} {units_label['temperature']}"
        )
    if "pressure" in main:
        lines.append(f"Pressure: {main['pressure']} hPa")
    if "visibility" in current:
        lines.append(f"Visibility: {_format_visibility(current['visibility'])}")
    if "gust" in wind:
        lines.append(f"Wind gusts: {wind['gust']} {units_label['wind_speed']}")
    if "dew_point" in onecall_current:
        lines.append(f"Dew point: {onecall_current['dew_point']} {units_label['temperature']}")
    today_precip = _daily_precip_percent(today)
    if today_precip is not None:
        lines.append(f"Chance of precipitation today: {today_precip}%")
    today_temps = today.get("temp", {})
    if "max" in today_temps:
        lines.append(f"Today's high: {today_temps['max']} {units_label['temperature']}")
    if "min" in today_temps:
        lines.append(f"Today's low: {today_temps['min']} {units_label['temperature']}")
    if "sunrise" in sys:
        lines.append(f"Sunrise: {_format_unix_time(sys['sunrise'], current.get('timezone'), time_only=True)}")
    if "sunset" in sys:
        lines.append(f"Sunset: {_format_unix_time(sys['sunset'], current.get('timezone'), time_only=True)}")

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


def _fetch_current_weather(location: str) -> dict:
    response = requests.get(
        OPENWEATHER_CURRENT_URL,
        params={
            "q": location,
            "appid": OPEN_WEATHER_API_KEY,
            "units": _weather_units(),
        },
        timeout=10,
    )
    response.raise_for_status()
    return response.json()


def _fetch_onecall(current: dict) -> dict:
    coordinates = current.get("coord", {})
    latitude = coordinates.get("lat")
    longitude = coordinates.get("lon")
    if latitude is None or longitude is None:
        raise RuntimeError("Current weather response did not include coordinates for One Call lookup.")

    response = requests.get(
        OPENWEATHER_ONECALL_URL,
        params={
            "lat": latitude,
            "lon": longitude,
            "appid": OPEN_WEATHER_API_KEY,
            "units": _weather_units(),
            "exclude": "minutely,alerts,hourly",
        },
        timeout=10,
    )
    response.raise_for_status()
    return response.json()


def _normalize_location_query(location: str) -> str:
    normalized = " ".join(str(location).split())
    while " ," in normalized:
        normalized = normalized.replace(" ,", ",")
    while ",," in normalized:
        normalized = normalized.replace(",,", ",")
    return normalized.strip(" ,")


def _format_current_location(current: dict) -> str:
    parts = [str(current.get("name", "")).strip()]
    sys = current.get("sys", {})
    country = str(sys.get("country", "")).strip()
    state = str(current.get("state", "")).strip()
    if state:
        parts.append(state)
    if country:
        parts.append(country)
    return ", ".join(part for part in parts if part)


def _format_unix_time(
    timestamp: int | None,
    timezone_offset_seconds: int | None,
    *,
    time_only: bool = False,
) -> str:
    if not timestamp:
        return "unknown"

    if isinstance(timezone_offset_seconds, int):
        from datetime import timezone, timedelta

        moment = datetime.fromtimestamp(timestamp, timezone(timedelta(seconds=timezone_offset_seconds)))
    else:
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


def _format_timezone_name(timezone_offset_seconds: int | None) -> str:
    if not isinstance(timezone_offset_seconds, int):
        return "unknown"
    sign = "+" if timezone_offset_seconds >= 0 else "-"
    total_minutes = abs(timezone_offset_seconds) // 60
    hours, minutes = divmod(total_minutes, 60)
    return f"UTC{sign}{hours:02d}:{minutes:02d}"


def _daily_precip_percent(day: dict) -> int | None:
    if "pop" not in day:
        return None
    return round(float(day["pop"]) * 100)
