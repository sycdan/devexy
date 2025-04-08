import logging
from logging.handlers import RotatingFileHandler

from devexy.settings import APP_DIR

LOG_FILE = APP_DIR / "app.log"
LOG_FORMAT = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
MAX_BYTES = 1024 * 1024 * 5  # 5MB
BACKUP_COUNT = 5


def configure_logger(level):
  root_logger = logging.getLogger()
  root_logger.setLevel(level)
  for handler in root_logger.handlers:
    handler.setLevel(level)


def get_logger(name):
  logger = logging.getLogger(name)
  logger.propagate = False

  if not logger.handlers:
    rotating_handler = RotatingFileHandler(
      LOG_FILE,
      maxBytes=MAX_BYTES,
      backupCount=BACKUP_COUNT,
    )
    rotating_handler.setFormatter(logging.Formatter(LOG_FORMAT))
    logger.addHandler(rotating_handler)

  return logger
