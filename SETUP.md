# Setup & Run Guide — NVVN Chhattisgarh Demand Forecast

## Requirements
- **Python 3.10 or 3.11** (recommended — do NOT use Python 3.12+)
- Internet connection (for live demand + weather data)

---

## Step 1 — Extract the Zip

Extract `NVVN-full-project.zip`. You will get a folder called `NVVN-full-project`.

Open a **terminal / command prompt inside that folder**.

**Windows:** Right-click inside the folder → "Open in Terminal"  
**Or:** Open CMD and type:
```
cd C:\path\to\NVVN-full-project
```

---

## Step 2 — Create Python Virtual Environment

```cmd
python -m venv venv
```

Then activate it:

- **Windows CMD:**
  ```cmd
  venv\Scripts\activate
  ```
- **Windows PowerShell:**
  ```powershell
  .\venv\Scripts\Activate.ps1
  ```
- **Mac / Linux:**
  ```bash
  source venv/bin/activate
  ```

You should see `(venv)` at the start of your terminal prompt.

---

## Step 3 — Install Dependencies

```cmd
pip install -r requirements.txt
```

This installs Django, XGBoost, pandas, and all other required packages.  
**Note:** The database is pre-loaded with 3 years of data — no seeding needed.

---

## Step 4 — Run Database Migrations

```cmd
python manage.py migrate
```

This sets up the scheduler tables. You will see several "OK" lines. That is normal.

---

## Step 5 — Start the Backend Server

```cmd
python manage.py runserver
```

You should see:
```
Starting development server at http://127.0.0.1:8000/
```

Leave this terminal open. The backend is now running.

---

## Step 6 — Open the Dashboard

Open a **second terminal**, go to the same folder, activate the venv again, then run:

```cmd
python -m http.server 8080 --directory dashboard
```

Now open your browser and go to:

- **NTPC Dashboard (heml):** http://127.0.0.1:8080/heml.html
- **Full Dashboard:** http://127.0.0.1:8080/

---

## Common Errors & Fixes

### Error: `'python' is not recognized`
Use `python3` instead of `python`, or install Python from https://python.org

### Error: `ModuleNotFoundError: No module named 'config'`
You are running `python manage.py` from the **wrong folder**.  
Make sure your terminal is inside the `NVVN-full-project` folder (where `manage.py` is).

### Error: `No module named 'xgboost'`
The venv is not activated. Run `venv\Scripts\activate` first (Windows).

### Error: `Address already in use` on port 8000
Something else is using port 8000. Kill it or use a different port:
```cmd
python manage.py runserver 8001
```
Then change the `API_URL` in `dashboard/heml.html` from `http://127.0.0.1:8000` to `http://127.0.0.1:8001`.

### Dashboard shows "Backend unreachable" / Synthetic data
The backend server is not running. Make sure Step 5 is done in a separate terminal window.

---

## Optional — Retrain ML Models

If you need to retrain the forecast models using fresh data:
```cmd
python train_CG.py
```

To run a manual prediction for a specific date:
```cmd
python predict_CG.py --date 2026-06-15
```
