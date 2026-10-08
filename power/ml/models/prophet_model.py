import pandas as pd
from prophet import Prophet




def train_prophet_model(df: pd.DataFrame):
    m = Prophet(
        daily_seasonality=True,
        weekly_seasonality=True,
        yearly_seasonality=True,
        changepoint_prior_scale=0.03,
        seasonality_prior_scale=10,
    )

    for col in [
        "temperature_c",
        "humidity_pct",
        "rain_mm",
        "wind_speed_ms",
        "is_weekend",
        "is_holiday",
        "season",
    ]:
        m.add_regressor(col)

    m.fit(df)
    return m
