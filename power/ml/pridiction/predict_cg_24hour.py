"""
power/ml/pridiction/predict_cg_24hour.py
------------------------------------------
Predicts next 30 days daily Chhattisgarh demand.

Usage:
    from power.ml.pridiction.predict_cg_24hour import predict_cg_24hour
    result = predict_cg_24hour(days=30)
    # returns DataFrame: ds, predicted_mw, temperature_c  (30 rows)
"""

import os, joblib, pandas as pd, numpy as np
from datetime import date, timedelta
from django.conf import settings


def _get_season(m):
    if m in [12,1,2]: return 1
    if m in [3,4,5]:  return 2
    if m in [6,7,8,9]:return 3
    return 4


def predict_cg_24hour(days: int = 30, anchor_date: str = None) -> pd.DataFrame:
    from power.models import ChhattsgarhLoad5Min, ChhattsgarhWeather5Min

    model_path = os.path.join(settings.BASE_DIR, "power", "ml", "models", "saved", "state_CG_24hour.pkl")
    if not os.path.exists(model_path):
        raise FileNotFoundError(f"Model not found: {model_path}\nRun: python manage.py train_cg_all_models --horizon 24hour")
    model = joblib.load(model_path)

    if anchor_date is None:
        anchor_dt = pd.Timestamp(date.today())
    else:
        anchor_dt = pd.Timestamp(anchor_date)

    start_date = anchor_dt + pd.Timedelta(days=1)
    end_date   = anchor_dt + pd.Timedelta(days=days)

    # Build daily grid
    df = pd.DataFrame({"ds": pd.date_range(start_date, end_date, freq="D")})
    df["mmdd"] = df["ds"].dt.strftime("%m-%d")

    # Historical daily profile
    hist_demand = pd.DataFrame(
        ChhattsgarhLoad5Min.objects.order_by("datetime").values("datetime","demand_mw")
    )
    hist_demand["datetime"] = pd.to_datetime(hist_demand["datetime"])
    hist_daily = (
        hist_demand.set_index("datetime")
        .resample("D")
        .agg(y=("demand_mw","mean"), peak_mw=("demand_mw","max"), min_mw=("demand_mw","min"))
        .reset_index().rename(columns={"datetime":"ds"})
    )
    hist_daily["mmdd"] = hist_daily["ds"].dt.strftime("%m-%d")
    profile = hist_daily.groupby("mmdd")["y"].mean().reset_index().rename(columns={"y":"profile_y"})
    df = df.merge(profile, on="mmdd", how="left")
    df["profile_y"] = df["profile_y"].ffill().bfill()

    # Recent demand lags (from last known data before the start date)
    hist_before = hist_daily[hist_daily["ds"] < start_date]
    if hist_before.empty:
        hist_before = hist_daily
    last_days = hist_before.tail(30).copy()
    recent_y  = last_days["y"].values

    # Weather: use same calendar day from last year as forecast
    hist_weather = pd.DataFrame(
        ChhattsgarhWeather5Min.objects.order_by("datetime")
        .values("datetime","temperature_c","humidity_pct","rain_mm","wind_speed_ms")
    )
    hist_weather["datetime"] = pd.to_datetime(hist_weather["datetime"])
    hist_weather_daily = (
        hist_weather.set_index("datetime")
        .resample("D")
        .agg(temperature_c=("temperature_c","mean"), max_temp=("temperature_c","max"),
             min_temp=("temperature_c","min"), humidity_pct=("humidity_pct","mean"),
             rain_mm=("rain_mm","sum"), wind_speed_ms=("wind_speed_ms","mean"))
        .reset_index().rename(columns={"datetime":"ds"})
    )
    hist_weather_daily["mmdd"] = hist_weather_daily["ds"].dt.strftime("%m-%d")
    weather_profile = (
        hist_weather_daily.groupby("mmdd")
        .agg(temperature_c=("temperature_c","mean"), max_temp=("max_temp","mean"),
             min_temp=("min_temp","mean"), humidity_pct=("humidity_pct","mean"),
             rain_mm=("rain_mm","mean"), wind_speed_ms=("wind_speed_ms","mean"))
        .reset_index()
    )
    df = df.merge(weather_profile, on="mmdd", how="left")
    for col in ["temperature_c","max_temp","min_temp","humidity_pct","rain_mm","wind_speed_ms"]:
        df[col] = df[col].ffill().bfill().fillna(0)

    # Features
    df["month"]     = df["ds"].dt.month
    df["dayofweek"] = df["ds"].dt.dayofweek
    df["is_weekend"]= df["dayofweek"].isin([5,6]).astype(int)
    df["is_holiday"]= 0
    df["dayofyear"] = df["ds"].dt.dayofyear
    df["season"]    = df["month"].map(_get_season)

    # Peak/min from profile
    peak_profile = hist_daily.groupby("mmdd")["peak_mw"].mean().reset_index().rename(columns={"peak_mw":"peak_mw_p"})
    min_profile  = hist_daily.groupby("mmdd")["min_mw"].mean().reset_index().rename(columns={"min_mw":"min_mw_p"})
    df = df.merge(peak_profile, on="mmdd", how="left").rename(columns={"peak_mw_p":"peak_mw"})
    df = df.merge(min_profile,  on="mmdd", how="left").rename(columns={"min_mw_p":"min_mw"})
    df["peak_mw"] = df["peak_mw"].ffill().bfill()
    df["min_mw"]  = df["min_mw"].ffill().bfill()

    # Predict iteratively (use previous prediction as lag)
    predictions = []
    lag_buffer  = list(recent_y)   # last 30 known daily values

    for i, row in df.iterrows():
        lag_vals = lag_buffer[-30:] if len(lag_buffer) >= 30 else [lag_buffer[0]] * 30
        features = {
            "temperature_c": row["temperature_c"], "max_temp": row["max_temp"],
            "min_temp": row["min_temp"], "humidity_pct": row["humidity_pct"],
            "rain_mm": row["rain_mm"], "wind_speed_ms": row["wind_speed_ms"],
            "month": row["month"], "dayofweek": row["dayofweek"],
            "is_weekend": row["is_weekend"], "is_holiday": 0,
            "dayofyear": row["dayofyear"], "season": row["season"],
            "profile_y": row["profile_y"], "peak_mw": row["peak_mw"], "min_mw": row["min_mw"],
            "y_lag_1": lag_vals[-1],  "y_lag_2": lag_vals[-2],
            "y_lag_3": lag_vals[-3],  "y_lag_4": lag_vals[-4],
            "y_lag_5": lag_vals[-5],  "y_lag_6": lag_vals[-6],
            "y_lag_7": lag_vals[-7],
            "y_lag_7d": lag_vals[-7],
            "y_lag_14d": lag_vals[-14] if len(lag_vals)>=14 else lag_vals[0],
            "y_lag_30d": lag_vals[-30] if len(lag_vals)>=30 else lag_vals[0],
            "roll_7d_mean":  np.mean(lag_vals[-7:]),
            "roll_7d_max":   np.max(lag_vals[-7:]),
            "roll_30d_mean": np.mean(lag_vals[-30:]),
        }
        X_row = pd.DataFrame([features])[model.feature_cols]
        pred  = float(model.predict(X_row)[0])
        predictions.append(pred)
        lag_buffer.append(pred)

    df["predicted_mw"] = predictions
    print(f"[CG 24HR PREDICT] {days}-day forecast  Peak={max(predictions):.1f} Avg={np.mean(predictions):.1f} MW")
    return df[["ds","predicted_mw","temperature_c"]].reset_index(drop=True)
