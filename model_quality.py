import joblib
import pandas as pd
import numpy as np

from sklearn.metrics import (
    mean_absolute_error,
    mean_absolute_percentage_error,
    mean_squared_error,
    r2_score,
)

# =========================
# LOAD MODEL
# =========================

MODEL_PATH = "power/ml/models/saved/state_5min_CG.pkl"

model = joblib.load(MODEL_PATH)

print("=" * 60)
print("MODEL LOADED")
print("=" * 60)

# =========================
# LOAD DATA
# =========================

load_df = pd.read_excel("Demand_2023_2026_Fixed.xlsx")

load_df = load_df.rename(
    columns={
        "Datetime": "ds",
        "Demand_MW": "load_mw",
    }
)

load_df["ds"] = pd.to_datetime(load_df["ds"])

weather_df = pd.read_csv(
    "cg_weather_combined.csv",
    parse_dates=["datetime"]
)

weather_df = weather_df.rename(
    columns={"datetime": "ds"}
)

weather_df["ds"] = (
    pd.to_datetime(weather_df["ds"])
    .dt.tz_localize(None)
)

df = pd.merge_asof(
    load_df.sort_values("ds"),
    weather_df[
        [
            "ds",
            "temperature_c",
            "humidity_pct",
            "wind_speed_ms",
            "rain_mm",
        ]
    ].sort_values("ds"),
    on="ds",
    direction="nearest",
    tolerance=pd.Timedelta("10min"),
)

df["y"] = df["load_mw"]

# =========================
# FEATURES
# =========================

df["slot"] = (
    df["ds"].dt.hour * 12
    + df["ds"].dt.minute // 5
)

df["hour"] = df["ds"].dt.hour
df["minute"] = df["ds"].dt.minute
df["day_of_week"] = df["ds"].dt.dayofweek
df["month"] = df["ds"].dt.month
df["day_of_month"] = df["ds"].dt.day
df["quarter"] = df["ds"].dt.quarter

df["is_weekend"] = (
    df["day_of_week"] >= 5
).astype(int)

df["mmdd"] = df["ds"].dt.strftime("%m-%d")

# =========================
# PROFILE
# =========================

profile = (
    df.groupby(["mmdd", "slot"])["y"]
    .median()
    .reset_index()
    .rename(columns={"y": "profile_y"})
)

df = df.merge(
    profile,
    on=["mmdd", "slot"],
    how="left"
)

# =========================
# WEATHER INTERACTIONS
# =========================

df["is_heatwave"] = (
    df["temperature_c"] > 42
).astype(int)

df["temp_x_hour"] = (
    df["temperature_c"] * df["hour"]
)

df["humidity_x_hour"] = (
    df["humidity_pct"] * df["hour"]
)

# =========================
# LAGS
# =========================

df = df.sort_values("ds")

df["y_lag_1"] = df["y"].shift(1)
df["y_lag_2"] = df["y"].shift(2)
df["y_lag_3"] = df["y"].shift(3)
df["y_lag_6"] = df["y"].shift(6)

df["y_lag_24h"] = df["y"].shift(288)
df["y_lag_7d"] = df["y"].shift(2016)

df["rolling_mean_7d"] = (
    df["y"]
    .shift(1)
    .rolling(2016)
    .mean()
)

df["rolling_std_7d"] = (
    df["y"]
    .shift(1)
    .rolling(2016)
    .std()
)

# =========================
# CG FEATURES
# =========================

def agri_season(month):
    if month in [6, 7, 11, 12]:
        return 2
    elif month in [3, 4, 10]:
        return 1
    return 0


df["agri_season"] = (
    df["month"]
    .apply(agri_season)
)

df["is_peak"] = (
    df["hour"]
    .between(18, 23)
).astype(int)

# =========================
# CLEAN
# =========================

df = df.dropna()

# =========================
# FEATURES
# =========================

FEATURE_COLS = model.feature_cols

X = df[FEATURE_COLS]
y = df["y"]

# =========================
# TEST SPLIT
# =========================

split_date = (
    df["ds"].max()
    - pd.Timedelta(days=30)
)

test_mask = (
    df["ds"] > split_date
)

X_test = X[test_mask]
y_test = y[test_mask]

# =========================
# PREDICT
# =========================

y_pred = model.predict(X_test)

# =========================
# METRICS
# =========================

mae = mean_absolute_error(
    y_test,
    y_pred
)

rmse = np.sqrt(
    mean_squared_error(
        y_test,
        y_pred
    )
)

mape = (
    mean_absolute_percentage_error(
        y_test,
        y_pred
    ) * 100
)

r2 = r2_score(
    y_test,
    y_pred
)

# =========================
# NAIVE BASELINE
# =========================

naive_pred = df.loc[
    test_mask,
    "y_lag_1"
]

naive_mae = mean_absolute_error(
    y_test,
    naive_pred
)

naive_mape = (
    mean_absolute_percentage_error(
        y_test,
        naive_pred
    ) * 100
)

# =========================
# RESULTS
# =========================

print("\n")
print("=" * 60)
print("MODEL EVALUATION")
print("=" * 60)

print(f"MAE  : {mae:.2f} MW")
print(f"RMSE : {rmse:.2f} MW")
print(f"MAPE : {mape:.4f}%")
print(f"R²   : {r2:.6f}")

print("\n")

print("=" * 60)
print("NAIVE BASELINE")
print("=" * 60)

print(f"MAE  : {naive_mae:.2f} MW")
print(f"MAPE : {naive_mape:.4f}%")

print("\n")

improvement = (
    (naive_mae - mae)
    / naive_mae
) * 100

print("=" * 60)
print(f"Improvement over naive: {improvement:.2f}%")
print("=" * 60)

# =========================
# FEATURE IMPORTANCE
# =========================

if hasattr(
    model,
    "feature_importances_"
):
    print("\nTop 20 Features\n")

    importance = (
        pd.Series(
            model.feature_importances_,
            index=FEATURE_COLS
        )
        .sort_values(
            ascending=False
        )
    )

    print(
        importance.head(20)
    )