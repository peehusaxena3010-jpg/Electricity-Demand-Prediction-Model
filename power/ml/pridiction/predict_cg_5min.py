"""
power/ml/pridiction/predict_cg_5min.py
-----------------------------------------
Predicts 5-minute Chhattisgarh demand for a given date.

Uses:
  - Trained model: power/ml/models/saved/state_5min_CG.pkl
  - Historical profile: ChhattsgarhLoad5Min (same month-day slots)
  - Live weather: ChhattsgarhWeather5Min

Usage:
    from power.ml.pridiction.predict_cg_5min import predict_cg_5min
    result = predict_cg_5min("2026-06-10")
    # returns DataFrame with columns: ds, predicted_mw, temperature_c
"""

import os
import joblib
import pandas as pd
from datetime import timedelta

from django.conf import settings


# ─────────────────────────────────────────────────────────────────────────────
# HELPERS (same as training)
# ─────────────────────────────────────────────────────────────────────────────

def _add_calendar_features(df):
    df = df.copy()
    df["month"]      = df["ds"].dt.month
    df["is_weekend"] = df["ds"].dt.dayofweek.isin([5, 6]).astype(int)
    df["is_holiday"] = 0

    def get_season(m):
        if m in [12, 1, 2]:    return 1
        if m in [3, 4, 5]:     return 2
        if m in [6, 7, 8, 9]:  return 3
        return 4

    df["season"] = df["month"].map(get_season)
    return df


def _add_peak_features(df):
    df = df.copy()
    df["hour"]            = df["ds"].dt.hour
    df["is_peak"]         = df["hour"].between(18, 23).astype(int)
    df["temp_x_hour"]     = df["temperature_c"] * df["hour"]
    df["humidity_x_hour"] = df["humidity_pct"]  * df["hour"]
    df["wind_x_hour"]     = df["wind_speed_ms"] * df["hour"]
    return df


# ─────────────────────────────────────────────────────────────────────────────
# MAIN PREDICTION FUNCTION
# ─────────────────────────────────────────────────────────────────────────────

