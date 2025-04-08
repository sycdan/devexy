import typer

from devexy.tools.minikube import minikube
from devexy.utils.cli import begin, fail, ok

app = typer.Typer()


@app.command()
def start(
  force: bool = typer.Option(
    False,
    "--force",
    help="Delete the cluster before starting it.",
  ),
):
  """Start the minikube cluster."""
  if not minikube.is_installed:
    fail("minikube is not installed")

  if force:
    with begin("Deleting cluster"):
      if minikube.delete():
        ok()
      else:
        fail()

  if minikube.is_initialized:
    ok("Cluster already started")
  else:
    with begin("Starting cluster"):
      if minikube.start():
        ok()
      else:
        fail()
