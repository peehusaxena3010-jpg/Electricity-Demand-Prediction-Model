from datetime import date as date_type, datetime as datetime_type, timedelta
from typing import List

from django.db.models import Avg, Max, Min
import pandas as pd
from ninja import Router

from power.models import ChhattsgarhLoad5Min, ChhattsgarhWeather5Min
from power.schemas import (
    ChhattsgarhDailySummaryOut,
    ChhattsgarhDailySummaryPoint,
    ChhattsgarhDemandHistoryOut,
    ChhattsgarhDemandPoint,
    ChhattsgarhLatestOut,
    ChhattsgarhWeatherPoint,
)

router = Router()


# ── 1. Latest (last 24 hours) ─────────────────────────────────────────────────

@router.get("/chhattisgarh/latest", response=ChhattsgarhLatestOut)
def chhattisgarh_latest(request):
    """
    GET /chhattisgarh/latest
    Returns last 24 hours of Chhattisgarh demand + weather data.
    Use this for real-time dashboard panels.
    """
    since = datetime_type.now() - timedelta(hours=24)

    demand_qs = ChhattsgarhLoad5Min.objects.filter(datetime__gte=since).order_by("datetime")
    
    # Fallback to last 288 points if we have less than 1 hour (12 points) of live data
    is_fallback = False
    if demand_qs.count() < 12:
        demand_qs = ChhattsgarhLoad5Min.objects.order_by("-datetime")[:288]
        demand_qs = sorted(demand_qs, key=lambda x: x.datetime)
        is_fallback = True

    if is_fallback and demand_qs:
        min_dt = demand_qs[0].datetime
        max_dt = demand_qs[-1].datetime
        weather_qs = ChhattsgarhWeather5Min.objects.filter(
            datetime__gte=min_dt, datetime__lte=max_dt
        ).order_by("datetime")
    else:
        weather_qs = ChhattsgarhWeather5Min.objects.filter(
            datetime__gte=since, datetime__lte=datetime_type.now()
        ).order_by("datetime")

    demand_points = [
        ChhattsgarhDemandPoint(
            datetime=obj.datetime.isoformat(),
            demand_mw=round(obj.demand_mw, 2),
            isgs_mw=round(obj.isgs_mw, 2) if obj.isgs_mw is not None else None,
            import_mw=round(obj.import_mw, 2) if obj.import_mw is not None else None,
            source=obj.source,
        )
        for obj in demand_qs
    ]

    weather_points = [
        ChhattsgarhWeatherPoint(
            datetime=obj.datetime.isoformat(),
            temperature_c=round(obj.temperature_c, 2),
            humidity_pct=round(obj.humidity_pct, 2) if obj.humidity_pct is not None else None,
            rain_mm=round(obj.rain_mm, 4) if obj.rain_mm is not None else None,
            wind_speed_ms=round(obj.wind_speed_ms, 2) if obj.wind_speed_ms is not None else None,
            source=obj.source,
        )
        for obj in weather_qs
    ]

    demand_list = list(demand_qs)
    avg_demand = sum(obj.demand_mw for obj in demand_list) / len(demand_list) if demand_list else 0.0
    peak_demand = max(obj.demand_mw for obj in demand_list) if demand_list else 0.0
    latest = demand_list[-1] if demand_list else None

    return ChhattsgarhLatestOut(
        as_of=latest.datetime.isoformat() if latest else datetime_type.now().isoformat(),
        avg_demand_mw=round(avg_demand, 2),
        peak_demand_mw=round(peak_demand, 2),
        demand_points=demand_points,
        weather_points=weather_points,
    )


# ── 2. Demand History ─────────────────────────────────────────────────────────

@router.get("/chhattisgarh/demand-history", response=ChhattsgarhDemandHistoryOut)
def chhattisgarh_demand_history(
    request,
    start_date: date_type,
    end_date:   date_type = None,
    limit:      int = 2016,
):
    """
    GET /chhattisgarh/demand-history?start_date=2025-01-01&end_date=2025-01-31
    Returns 5-min demand data for a date range.
    """
    if end_date is None:
        end_date = start_date

    qs = (
        ChhattsgarhLoad5Min.objects
        .filter(datetime__date__gte=start_date, datetime__date__lte=end_date)
        .order_by("datetime")[:limit]
    )

    agg = (
        ChhattsgarhLoad5Min.objects
        .filter(datetime__date__gte=start_date, datetime__date__lte=end_date)
        .aggregate(avg=Avg("demand_mw"), peak=Max("demand_mw"))
    )

    points = [
        ChhattsgarhDemandPoint(
            datetime=obj.datetime.isoformat(),
            demand_mw=round(obj.demand_mw, 2),
            isgs_mw=round(obj.isgs_mw, 2) if obj.isgs_mw is not None else None,
            import_mw=round(obj.import_mw, 2) if obj.import_mw is not None else None,
            source=obj.source,
        )
        for obj in qs
    ]

    return ChhattsgarhDemandHistoryOut(
        start_date=str(start_date),
        end_date=str(end_date),
        total_points=len(points),
        avg_demand_mw=round(agg["avg"] or 0, 2),
        peak_demand_mw=round(agg["peak"] or 0, 2),
        points=points,
    )


