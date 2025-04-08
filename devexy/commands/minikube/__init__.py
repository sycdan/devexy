import typer

from devexy.commands.minikube import inspect, stop

app = typer.Typer(no_args_is_help=True)
app.add_typer(inspect.app)
app.add_typer(stop.app)
