"""
power/ml/trainy/train_cg_5min.py
----------------------------------
Trains an XGBoost 5-minute demand forecast model for Chhattisgarh (CG).

Data source  : ChhattsgarhLoad5Min + ChhattsgarhWeather5Min (our new tables)
Output model : power/ml/models/saved/state_5min_CG.pkl

Run via management command:
    python manage.py train_cg_model
"""

import os
import pandas as pd


# ─────────────────────────────────────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────────────────────────────────────

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
    df.index = pd.to_datetime(df.index)
    mu, sigma = df["y"].mean(), df["y"].std()
    df.loc[(df["y"] - mu).abs() > 3 * sigma, "y"] = None
    df["y"] = df["y"].interpolate().bfill().ffill()
    return df.reset_index()


# ─────────────────────────────────────────────────────────────────────────────
# MAIN TRAINING FUNCTION
# ─────────────────────────────────────────────────────────────────────────────

def train_cg_5min_model():
    """
    Full pipeline: load CG data -> features -> train XGBoost -> save model.
    Returns trained model.
    """
    from power.models import ChhattsgarhLoad5Min, ChhattsgarhWeather5Min
    from power.ml.models.xgb_model import train_xgb_model
    import joblib
    from django.conf import settings

    # ── 1. Load demand ────────────────────────────────────────────────────────
    print("[CG TRAIN] Step 1/6 — Loading demand data...")
    raw = pd.DataFrame(
        ChhattsgarhLoad5Min.objects
        .order_by("datetime")
        .values("datetime", "demand_mw")
    )
    if raw.empty:
        raise ValueError("No data in ChhattsgarhLoad5Min! Run seed command first.")

    raw["datetime"] = pd.to_datetime(raw["datetime"])
    raw = raw.rename(columns={"datetime": "ds", "demand_mw": "y"})
    raw = raw.sort_values("ds").reset_index(drop=True)
    print(f"   Loaded {len(raw):,} rows  "
          f"({raw['ds'].min().date()} -> {raw['ds'].max().date()})")

    # ── 2. Resample to clean 5-min grid ──────────────────────────────────────
    print("[CG TRAIN] Step 2/6 — Resampling to clean 5-min grid...")
    df = (
        raw.set_index("ds")
        .resample("5min")
        .mean()
        .interpolate()
        .reset_index()
    )
    print(f"   Grid rows after resample: {len(df):,}")

    # ── 3. Load weather ───────────────────────────────────────────────────────
    print("[CG TRAIN] Step 3/6 — Loading weather data...")
    weather = pd.DataFrame(
        ChhattsgarhWeather5Min.objects
        .order_by("datetime")
        .values("datetime", "temperature_c", "humidity_pct", "rain_mm", "wind_speed_ms")
    )
    if weather.empty:
        raise ValueError("No data in ChhattsgarhWeather5Min! Run seed command first.")

    weather["datetime"] = pd.to_datetime(weather["datetime"])
    weather = weather.rename(columns={"datetime": "ds"})
    weather = weather.sort_values("ds").drop_duplicates("ds")
    print(f"   Loaded {len(weather):,} weather rows")

    # ── 4. Merge demand + weather ─────────────────────────────────────────────
    df = pd.merge_asof(
        df.sort_values("ds"),
        weather.sort_values("ds"),
        on="ds",
        direction="nearest",
        tolerance=pd.Timedelta("30min"),
    )
    for col in ["temperature_c", "humidity_pct", "rain_mm", "wind_speed_ms"]:
        df[col] = df[col].ffill().bfill().fillna(0)

    # ── 5. Feature engineering ────────────────────────────────────────────────
    print("[CG TRAIN] Step 4/6 — Engineering features...")
    df = add_calendar_features(df)
    df = add_peak_features(df)

    df["slot"] = df["ds"].dt.hour * 12 + df["ds"].dt.minute // 5
    df["mmdd"] = df["ds"].dt.strftime("%m-%d")

    profile = (
        df.groupby(["mmdd", "slot"])["y"]
        .mean()
        .reset_index()
        .rename(columns={"y": "profile_y"})
    )
    df = df.merge(profile, on=["mmdd", "slot"], how="left")

    df = clean_outliers(df)

    for i in range(1, 7):
        df[f"y_lag_{i}"] = df["y"].shift(i)
    df["y_lag_24h"] = df["y"].shift(288)
    df["y_lag_7d"]  = df["y"].shift(2016)

    df = add_sample_weight(df)
    df = df.dropna().reset_index(drop=True)
    print(f"   Training rows: {len(df):,}  |  Columns: {df.shape[1]}")

    # ── 6. Train XGBoost ──────────────────────────────────────────────────────
    print("[CG TRAIN] Step 5/6 — Training XGBoost (this takes 2-5 min)...")
    model = train_xgb_model(df)
    print(f"   Training done!  Features: {model.feature_cols}")

    # ── 7. Save model ─────────────────────────────────────────────────────────
    print("[CG TRAIN] Step 6/6 — Saving model...")
    save_dir  = os.path.join(settings.BASE_DIR, "power", "ml", "models", "saved")
    os.makedirs(save_dir, exist_ok=True)
    save_path = os.path.join(save_dir, "state_5min_CG.pkl")
    joblib.dump(model, save_path)
    size_mb = os.path.getsize(save_path) / (1024 * 1024)
    print(f"   Model saved -> {save_path}  ({size_mb:.1f} MB)")

    return model