# ── 3. Daily Summary ──────────────────────────────────────────────────────────

@router.get("/chhattisgarh/daily-summary", response=ChhattsgarhDailySummaryOut)
def chhattisgarh_daily_summary(
    request,
    start_date: date_type,
    end_date:   date_type = None,
):
    """
    GET /chhattisgarh/daily-summary?start_date=2023-01-01&end_date=2026-03-31
    Returns day-wise avg, peak, min demand + avg temperature.
    Best for dashboard charts and year-over-year comparisons.
    """
    from django.db.models.functions import TruncDate
    from django.db.models import Avg, Max, Min

    if end_date is None:
        end_date = start_date

    start_dt = datetime_type.combine(start_date, datetime_type.min.time())
    end_dt = datetime_type.combine(end_date, datetime_type.max.time())

    demand_summary = (
        ChhattsgarhLoad5Min.objects
        .filter(datetime__gte=start_dt, datetime__lte=end_dt)
        .annotate(date=TruncDate("datetime"))
        .values("date")
        .annotate(
            avg_demand=Avg("demand_mw"),
            peak_demand=Max("demand_mw"),
            min_demand=Min("demand_mw"),
        )
        .order_by("date")
    )

    weather_summary = (
        ChhattsgarhWeather5Min.objects
        .filter(datetime__gte=start_dt, datetime__lte=end_dt)
        .annotate(date=TruncDate("datetime"))
        .values("date")
        .annotate(
            avg_temp=Avg("temperature_c"),
        )
        .order_by("date")
    )

    weather_dict = {row["date"]: row["avg_temp"] for row in weather_summary}

    days = [
        ChhattsgarhDailySummaryPoint(
            date=str(row["date"]),
            avg_demand_mw=round(row["avg_demand"], 2) if row["avg_demand"] is not None else 0.0,
            peak_demand_mw=round(row["peak_demand"], 2) if row["peak_demand"] is not None else 0.0,
            min_demand_mw=round(row["min_demand"], 2) if row["min_demand"] is not None else 0.0,
            avg_temp_c=round(weather_dict[row["date"]], 2) if row["date"] in weather_dict and weather_dict[row["date"]] is not None else None,
        )
        for row in demand_summary
    ]

    return ChhattsgarhDailySummaryOut(
        start_date=str(start_date),
        end_date=str(end_date),
        days=days,
    )


# ── 4. Manual Trigger ────────────────────────────────────────────────────────

@router.post("/chhattisgarh/trigger-fetch", response={200: dict})
def chhattisgarh_trigger_fetch(request):
    """
    POST /chhattisgarh/trigger-fetch
    Manually triggers live demand + weather fetch for Chhattisgarh.
    """
    from power.chhattisgarh.fetch_demand  import fetch_and_save_chhattisgarh_demand
    from power.chhattisgarh.fetch_weather import fetch_and_save_chhattisgarh_weather

    demand_ok    = fetch_and_save_chhattisgarh_demand()
    weather_rows = fetch_and_save_chhattisgarh_weather()

    return {
        "demand_fetch":       "success" if demand_ok else "failed",
        "weather_rows_saved": weather_rows,
        "timestamp":          datetime_type.now().isoformat(),
    }


# ── 5. ML Forecast ────────────────────────────────────────────────────────────

