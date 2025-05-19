#Contains code that should be run in the morning for checking weather, time, morning briefings.

import requests
from datetime import datetime
api_key = "c5bbe0c6b2d7ab5f9ae92a9441d47253"
city = "New York"


def get_weather_report(api_key, city):
    # Get current weather
    current_url = "https://api.openweathermap.org/data/2.5/weather"
    current_params = {
        "q": city,
        "appid": api_key,
        "units": "metric"
    }
    current_response = requests.get(current_url, params=current_params)
    if current_response.status_code != 200:
        raise Exception(f"Current weather API error: {current_response.status_code} - {current_response.text}")
    current_data = current_response.json()
    
    current_temp = current_data["main"]["temp"]
    current_weather = current_data["weather"][0]["description"]

    # Get forecast to compute today's high/low
    forecast_url = "https://api.openweathermap.org/data/2.5/forecast"
    forecast_params = {
        "q": city,
        "appid": api_key,
        "units": "metric"
    }
    forecast_response = requests.get(forecast_url, params=forecast_params)
    if forecast_response.status_code != 200:
        raise Exception(f"Forecast API error: {forecast_response.status_code} - {forecast_response.text}")
    forecast_data = forecast_response.json()

    today = datetime.utcnow().date()
    today_temps = [
        entry["main"]["temp"]
        for entry in forecast_data["list"]
        if datetime.utcfromtimestamp(entry["dt"]).date() == today
    ]

    temp_max = max(today_temps) if today_temps else None
    temp_min = min(today_temps) if today_temps else None

    return {
        "current_temperature": current_temp,
        "current_weather": current_weather,
        "today_high": temp_max,
        "today_low": temp_min
    }

report = get_weather_report(api_key, city)

for key, value in report.items():
    print(f"{key}: {value}")