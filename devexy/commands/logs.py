import os
import signal
import time

import typer

from devexy.utils.logging import LOG_FILE

app = typer.Typer()


@app.command()
def logs(
  lines: int = typer.Option(20, help="Number of lines to display."),
  follow: bool = typer.Option(False, "--follow", "-f", help="Follow the log file."),
  update_interval: float = typer.Option(0.1, help="Update interval in seconds."),
):
  """
  Display the last N lines of the log file, or follow the log file.
  """
  if follow:
    try:
      stop_flag = False
      line_count = 0
      start_time = time.time()

      def signal_handler(sig, frame):
        nonlocal stop_flag, line_count, start_time
        stop_flag = True
        end_time = time.time()
        duration = end_time - start_time
        typer.echo(f"Logged {line_count} lines in {duration:.2f} seconds.")

      signal.signal(signal.SIGINT, signal_handler)

      with open(LOG_FILE, "r") as f:
        f.seek(0, os.SEEK_END)
        while not stop_flag:
          line = f.readline()
          if line:
            typer.echo(line.strip())
            line_count += 1
          time.sleep(update_interval)
    except FileNotFoundError:
      typer.echo(f"Log file not found: {LOG_FILE}", err=True)
    except Exception as e:
      typer.echo(f"An error occurred: {e}", err=True)
  else:
    try:
      with open(LOG_FILE, "r") as f:
        log_lines = f.readlines()
        last_lines = log_lines[-lines:]
        for line in last_lines:
          typer.echo(line.strip())
    except FileNotFoundError:
      typer.echo(f"Log file not found: {LOG_FILE}", err=True)
    except Exception as e:
      typer.echo(f"An error occurred: {e}", err=True)