@router.get("/chhattisgarh/forecast", response={200: dict, 400: dict})
def chhattisgarh_forecast(request, date: date_type = None):
    """
    GET /chhattisgarh/forecast?date=2026-06-10
    Runs the trained XGBoost model and returns 288 predicted 5-min values.
    Defaults to tomorrow if no date given.
    """
    from power.ml.pridiction.predict_cg_5min import predict_cg_5min
    import math

    if date is None:
        from datetime import date as date_cls
        date = date_cls.today() + timedelta(days=1)

    try:
        result = predict_cg_5min(str(date))
        
        # Fetch actual demand points for the query date
        from power.models import ChhattsgarhLoad5Min
        actual_qs = ChhattsgarhLoad5Min.objects.filter(datetime__date=date).order_by("datetime")
        actual_dict = {pd.to_datetime(obj.datetime).floor("5min"): obj.demand_mw for obj in actual_qs}
        
        slots  = [
            {
                "datetime":     str(row["ds"]),
                "predicted_mw": round(float(row["predicted_mw"]), 2),
                "actual_mw":    round(float(actual_dict[pd.to_datetime(row["ds"])]), 2)
                    if pd.to_datetime(row["ds"]) in actual_dict else None,
                "temperature_c": round(float(row["temperature_c"]), 2)
                    if not math.isnan(row["temperature_c"]) else None,
            }
            for _, row in result.iterrows()
        ]
        return 200, {
            "forecast_date":    str(date),
            "total_slots":      len(slots),
            "peak_demand_mw":   round(max(s["predicted_mw"] for s in slots), 2),
            "avg_demand_mw":    round(sum(s["predicted_mw"] for s in slots) / len(slots), 2),
            "min_demand_mw":    round(min(s["predicted_mw"] for s in slots), 2),
            "slots":            slots,
        }
    except FileNotFoundError as exc:
        return 400, {"error": str(exc), "fix": "Run: python manage.py train_cg_model"}
    except Exception as exc:
        return 400, {"error": str(exc)}


# ── 6. 1-Hour Forecast ───────────────────────────────────────────────────────

@router.get("/chhattisgarh/forecast/1hour", response={200: dict, 400: dict})
def chhattisgarh_forecast_1hour(request, date: date_type = None):
    """
    GET /chhattisgarh/forecast/1hour?date=2026-06-10
    Returns 24 hourly predicted demand values for the given date.
    Defaults to tomorrow.
    """
    from power.ml.pridiction.predict_cg_1hour import predict_cg_1hour
    import math

    if date is None:
        from datetime import date as date_cls
        date = date_cls.today() + timedelta(days=1)

    try:
        result = predict_cg_1hour(str(date))
        
        # Load actual demand values, resample to hourly
        from power.models import ChhattsgarhLoad5Min
        actual_qs = ChhattsgarhLoad5Min.objects.filter(datetime__date=date).order_by("datetime")
        actual_df = pd.DataFrame(actual_qs.values("datetime", "demand_mw"))
        if not actual_df.empty:
            actual_df["datetime"] = pd.to_datetime(actual_df["datetime"])
            actual_hourly = actual_df.set_index("datetime").resample("1h").mean().reset_index()
            actual_dict = {row["datetime"]: row["demand_mw"] for _, row in actual_hourly.iterrows()}
        else:
            actual_dict = {}
            
        slots  = [
            {
                "datetime":     str(row["ds"]),
                "predicted_mw": round(float(row["predicted_mw"]), 2),
                "actual_mw":    round(float(actual_dict[pd.to_datetime(row["ds"])]), 2)
                    if pd.to_datetime(row["ds"]) in actual_dict else None,
                "temperature_c": round(float(row["temperature_c"]), 2)
                    if not math.isnan(row["temperature_c"]) else None,
            }
            for _, row in result.iterrows()
        ]
        return 200, {
            "forecast_date":  str(date),
            "horizon":        "1-hour",
            "total_slots":    len(slots),
            "peak_demand_mw": round(max(s["predicted_mw"] for s in slots), 2),
            "avg_demand_mw":  round(sum(s["predicted_mw"] for s in slots) / len(slots), 2),
            "min_demand_mw":  round(min(s["predicted_mw"] for s in slots), 2),
            "slots":          slots,
        }
    except FileNotFoundError as exc:
        return 400, {"error": str(exc), "fix": "Run: python manage.py train_cg_all_models --horizon 1hour"}
    except Exception as exc:
        return 400, {"error": str(exc)}


# ── 7. 3-Hour Forecast ───────────────────────────────────────────────────────