def predict_cg_5min(forecast_date: str) -> pd.DataFrame:
    """
    Predict Chhattisgarh 5-min demand for a given date.

    Args:
        forecast_date: Date string like "2026-06-10"

    Returns:
        DataFrame with columns: ds, predicted_mw, temperature_c
        288 rows (one per 5-min slot in a day)
    """
    from power.models import ChhattsgarhLoad5Min, ChhattsgarhWeather5Min

    # ── Load model ────────────────────────────────────────────────────────────
    model_path = os.path.join(
        settings.BASE_DIR, "power", "ml", "models", "saved", "state_5min_CG.pkl"
    )
    if not os.path.exists(model_path):
        raise FileNotFoundError(
            f"Model not found: {model_path}\n"
            "Run: python manage.py train_cg_model"
        )
    model = joblib.load(model_path)

    forecast_date = pd.to_datetime(forecast_date).normalize()

    # ── Build 288-slot time grid (full day) ───────────────────────────────────
    df = pd.DataFrame({
        "ds": pd.date_range(
            forecast_date,
            forecast_date + timedelta(days=1) - timedelta(minutes=5),
            freq="5min",
        )
    })
    df["slot"] = df["ds"].dt.hour * 12 + df["ds"].dt.minute // 5
    df["mmdd"] = df["ds"].dt.strftime("%m-%d")

    # ── Historical profile: same month-day from past years ───────────────────
    hist = pd.DataFrame(
        ChhattsgarhLoad5Min.objects
        .filter(
            datetime__month=forecast_date.month,
            datetime__day=forecast_date.day,
        )
        .values("datetime", "demand_mw")
    )

    if hist.empty:
        raise ValueError(
            f"No historical data for {forecast_date.strftime('%b %d')}. "
            "Cannot build demand profile."
        )

    hist["datetime"] = pd.to_datetime(hist["datetime"])
    hist["slot"]     = hist["datetime"].dt.hour * 12 + hist["datetime"].dt.minute // 5

    # IQR-based outlier removal
    Q1 = hist["demand_mw"].quantile(0.25)
    Q3 = hist["demand_mw"].quantile(0.75)
    IQR = Q3 - Q1
    hist = hist[
        (hist["demand_mw"] >= Q1 - 1.5 * IQR) &
        (hist["demand_mw"] <= Q3 + 1.5 * IQR)
    ]

    profile = (
        hist.groupby("slot")["demand_mw"]
        .median()
        .reset_index()
        .rename(columns={"demand_mw": "profile_y"})
    )
    df = df.merge(profile, on="slot", how="left")
    df["profile_y"] = df["profile_y"].interpolate().ffill().bfill()

    # ── Weather for forecast date ─────────────────────────────────────────────
    weather = pd.DataFrame(
        ChhattsgarhWeather5Min.objects
        .filter(datetime__date=forecast_date.date())
        .order_by("datetime")
        .values("datetime", "temperature_c", "humidity_pct", "rain_mm", "wind_speed_ms")
    )

    if weather.empty:
        # Fall back to same day last year
        fallback = forecast_date - timedelta(days=365)
        weather = pd.DataFrame(
            ChhattsgarhWeather5Min.objects
            .filter(datetime__date=fallback.date())
            .order_by("datetime")
            .values("datetime", "temperature_c", "humidity_pct", "rain_mm", "wind_speed_ms")
        )

    if not weather.empty:
        weather["datetime"] = pd.to_datetime(weather["datetime"])
        weather["slot"]     = weather["datetime"].dt.hour * 12 + weather["datetime"].dt.minute // 5
        weather = weather.rename(columns={"datetime": "ds"})
        df = pd.merge_asof(
            df.sort_values("ds"),
            weather.sort_values("ds"),
            on="ds",
            direction="nearest",
            tolerance=pd.Timedelta("30min"),
        )
    else:
        # Last resort: use mean weather from entire dataset
        from django.db.models import Avg
        avg = ChhattsgarhWeather5Min.objects.aggregate(
            t=Avg("temperature_c"), h=Avg("humidity_pct"),
            r=Avg("rain_mm"),       w=Avg("wind_speed_ms"),
        )
        df["temperature_c"] = avg["t"] or 25.0
        df["humidity_pct"]  = avg["h"] or 60.0
        df["rain_mm"]       = avg["r"] or 0.0
        df["wind_speed_ms"] = avg["w"] or 2.0

    for col in ["temperature_c", "humidity_pct", "rain_mm", "wind_speed_ms"]:
        df[col] = df[col].ffill().bfill().fillna(0)

    # ── Features ──────────────────────────────────────────────────────────────
    df = _add_calendar_features(df)
    df = _add_peak_features(df)

    # ── Autoregressive Lags & Prediction ──────────────────────────────────────
    # Fetch actual demand for the forecast date
    actual_qs = ChhattsgarhLoad5Min.objects.filter(datetime__date=forecast_date.date()).order_by("datetime")
    actual_dict = {pd.to_datetime(obj.datetime).floor("5min"): obj.demand_mw for obj in actual_qs}

    # Initialize buffer for lags
    y_buffer = [None] * len(df)
    predicted_mw = []

    # Initialize columns to avoid pandas warnings
    for i in range(1, 7):
        df[f"y_lag_{i}"] = df["profile_y"]
    df["y_lag_24h"] = df["profile_y"]
    df["y_lag_7d"]  = df["profile_y"]

    for idx, row in df.iterrows():
        # Check if actual demand exists for this slot
        actual_val = actual_dict.get(pd.to_datetime(row["ds"]))
        if actual_val is not None:
            y_buffer[idx] = actual_val

        # Populate lag features dynamically
        for i in range(1, 7):
            if idx - i >= 0 and y_buffer[idx - i] is not None:
                df.at[idx, f"y_lag_{i}"] = y_buffer[idx - i]

        # Check for missing features
        X_row = df.loc[[idx], model.feature_cols]
        
        # Predict
        pred = float(model.predict(X_row)[0])
        predicted_mw.append(pred)

        # If it's a future slot, store the prediction as a lag proxy
        if y_buffer[idx] is None:
            y_buffer[idx] = pred

    df["predicted_mw"] = predicted_mw

    print(f"[CG PREDICT] {forecast_date.date()}  "
          f"Peak={df['predicted_mw'].max():.1f} MW  "
          f"Min={df['predicted_mw'].min():.1f} MW  "
          f"Avg={df['predicted_mw'].mean():.1f} MW")

    return df[["ds", "predicted_mw", "temperature_c"]].reset_index(drop=True)
