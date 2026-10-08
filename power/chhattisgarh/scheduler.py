"""
power/chhattisgarh/scheduler.py
---------------------------------
APScheduler configuration for Chhattisgarh live data collection.

Cron jobs:
  - fetch_and_save_chhattisgarh_demand  : every 5 minutes (Merit India API)
  - fetch_and_save_chhattisgarh_weather : every 1 hour    (Open-Meteo API)

Started from PowerConfig.ready() in power/apps.py.
Job state is persisted in Django DB via DjangoJobStore so jobs survive restarts.
"""

import logging

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger
from django_apscheduler.jobstores import DjangoJobStore
from django_apscheduler.models import DjangoJobExecution

logger    = logging.getLogger("chhattisgarh.scheduler")
scheduler = BackgroundScheduler(timezone="Asia/Kolkata")


def start_scheduler():
    """
    Initialise and start the APScheduler with Chhattisgarh cron jobs.
    Safe to call multiple times (replace_existing=True prevents duplicates).
    """
    scheduler.add_jobstore(DjangoJobStore(), "default")

    # ── 1. Live demand: every 5 minutes ─────────────────────────────────
    from power.chhattisgarh.fetch_demand import fetch_and_save_chhattisgarh_demand

    scheduler.add_job(
        fetch_and_save_chhattisgarh_demand,
        trigger=IntervalTrigger(minutes=5, timezone="Asia/Kolkata"),
        id="chhattisgarh_demand_5min",
        name="Chhattisgarh Demand (Merit India, every 5 min)",
        replace_existing=True,
        misfire_grace_time=60,
    )

    # ── 2. Live weather: every 1 hour ────────────────────────────────────
    from power.chhattisgarh.fetch_weather import fetch_and_save_chhattisgarh_weather

    scheduler.add_job(
        fetch_and_save_chhattisgarh_weather,
        trigger=IntervalTrigger(hours=1, timezone="Asia/Kolkata"),
        id="chhattisgarh_weather_1hr",
        name="Chhattisgarh Weather (Open-Meteo, every hour)",
        replace_existing=True,
        misfire_grace_time=300,
    )

    # ── 3. Cleanup old job execution records (keep last 7 days) ──────────
    scheduler.add_job(
        _cleanup_old_executions,
        trigger=IntervalTrigger(hours=24, timezone="Asia/Kolkata"),
        id="chhattisgarh_scheduler_cleanup",
        name="Cleanup APScheduler execution history (daily)",
        replace_existing=True,
    )

    try:
        scheduler.start()
        logger.info(
            "[CG Scheduler] Started. Jobs: %s",
            [job.id for job in scheduler.get_jobs()],
        )
    except Exception as exc:
        logger.exception("[CG Scheduler] Failed to start: %s", exc)


def _cleanup_old_executions():
    """Delete APScheduler execution records older than 7 days to keep DB lean."""
    from datetime import datetime, timedelta
    cutoff   = datetime.now() - timedelta(days=7)
    deleted, _ = DjangoJobExecution.objects.filter(run_time__lt=cutoff).delete()
    logger.info("[CG Scheduler Cleanup] Deleted %d old execution records", deleted)
