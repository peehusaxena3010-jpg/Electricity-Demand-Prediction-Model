from datetime import date
from power.ml.manage_models import STATE_TO_REGION
from django.db import transaction
from power.ml.pridiction.predict_state_5min import predict_state_5min_data
from power.models import DailyPredictionHistory
from power.utils.backgroundwork import background_work
import pandas as pd
import numpy as np
from ninja.errors import HttpError
from power.utils.metadata import STATE_CODE_TO_NAME, day_metadata






# ------------------- RESPONSE BUILDERS -------------------
def build_hourly_forecast_response(state, date_str, forecast_df):
    points = [
        {
            "datetime": row.ds.isoformat(),
            "mw": round(row.yhat, 2),
            "temperature": round(getattr(row, "temperature_c", None), 2),
        }
        for _, row in forecast_df.iterrows()
    ]
    return {"state": state, "date": date_str, "points": points}


def build_daily_forecast_response(state, forecast_df):
    return {
        "state": state,
        "days": [
            {
                "date": row.ds.date().isoformat(),
                "energy_consumption_mu_per_day": round(row.yhat, 2),
            }
            for _, row in forecast_df.iterrows()
        ],
    }










# def build_5min_forecast_response(
#     state: str,
#     forecast_date,
#     forecast_df: pd.DataFrame
# ):
#     try:
#         # -------------------------
#         # Date handling
#         # -------------------------
#         if isinstance(forecast_date, str):
#             forecast_date_obj = date.fromisoformat(forecast_date)
#         elif isinstance(forecast_date, date):
#             forecast_date_obj = forecast_date
#         else:
#             raise ValueError("forecast_date must be str or date")

#         if forecast_df is None or forecast_df.empty:
#             raise ValueError("Empty forecast dataframe")

#         meta = day_metadata(forecast_date_obj)

#         # -------------------------
#         # Temperature safety
#         # -------------------------
#         if "temperature_c" not in forecast_df.columns:
#             forecast_df["temperature_c"] = 25.0
#         else:
#             forecast_df["temperature_c"] = (
#                 pd.to_numeric(forecast_df["temperature_c"], errors="coerce")
#                 .ffill()
#                 .bfill()
#                 .fillna(25.0)
#             )

#         forecast_df["mw"] = forecast_df["mw"].astype(float).round(2)
#         forecast_df["temperature_c"] = forecast_df["temperature_c"].round(2)

#         # -------------------------
#         # Points
#         # -------------------------
#         points = [
#             {
#                 "datetime": row.ds.isoformat(),
#                 "mw": row.mw,
#                 "temperature": row.temperature_c,
#             }
#             for _, row in forecast_df.iterrows()
#         ]

#         loads = forecast_df["mw"]
#         energy_mwh = loads.sum() * (5 / 60)

#         return {
#             "state": STATE_CODE_TO_NAME.get(state, state),
#             "date": forecast_date_obj.isoformat(),
#             **meta,
#             "energy_consumption_mu_per_day": round(energy_mwh / 1000, 2),
#             "average_load_mw": round(loads.mean(), 2),
#             "peak_load_mw": round(loads.max(), 2),
#             "mape_difference_percent": None,
#             "points": points,
#         }

#     except Exception as e:
#         raise HttpError(400, str(e))
    




def build_5min_forecast_response(state: str, forecast_date):
    try:
        # -----------------------------
        # SAFE DATE
        # -----------------------------
        if isinstance(forecast_date, date):
            forecast_date_obj = forecast_date
        elif isinstance(forecast_date, str):
            forecast_date_obj = date.fromisoformat(forecast_date.strip())
        else:
            raise ValueError("forecast_date must be str or date")

        meta = day_metadata(forecast_date_obj)

        # -----------------------------
        # CALL PREDICT
        # -----------------------------
        forecast_df = predict_state_5min_data(
            state=state,
            forecast_date=forecast_date_obj
        )

        if forecast_df.empty:
            raise ValueError("Empty forecast data")

        forecast_df["temperature_c"] = (
            forecast_df["temperature_c"]
            .astype(float)
            .ffill()
            .bfill()
            .fillna(25)
            .round(2)
        )

        forecast_df["mw"] = forecast_df["mw"].astype(float).round(2)

        points = [
            {
                "datetime": row.ds.isoformat(),
                "mw": row.mw,
                "temperature": row.temperature_c,
            }
            for _, row in forecast_df.iterrows()
        ]

        loads = forecast_df["mw"]
        energy_mwh = loads.sum() * (5 / 60)

        average_load_mw = round(loads.mean(), 2)

        with transaction.atomic():
            DailyPredictionHistory.objects.update_or_create(
                state=state,
                date=forecast_date,
                defaults={"load_mw": average_load_mw}
            )

        return {
            "state": STATE_CODE_TO_NAME.get(state, state),
            "date": forecast_date_obj.isoformat(),
            **meta,
            "energy_consumption_mu_per_day": round(energy_mwh / 1000, 2),
            "average_load_mw": average_load_mw,
            "peak_load_mw": round(loads.max(), 2),
            "mape_difference_percent": None,
            "points": points,
        }

    except Exception as e:
        raise HttpError(400, str(e))




# ------------------- MAIN FORECAST GENERATOR -------------------
def generate_all_forecasts(state_short: str, start_date: str):
    models = background_work(state_short, start_date)
    region_code = STATE_TO_REGION[state_short]
    print(models)

    # region_pred = predict_region_hourly(models["region_model"], region_code)
    # daily_pred = predict_state_daily(models["state_daily_model"], state_short)
    min5_pred = predict_state_5min_data(
        state=state_short,
        forecast_date=start_date
    )

    return {
        # "hourly": build_hourly_forecast_response(state_short, start_date, region_pred),
        # "daily": build_daily_forecast_response(state_short, daily_pred),
        "5min": build_5min_forecast_response(state_short, start_date, min5_pred),
    }
