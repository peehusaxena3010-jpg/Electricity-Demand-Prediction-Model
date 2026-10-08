import os

from django.apps import AppConfig


class PowerConfig(AppConfig):
    name = "power"

    def ready(self):
        """
        Called once when Django is fully initialised.
        We start the APScheduler here so Chhattisgarh cron jobs begin
        automatically with the server.

        The RUN_MAIN check prevents the scheduler from starting twice
        in development mode (Django's auto-reloader spawns a child process
        with RUN_MAIN=true; we only start the scheduler in that child).
        """
        import sys
        # Don't start the scheduler during management commands
        # (migrate, makemigrations, shell, seed_chhattisgarh_history, etc.)
        # Only start when running the actual server (runserver / gunicorn / uvicorn)
        _SKIP_COMMANDS = {
            "migrate", "makemigrations", "shell", "createsuperuser",
            "collectstatic", "seed_chhattisgarh_history", "train_cg_model", "train_cg_all_models", "test",
        }
        if len(sys.argv) > 1 and sys.argv[1] in _SKIP_COMMANDS:
            return

        is_runserver = "runserver" in sys.argv
        if is_runserver and os.environ.get("RUN_MAIN") != "true":
            return

        try:
            from power.chhattisgarh.scheduler import start_scheduler
            start_scheduler()
        except Exception as exc:  # noqa: BLE001
            # Don't crash Django startup if scheduler fails
            import logging
            logging.getLogger("chhattisgarh.scheduler").error(
                "Scheduler failed to start: %s", exc
            )





