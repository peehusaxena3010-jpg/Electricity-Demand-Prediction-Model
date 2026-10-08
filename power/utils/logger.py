import logging
import sys




class ColorFormatter(logging.Formatter):
    COLORS = {
        "INFO": "\033[92m",
        "WARNING": "\033[93m",
        "ERROR": "\033[91m",
        "DEBUG": "\033[94m",
        "CRITICAL": "\033[95m",
        "RESET": "\033[0m",
    }

    def format(self, record):
        level = record.levelname
        color = self.COLORS.get(level, "")
        reset = self.COLORS["RESET"]

        record.levelname = f"{color}{level}{reset}"
        msg = super().format(record)
        record.levelname = level
        return msg





def get_logger(name: str) -> logging.Logger:
    logger = logging.getLogger(name)

    if logger.handlers:
        return logger

    logger.setLevel(logging.INFO)
    logger.propagate = False

    handler = logging.StreamHandler(sys.stdout)
    handler.setLevel(logging.INFO)
    handler.flush = sys.stdout.flush

    formatter = ColorFormatter("[%(asctime)s] [%(levelname)s] %(name)s | %(message)s",datefmt="%Y-%m-%d %H:%M:%S")

    handler.setFormatter(formatter)
    logger.addHandler(handler)
    return logger
