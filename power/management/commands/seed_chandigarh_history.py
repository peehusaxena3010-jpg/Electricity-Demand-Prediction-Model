"""
Management command: seed_chandigarh_history
-------------------------------------------
Seeds 3 years of historical Chandigarh demand + weather data into the DB
from the files inside the uploaded zip.

Usage:
  python manage.py seed_chandigarh_history
  python manage.py seed_chandigarh_history --demand-only
  python manage.py seed_chandigarh_history --weather-only
  python manage.py seed_chandigarh_history --demand-file path/to/file.xlsx
  python manage.py seed_chandigarh_history --weather-file path/to/file.csv

Expected files (auto-detected from project root):
  Demand_2023_2026_Fixed.xlsx   -- columns: Datetime, Demand_MW
  cg_weather_combined.csv       -- columns: datetime, temperature_c,
                                             humidity_pct, wind_speed_ms,
                                             rain_mm, state, frequency

Data range: Jan 2023 --> Mar 2026  (~341,500 rows each)
"""

import csv
import os
from datetime import datetime
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from power.models import ChandigarhLoad5Min, ChandigarhWeather5Min


BASE_DIR = Path(__file__).resolve().parent.parent.parent.parent  # project root
# File lives at: power/management/commands/seed_chandigarh_history.py
#   .parent → commands/
#   .parent → management/
#   .parent → power/
#   .parent → project root

DEFAULT_DEMAND_FILE  = BASE_DIR / "zip_extract" / "NVVN-backend" / "Demand_2023_2026_Fixed.xlsx"
DEFAULT_WEATHER_FILE = BASE_DIR / "zip_extract" / "NVVN-backend" / "cg_weather_combined.csv"

BATCH_SIZE = 2000   # rows per DB bulk_create call


class Command(BaseCommand):
    help = "Seed historical Chandigarh demand and weather data into DB"

    def add_arguments(self, parser):
        parser.add_argument("--demand-file",  type=str, help="Path to demand XLSX file")
        parser.add_argument("--weather-file", type=str, help="Path to weather CSV file")
        parser.add_argument("--demand-only",  action="store_true", help="Only seed demand data")
        parser.add_argument("--weather-only", action="store_true", help="Only seed weather data")

    # ------------------------------------------------------------------
    def handle(self, *args, **options):
        demand_only  = options["demand_only"]
        weather_only = options["weather_only"]

        if not demand_only:
            weather_file = Path(options["weather_file"] or DEFAULT_WEATHER_FILE)
            self._seed_weather(weather_file)

        if not weather_only:
            demand_file = Path(options["demand_file"] or DEFAULT_DEMAND_FILE)
            self._seed_demand(demand_file)

        self.stdout.write(self.style.SUCCESS("[OK] Seeding complete."))

    # ------------------------------------------------------------------
    def _seed_demand(self, filepath: Path):
        self.stdout.write(f"\n[DEMAND] Seeding from: {filepath}")

        if not filepath.exists():
            raise CommandError(f"Demand file not found: {filepath}")

        try:
            import openpyxl
        except ImportError:
            raise CommandError(
                "openpyxl is required: pip install openpyxl"
            )

        wb = openpyxl.load_workbook(filepath, read_only=True, data_only=True)
        ws = wb.active

        headers = [cell.value for cell in next(ws.iter_rows(min_row=1, max_row=1))]
        try:
            dt_col  = headers.index("Datetime")
            mw_col  = headers.index("Demand_MW")
        except ValueError:
            raise CommandError(
                f"Expected columns 'Datetime' and 'Demand_MW'. Found: {headers}"
            )

        batch  = []
        total  = 0
        skip   = 0

        for row in ws.iter_rows(min_row=2, values_only=True):
            raw_dt = row[dt_col]
            raw_mw = row[mw_col]

            if raw_dt is None or raw_mw is None:
                skip += 1
                continue

            # openpyxl gives datetime objects directly from xlsx
            dt = raw_dt if isinstance(raw_dt, datetime) else datetime.strptime(str(raw_dt), "%Y-%m-%d %H:%M:%S")
            mw = float(raw_mw)

            batch.append(
                ChandigarhLoad5Min(
                    datetime  = dt,
                    demand_mw = mw,
                    isgs_mw   = None,
                    import_mw = None,
                    source    = "historical",
                )
            )

            if len(batch) >= BATCH_SIZE:
                total += self._flush_demand(batch)
                batch = []
                self.stdout.write(f"  ... {total:,} demand rows inserted", ending="\r")

        if batch:
            total += self._flush_demand(batch)

        wb.close()
        self.stdout.write(
            self.style.SUCCESS(
                f"\n[OK] Demand seeding done: {total:,} rows inserted / updated  "
                f"({skip} skipped)"
            )
        )

    # ------------------------------------------------------------------
    def _flush_demand(self, batch: list) -> int:
        """Bulk-insert with conflict handling (skip duplicates)."""
        with transaction.atomic():
            ChandigarhLoad5Min.objects.bulk_create(
                batch,
                batch_size=BATCH_SIZE,
                update_conflicts=True,
                unique_fields=["datetime"],
                update_fields=["demand_mw", "isgs_mw", "import_mw", "source"],
            )
        return len(batch)

    # ------------------------------------------------------------------
    def _seed_weather(self, filepath: Path):
        self.stdout.write(f"\n[WEATHER] Seeding from: {filepath}")

        if not filepath.exists():
            raise CommandError(f"Weather file not found: {filepath}")

        batch = []
        total = 0
        skip  = 0

        with open(filepath, newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)

            # Validate expected columns
            required = {"datetime", "temperature_c", "humidity_pct", "wind_speed_ms", "rain_mm"}
            if not required.issubset(reader.fieldnames or []):
                raise CommandError(
                    f"Missing columns. Expected: {required}. Found: {reader.fieldnames}"
                )

            for line in reader:
                try:
                    dt = datetime.strptime(line["datetime"], "%Y-%m-%d %H:%M:%S")
                except ValueError:
                    skip += 1
                    continue

                def _safe_float(val):
                    try:
                        return float(val) if val not in (None, "", "None") else None
                    except (TypeError, ValueError):
                        return None

                batch.append(
                    ChandigarhWeather5Min(
                        datetime       = dt,
                        temperature_c  = float(line["temperature_c"]),
                        humidity_pct   = _safe_float(line["humidity_pct"]),
                        rain_mm        = _safe_float(line["rain_mm"]),
                        wind_speed_ms  = _safe_float(line["wind_speed_ms"]),
                        source         = "historical",
                    )
                )

                if len(batch) >= BATCH_SIZE:
                    total += self._flush_weather(batch)
                    batch = []
                    self.stdout.write(f"  ... {total:,} weather rows inserted", ending="\r")

        if batch:
            total += self._flush_weather(batch)

        self.stdout.write(
            self.style.SUCCESS(
                f"\n[OK] Weather seeding done: {total:,} rows inserted / updated  "
                f"({skip} skipped)"
            )
        )

    # ------------------------------------------------------------------
    def _flush_weather(self, batch: list) -> int:
        with transaction.atomic():
            ChandigarhWeather5Min.objects.bulk_create(
                batch,
                batch_size=BATCH_SIZE,
                update_conflicts=True,
                unique_fields=["datetime"],
                update_fields=["temperature_c", "humidity_pct", "rain_mm", "wind_speed_ms", "source"],
            )
        return len(batch)
