import typer

from devexy.tools.minikube import minikube
from devexy.utils.cli import begin

app = typer.Typer()


@app.command()
def stop():
  """Stop the cluster."""
  if not minikube.is_installed:
    return

  with begin("Stopping cluster"):
    minikube.stop()
