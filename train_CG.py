# train_cg_standalone.py
# Run this from NVVN-backend root:
# python train_cg_standalone.py

import os
import pandas as pd
import numpy as np
from datetime import datetime
from sklearn.model_selection import train_test_split
from sklearn.metrics import mean_absolute_percentage_error
import xgboost as xgb
import joblib

# ─────────────────────────────────────────
# 1. LOAD DATA
# ─────────────────────────────────────────
print("Loading CG load data...")
load_df = pd.read_excel("Demand_2023_2026_Fixed.xlsx")
load_df = load_df.rename(columns={
    "Datetime":  "ds",
    "Demand_MW": "load_mw"
})
load_df["ds"] = pd.to_datetime(load_df["ds"])
load_df = load_df.sort_values("ds").reset_index(drop=True)
print(f"Load data: {load_df.shape}")
print(f"Date range: {load_df['ds'].min()} → {load_df['ds'].max()}")
print(f"Load range: {load_df['load_mw'].min():.0f} to {load_df['load_mw'].max():.0f} MW")

# ─────────────────────────────────────────
# 2. MERGE LOAD + WEATHER
# ─────────────────────────────────────────
print("\nMerging load + weather...")
weather_df = pd.read_csv("cg_weather_combined.csv", parse_dates=["datetime"])
weather_df = weather_df.rename(columns={"datetime": "ds"})
weather_df["ds"] = pd.to_datetime(weather_df["ds"]).dt.tz_localize(None)
df = pd.merge_asof(
    load_df.sort_values("ds"),
    weather_df[["ds","temperature_c","humidity_pct","wind_speed_ms","rain_mm"]].sort_values("ds"),
    on="ds",
    direction="nearest",
    tolerance=pd.Timedelta("10min"),
)
print(f"Merged shape: {df.shape}")
print(f"Weather nulls after merge: {df['temperature_c'].isna().sum()}")
df["temp_change_1h"] = (
    df["temperature_c"]
    - df["temperature_c"].shift(12)
)

df["humidity_change_1h"] = (
    df["humidity_pct"]
    - df["humidity_pct"].shift(12)
)

df["rain_last_6h"] = (
    df["rain_mm"]
    .rolling(72)
    .sum()
)


# ─────────────────────────────────────────
# 3. TARGET VARIABLE
# ─────────────────────────────────────────
HORIZONS = {
    "5min": 1,
    "1hour": 12,
    "3hour": 36,
    "24hour": 288,
}

FORECAST_HORIZON = 12  # 1 hour model

df["y"] = df["load_mw"].shift(-FORECAST_HORIZON)
df = df.dropna(subset=["y"])

# ─────────────────────────────────────────
# 4. TIME FEATURES
# ─────────────────────────────────────────
print("\nBuilding features...")
df["slot"]         = df["ds"].dt.hour * 12 + df["ds"].dt.minute // 5
df["hour"]         = df["ds"].dt.hour
df["minute"]       = df["ds"].dt.minute
df["day_of_week"]  = df["ds"].dt.dayofweek      # 0=Mon, 6=Sun
df["month"]        = df["ds"].dt.month
df["day_of_month"] = df["ds"].dt.day
df["quarter"]      = df["ds"].dt.quarter
df["is_weekend"]   = (df["day_of_week"] >= 5).astype(int)
df["mmdd"]         = df["ds"].dt.strftime("%m-%d")

# ─────────────────────────────────────────
# 5. CG-SPECIFIC FEATURES
# ─────────────────────────────────────────

# Agricultural season — irrigation pump load
def agri_season(month):
    if month in [6, 7, 11, 12]:  # Kharif sowing + Rabi sowing
        return 2
    elif month in [3, 4, 10]:    # harvest months
        return 1
    else:
        return 0

df["agri_season"] = df["month"].apply(agri_season)

# Peak hours (evening peak in CG)
df["is_peak"] = df["hour"].between(18, 23).astype(int)

# Heatwave flag (CG summers brutal)
df["is_heatwave"] = (df["temperature_c"] > 42).astype(int)

# Interaction features
df["temp_x_hour"]     = df["temperature_c"] * df["hour"]
df["humidity_x_hour"] = df["humidity_pct"]   * df["hour"]

# ─────────────────────────────────────────
# 6. HOLIDAY FEATURES
# ─────────────────────────────────────────
# National + CG state holidays 2023-2026
CG_HOLIDAYS = [
    # 2023
    "2023-01-26","2023-03-07","2023-03-30","2023-04-14",
    "2023-08-15","2023-10-02","2023-10-24","2023-11-01",
    "2023-11-13","2023-12-25",
    # 2024
    "2024-01-26","2024-03-25","2024-04-14","2024-04-17",
    "2024-08-15","2024-10-02","2024-10-12","2024-11-01",
    "2024-11-15","2024-12-25",
    # 2025
    "2025-01-26","2025-03-14","2025-04-14","2025-08-15",
    "2025-10-02","2025-10-02","2025-11-01","2025-12-25",
    # 2026
    "2026-01-26","2026-03-03","2026-04-14","2026-08-15",
]
holidays_set = set(pd.to_datetime(CG_HOLIDAYS).strftime("%Y-%m-%d"))
df["is_holiday"] = df["ds"].dt.strftime("%Y-%m-%d").isin(holidays_set).astype(int)

# ─────────────────────────────────────────
# 7. PROFILE FEATURE (historical median)
# ─────────────────────────────────────────
profile = (
    df.groupby(["mmdd", "slot"])["y"]
    .median()
    .reset_index()
    .rename(columns={"y": "profile_y"})
)
df = df.merge(profile, on=["mmdd", "slot"], how="left")

