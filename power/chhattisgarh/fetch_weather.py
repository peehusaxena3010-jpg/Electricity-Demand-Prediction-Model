"""
power/chhattisgarh/fetch_weather.py
-------------------------------------
Fetches hourly weather for Chhattisgarh from Open-Meteo API,
interpolates to 5-minute resolution, and saves to ChhattsgarhWeather5Min.

Chhattisgarh (Raipur) coordinates: lat=21.2514, lon=81.6296

Runs every hour via APScheduler.
For past dates  -> archive-api.open-meteo.com  (historical archive)
For today/future -> api.open-meteo.com          (forecast)
"""

import logging
import time
from datetime import datetime, date, timedelta

import requests
import pandas as pd

logger = logging.getLogger("chhattisgarh.weather")

CHHATTISGARH_LAT = 21.2514   # Raipur, Chhattisgarh
CHHATTISGARH_LON = 81.6296

ARCHIVE_URL  = "https://archive-api.open-meteo.com/v1/archive"
FORECAST_URL = "https://api.open-meteo.com/v1/forecast"

HOURLY_VARS = "temperature_2m,relativehumidity_2m,windspeed_10m,precipitation"


def _fetch_hourly_for_date(date_str: str) -> pd.DataFrame:
    """
    Fetch hourly weather for a single date and return a DataFrame.
    Returns empty DataFrame on failure.
    """
    target = datetime.strptime(date_str, "%Y-%m-%d").date()
    today  = datetime.now().date()

    url = ARCHIVE_URL if target < today else FORECAST_URL

    params = {
        "latitude":   CHHATTISGARH_LAT,
        "longitude":  CHHATTISGARH_LON,
        "hourly":     HOURLY_VARS,
        "start_date": date_str,
        "end_date":   date_str,
        "timezone":   "Asia/Kolkata",
    }

    for attempt in range(3):
        try:
            r = requests.get(url, params=params, timeout=20)
            r.raise_for_status()
            data = r.json()
            logger.info("[CG Weather] Fetched %s from %s", date_str, url)
            break
        except Exception as exc:
            if attempt == 2:
                logger.error("[CG Weather] Failed for %s: %s", date_str, exc)
                return pd.DataFrame()
            time.sleep(2)

    if "hourly" not in data:
        logger.warning("[CG Weather] No hourly key for %s", date_str)
        return pd.DataFrame()

    hourly = data["hourly"]
    df = pd.DataFrame({
        "datetime":      hourly["time"],
        "temperature_c": hourly["temperature_2m"],
        "humidity_pct":  hourly["relativehumidity_2m"],
        "wind_speed_ms": hourly["windspeed_10m"],
        "rain_mm":       hourly["precipitation"],
    })

    df["datetime"] = pd.to_datetime(df["datetime"]).dt.tz_localize(None)
    return df


def _interpolate_to_5min(df: pd.DataFrame) -> pd.DataFrame:
    """Upsample hourly DataFrame to 5-minute resolution via linear interpolation."""
    df = (
        df.set_index("datetime")
        .resample("5min")
        .interpolate("time")
        .reset_index()
    )
    return df


def fetch_and_save_chhattisgarh_weather(target_date: str = None) -> int:
    """
    Fetch and save weather for `target_date` (defaults to today).
    Returns number of rows upserted.
    Called by APScheduler every hour.
    """
    from power.models import ChhattsgarhWeather5Min

    if target_date is None:
        target_date = datetime.now().strftime("%Y-%m-%d")

    df = _fetch_hourly_for_date(target_date)
    if df.empty:
        return 0

    df = _interpolate_to_5min(df)

    from django.db import transaction

    count = 0
    with transaction.atomic():
        for _, row in df.iterrows():
            _, created = ChhattsgarhWeather5Min.objects.update_or_create(
                datetime=row["datetime"],
                defaults={
                    "temperature_c": round(float(row["temperature_c"]), 4),
                    "humidity_pct":  round(float(row["humidity_pct"]),  4) if pd.notna(row["humidity_pct"]) else None,
                    "rain_mm":       round(float(row["rain_mm"]),       4) if pd.notna(row["rain_mm"])       else None,
                    "wind_speed_ms": round(float(row["wind_speed_ms"]), 4) if pd.notna(row["wind_speed_ms"]) else None,
                    "source":        "open_meteo",
                },
            )
            count += 1

    logger.info("[CG Weather] Saved %d rows for %s", count, target_date)
    return count


def fetch_and_save_weather_range(start_date: str, end_date: str) -> int:
    """
    Fetch weather for a date range (used during backfill / seeding).
    Returns total rows inserted.
    """
    start_dt = datetime.strptime(start_date, "%Y-%m-%d").date()
    end_dt   = datetime.strptime(end_date,   "%Y-%m-%d").date()

    total   = 0
    current = start_dt

    while current <= end_dt:
        count  = fetch_and_save_chhattisgarh_weather(current.strftime("%Y-%m-%d"))
        total += count
        current += timedelta(days=1)
        time.sleep(0.3)

    logger.info("[CG Weather] Range fetch complete: %d total rows", total)
    return total
