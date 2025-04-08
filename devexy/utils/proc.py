import subprocess
from typing import List


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
  result = subprocess.run(
    args,
    input=input,
    capture_output=True,
    text=True,
    check=False,
    encoding="utf-8",
  )
  return result
