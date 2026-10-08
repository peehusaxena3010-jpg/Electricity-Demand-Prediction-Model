# Chhattisgarh Demand Forecast — Backend

Django backend for collecting and serving Chhattisgarh electricity demand data.

## Setup

```bash
pip install -r requirements.txt
python manage.py migrate
python manage.py runserver
```

## What's Inside

- **Database:** 3 years of Chhattisgarh demand + weather data (Jan 2023 - Mar 2026)
- **Live Collection:** Auto-collects demand every 5 minutes from Merit India API (StateCode=CTG)
- **API:** 4 endpoints ready for dashboard

## API Endpoints

| Endpoint | Use |
|---|---|
| GET /api/chhattisgarh/latest | Last 24 hours live data |
| GET /api/chhattisgarh/demand-history?start_date=2025-01-01&end_date=2025-01-31 | Historical 5-min data |
| GET /api/chhattisgarh/daily-summary?start_date=2023-01-01&end_date=2026-03-31 | Day-wise avg/peak/min |
| POST /api/chhattisgarh/trigger-fetch | Test live fetch manually |

## API Docs

After starting server visit: http://127.0.0.1:8000/api/docs