# ─────────────────────────────────────────
# 8. LAG FEATURES
# ─────────────────────────────────────────
print("Building lag features...")
df = df.sort_values("ds").reset_index(drop=True)

df["y_lag_1"] = df["y"].shift(1)
df["y_lag_3"] = df["y"].shift(3)
df["y_lag_6"] = df["y"].shift(6)

df["y_lag_1h"] = df["y"].shift(12)
df["y_lag_3h"] = df["y"].shift(36)
df["y_lag_6h"] = df["y"].shift(72)

df["y_lag_24h"] = df["y"].shift(288)
df["y_lag_48h"] = df["y"].shift(576)

df["y_lag_7d"] = df["y"].shift(2016)

# Rolling averages
df["rolling_mean_7d"] = df["y"].shift(1).rolling(2016).mean()
df["rolling_std_7d"]  = df["y"].shift(1).rolling(2016).std()

df["hour_sin"] = np.sin(2 * np.pi * df["hour"] / 24)
df["hour_cos"] = np.cos(2 * np.pi * df["hour"] / 24)

df["dow_sin"] = np.sin(2 * np.pi * df["day_of_week"] / 7)
df["dow_cos"] = np.cos(2 * np.pi * df["day_of_week"] / 7)

df["month_sin"] = np.sin(2 * np.pi * df["month"] / 12)
df["month_cos"] = np.cos(2 * np.pi * df["month"] / 12)

# ─────────────────────────────────────────
# 9. OUTLIER REMOVAL
# ─────────────────────────────────────────
Q1 = df["y"].quantile(0.25)
Q3 = df["y"].quantile(0.75)
IQR = Q3 - Q1
df = df[(df["y"] >= Q1 - 1.5*IQR) & (df["y"] <= Q3 + 1.5*IQR)]

# ─────────────────────────────────────────
# 10. SAMPLE WEIGHTS (peak hours weighted more)
# ─────────────────────────────────────────
df["sample_weight"] = df["is_peak"].map({1: 3.0, 0: 1.0})

# ─────────────────────────────────────────
# 11. DROP NULLS
# ─────────────────────────────────────────
df = df.dropna().reset_index(drop=True)
print(f"\nFinal training rows: {len(df)}")
print(f"Columns: {df.shape[1]}")

# ─────────────────────────────────────────
# 12. DEFINE FEATURES
# ─────────────────────────────────────────
FEATURE_COLS = [
    # time
    "slot", "hour", "minute", "day_of_week",
    "month", "day_of_month", "quarter",
    "is_weekend", "is_holiday",
    # CG specific
    "agri_season", "is_peak", "is_heatwave",
    # weather
    "temperature_c", "humidity_pct",
    "wind_speed_ms", "rain_mm",
    "temp_x_hour", "humidity_x_hour",
    # profile
    "profile_y",
    # lags
    "y_lag_1", "y_lag_2", "y_lag_3", "y_lag_6",
    "y_lag_24h", "y_lag_7d",
    "rolling_mean_7d", "rolling_std_7d",
]

X = df[FEATURE_COLS]
y = df["y"]
w = df["sample_weight"]

# ─────────────────────────────────────────
# 13. TRAIN / TEST SPLIT (time-based)
# ─────────────────────────────────────────
# Last 30 days = test, rest = train
split_date = df["ds"].max() - pd.Timedelta(days=30)
train_mask = df["ds"] <= split_date

X_train, X_test = X[train_mask], X[~train_mask]
y_train, y_test = y[train_mask], y[~train_mask]
w_train         = w[train_mask]

print(f"\nTrain: {len(X_train)} rows | Test: {len(X_test)} rows")

# ─────────────────────────────────────────
# 14. TRAIN XGBOOST
# ─────────────────────────────────────────

print("\nTraining XGBoost...")
model = xgb.XGBRegressor(
    n_estimators=1000,
    learning_rate=0.05,
    max_depth=6,
    subsample=0.8,
    colsample_bytree=0.8,
    min_child_weight=5,
    random_state=42,
    n_jobs=-1,
    early_stopping_rounds=50,
    eval_metric="mae",
)
for name, horizon in {
    "5min": 1,
    "1hour": 12,
    "3hour": 36,
    "24hour": 288,
}.items():

    print(f"\nTraining {name}")

    temp_df = df.copy()

    temp_df["y"] = (
        temp_df["load_mw"]
        .shift(-horizon)
    )

    temp_df = temp_df.dropna()

    # train exactly same way

    joblib.dump(
        model,
        f"power/ml/models/saved/state_CG_{name}.pkl"
    )

model.fit(
    X_train, y_train,
    sample_weight=w_train,
    eval_set=[(X_test, y_test)],
    verbose=100,
)

# ─────────────────────────────────────────
# 15. EVALUATE
# ─────────────────────────────────────────
y_pred = model.predict(X_test)
mape = mean_absolute_percentage_error(y_test, y_pred) * 100
mae  = abs(y_test.values - y_pred).mean()

print(f"\n{'='*40}")
print(f"MAPE : {mape:.2f}%")
print(f"MAE  : {mae:.2f} MW")
print(f"{'='*40}")

if mape < 5:
    print("✓ Excellent — production ready")
elif mape < 10:
    print("~ Acceptable — can improve with more data")
else:
    print("✗ Needs work — check data quality")

# ─────────────────────────────────────────
# 16. SAVE MODEL
# ─────────────────────────────────────────
model.feature_cols = FEATURE_COLS  # attach so predict script knows

os.makedirs("power/ml/models/saved", exist_ok=True)
joblib.dump(model, "power/ml/models/saved/state_5min_CG.pkl")
print("\nModel saved → power/ml/models/saved/state_5min_CG.pkl")