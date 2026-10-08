"""
power/ml/pridiction/predict_cg_1hour.py
-----------------------------------------
Predicts next 24 hourly Chhattisgarh demand slots.

Usage:
    from power.ml.pridiction.predict_cg_1hour import predict_cg_1hour
    result = predict_cg_1hour("2026-06-10")
    # returns DataFrame: ds, predicted_mw, temperature_c  (24 rows)
"""

import os, joblib, pandas as pd
from datetime import timedelta
from django.conf import settings


def _get_season(m):
    if m in [12,1,2]: return 1
    if m in [3,4,5]:  return 2
    if m in [6,7,8,9]:return 3
    return 4


def predict_cg_1hour(forecast_date: str) -> pd.DataFrame:
    from power.models import ChhattsgarhLoad5Min, ChhattsgarhWeather5Min

    model_path = os.path.join(settings.BASE_DIR, "power", "ml", "models", "saved", "state_CG_1hour.pkl")
    if not os.path.exists(model_path):
        raise FileNotFoundError(f"Model not found: {model_path}\nRun: python manage.py train_cg_all_models --horizon 1hour")
    model = joblib.load(model_path)

    forecast_date = pd.to_datetime(forecast_date).normalize()

    # 24-slot time grid
    df = pd.DataFrame({"ds": pd.date_range(forecast_date, periods=24, freq="1h")})
    df["slot"] = df["ds"].dt.hour
    df["mmdd"] = df["ds"].dt.strftime("%m-%d")

    # Historical profile (same month-day from past)
    hist = pd.DataFrame(
        ChhattsgarhLoad5Min.objects
        .filter(datetime__month=forecast_date.month, datetime__day=forecast_date.day)
        .values("datetime", "demand_mw")
    )
    if hist.empty:
        raise ValueError(f"No historical data for {forecast_date.strftime('%b %d')}")

    hist["datetime"] = pd.to_datetime(hist["datetime"])
    hist = hist.set_index("datetime").resample("1h").mean().reset_index()
    hist["slot"] = hist["datetime"].dt.hour
    profile = hist.groupby("slot")["demand_mw"].median().reset_index().rename(columns={"demand_mw": "profile_y"})
    df = df.merge(profile, on="slot", how="left")
    df["profile_y"] = df["profile_y"].ffill().bfill()

    # Weather
    weather = pd.DataFrame(
        ChhattsgarhWeather5Min.objects
        .filter(datetime__date=forecast_date.date())
        .order_by("datetime")
        .values("datetime", "temperature_c", "humidity_pct", "rain_mm", "wind_speed_ms")
    )
    if weather.empty:
        fallback = forecast_date - timedelta(days=365)
        weather = pd.DataFrame(
            ChhattsgarhWeather5Min.objects
            .filter(datetime__date=fallback.date())
            .order_by("datetime")
            .values("datetime", "temperature_c", "humidity_pct", "rain_mm", "wind_speed_ms")
        )
    if not weather.empty:
        weather["datetime"] = pd.to_datetime(weather["datetime"])
        weather = weather.set_index("datetime").resample("1h").mean().reset_index().rename(columns={"datetime": "ds"})
        df = pd.merge_asof(df.sort_values("ds"), weather.sort_values("ds"), on="ds", direction="nearest", tolerance=pd.Timedelta("1h"))
    else:
        from django.db.models import Avg
        avg = ChhattsgarhWeather5Min.objects.aggregate(t=Avg("temperature_c"), h=Avg("humidity_pct"), r=Avg("rain_mm"), w=Avg("wind_speed_ms"))
        df["temperature_c"] = avg["t"] or 25.0; df["humidity_pct"] = avg["h"] or 60.0
        df["rain_mm"] = avg["r"] or 0.0; df["wind_speed_ms"] = avg["w"] or 2.0

    for col in ["temperature_c","humidity_pct","rain_mm","wind_speed_ms"]:
        df[col] = df[col].ffill().bfill().fillna(0)

    # Features
    df["month"]           = df["ds"].dt.month
    df["is_weekend"]      = df["ds"].dt.dayofweek.isin([5,6]).astype(int)
    df["is_holiday"]      = 0
    df["season"]          = df["month"].map(_get_season)
    df["hour"]            = df["ds"].dt.hour
    df["is_peak"]         = df["hour"].between(18,23).astype(int)
    df["temp_x_hour"]     = df["temperature_c"] * df["hour"]
    df["humidity_x_hour"] = df["humidity_pct"]  * df["hour"]
    df["wind_x_hour"]     = df["wind_speed_ms"] * df["hour"]
    # ── Autoregressive Lags & Prediction ──────────────────────────────────────
    # Fetch actual demand for the forecast date (resampled to hourly averages)
    actual_qs = ChhattsgarhLoad5Min.objects.filter(datetime__date=forecast_date.date()).order_by("datetime")
    actual_df = pd.DataFrame(list(actual_qs.values("datetime", "demand_mw")))
    actual_dict = {}
    if not actual_df.empty:
        actual_df["datetime"] = pd.to_datetime(actual_df["datetime"])
        actual_hourly = actual_df.set_index("datetime").resample("1h").mean().reset_index()
        actual_dict = {pd.to_datetime(row["datetime"]): row["demand_mw"] for _, row in actual_hourly.iterrows()}

    # Initialize buffer for lags
    y_buffer = [None] * len(df)
    predicted_mw = []

    # Initialize columns to avoid pandas warnings
    for i in range(1, 7):
        df[f"y_lag_{i}"] = df["profile_y"]
    df["y_lag_24h"] = df["profile_y"]
    df["y_lag_7d"]  = df["profile_y"]

    for idx, row in df.iterrows():
        # Check if actual demand exists for this hour
        actual_val = actual_dict.get(pd.to_datetime(row["ds"]))
        if actual_val is not None and not pd.isna(actual_val):
            y_buffer[idx] = actual_val

        # Populate lag features dynamically
        for i in range(1, 7):
            if idx - i >= 0 and y_buffer[idx - i] is not None:
                df.at[idx, f"y_lag_{i}"] = y_buffer[idx - i]

        X_row = df.loc[[idx], model.feature_cols]
        
        # Predict
        pred = float(model.predict(X_row)[0])
        predicted_mw.append(pred)

        # If it's a future hour, store the prediction as a lag proxy
        if y_buffer[idx] is None:
            y_buffer[idx] = pred

    df["predicted_mw"] = predicted_mw
    print(f"[CG 1HR PREDICT] {forecast_date.date()} Peak={df['predicted_mw'].max():.1f} Avg={df['predicted_mw'].mean():.1f} MW")
    return df[["ds","predicted_mw","temperature_c"]].reset_index(drop=True)
