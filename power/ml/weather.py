from datetime import date, datetime, timedelta
import time
import pandas as pd
import requests
from power.utils.logger import get_logger

logger = get_logger("WeatherFetch")





STATE_COORDS = {
    "DL": {"lat": 28.6139, "lon": 77.2090},
    "MH": {"lat": 19.7515, "lon": 75.7139},
    "TN": {"lat": 11.1271, "lon": 78.6569},
    "UP": {"lat": 26.8467, "lon": 80.9462},
    "AP": {"lat": 15.9129, "lon": 79.7400},
    "AR": {"lat": 28.2180, "lon": 94.7278},
    "AS": {"lat": 26.2006, "lon": 92.9376},
    "BR": {"lat": 25.0961, "lon": 85.3131},
    "CH": {"lat": 30.7333, "lon": 76.7794},
    "CG": {"lat": 21.2787, "lon": 81.8661},
    "GA": {"lat": 15.2993, "lon": 74.1240},
    "GJ": {"lat": 22.2587, "lon": 71.1924},
    "HR": {"lat": 29.0588, "lon": 76.0856},
    "HP": {"lat": 31.1048, "lon": 77.1734},
    "JK": {"lat": 33.7782, "lon": 76.5762},
    "JH": {"lat": 23.6102, "lon": 85.2799},
    "KA": {"lat": 15.3173, "lon": 75.7139},
    "KL": {"lat": 10.8505, "lon": 76.2711},
    "MN": {"lat": 24.6637, "lon": 93.9063},
    "ML": {"lat": 25.4670, "lon": 91.3662},
    "MZ": {"lat": 23.1645, "lon": 92.9376},
    "MP": {"lat": 22.9734, "lon": 78.6569},
    "NL": {"lat": 26.1584, "lon": 94.5624},
    "OD": {"lat": 20.9517, "lon": 85.0985},
    "PY": {"lat": 11.9416, "lon": 79.8083},
    "PB": {"lat": 31.1471, "lon": 75.3412},
    "RJ": {"lat": 27.0238, "lon": 74.2179},
    "SK": {"lat": 27.5330, "lon": 88.5122},
    "TS": {"lat": 18.1124, "lon": 79.0193},
    "TR": {"lat": 23.9408, "lon": 91.9882},
    "UK": {"lat": 30.0668, "lon": 79.0193},
    "WB": {"lat": 22.9868, "lon": 87.8550},
}



# Add this after STATE_COORDS dictionary

# Multi-city weighted weather for large industrial states
STATE_CITY_WEIGHTS = {
    "CG": [
        # city, lat, lon, weight
        # Weights based on grid map — Korba is industrial heart
        ("Korba",     22.3595, 82.7501, 0.30),  # BALCO + NTPC Korba
        ("Raipur",    21.2514, 81.6296, 0.25),  # capital, urban load
        ("Durg",      21.1904, 81.2849, 0.15),  # Bhilai Steel Plant
        ("Bilaspur",  22.0797, 82.1391, 0.15),  # secondary hub
        ("Raigarh",   21.8974, 83.3950, 0.10),  # eastern thermal plants
        ("Jagdalpur", 19.0748, 82.0339, 0.05),  # south, low load
    ],
    # Add MP cities here later if needed
    # "MP": [...],
}


