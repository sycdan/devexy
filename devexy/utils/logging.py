import logging


def get_logger(name):
  logger = logging.getLogger(name)
  logger.propagate = False
  return logger