@router.get("/chhattisgarh/forecast/3hour", response={200: dict, 400: dict})
def chhattisgarh_forecast_3hour(request, date: date_type = None):
    """
    GET /chhattisgarh/forecast/3hour?date=2026-06-10
    Returns 8 slots (3-hour each) of predicted demand for the given date.
    Defaults to tomorrow.
    """
    from power.ml.pridiction.predict_cg_3hour import predict_cg_3hour
    import math

    if date is None:
        from datetime import date as date_cls
        date = date_cls.today() + timedelta(days=1)

    try:
        result = predict_cg_3hour(str(date))
        
        # Load actual demand values, resample to 3-hourly
        from power.models import ChhattsgarhLoad5Min
        actual_qs = ChhattsgarhLoad5Min.objects.filter(datetime__date=date).order_by("datetime")
        actual_df = pd.DataFrame(actual_qs.values("datetime", "demand_mw"))
        if not actual_df.empty:
            actual_df["datetime"] = pd.to_datetime(actual_df["datetime"])
            actual_3h = actual_df.set_index("datetime").resample("3h").mean().reset_index()
            actual_dict = {row["datetime"]: row["demand_mw"] for _, row in actual_3h.iterrows()}
        else:
            actual_dict = {}
            
        slots  = [
            {
                "datetime":     str(row["ds"]),
                "predicted_mw": round(float(row["predicted_mw"]), 2),
                "actual_mw":    round(float(actual_dict[pd.to_datetime(row["ds"])]), 2)
                    if pd.to_datetime(row["ds"]) in actual_dict else None,
                "temperature_c": round(float(row["temperature_c"]), 2)
                    if not math.isnan(row["temperature_c"]) else None,
            }
            for _, row in result.iterrows()
        ]
        return 200, {
            "forecast_date":  str(date),
            "horizon":        "3-hour",
            "total_slots":    len(slots),
            "peak_demand_mw": round(max(s["predicted_mw"] for s in slots), 2),
            "avg_demand_mw":  round(sum(s["predicted_mw"] for s in slots) / len(slots), 2),
            "min_demand_mw":  round(min(s["predicted_mw"] for s in slots), 2),
            "slots":          slots,
        }
    except FileNotFoundError as exc:
        return 400, {"error": str(exc), "fix": "Run: python manage.py train_cg_all_models --horizon 3hour"}
    except Exception as exc:
        return 400, {"error": str(exc)}


# ── 8. 24-Hour Daily Forecast ────────────────────────────────────────────────

@router.get("/chhattisgarh/forecast/24hour", response={200: dict, 400: dict})
def chhattisgarh_forecast_24hour(request, date: date_type = None, days: int = 30):
    """
    GET /chhattisgarh/forecast/24hour?date=2026-06-09&days=30
    Returns day-wise predicted demand for next N days (default 30).
    """
    from power.ml.pridiction.predict_cg_24hour import predict_cg_24hour
    import math

    try:
        result = predict_cg_24hour(days=days, anchor_date=str(date) if date else None)
        
        # Load actual demand values, resample to daily
        from power.models import ChhattsgarhLoad5Min
        actual_qs = ChhattsgarhLoad5Min.objects.filter(
            datetime__date__in=list(result["ds"].dt.date)
        ).order_by("datetime")
        actual_df = pd.DataFrame(actual_qs.values("datetime", "demand_mw"))
        if not actual_df.empty:
            actual_df["datetime"] = pd.to_datetime(actual_df["datetime"])
            actual_daily = actual_df.set_index("datetime").resample("D").mean().reset_index()
            actual_dict = {row["datetime"].date(): row["demand_mw"] for _, row in actual_daily.iterrows()}
        else:
            actual_dict = {}
            
        day_slots = [
            {
                "date":         str(row["ds"].date()),
                "predicted_mw": round(float(row["predicted_mw"]), 2),
                "actual_mw":    round(float(actual_dict[row["ds"].date()]), 2)
                    if row["ds"].date() in actual_dict else None,
                "temperature_c": round(float(row["temperature_c"]), 2)
                    if not math.isnan(row["temperature_c"]) else None,
            }
            for _, row in result.iterrows()
        ]
        return 200, {
            "forecast_days":  days,
            "horizon":        "24-hour (daily)",
            "total_days":     len(day_slots),
            "peak_demand_mw": round(max(s["predicted_mw"] for s in day_slots), 2),
            "avg_demand_mw":  round(sum(s["predicted_mw"] for s in day_slots) / len(day_slots), 2),
            "min_demand_mw":  round(min(s["predicted_mw"] for s in day_slots), 2),
            "days":           day_slots,
        }
    except FileNotFoundError as exc:
        return 400, {"error": str(exc), "fix": "Run: python manage.py train_cg_all_models --horizon 24hour"}
    except Exception as exc:
        return 400, {"error": str(exc)}