def fetch_weather_weighted(state_short: str, date_str: str, frequency="hourly") -> pd.DataFrame:
    """
    For states with multi-city weights (like CG), fetch weather for each
    city and return a single weighted average DataFrame.
    Falls back to single-point fetch_weather() for other states.
    """
    # If no city weights defined, use existing single-point function
    if state_short not in STATE_CITY_WEIGHTS:
        return fetch_weather(state_short, date_str, frequency)

    cities = STATE_CITY_WEIGHTS[state_short]
    city_dfs = []

    for city_name, lat, lon, weight in cities:
        target_date = datetime.strptime(date_str, "%Y-%m-%d").date()
        today = datetime.now().date()

        url = (
            "https://archive-api.open-meteo.com/v1/archive"
            if target_date < today
            else "https://api.open-meteo.com/v1/forecast"
        )

        params = {
            "latitude": round(lat, 4),
            "longitude": round(lon, 4),
            "hourly": "temperature_2m,relativehumidity_2m,windspeed_10m,precipitation",
            "start_date": date_str,
            "end_date": date_str,
            "timezone": "Asia/Kolkata",
        }

        for attempt in range(3):
            try:
                r = requests.get(url, params=params, timeout=20)
                r.raise_for_status()
                data = r.json()
                logger.info(f"[{state_short}] Weather fetched for {city_name} on {date_str}")
                break
            except Exception as e:
                if attempt == 2:
                    logger.error(f"[{state_short}] {city_name} failed: {e}")
                    data = None
                time.sleep(2)

        if not data or "hourly" not in data:
            logger.warning(f"[{state_short}] Skipping {city_name} — no data")
            continue

        df = pd.DataFrame({
            "datetime": data["hourly"]["time"],
            "temperature_c": data["hourly"]["temperature_2m"],
            "humidity_pct":  data["hourly"]["relativehumidity_2m"],
            "wind_speed_ms": data["hourly"]["windspeed_10m"],
            "rain_mm":       data["hourly"]["precipitation"],
        })

        df["datetime"] = pd.to_datetime(df["datetime"]).dt.tz_localize(None)
        df["weight"] = weight
        df["city"] = city_name
        city_dfs.append(df)
        time.sleep(0.3)  # rate limit between cities

    if not city_dfs:
        logger.error(f"[{state_short}] All city fetches failed for {date_str}")
        return pd.DataFrame()

    combined = pd.concat(city_dfs, ignore_index=True)

    # ── WEIGHTED AVERAGE PER TIMESTAMP ──────────────────────
    import numpy as np

    def weighted_avg(group):
        w = group["weight"]
        return pd.Series({
            "temperature_c": np.average(group["temperature_c"], weights=w),
            "humidity_pct":  np.average(group["humidity_pct"],  weights=w),
            "wind_speed_ms": np.average(group["wind_speed_ms"], weights=w),
            "rain_mm":       np.average(group["rain_mm"],       weights=w),
        })

    weighted = (
        combined.groupby("datetime")
        .apply(weighted_avg)
        .reset_index()
    )

    # ── 5-MIN INTERPOLATION (same as existing fetch_weather) ─
    weighted = (
        weighted.set_index("datetime")
        .resample("5min")
        .interpolate("time")
        .reset_index()
    )

    weighted["state"] = state_short
    weighted["frequency"] = frequency

    return weighted


def fetch_weather_range_weighted(
    state_short: str,
    start_date,
    end_date,
    frequency="hourly"
) -> pd.DataFrame:
    """
    Same as fetch_weather_range but uses weighted multi-city
    fetch for states like CG.
    """
    if isinstance(start_date, date):
        start_dt = start_date
    else:
        start_dt = datetime.strptime(start_date, "%Y-%m-%d").date()

    if isinstance(end_date, date):
        end_dt = end_date
    else:
        end_dt = datetime.strptime(end_date, "%Y-%m-%d").date()

    all_df = []
    current = start_dt

    while current <= end_dt:
        df = fetch_weather_weighted(
            state_short=state_short,
            date_str=current.strftime("%Y-%m-%d"),
            frequency=frequency,
        )

        if not df.empty:
            all_df.append(df)
        else:
            logger.warning(f"[{state_short}] No weighted weather for {current}")

        current += timedelta(days=1)
        time.sleep(0.3)

    if not all_df:
        return pd.DataFrame()

    return pd.concat(all_df, ignore_index=True)






# def fetch_weather(state_short: str, date_str: str, frequency="hourly") -> pd.DataFrame:
#     if state_short not in STATE_COORDS:
#         raise ValueError(f"State coords missing: {state_short}")

#     coords = STATE_COORDS[state_short]
#     target_date = datetime.strptime(date_str, "%Y-%m-%d").date()
#     today = datetime.now().date()

#     if target_date < today:
#         url = "https://archive-api.open-meteo.com/v1/archive"
#         api_type = "ARCHIVE"
#     else:
#         url = "https://api.open-meteo.com/v1/forecast"
#         api_type = "FORECAST"

#     params = {
#         "latitude": round(coords["lat"], 4),
#         "longitude": round(coords["lon"], 4),
#         "hourly": "temperature_2m,relativehumidity_2m,windspeed_10m,precipitation",
#         "start_date": date_str,
#         "end_date": date_str,
#         "timezone": "Asia/Kolkata",
#     }

