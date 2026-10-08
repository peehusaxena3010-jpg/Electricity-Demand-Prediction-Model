from django.tasks import task
from time import sleep
from power.sldc.ingest_sldc_daily import ingest_sldc_daily_data


@task
def sldc_daily_runner():
    """
    Runs SLDC ingestion once every 24 hours continuously.
    """
    while True:
        try:
            ingest_sldc_daily_data()
        except Exception as e:
            print("[SLDC TASK ERROR]", e)

        # 24 hours sleep
        sleep(60 * 60 * 24)
