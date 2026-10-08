"""
power/ml/trainy/train_cg_1hour.py
-----------------------------------
Trains XGBoost 1-hour demand forecast model for Chhattisgarh.

Aggregates 5-min data → 1-hour intervals.
Output: power/ml/models/saved/state_CG_1hour.pkl

Run: python manage.py train_cg_model --horizon 1hour
"""

import os
import pandas as pd
import numpy as np


def add_calendar_features(df):
    df = df.copy()
    df["month"]      = df["ds"].dt.month
    df["is_weekend"] = df["ds"].dt.dayofweek.isin([5, 6]).astype(int)
    df["is_holiday"] = 0

    def get_season(m):
        if m in [12, 1, 2]:    return 1   # Winter
        if m in [3, 4, 5]:     return 2   # Summer
        if m in [6, 7, 8, 9]:  return 3   # Monsoon
        return 4                            # Post-monsoon

    df["season"] = df["month"].map(get_season)
    return df


def add_peak_features(df):
    df = df.copy()
    df["hour"]            = df["ds"].dt.hour
    df["is_peak"]         = df["hour"].between(18, 23).astype(int)
    df["temp_x_hour"]     = df["temperature_c"] * df["hour"]
    df["humidity_x_hour"] = df["humidity_pct"]  * df["hour"]
    df["wind_x_hour"]     = df["wind_speed_ms"] * df["hour"]
    return df


def add_sample_weight(df):
    df["sample_weight"] = df["is_peak"].map(lambda x: 3.0 if x == 1 else 1.0)
    return df


def clean_outliers(df):
    df = df.copy().set_index("ds")
    mu, sigma = df["y"].mean(), df["y"].std()
    df.loc[(df["y"] - mu).abs() > 3 * sigma, "y"] = None
    df["y"] = df["y"].interpolate().bfill().ffill()
    return df.reset_index()


def train_cg_1hour_model():
    from power.models import ChhattsgarhLoad5Min, ChhattsgarhWeather5Min
    from power.ml.models.xgb_model import train_xgb_model
    import joblib
    from django.conf import settings

    # ── 1. Load + aggregate demand to 1-hour ──────────────────────────────────
    print("[CG 1HR] Step 1/6 — Loading & aggregating demand to 1-hour...")
    raw = pd.DataFrame(
        ChhattsgarhLoad5Min.objects.order_by("datetime").values("datetime", "demand_mw")
    )
    raw["datetime"] = pd.to_datetime(raw["datetime"])
    raw = raw.rename(columns={"datetime": "ds", "demand_mw": "y"})

    df = (
        raw.set_index("ds")
        .resample("1h")
        .agg({"y": "mean"})
        .interpolate()
        .reset_index()
    )
    print(f"   1-hour rows: {len(df):,}  ({df['ds'].min().date()} -> {df['ds'].max().date()})")

    # ── 2. Load + aggregate weather to 1-hour ─────────────────────────────────
    print("[CG 1HR] Step 2/6 — Loading & aggregating weather to 1-hour...")
    weather = pd.DataFrame(
        ChhattsgarhWeather5Min.objects.order_by("datetime")
        .values("datetime", "temperature_c", "humidity_pct", "rain_mm", "wind_speed_ms")
    )
    weather["datetime"] = pd.to_datetime(weather["datetime"])
    weather = (
        weather.set_index("datetime")
        .resample("1h")
        .mean()
        .interpolate()
        .reset_index()
        .rename(columns={"datetime": "ds"})
    )

    # ── 3. Merge ───────────────────────────────────────────────────────────────
    df = pd.merge_asof(
        df.sort_values("ds"),
        weather.sort_values("ds"),
        on="ds", direction="nearest", tolerance=pd.Timedelta("1h"),
    )
    for col in ["temperature_c", "humidity_pct", "rain_mm", "wind_speed_ms"]:
        df[col] = df[col].ffill().bfill().fillna(0)

    # ── 4. Features ────────────────────────────────────────────────────────────
    print("[CG 1HR] Step 3/6 — Engineering features...")
    df = add_calendar_features(df)
    df = add_peak_features(df)

    df["slot"] = df["ds"].dt.hour   # 0-23 for hourly model
    df["mmdd"] = df["ds"].dt.strftime("%m-%d")

    profile = (
        df.groupby(["mmdd", "slot"])["y"].mean()
        .reset_index().rename(columns={"y": "profile_y"})
    )
    df = df.merge(profile, on=["mmdd", "slot"], how="left")
    df = clean_outliers(df)

    # Hourly lags (1hr, 2hr, ... 6hr, 24hr, 7d)
    for i in range(1, 7):
        df[f"y_lag_{i}"] = df["y"].shift(i)
    df["y_lag_24h"] = df["y"].shift(24)    # 1 day ago
    df["y_lag_7d"]  = df["y"].shift(168)   # 7 days ago

    df = add_sample_weight(df)
    df = df.dropna().reset_index(drop=True)
    print(f"   Training rows: {len(df):,}")

    # ── 5. Train ───────────────────────────────────────────────────────────────
    print("[CG 1HR] Step 4/6 — Training XGBoost...")
    model = train_xgb_model(df)

    # ── 6. Save ────────────────────────────────────────────────────────────────
    print("[CG 1HR] Step 5/6 — Saving model...")
    save_dir  = os.path.join(settings.BASE_DIR, "power", "ml", "models", "saved")
    save_path = os.path.join(save_dir, "state_CG_1hour.pkl")
    joblib.dump(model, save_path)
    size_mb = os.path.getsize(save_path) / (1024 * 1024)
    print(f"   Saved -> {save_path}  ({size_mb:.1f} MB)")

    return model
