# predict_CG.py
# Run: python predict_CG.py --date 2026-06-08 --horizon 5min

import joblib
import pandas as pd
import numpy as np
import requests
import argparse
import warnings
warnings.filterwarnings("ignore")


def fetch_weather(date_str):
    """
    Fetch hourly weather for date_str and resample to 5-min.
    Strategy:
      - yesterday or older  -> archive API (start_date/end_date)
      - today or future     -> forecast API (forecast_days param, not date range)
    Falls back to same-day last year if both APIs fail.
    """
    target   = pd.to_datetime(date_str).date()
    today    = pd.Timestamp.now().date()
    days_out = (target - today).days   # negative=past, 0=today, +N=future

    COORDS = {"latitude": 21.2787, "longitude": 81.8661, "timezone": "Asia/Kolkata"}
    FIELDS = "temperature_2m,relativehumidity_2m,windspeed_10m,precipitation"

    def _parse(data):
        df = pd.DataFrame({
            "ds":            pd.to_datetime(data["hourly"]["time"]),
            "temperature_c": data["hourly"]["temperature_2m"],
            "humidity_pct":  data["hourly"]["relativehumidity_2m"],
            "wind_speed_ms": data["hourly"]["windspeed_10m"],
            "rain_mm":       data["hourly"]["precipitation"],
        })
        df["ds"] = df["ds"].dt.tz_localize(None)
        # keep only target date (forecast API returns multiple days)
        df = df[df["ds"].dt.date == target].reset_index(drop=True)
        df = df.set_index("ds").resample("5min").interpolate("time").reset_index()
        return df

    # Past dates: archive API
    if days_out < 0:
        try:
            params = {**COORDS, "hourly": FIELDS,
                      "start_date": date_str, "end_date": date_str}
            r = requests.get("https://archive-api.open-meteo.com/v1/archive",
                             params=params, timeout=20)
            r.raise_for_status()
            return _parse(r.json())
        except Exception as e:
            print(f"  Warning: Archive API failed ({e}), trying forecast API...")

    # Today / future: forecast API using forecast_days (not start_date/end_date)
    # start_date on current day returns empty body from the forecast endpoint
    try:
        forecast_days = max(1, days_out + 1)
        params = {**COORDS, "hourly": FIELDS, "forecast_days": forecast_days}
        r = requests.get("https://api.open-meteo.com/v1/forecast",
                         params=params, timeout=20)
        r.raise_for_status()
        df = _parse(r.json())
        if len(df) > 0:
            return df
        raise ValueError("Forecast API returned 0 rows for target date")
    except Exception as e:
        print(f"  Warning: Forecast API failed ({e}), falling back to last-year proxy...")

    # Last resort: same calendar day 1 year ago
    proxy_date = (pd.Timestamp(date_str) - pd.DateOffset(years=1)).strftime("%Y-%m-%d")
    print(f"  Using weather proxy from {proxy_date}")
    params = {**COORDS, "hourly": FIELDS,
              "start_date": proxy_date, "end_date": proxy_date}
    r = requests.get("https://archive-api.open-meteo.com/v1/archive",
                     params=params, timeout=20)
    r.raise_for_status()
    df = _parse(r.json())
    df["ds"] = df["ds"] + pd.DateOffset(years=1)
    return df


def fetch_live():
    try:
        r = requests.get(
            "https://meritindia.in/StateWiseDetails/BindCurrentStateStatus?StateCode=CTG",
            verify=False, timeout=10)
        d = r.json()[0]
        return float(d["Demand"].replace(",", ""))
    except:
        return None


