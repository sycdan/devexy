import typer
from rich.console import Console

from devexy import constants

console = Console()


def begin(message):
  return console.status(message + "... ")


def fail(message="fail"):
  """Exit with an error code after printing the message."""
  typer.secho(f"{constants.CROSS_MARK} {message}", fg=typer.colors.RED)
  raise typer.Exit(1)


def ok(message="ok"):
  """Print a success message with a check mark."""
  typer.secho(f"{constants.CHECK_MARK} {message}", fg=typer.colors.GREEN)


def say(message):
  typer.echo(message)
