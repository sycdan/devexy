import logging
from logging.handlers import RotatingFileHandler

from devexy import settings
from devexy.settings import APP_DIR

LOG_FILE = APP_DIR / "app.log"
LOG_LEVEL = logging.DEBUG if settings.NOISY else logging.INFO
LOG_FORMAT = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
MAX_BYTES = 1024 * 1024 * 5  # 5MB
BACKUP_COUNT = 5


def get_logger(name):
  logger = logging.getLogger(name)
  logger.setLevel(LOG_LEVEL)
  logger.propagate = False

  rotating_handler = RotatingFileHandler(
    LOG_FILE,
    maxBytes=MAX_BYTES,
    backupCount=BACKUP_COUNT,
  )
  rotating_handler.setFormatter(logging.Formatter(LOG_FORMAT))
  logger.addHandler(rotating_handler)

  return logger
