from datetime import date
from power.utils.metadata import day_metadata


def mu_per_day_to_average_mw(energy_mu_per_day: float) -> float:
    """
    Convert daily electricity consumption from MU/day
    to average load in MW for 24 hours.

    Formula:
        Average Load (MW) = (MU/day × 1000) / 24
    """
    if energy_mu_per_day < 0:
        raise ValueError("Energy (MU/day) cannot be negative")

    return round((energy_mu_per_day * 1000) / 24, 2)



def calculate_mape(actual: float | None, predicted: float) -> float | None:
    """
    Returns MAPE % if actual is available and non-zero,
    otherwise returns None.
    """
    if actual is None or actual == 0:
        return None

    return round(abs((actual - predicted) / actual) * 100, 2)









def build_load_forecast_response(state, forecast_date, forecast_df):
    meta = day_metadata(date.fromisoformat(forecast_date))

    points = [
        {
            "datetime": row.ds.isoformat(),
            "mw": round(row.yhat, 2),
            "temperature": round(row.temperature_c, 2)
            if "temperature_c" in forecast_df.columns
            else None,
        }
        for _, row in forecast_df.iterrows()
    ]

    loads = forecast_df["yhat"]

    return {
        "state": state,
        "date": forecast_date,
        **meta,
        "energy_consumption_mu_per_day": round(loads.sum() / 1000, 2),
        "average_load_mw": round(loads.mean(), 2),
        "peak_load_mw": round(loads.max(), 2),
        "mape_difference_percent": None,
        "points": points,
    }
