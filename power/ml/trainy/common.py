import pandas as pd
from power.ml.weather import fetch_weather_range


REGION_TO_STATES = {
    "NR": ["DL", "UP", "HR", "PB", "HP", "JK", "UK", "CH"],
    "WR": ["MH", "GJ", "MP", "RJ", "CG", "GA"],
    "SR": ["TN", "AP", "TS", "KA", "KL", "PY"],
    "ER": ["WB", "BR", "OD", "JH"],
    "NER": ["AR", "AS", "MN", "ML", "MZ", "NL", "SK", "TR"],
}





# ------------------------------------------------------------------
# OUTLIER CLEAN (SAFE)
# ------------------------------------------------------------------
def clean_outliers(df: pd.DataFrame):
    df = df.copy()

    df = df.set_index("ds")
    df.index = pd.to_datetime(df.index)

    mu = df["y"].mean()
    sigma = df["y"].std()

    df.loc[(df["y"] - mu).abs() > 3 * sigma, "y"] = None

    df["y"] = df["y"].interpolate().bfill().ffill()

    return df.reset_index()








# ------------------------------------------------------------------
# WEATHER LIVE MERGE
# ------------------------------------------------------------------
def merge_live_weather(start_date, end_date, state, frequency="hourly") -> pd.DataFrame:
    weather = fetch_weather_range(
        state_short=state,
        start_date=start_date,
        end_date=end_date,
        frequency=frequency,
    )

    if weather.empty:
        raise ValueError("Weather data not available")

    weather = (
        weather.rename(columns={"datetime": "ds"})
        .sort_values("ds")
        .drop_duplicates("ds")
    )

    # ✅ split numeric + non-numeric
    num_cols = weather.select_dtypes(include="number").columns
    other_cols = [c for c in weather.columns if c not in num_cols and c != "ds"]

    weather = (
        weather.set_index("ds")
    )

    weather[num_cols] = weather[num_cols].resample("5min").interpolate("time")
    weather = weather.reset_index()

    # reattach string columns
    for c in other_cols:
        weather[c] = state if c == "state" else frequency

    return weather

