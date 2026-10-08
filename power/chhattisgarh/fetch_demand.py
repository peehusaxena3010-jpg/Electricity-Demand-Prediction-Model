"""
power/chhattisgarh/fetch_demand.py
-----------------------------------
Polls the Merit India API for Chhattisgarh (CTG) live demand every 5 minutes
and saves to ChhattsgarhLoad5Min.

Merit India endpoint:
  GET https://meritindia.in/StateWiseDetails/BindCurrentStateStatus?StateCode=CTG
  Response: [{"Demand":"4,731","ISGS":"2,063","ImportData":"2,668"}]
"""

import logging
from datetime import datetime, timedelta

import requests

logger = logging.getLogger("chhattisgarh.demand")

MERIT_URL = (
    "https://meritindia.in/StateWiseDetails/"
    "BindCurrentStateStatus?StateCode=CTG"   # CTG = Chhattisgarh
)


def _round_to_5min(dt: datetime) -> datetime:
    """Floor datetime to the nearest 5-minute slot."""
    return dt - timedelta(minutes=dt.minute % 5, seconds=dt.second, microseconds=dt.microsecond)


def _parse_mw(value) -> float:
    """Parse Merit India's comma-formatted number strings to float."""
    if value is None:
        return 0.0
    if isinstance(value, (int, float)):
        return float(value)
    val_str = str(value).replace(",", "").strip()
    return float(val_str) if val_str else 0.0


def fetch_and_save_chhattisgarh_demand() -> bool:
    """
    Fetches current Chhattisgarh demand from Merit India and upserts into DB.

    Returns True on success, False on failure.
    Called by APScheduler every 5 minutes.
    """
    from power.models import ChhattsgarhLoad5Min

    try:
        resp = requests.get(MERIT_URL, timeout=10, verify=False)
        resp.raise_for_status()
        data = resp.json()

        if not data or not isinstance(data, list):
            logger.warning("[CG Demand] Unexpected API response: %s", data)
            return False

        row       = data[0]
        demand_mw = _parse_mw(row.get("Demand", "0"))
        isgs_mw   = _parse_mw(row.get("ISGS", "0"))
        import_mw = _parse_mw(row.get("ImportData", "0"))

        # Fallback mechanism for upstream API glitches
        # Chhattisgarh base load is never below 2000 MW. If it is less, the API is glitched.
        if demand_mw < 2000.0:
            logger.warning(
                "[CG Demand] Upstream API returned abnormally low demand (%.1f MW). "
                "Attempting database fallback.", demand_mw
            )
            last_valid = ChhattsgarhLoad5Min.objects.filter(demand_mw__gte=2000.0).order_by("-datetime").first()
            if last_valid:
                demand_mw = last_valid.demand_mw
                # If ISGS is missing but import is present, estimate ISGS
                if row.get("ISGS") is None or isgs_mw == 0.0:
                    isgs_mw = max(0.0, demand_mw - import_mw)
                logger.info(
                    "[CG Demand] Fallback applied. Using last valid demand: %.1f MW (Estimated ISGS: %.1f)",
                    demand_mw, isgs_mw
                )

        slot = _round_to_5min(datetime.now())

        obj, created = ChhattsgarhLoad5Min.objects.update_or_create(
            datetime=slot,
            defaults={
                "demand_mw": demand_mw,
                "isgs_mw":   isgs_mw,
                "import_mw": import_mw,
                "source":    "merit" if (row.get("Demand") and _parse_mw(row.get("Demand")) >= 2000.0) else "merit-fallback",
            },
        )

        action = "CREATED" if created else "UPDATED"
        logger.info(
            "[CG Demand] %s @ %s  ->  %.1f MW (ISGS=%.1f, Import=%.1f)",
            action, slot, demand_mw, isgs_mw, import_mw,
        )
        return True

    except requests.Timeout:
        logger.error("[CG Demand] Request timed out")
    except requests.HTTPError as exc:
        logger.error("[CG Demand] HTTP error: %s", exc)
    except Exception as exc:
        logger.exception("[CG Demand] Unexpected error: %s", exc)

    return False
