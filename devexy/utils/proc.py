import subprocess
from typing import List

from devexy.utils import logging

logger = logging.get_logger(__name__)


def run(
  args: List[str],
  input: str = None,
) -> subprocess.CompletedProcess:
  """
  Lightweight wrapper around `subprocess.run`. Always captures output and treats i/o as text.

  Args:
      args: The command to run and all its arguments, as a list of strings.

  Returns:
      A subprocess.CompletedProcess instance, with a nonzero `returncode` on failure.
  """
  args = [str(x) for x in args]
  result = subprocess.run(
    args,
    input=input,
    capture_output=True,
    text=True,
    check=False,
    encoding="utf-8",
  )
  logger.debug("%s returncode: %s", " ".join(args), result.returncode)
  return result
