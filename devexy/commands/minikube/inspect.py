import threading
from pathlib import Path
from typing import Any, Dict, Iterator, List

import typer
import yaml
from pynput import keyboard
from rich import box
from rich.live import Live
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from devexy import settings
from devexy.constants import APP_NAME, CHECK_MARK, CROSS_MARK
from devexy.exceptions import ToolError
from devexy.k8s import utils as k8s
from devexy.k8s.models.resource import Resource
from devexy.settings import KUSTOMIZE_OVERLAY_DIR
from devexy.tools.kubectl import kubectl
from devexy.tools.kustomize import kustomize
from devexy.tools.minikube import minikube
from devexy.utils.cli import begin, console, fail, ok, say
from devexy.utils.logging import get_logger

logger = get_logger(__name__)


def get_running(resource: Resource) -> str:
  """
  Fetches the running status of a Kubernetes resource from the k8s cache.
  """
  replicas = resource._state_cache.get("replicas")
  if isinstance(replicas, int):
    return CHECK_MARK if replicas > 0 else CROSS_MARK
  return "?"


app = typer.Typer()


class ClusterTable:
  def __init__(
    self,
    items: List[Resource],
  ):
    self.items = sorted(items, key=lambda x: x.name or "Unknown")
    self.selected_index = 0
    self.running = True

  def render_table(
    self,
  ):
    table = Table(
      show_header=True,
      header_style="bold magenta",
      title=f"{APP_NAME} - Scalable Resources",
    )
    table.add_column("Name", justify="left")
    table.add_column("Kind", justify="left")
    table.add_column("Namespace", style="dim", justify="left")
    table.add_column("🏃", justify="center")

    for i, resource in enumerate(self.items):
      namespace = resource.namespace
      kind = resource.kind
      name = resource.name

      if i == self.selected_index:
        table.add_row(
          f"[bold green]{name}[/bold green]",
          f"[bold green]{kind}[/bold green]",
          f"[bold yellow]{namespace}[/bold yellow]",
          style="on grey23",  # Highlight style
        )
      else:
        status = get_running(resource)
        table.add_row(name, kind, namespace, status)

    return table

  def on_key_press(
    self,
    key,
  ):
    if not self.items:
      return
    try:
      if key == keyboard.Key.up:
        self.selected_index = (self.selected_index - 1) % len(self.items)
      elif key == keyboard.Key.down:
        self.selected_index = (self.selected_index + 1) % len(self.items)
      elif key == keyboard.Key.esc:
        self.running = False
      # TODO: Add key press for scaling up/down selected resource
    except Exception as e:
      console.print(f"[red]Error: {e}[/red]")

  def run(
    self,
  ):
    if not self.items:
      console.print("[yellow]No scalable resources to display.[/yellow]")
      return

    with Live(
      self.render_table(),
      refresh_per_second=10,
      console=console,
      vertical_overflow="visible",  # Ensure table doesn't get cut off
    ) as live:
      with keyboard.Listener(on_press=self.on_key_press) as listener:
        while self.running:
          live.update(self.render_table())
        listener.stop()


