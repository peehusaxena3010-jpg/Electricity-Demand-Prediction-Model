"""
power/ml/trainy/train_cg_24hour.py
------------------------------------
Trains XGBoost 24-hour (daily) demand forecast model for Chhattisgarh.

Aggregates 5-min data → daily intervals.
Output: power/ml/models/saved/state_CG_24hour.pkl
"""

import os
import pandas as pd


def add_calendar_features(df):
    df = df.copy()
    df["month"]      = df["ds"].dt.month
    df["dayofweek"]  = df["ds"].dt.dayofweek
    df["is_weekend"] = df["dayofweek"].isin([5, 6]).astype(int)
    df["is_holiday"] = 0
    df["dayofyear"]  = df["ds"].dt.dayofyear

    def get_season(m):
        if m in [12, 1, 2]:    return 1
        if m in [3, 4, 5]:     return 2
        if m in [6, 7, 8, 9]:  return 3
        return 4

    df["season"] = df["month"].map(get_season)
    return df


def add_sample_weight(df):
    # Weight recent data more (last 6 months gets 2x)
    max_date = df["ds"].max()
    cutoff   = max_date - pd.Timedelta(days=180)
    df["sample_weight"] = df["ds"].apply(lambda x: 2.0 if x >= cutoff else 1.0)
    return df


def clean_outliers(df):
    df = df.copy().set_index("ds")
    mu, sigma = df["y"].mean(), df["y"].std()
    df.loc[(df["y"] - mu).abs() > 3 * sigma, "y"] = None
    df["y"] = df["y"].interpolate().bfill().ffill()
    return df.reset_index()


def train_cg_24hour_model():
    from power.models import ChhattsgarhLoad5Min, ChhattsgarhWeather5Min
    from django.conf import settings
    from xgboost import XGBRegressor
    import joblib

    # ── 1. Load + aggregate demand to daily ───────────────────────────────────
    print("[CG 24HR] Step 1/6 — Loading & aggregating demand to daily...")
    raw = pd.DataFrame(
        ChhattsgarhLoad5Min.objects.order_by("datetime").values("datetime", "demand_mw")
    )
    raw["datetime"] = pd.to_datetime(raw["datetime"])
    raw = raw.rename(columns={"datetime": "ds", "demand_mw": "y"})

    df = (
        raw.set_index("ds")
        .resample("D")
        .agg(
            y=("y", "mean"),
            peak_mw=("y", "max"),
            min_mw=("y", "min"),
        )
        .interpolate()
        .reset_index()
    )
    print(f"   Daily rows: {len(df):,}  ({df['ds'].min().date()} -> {df['ds'].max().date()})")

    # ── 2. Load + aggregate weather to daily ──────────────────────────────────
    print("[CG 24HR] Step 2/6 — Loading & aggregating weather to daily...")
    weather = pd.DataFrame(
        ChhattsgarhWeather5Min.objects.order_by("datetime")
        .values("datetime", "temperature_c", "humidity_pct", "rain_mm", "wind_speed_ms")
    )
    weather["datetime"] = pd.to_datetime(weather["datetime"])
    weather = (
        weather.set_index("datetime")
        .resample("D")
        .agg(
            temperature_c=("temperature_c", "mean"),
            max_temp=("temperature_c", "max"),
            min_temp=("temperature_c", "min"),
            humidity_pct=("humidity_pct", "mean"),
            rain_mm=("rain_mm", "sum"),
            wind_speed_ms=("wind_speed_ms", "mean"),
        )
        .interpolate()
        .reset_index()
        .rename(columns={"datetime": "ds"})
    )

    # ── 3. Merge ───────────────────────────────────────────────────────────────
    df = pd.merge(df, weather, on="ds", how="left")
    for col in ["temperature_c", "max_temp", "min_temp", "humidity_pct", "rain_mm", "wind_speed_ms"]:
        df[col] = df[col].ffill().bfill().fillna(0)

    # ── 4. Features ────────────────────────────────────────────────────────────
    print("[CG 24HR] Step 3/6 — Engineering features...")
    df = add_calendar_features(df)

    df["mmdd"] = df["ds"].dt.strftime("%m-%d")
    profile = (
        df.groupby("mmdd")["y"].mean()
        .reset_index().rename(columns={"y": "profile_y"})
    )
    df = df.merge(profile, on="mmdd", how="left")
    df = clean_outliers(df)

    # Daily lags
    for i in range(1, 8):
        df[f"y_lag_{i}"] = df["y"].shift(i)         # last 7 days
    df["y_lag_7d"]  = df["y"].shift(7)
    df["y_lag_14d"] = df["y"].shift(14)
    df["y_lag_30d"] = df["y"].shift(30)

    # Rolling features
    df["roll_7d_mean"]  = df["y"].shift(1).rolling(7).mean()
    df["roll_7d_max"]   = df["y"].shift(1).rolling(7).max()
    df["roll_30d_mean"] = df["y"].shift(1).rolling(30).mean()

    df = add_sample_weight(df)
    df = df.dropna().reset_index(drop=True)
    print(f"   Training rows: {len(df):,}")

    # ── 5. Train ───────────────────────────────────────────────────────────────
    print("[CG 24HR] Step 4/6 — Training XGBoost...")
    feature_cols = [
        "temperature_c", "max_temp", "min_temp",
        "humidity_pct", "rain_mm", "wind_speed_ms",
        "month", "dayofweek", "dayofyear",
        "is_weekend", "is_holiday", "season",
        "profile_y", "peak_mw", "min_mw",
        *[f"y_lag_{i}" for i in range(1, 8)],
        "y_lag_7d", "y_lag_14d", "y_lag_30d",
        "roll_7d_mean", "roll_7d_max", "roll_30d_mean",
    ]

    X = df[feature_cols]
    y = df["y"]

    model = XGBRegressor(
        n_estimators=600,
        learning_rate=0.05,
        max_depth=6,
        subsample=0.8,
        colsample_bytree=0.8,
        random_state=42,
        verbosity=0,
    )
    model.fit(X, y, sample_weight=df["sample_weight"])
    model.feature_cols = feature_cols
    model.target_col   = "y"
    print(f"   Training done! Features: {len(feature_cols)}")

    # ── 6. Save ────────────────────────────────────────────────────────────────
    print("[CG 24HR] Step 5/6 — Saving model...")
    save_dir  = os.path.join(settings.BASE_DIR, "power", "ml", "models", "saved")
    save_path = os.path.join(save_dir, "state_CG_24hour.pkl")
    joblib.dump(model, save_path)
    size_mb = os.path.getsize(save_path) / (1024 * 1024)
    print(f"   Saved -> {save_path}  ({size_mb:.1f} MB)")

    return model