def generate_forecast(date_str, horizon="5min",
                      history_path="Demand_2023_2026_Fixed.xlsx"):

    print(f"  Loading model...")
    model        = joblib.load(f"power/ml/models/saved/state_CG_{horizon}.pkl")
    feature_cols = model.feature_cols
    print(f"  Model expects {len(feature_cols)} features")

    print(f"  Loading history...")
    hist = pd.read_excel(history_path)
    hist = hist.rename(columns={"Datetime": "ds", "Demand_MW": "load_mw"})
    hist["ds"] = pd.to_datetime(hist["ds"])
    hist = hist.sort_values("ds").reset_index(drop=True)
    print(f"  History: {hist['ds'].min().date()} → {hist['ds'].max().date()}")

    # ── Extend history with last-year proxy if forecast date is beyond history ──
    hist_end       = hist["ds"].max()
    forecast_start = pd.Timestamp(date_str)

    if forecast_start > hist_end:
        gap_start   = hist_end + pd.Timedelta(minutes=5)
        gap_end     = forecast_start + pd.Timedelta(days=1)
        proxy_start = gap_start - pd.DateOffset(years=1)
        proxy_end   = gap_end   - pd.DateOffset(years=1)

        proxy = hist[
            (hist["ds"] >= proxy_start) &
            (hist["ds"] <= proxy_end)
        ].copy()
        proxy["ds"] = proxy["ds"] + pd.DateOffset(years=1)

        hist = pd.concat([hist, proxy], ignore_index=True)
        # Deduplicate after proxy concat — overlapping dates cause
        # duplicate keys in lag merge which explodes df row count
        hist = hist.drop_duplicates(subset=["ds"], keep="last")
        hist = hist.sort_values("ds").reset_index(drop=True)
        print(f"  Extended history with last-year proxy → {hist['ds'].max().date()}")

    print(f"  Fetching weather...")
    weather = fetch_weather(date_str)

    # ── Build 288-slot time grid for the forecast day ──
    slots = pd.date_range(pd.Timestamp(date_str), periods=288, freq="5min")
    df    = pd.DataFrame({"ds": slots})

    # ── Time features ──
    df["slot"]         = df["ds"].dt.hour * 12 + df["ds"].dt.minute // 5
    df["hour"]         = df["ds"].dt.hour
    df["minute"]       = df["ds"].dt.minute
    df["day_of_week"]  = df["ds"].dt.dayofweek
    df["month"]        = df["ds"].dt.month
    df["day_of_month"] = df["ds"].dt.day
    df["quarter"]      = df["ds"].dt.quarter
    df["year"]         = df["ds"].dt.year
    df["is_weekend"]   = (df["day_of_week"] >= 5).astype(int)
    df["mmdd"]         = df["ds"].dt.strftime("%m-%d")

    # Cyclical encodings
    df["hour_sin"]  = np.sin(2*np.pi*df["hour"]/24)
    df["hour_cos"]  = np.cos(2*np.pi*df["hour"]/24)
    df["dow_sin"]   = np.sin(2*np.pi*df["day_of_week"]/7)
    df["dow_cos"]   = np.cos(2*np.pi*df["day_of_week"]/7)
    df["month_sin"] = np.sin(2*np.pi*df["month"]/12)
    df["month_cos"] = np.cos(2*np.pi*df["month"]/12)
    df["slot_sin"]  = np.sin(2*np.pi*df["slot"]/288)
    df["slot_cos"]  = np.cos(2*np.pi*df["slot"]/288)

    # ── Holidays ──
    CG_HOLIDAYS = [
        "2023-01-26","2023-03-07","2023-03-30","2023-04-14",
        "2023-08-15","2023-10-02","2023-10-24","2023-11-01",
        "2023-11-13","2023-12-25",
        "2024-01-26","2024-03-25","2024-04-14","2024-04-17",
        "2024-08-15","2024-10-02","2024-10-12","2024-11-01",
        "2024-11-15","2024-12-25",
        "2025-01-26","2025-03-14","2025-04-14","2025-08-15",
        "2025-10-02","2025-11-01","2025-12-25",
        "2026-01-26","2026-03-03","2026-04-14","2026-08-15",
    ]
    hset   = set(pd.to_datetime(CG_HOLIDAYS).strftime("%Y-%m-%d"))
    hdates = pd.to_datetime(list(hset))
    df["is_holiday"]      = df["ds"].dt.strftime("%Y-%m-%d").isin(hset).astype(int)
    df["is_pre_holiday"]  = df["ds"].dt.normalize().isin(hdates - pd.Timedelta(days=1)).astype(int)
    df["is_post_holiday"] = df["ds"].dt.normalize().isin(hdates + pd.Timedelta(days=1)).astype(int)

    # ── CG-specific ──
    def agri(m):
        if m in [6,7,11,12]: return 2
        elif m in [3,4,10]:  return 1
        return 0
    df["agri_season"] = df["month"].apply(agri)
    df["is_peak"]     = df["hour"].between(18, 23).astype(int)
    df["is_morning"]  = df["hour"].between(9, 12).astype(int)
    df["is_night"]    = ((df["hour"] >= 22) | (df["hour"] <= 5)).astype(int)
    df["is_summer"]   = df["month"].isin([3,4,5,6]).astype(int)
    df["is_monsoon"]  = df["month"].isin([7,8,9]).astype(int)
    # agri_night computed after agri_season
    df["agri_night"]  = df["agri_season"] * df["is_night"]
    # is_heatwave filled after weather merge
    df["is_heatwave"] = 0

    # ── Weather merge ──
    df = pd.merge_asof(
        df.sort_values("ds"),
        weather[["ds","temperature_c","humidity_pct",
                 "wind_speed_ms","rain_mm"]].sort_values("ds"),
        on="ds", direction="nearest",
        tolerance=pd.Timedelta("10min")
    )
    # ffill/bfill handles any API gaps so downstream features don't NaN out
    for wcol in ["temperature_c","humidity_pct","wind_speed_ms","rain_mm"]:
        df[wcol] = df[wcol].ffill().bfill()

    df["is_heatwave"]        = (df["temperature_c"] > 42).astype(int)
    df["temp_x_hour"]        = df["temperature_c"] * df["hour"]
    df["hum_x_hour"]         = df["humidity_pct"]  * df["hour"]
    df["temp_x_peak"]        = df["temperature_c"] * df["is_peak"]
    df["temp_x_summer"]      = df["temperature_c"] * df["is_summer"]
    df["temp_x_monsoon"]     = df["temperature_c"] * df["is_monsoon"]
    df["temp_change_1h"]     = df["temperature_c"] - df["temperature_c"].shift(12)
    df["humidity_change_1h"] = df["humidity_pct"]  - df["humidity_pct"].shift(12)
    df["rain_last_6h"]       = df["rain_mm"].rolling(72, min_periods=1).sum()

    # ── Lag features ──
    print(f"  Building lag features...")

    forecast_stub = pd.DataFrame({"ds": slots, "load_mw": np.nan})
    combined = (
        pd.concat([hist[["ds","load_mw"]], forecast_stub], ignore_index=True)
        .drop_duplicates(subset=["ds"], keep="first")
        .sort_values("ds")
        .reset_index(drop=True)
    )

    combined["load_lag_1"]   = combined["load_mw"].shift(1)
    combined["load_lag_2"]   = combined["load_mw"].shift(2)
    combined["load_lag_3"]   = combined["load_mw"].shift(3)
    combined["load_lag_6"]   = combined["load_mw"].shift(6)
    combined["load_lag_1h"]  = combined["load_mw"].shift(12)
    combined["load_lag_3h"]  = combined["load_mw"].shift(36)
    combined["load_lag_6h"]  = combined["load_mw"].shift(72)
    combined["load_lag_24h"] = combined["load_mw"].shift(288)
    combined["load_lag_48h"] = combined["load_mw"].shift(576)
    combined["load_lag_7d"]  = combined["load_mw"].shift(2016)

    combined["roll_mean_1h"]  = combined["load_mw"].shift(1).rolling(12,   min_periods=3).mean()
    combined["roll_std_1h"]   = combined["load_mw"].shift(1).rolling(12,   min_periods=3).std()
    combined["roll_mean_24h"] = combined["load_mw"].shift(1).rolling(288,  min_periods=72).mean()
    combined["roll_std_24h"]  = combined["load_mw"].shift(1).rolling(288,  min_periods=72).std()
    combined["roll_mean_7d"]  = combined["load_mw"].shift(1).rolling(2016, min_periods=288).mean()
    combined["roll_std_7d"]   = combined["load_mw"].shift(1).rolling(2016, min_periods=288).std()

    lag_cols = [
        "ds",
        "load_lag_1","load_lag_2","load_lag_3","load_lag_6",
        "load_lag_1h","load_lag_3h","load_lag_6h",
        "load_lag_24h","load_lag_48h","load_lag_7d",
        "roll_mean_1h","roll_std_1h",
        "roll_mean_24h","roll_std_24h",
        "roll_mean_7d","roll_std_7d",
    ]

    lags = (
        combined[combined["ds"].isin(slots)]
        [lag_cols]
        .drop_duplicates(subset=["ds"])
    )
    assert len(lags) == 288, f"Expected 288 lag rows, got {len(lags)}"

    df = df.merge(lags, on="ds", how="left")
    assert len(df) == 288, f"df has {len(df)} rows after lag merge!"

    # ── Profile features ──
    print(f"  Building profile features...")
    hist_feat = hist.copy()
    hist_feat["slot"]       = hist_feat["ds"].dt.hour*12 + hist_feat["ds"].dt.minute//5
    hist_feat["mmdd"]       = hist_feat["ds"].dt.strftime("%m-%d")
    hist_feat["is_weekend"] = (hist_feat["ds"].dt.dayofweek >= 5).astype(int)
    hist_feat["is_summer"]  = hist_feat["ds"].dt.month.isin([3,4,5,6]).astype(int)
    hist_feat["is_monsoon"] = hist_feat["ds"].dt.month.isin([7,8,9]).astype(int)
    hist_feat["hour"]       = hist_feat["ds"].dt.hour
    hist_feat["month"]      = hist_feat["ds"].dt.month

    # profile_load: median per mmdd + slot
    p1 = (hist_feat.groupby(["mmdd","slot"])["load_mw"]
          .median().reset_index()
          .rename(columns={"load_mw":"profile_load"}))
    df = df.merge(p1, on=["mmdd","slot"], how="left")
    assert len(df) == 288

    # profile_weekday: median per slot + is_weekend
    p2 = (hist_feat.groupby(["slot","is_weekend"])["load_mw"]
          .median().reset_index()
          .rename(columns={"load_mw":"profile_weekday"}))
    df = df.merge(p2, on=["slot","is_weekend"], how="left")
    assert len(df) == 288

    # profile_season: median per slot + is_summer + is_monsoon
    df["is_summer_tmp"]  = df["month"].isin([3,4,5,6]).astype(int)
    df["is_monsoon_tmp"] = df["month"].isin([7,8,9]).astype(int)
    p3 = (hist_feat.groupby(["slot","is_summer","is_monsoon"])["load_mw"]
          .median().reset_index()
          .rename(columns={"load_mw":"profile_season",
                           "is_summer":"is_summer_tmp",
                           "is_monsoon":"is_monsoon_tmp"}))
    df = df.merge(p3, on=["slot","is_summer_tmp","is_monsoon_tmp"], how="left")
    df = df.drop(columns=["is_summer_tmp","is_monsoon_tmp"])
    assert len(df) == 288

    # profile_hour_month: median per hour + month
    p4 = (hist_feat.groupby(["hour","month"])["load_mw"]
          .median().reset_index()
          .rename(columns={"load_mw":"profile_hour_month"}))
    df = df.merge(p4, on=["hour","month"], how="left")
    assert len(df) == 288

    # ── Lag diagnostic ──
    print(f"\n  Lag feature check (slot 0 = midnight):")
    print(f"    load_lag_24h    : {df['load_lag_24h'].iloc[0]:.1f} MW")
    print(f"    load_lag_7d     : {df['load_lag_7d'].iloc[0]:.1f} MW")
    print(f"    load_lag_1h     : {df['load_lag_1h'].iloc[0]:.1f} MW")
    print(f"    profile_load    : {df['profile_load'].iloc[0]:.1f} MW")
    print(f"    profile_weekday : {df['profile_weekday'].iloc[0]:.1f} MW")
    print(f"    temperature_c   : {df['temperature_c'].iloc[0]:.1f} °C")

    # ── Fill any remaining NaNs with column median ──
    for col in feature_cols:
        if col in df.columns and df[col].isna().any():
            fill_val = df[col].median()
            df[col]  = df[col].fillna(fill_val if not pd.isna(fill_val) else 0.0)

    # ── Check all features present ──
    missing = [c for c in feature_cols if c not in df.columns]
    if missing:
        raise ValueError(f"Missing features: {missing}")

    # ── Predict ──
    print(f"  Running model...")
    X     = df[feature_cols]
    preds = model.predict(X)

    assert len(preds) == len(slots), (
        f"Length mismatch: preds={len(preds)}, slots={len(slots)}"
    )

    return pd.DataFrame({
        "datetime":     slots,
        "predicted_mw": np.round(preds, 2)
    })


