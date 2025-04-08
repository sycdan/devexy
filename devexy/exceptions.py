import subprocess


class ExecutableError(Exception):
  """Custom exception raised when a tool's executable is not found."""

  pass


class ToolError(subprocess.CalledProcessError):
  """Indicates that the tool command failed. `message` will be the output of `stderr`."""

  pass
