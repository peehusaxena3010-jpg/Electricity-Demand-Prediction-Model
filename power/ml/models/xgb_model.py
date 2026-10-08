from xgboost import XGBRegressor

def train_xgb_model(df):
    y = df["y"]

    feature_cols = [
        # weather
        "temperature_c", "humidity_pct", "rain_mm", "wind_speed_ms",

        # time
        "hour", "is_peak",
        "temp_x_hour", "humidity_x_hour", "wind_x_hour",

        # calendar
        "is_weekend", "is_holiday", "season",

        # 🔥 daily behaviour
        "profile_y",

        # lags
        *[f"y_lag_{i}" for i in range(1, 7)],
        "y_lag_24h", "y_lag_7d",
    ]

    X = df[feature_cols]

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

    # metadata
    model.feature_cols = feature_cols
    model.target_col = "y"

    return model
