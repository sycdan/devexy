import typer

from devexy.commands.minikube import start, stop

app = typer.Typer(
  help="Manage the minikube cluster.",
  name="mk",
  no_args_is_help=True,
)
app.add_typer(start.app)
app.add_typer(stop.app)
