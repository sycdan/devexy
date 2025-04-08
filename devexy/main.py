#!/usr/bin/env python
import typer

from devexy import settings
from devexy.commands.minikube import app as minikube_app
from devexy.commands.version import app as version_app

app = typer.Typer(no_args_is_help=True)

app.add_typer(version_app)
app.add_typer(minikube_app, name="mk", help="Manage the local Kubernetes cluster.")


@app.callback()
def main(
  verbose: bool = typer.Option(
    False,
    "--verbose",
    "-v",
    help="Enable verbose output.",
  ),
):
  settings.NOISY = verbose


if __name__ == "__main__":
  app()
