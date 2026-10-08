from datetime import date as date_type
from ninja.errors import HttpError
import pandas as pd


def validate_date(date_str: str) -> date_type:
    try:
        return pd.to_datetime(
            date_str,
            format="%Y-%m-%d",
            errors="raise"
        ).date()
    except Exception:
        raise HttpError( status_code=400, message="Invalid date format. Use YYYY-MM-DD (example: 2026-01-08)")
