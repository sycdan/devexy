#!/usr/bin/env python
import random
import threading
import time

from blessed import Terminal

term = Terminal()
headers = ["ID", "Value", "Status"]


def generate_data():
  """Generate random data for the table"""
  return [
    [i, random.randint(1, 100), random.choice(["Active", "Inactive", "Pending"])]
    for i in range(1, 6)
  ]


running = True


def render_table(data):
  """Render the table efficiently in a separate thread"""
  global running

  def render():
    with term.fullscreen(), term.cbreak(), term.hidden_cursor():
      print(term.home + term.clear)  # Clear screen once at the beginning
      print(term.center(term.bold("Live Data Table")) + "\n")

      # Render headers once
      print(term.bold(term.white("{:<5} {:<10} {:<10}".format(*headers))))
      print(term.bold("=" * 30))

      while running:
        for i, row in enumerate(data):
          # Move cursor to the correct line to update row instead of clearing screen
          print(term.move_xy(0, 4 + i) + "{:<5} {:<10} {:<10}".format(*row))
        # Clear the footer line before re-rendering it
        print(term.move_xy(0, term.height - 1) + term.clear_eol, end="")
        # Render static footer pinned to the bottom of the terminal
        print(
          term.move_xy(0, term.height - 1)
          + term.bold(term.yellow("Press 'q' to quit.")),
          end="",
          flush=True,
        )
        time.sleep(0.1)

  render_thread = threading.Thread(target=render, daemon=True)

  render_thread.start()

  while running:
    key = term.inkey()
    if key:
      if key == "q":
        print(term.home + term.clear)  # Clear screen before exiting
        print(term.center(term.bold("Exiting...")))
        running = False
      # Update data in response to keypress
      for row in data:
        row[1] = random.randint(1, 100)
        row[2] = random.choice(["Active", "Inactive", "Pending"])

  render_thread.join()


if __name__ == "__main__":
  initial_data = generate_data()
  render_table(initial_data)
