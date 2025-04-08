import typer

from devexy.tools.minikube import minikube
from devexy.utils.cli import begin, fail, ok

app = typer.Typer()


@app.command()
def stop():
  """Stop the cluster."""
  if not minikube.is_installed:
    fail("minikube is not installed")

  with begin("Stopping cluster"):
    minikube.stop()
    ok()