if __name__ == "__main__":
    import time as _time
    parser = argparse.ArgumentParser()
    parser.add_argument("--date",    default=pd.Timestamp.now().strftime("%Y-%m-%d"))
    parser.add_argument("--horizon", default="5min",
                        choices=["5min","1hour","3hour","24hour"])
    args = parser.parse_args()

    print(f"\nGenerating {args.horizon} forecast for {args.date}...")
    t0       = _time.time()
    forecast = generate_forecast(args.date, args.horizon)
    elapsed  = _time.time() - t0

    print(f"\n{'='*45}")
    print(f"  Done in {elapsed:.1f}s")
    print(f"  Peak : {forecast['predicted_mw'].max():.0f} MW "
          f"at {forecast.loc[forecast['predicted_mw'].idxmax(),'datetime'].strftime('%H:%M')}")
    print(f"  Base : {forecast['predicted_mw'].min():.0f} MW")
    print(f"  Avg  : {forecast['predicted_mw'].mean():.0f} MW")
    print(f"  Range: {forecast['predicted_mw'].max() - forecast['predicted_mw'].min():.0f} MW")
    print(f"{'='*45}")

    live = fetch_live()
    if live:
        print(f"  Live demand now: {live:.0f} MW")

    print(f"\nFull day forecast (hourly):")
    hourly = forecast.iloc[::12].copy()
    hourly["time"] = hourly["datetime"].dt.strftime("%H:%M")
    print(hourly[["time","predicted_mw"]].to_string(index=False))