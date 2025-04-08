from devexy.exceptions import ExecutableError, ToolError
from devexy.utils import proc


class Tool:
  exe = None

  def __init__(self, exe: str):
    self.exe = exe

  def exec(
    self,
    command: str,
    *command_args,
    input=None,
    raise_on_error=True,
  ) -> str:
    """
    Run a command synchronously, returning its standard output.

    Args:
      command: The command to run (e.g., "version", "build").
      *command_args: Additional arguments for the command.
      raise_on_error: Whether to raise an exception if the command fails.
      input: text to pass to the executable.

    Returns:
      The standard output of the command as a string, or `None` if the command failed and `raise_on_error` is `False`.

    Raises:
      ToolError: If the command returns a non-zero exit code and `raise_on_error` is `True`.
      ExecutableError: If the executable (`self.exe`) is not found.
    """
    args = [self.exe, command]
    args.extend(command_args)

    try:
      result = proc.run(args, input)
      if result.returncode == 0:
        return result.stdout
      else:
        if raise_on_error:
          raise ToolError(result.returncode, args, result.stdout, result.stderr)
        else:
          return None
    except FileNotFoundError:
      raise ExecutableError(f"Executable '{self.exe}' not found.")