@app.command(name="i")
def inspect(
  kustomize_root: str = typer.Option(
    settings.KUSTOMIZE_ROOT,
    help="Path to the Kustomize root directory (above overlays).",
  ),
  overlay: str = typer.Option(
    settings.KUSTOMIZE_OVERLAY,
    help="Name of the Kustomize overlay to use.",
  ),
  rebuild: bool = typer.Option(
    False,
    help="Destroy and restart the cluster before using it.",
  ),
):
  """Inspect the cluster and toggle services interactively."""
  if not minikube.is_installed:
    fail("Minikube is not installed")

  if not kustomize.is_installed:
    fail("Kustomize is not installed")

  kustomize_path = Path(kustomize_root).resolve()
  if not kustomize_path.is_dir():
    fail(f"Invalid Kustomize root directory: {kustomize_root}")

  overlay_path = KUSTOMIZE_OVERLAY_DIR
  if not overlay_path.is_dir():
    fail(f"Invalid Overlay directory: {overlay_path}")
  if settings.NOISY:
    say(f"Using overlay {str(overlay_path)}")

  if rebuild:
    with begin("Deleting cluster"):
      if minikube.delete():
        ok()
      else:
        fail()

  if not minikube.is_initialized:
    with begin("Creating cluster"):
      if minikube.start():
        ok()
      else:
        fail()

  scalable_resources = apply_cluster_config(overlay_path)

  if scalable_resources:
    console.clear()
    # Instantiate and run ClusterTable with scalable_resources
    table_display = ClusterTable(scalable_resources)
    table_display.run()  # Replaced temporary table print with this
  else:
    # Message moved to ClusterTable.run() if list is empty after instantiation
    pass  # No need to print the "not found" message here anymore


def ensure_namespaces(resources: list[Resource]):
  """Extracts namespaces from the provided documents and ensures they exist using kubectl."""
  namespaces = set()

  for resource in resources:
    namespace = resource.namespace
    if namespace:
      namespaces.add(namespace)

  if not namespaces:
    return

  with begin("Checking namespaces"):
    for namespace in namespaces:
      kubectl.create_namespace_if_not_exists(namespace)
    ok()


def _iter_resources(yaml_content: str) -> Iterator[Resource]:
  """Parses YAML content and yields only valid dictionary documents as Resource instances."""
  all_docs = yaml.safe_load_all(yaml_content)
  for doc in all_docs:
    if isinstance(doc, dict):
      yield Resource(doc)
    elif doc is not None:
      logger.warning("Skipping non-dictionary item in YAML stream: %s", type(doc))


def apply_cluster_config(
  overlay_path: Path,
) -> List[Dict[str, str]]:
  """Builds cluster config via Kustomize and applies via kubectl.
  Scalable resources will be set to 0 replicas when deployed for the first time.
  Unchanged resources will not be re-deployed.

  Returns:
      A list of dictionaries, each containing namespace, kind, and name
      for the scalable resources found in the configuration.
  """
  resources: List[Resource] = []
  scalable_resources: List[Resource] = []
  changed_count = 0
  skipped_count = 0
  unchanged_count = 0

  try:
    with begin("Loading cluster configuration"):
      yaml_output = kustomize.build(overlay_path)
      # Resources will be grouped according to dependencies, so process in receive order
      for resource in _iter_resources(yaml_output):
        resources.append(resource)
      ok(f"{len(resources)} resources found")
  except ToolError as e:
    fail(f"{e}\n{e.stderr or ''}")
    return []
  except yaml.YAMLError as e:
    fail(f"Error parsing YAML: {e}")
    return []

  ensure_namespaces(resources)

  with begin("Applying configuration"):
    for resource in resources:
      if resource.is_scalable:
        scalable_resources.append(resource)

        try:
          # Set replicas to 0 for new scalable resources, preserving existing counts
          existing_replicas = kubectl.get_replicas(
            namespace=resource.namespace, kind=resource.kind, name=resource.name
          )
          if existing_replicas is None:
            resource.set_replicas(0)
          else:  # Resource exists, preserve its current replica count
            resource.set_replicas(existing_replicas)
        except Exception as e:
          logger.warning(
            "An unexpected error occurred while checking/setting replicas for %s: %s",
            resource.key,
            e,
            exc_info=True,
          )

      result = resource.apply()
      if result is None:
        skipped_count += 1
      elif result:
        changed_count += 1
      else:
        unchanged_count += 1

    summary = (
      f"{unchanged_count} unchanged, {changed_count} applied, {skipped_count} skipped"
    )
    if skipped_count:
      fail(f"{summary} (Encountered errors during apply)")
    else:
      ok(summary)

  return scalable_resources
