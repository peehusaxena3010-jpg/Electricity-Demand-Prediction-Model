from datetime import datetime
from typing import Optional


def log_progress(logger,step: str,model_name: str,percent: Optional[int] = None,extra: Optional[dict] = None):
    payload = {
        "time": datetime.utcnow().isoformat(),
        "model": model_name,
        "step": step,
    }

    if percent is not None:
        payload["progress"] = f"{percent}%"

    if extra:
        payload.update(extra)

    logger.info(payload)
