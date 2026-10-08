from datetime import date
from power.ml.manage_models import STATE_TO_REGION
from power.ml.model_store import load_model, save_model
from power.ml.task import train_region_task, train_state_5min_task, train_state_daily_task
from power.ml.weather import fetch_weather_range
from power.utils.logger import get_logger



logger = get_logger(__name__)




def background_work(state_short: str, start_date: str = None, frequency: str = "hourly"):
    logger.info("🚀 Background work started for state=%s freq=%s", state_short, frequency)

    start_date = start_date or date.today().isoformat()
    end_date = date.today().isoformat()

    # =========================
    # WEATHER FETCH (optional)
    # =========================
    try:
        logger.info("🌦️ Fetching weather data for %s", state_short)
        weather_data = fetch_weather_range(state_short=state_short, start_date=start_date, end_date=end_date, frequency=frequency)
        logger.info("✅ Weather data ready")
    except Exception as e:
        logger.exception("❌ Weather fetch failed")
        weather_data = None

    # =========================
    # REGION CODE
    # =========================
    try:
        region_code = STATE_TO_REGION[state_short]
    except KeyError:
        raise ValueError(f"Invalid state code: {state_short}")

    # =========================
    # REGION HOURLY MODEL
    # =========================
    try:
        region_model = load_model(f"region_{region_code}.pkl")
        logger.info("✅ Loaded region model [%s]", region_code)
    except FileNotFoundError:
        logger.warning("⚠️ Region model not found, training...")
        region_model = train_region_task.delay(region_code)
        save_model(f"region_{region_code}.pkl", region_model)
        logger.info("💾 Region model saved [%s]", region_code)

    # =========================
    # STATE DAILY MODEL
    # =========================
    try:
        state_daily_model = load_model(f"state_daily_{state_short}.pkl")
        logger.info("✅ Loaded state daily model [%s]", state_short)
    except FileNotFoundError:
        logger.warning("⚠️ State daily model not found, training...")
        state_daily_model = train_state_daily_task.delay(state_short)
        save_model(f"state_daily_{state_short}.pkl", state_daily_model)
        logger.info("💾 State daily model saved [%s]", state_short)

    # =========================
    # STATE 5-MIN MODEL
    # =========================
    try:
        state_5min_model = load_model(f"state_5min_{state_short}.pkl")
        logger.info("✅ Loaded state 5-min model [%s]", state_short)
    except FileNotFoundError:
        logger.warning("⚠️ State 5-min model not found, training...")
        state_5min_model = train_state_5min_task.delay(state_short)
        save_model(f"state_5min_{state_short}.pkl", state_5min_model)
        logger.info("💾 State 5-min model saved [%s]", state_short)

    logger.info("🎯 Background work completed for %s", state_short)

    return {
        "weather": weather_data,
        "region_model": region_model,
        "state_daily_model": state_daily_model,
        "state_5min_model": state_5min_model,
    }











