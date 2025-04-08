#!/usr/bin/env python
import importlib
import logging
import pkgutil
from pathlib import Path
from typing import Optional

import typer

from devexy import settings
from devexy.utils.logging import configure_logger

app = typer.Typer(no_args_is_help=True)


def get_typer_instance(module) -> Optional[typer.Typer]:
  app = getattr(module, "app", None)
  if isinstance(app, typer.Typer):
    return app
  return None


# Import commands dynamically
commands_path = Path(__file__).parent / "commands"
for module_info in pkgutil.iter_modules([str(commands_path)]):
  module_name = f"devexy.commands.{module_info.name}"
  try:
    module = importlib.import_module(module_name)
    typer_instance = get_typer_instance(module)
    if typer_instance:
      app.add_typer(typer_instance)
  except Exception as e:
    logging.exception(f"Failed to load command module {module_name}: {e}")


@app.callback()
def main(
  verbose: bool = typer.Option(
    False,
    "--verbose",
    "-v",
    help="Enable verbose output.",
  ),
):
  settings.DEBUG = verbose
  log_level = logging.DEBUG if verbose else logging.INFO
  configure_logger(log_level)


if __name__ == "__main__":
  app()
