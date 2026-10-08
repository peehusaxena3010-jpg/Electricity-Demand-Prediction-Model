import holidays
from datetime import date

import pandas as pd

INDIA_HOLIDAYS = holidays.India()




def get_season(month: int) -> str:
    if month in [12, 1, 2]:
        return "winter"
    elif month in [3, 4, 5]:
        return "summer"
    elif month in [6, 7, 8, 9]:
        return "monsoon"
    else:
        return "post-monsoon"




def day_metadata(d: date):
    return {
        "season": get_season(d.month),
        "weekday": d.strftime("%A"),
        "is_weekend": d.weekday() >= 5,
        "is_holiday": d in INDIA_HOLIDAYS
    }





def add_calendar_features(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df["ds"] = pd.to_datetime(df["ds"])

    df["is_weekend"] = (df["ds"].dt.weekday >= 5).astype(int)
    df["is_holiday"] = df["ds"].dt.date.apply(lambda d: int(d in INDIA_HOLIDAYS))

    month = df["ds"].dt.month

    df["season"] = 0
    df.loc[month.isin([12, 1, 2]), "season"] = 0
    df.loc[month.isin([3, 4, 5]), "season"] = 1
    df.loc[month.isin([6, 7, 8, 9]), "season"] = 2
    df.loc[month.isin([10, 11]), "season"] = 3

    return df









# STATE_IN = [
#     {"code": "DL", "name": "Delhi"},
#     {"code": "MH", "name": "Maharashtra"},
#     {"code": "TN", "name": "Tamil Nadu"},
#     {"code": "UP", "name": "Uttar Pradesh"},
#     {"code": "AP", "name": "Andhra Pradesh"},
#     {"code": "AR", "name": "Arunachal Pradesh"},
#     {"code": "AS", "name": "Assam"},
#     {"code": "BR", "name": "Bihar"},
#     {"code": "CH", "name": "Chandigarh"},
#     {"code": "CG", "name": "Chhattisgarh"},
#     {"code": "GA", "name": "Goa"},
#     {"code": "GJ", "name": "Gujarat"},
#     {"code": "HR", "name": "Haryana"},
#     {"code": "HP", "name": "Himachal Pradesh"},
#     {"code": "JK", "name": "Jammu & Kashmir"},
#     {"code": "JH", "name": "Jharkhand"},
#     {"code": "KA", "name": "Karnataka"},
#     {"code": "KL", "name": "Kerala"},
#     {"code": "MN", "name": "Manipur"},
#     {"code": "ML", "name": "Meghalaya"},
#     {"code": "MZ", "name": "Mizoram"},
#     {"code": "MP", "name": "Madhya Pradesh"},
#     {"code": "NL", "name": "Nagaland"},
#     {"code": "OD", "name": "Odisha"},
#     {"code": "PY", "name": "Pondicherry"},
#     {"code": "PB", "name": "Punjab"},
#     {"code": "RJ", "name": "Rajasthan"},
#     {"code": "SK", "name": "Sikkim"},
#     {"code": "TS", "name": "Telangana"},
#     {"code": "TR", "name": "Tripura"},
#     {"code": "UK", "name": "Uttarakhand"},
#     {"code": "WB", "name": "West Bengal"},
# ]



# STATE_CODE_TO_NAME = {s["code"]: s["name"] for s in STATE_IN}






STATE_IN = [
    {"code": "AP",  "name": "Andhra Pradesh"},
    {"code": "ACP", "name": "Andhra Pradesh (APCPDCL)"},
    {"code": "ASM", "name": "Assam"},
    {"code": "BHR", "name": "Bihar"},
    {"code": "CTG", "name": "Chhattisgarh"},
    {"code": "CHG", "name": "Chandigarh"},
    {"code": "DNH", "name": "Dadra and Nagar Haveli"},
    {"code": "DND", "name": "Daman and Diu"},
    {"code": "DL",  "name": "Delhi"},
    {"code": "GOA", "name": "Goa"},
    {"code": "GJT", "name": "Gujarat"},
    {"code": "HRN", "name": "Haryana"},
    {"code": "HP",  "name": "Himachal Pradesh"},
    {"code": "JAK", "name": "Jammu and Kashmir"},
    {"code": "JHK", "name": "Jharkhand"},
    {"code": "KRT", "name": "Karnataka"},
    {"code": "KRL", "name": "Kerala"},
    {"code": "MPD", "name": "Madhya Pradesh"},
    {"code": "MHA", "name": "Maharashtra"},
    {"code": "MIP", "name": "Manipur"},
    {"code": "MGA", "name": "Meghalaya"},
    {"code": "MZM", "name": "Mizoram"},
    {"code": "NGD", "name": "Nagaland"},
    {"code": "ODI", "name": "Odisha"},
    {"code": "PU",  "name": "Puducherry"},
    {"code": "PNB", "name": "Punjab"},
    {"code": "RJ",  "name": "Rajasthan"},
    {"code": "SKM", "name": "Sikkim"},
    {"code": "TND", "name": "Tamil Nadu"},
    {"code": "TLG", "name": "Telangana"},
    {"code": "TPA", "name": "Tripura"},
    {"code": "UP",  "name": "Uttar Pradesh"},
    {"code": "UTK", "name": "Uttarakhand"},
    {"code": "BGL", "name": "West Bengal"},
]


STATE_CODE_TO_NAME = {s["code"]: s["name"] for s in STATE_IN}

