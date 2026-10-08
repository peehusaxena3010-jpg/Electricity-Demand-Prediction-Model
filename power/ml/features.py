import pandas as pd

from power.models import StateLoad5Min

def daily_features(df: pd.DataFrame):
    df["shortage"] = df["demand_scheduled_mw"] - df["actual_load_mw"]
    df["date"] = df["start_time"].dt.date

    daily = df.groupby("date").agg(
        energy_consumption_mu=("actual_load_mw", lambda x: x.sum()/1000),
        average_load_mw=("actual_load_mw", "mean"),
        peak_load_mw=("actual_load_mw", "max"),
        peak_shortage_mw=("shortage", "max"),
        demand_max=("demand_scheduled_mw", "max"),
        energy_shortage_mu=("shortage", lambda x: x.sum()/1000)
    ).reset_index()

    daily["peak_shortage_percent"] = (
        daily["peak_shortage_mw"] / daily["demand_max"] * 100
    )

    daily["energy_shortage_percent"] = (
        daily["energy_shortage_mu"] /
        (daily["energy_consumption_mu"] + daily["energy_shortage_mu"]) * 100
    )

    return daily












def build_5min_ratio_profile(state: str) -> pd.Series:
    qs = (
        StateLoad5Min.objects
        .filter(state=state)
        .order_by("datetime")
        .values("datetime", "load_mw")
    )

    df = pd.DataFrame(qs)
    if df.empty:
        raise ValueError("No historical 5-min data found")

    df["time"] = df["datetime"].dt.strftime("%H:%M")
    avg_by_time = df.groupby("time")["load_mw"].mean()

    ratio = avg_by_time / avg_by_time.mean()
    return ratio
