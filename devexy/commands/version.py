import typer

from devexy import constants

app = typer.Typer()


@app.command()
def version():
  """Show the application version number."""
  print(constants.APP_VERSION)