#     try:
#         r = requests.get(url, params=params, timeout=20)
#         r.raise_for_status()
#         data = r.json()
#         logger.info(f"[{state_short}] {api_type} weather fetched for {date_str}")
#     except Exception as e:
#         logger.error(f"[{state_short}] Weather fetch failed: {e}")
#         return pd.DataFrame()
    

#     if "hourly" not in data:
#         return pd.DataFrame()

#     df = pd.DataFrame({
#         "datetime": data["hourly"]["time"],
#         "temperature_c": data["hourly"]["temperature_2m"],
#         "humidity_pct": data["hourly"]["relativehumidity_2m"],
#         "wind_speed_ms": data["hourly"]["windspeed_10m"],
#         "rain_mm": data["hourly"]["precipitation"],
#     })

#     weather = weather.set_index("ds").resample("5min").interpolate("time").reset_index()
#     weather["state"] = weather["state"].ffill()
#     weather["frequency"] = weather["frequency"].ffill()

#     print(df.head())

#     return df




def fetch_weather(state_short: str, date_str: str, frequency="hourly") -> pd.DataFrame:
    if state_short not in STATE_COORDS:
        raise ValueError(f"State coords missing: {state_short}")

    coords = STATE_COORDS[state_short]
    target_date = datetime.strptime(date_str, "%Y-%m-%d").date()
    today = datetime.now().date()

    if target_date < today:
        url = "https://archive-api.open-meteo.com/v1/archive"
        api_type = "ARCHIVE"
    else:
        url = "https://api.open-meteo.com/v1/forecast"
        api_type = "FORECAST"

    params = {
        "latitude": round(coords["lat"], 4),
        "longitude": round(coords["lon"], 4),
        "hourly": "temperature_2m,relativehumidity_2m,windspeed_10m,precipitation",
        "start_date": date_str,
        "end_date": date_str,
        "timezone": "Asia/Kolkata",
    }

    # 🔁 RETRY LOGIC
    for attempt in range(3):
        try:
            r = requests.get(url, params=params, timeout=20)
            r.raise_for_status()
            data = r.json()
            logger.info(f"[{state_short}] {api_type} weather fetched for {date_str}")
            break
        except Exception as e:
            if attempt == 2:
                logger.error(f"[{state_short}] Weather fetch failed for {date_str}: {e}")
                return pd.DataFrame()
            time.sleep(2)   # 🔥 VERY IMPORTANT

    if "hourly" not in data:
        return pd.DataFrame()

    df = pd.DataFrame({
        "datetime": data["hourly"]["time"],
        "temperature_c": data["hourly"]["temperature_2m"],
        "humidity_pct": data["hourly"]["relativehumidity_2m"],
        "wind_speed_ms": data["hourly"]["windspeed_10m"],
        "rain_mm": data["hourly"]["precipitation"],
    })

    df["datetime"] = pd.to_datetime(df["datetime"]).dt.tz_localize(None)

    # 🔥 5-MIN INTERPOLATION
    df = (
        df.set_index("datetime")
        .resample("5min")
        .interpolate("time")
        .reset_index()
    )

    df["state"] = state_short
    df["frequency"] = frequency

    return df










def fetch_weather_range(state_short: str, start_date, end_date, frequency="hourly") -> pd.DataFrame:

    if isinstance(start_date, date):
        start_dt = start_date
    else:
        start_dt = datetime.strptime(start_date, "%Y-%m-%d").date()

    if isinstance(end_date, date):
        end_dt = end_date
    else:
        end_dt = datetime.strptime(end_date, "%Y-%m-%d").date()

    all_df = []
    current = start_dt

    while current <= end_dt:
        df = fetch_weather(
            state_short=state_short,
            date_str=current.strftime("%Y-%m-%d"),
            frequency=frequency,
        )

        if not df.empty:
            all_df.append(df)
        else:
            logger.warning(f"[{state_short}] No weather data for {current}")

        current += timedelta(days=1)
        time.sleep(0.3)  # 🔥 RATE-LIMIT PROTECTION

    if not all_df:
        return pd.DataFrame()

    final_df = pd.concat(all_df, ignore_index=True)
    return final_df




