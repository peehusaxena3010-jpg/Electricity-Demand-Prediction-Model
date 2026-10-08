from typing import Optional, List
from ninja import Schema


class ChhattsgarhDemandPoint(Schema):
    datetime:  str
    demand_mw: float
    isgs_mw:   Optional[float] = None
    import_mw: Optional[float] = None
    source:    str


class ChhattsgarhDemandHistoryOut(Schema):
    start_date:     str
    end_date:       str
    total_points:   int
    avg_demand_mw:  float
    peak_demand_mw: float
    points:         List[ChhattsgarhDemandPoint]


class ChhattsgarhWeatherPoint(Schema):
    datetime:      str
    temperature_c: float
    humidity_pct:  Optional[float] = None
    rain_mm:       Optional[float] = None
    wind_speed_ms: Optional[float] = None
    source:        str


class ChhattsgarhLatestOut(Schema):
    as_of:          str
    avg_demand_mw:  float
    peak_demand_mw: float
    demand_points:  List[ChhattsgarhDemandPoint]
    weather_points: List[ChhattsgarhWeatherPoint]


class ChhattsgarhDailySummaryPoint(Schema):
    date:           str
    avg_demand_mw:  float
    peak_demand_mw: float
    min_demand_mw:  float
    avg_temp_c:     Optional[float] = None


class ChhattsgarhDailySummaryOut(Schema):
    start_date: str
    end_date:   str
    days:       List[ChhattsgarhDailySummaryPoint]
