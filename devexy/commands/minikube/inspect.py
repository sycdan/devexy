from pathlib import Path

import typer
import yaml
from pynput import keyboard
from rich.live import Live
from rich.table import Table

from devexy import settings
from devexy.exceptions import ExecutableError, ToolError
from devexy.tools.kubectl import kubectl
from devexy.tools.kustomize import kustomize
from devexy.tools.minikube import minikube
from devexy.utils import k8s
from devexy.utils.cli import begin, console, fail, ok, say

app = typer.Typer()


class ClusterTable:
  def __init__(
    self,
    items,
  ):
    self.items = items
    self.selected_index = 0
    self.running = True

  def render_table(
    self,
  ):
    table = Table(
      show_header=True,
      header_style="bold magenta",
    )
    table.add_column(
      "Index",
      justify="center",
    )
    table.add_column(
      "Item",
      justify="left",
    )

    for (
      i,
      item,
    ) in enumerate(self.items):
      if i == self.selected_index:
        table.add_row(
          f"[bold yellow]{i}[/bold yellow]",
          f"[bold green]{item}[/bold green]",
        )
      else:
        table.add_row(
          f"{i}",
          item,
        )

    return table

  def on_key_press(
    self,
    key,
  ):
    try:
      if key == keyboard.Key.up:
        self.selected_index = (self.selected_index - 1) % len(self.items)
      elif key == keyboard.Key.down:
        self.selected_index = (self.selected_index + 1) % len(self.items)
      elif key == keyboard.Key.esc:
        self.running = False
    except Exception as e:
      console.print(f"[red]Error: {e}[/red]")

  def run(
    self,
  ):
    with Live(
      self.render_table(),
      refresh_per_second=10,
      console=console,
    ) as live:
      with keyboard.Listener(on_press=self.on_key_press) as listener:
        while self.running:
          live.update(self.render_table())
        listener.stop()


@app.command(name="i")
def inspect(
  ctx: typer.Context,
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

  if ctx.invoked_subcommand:
    return

  kustomize_path = Path(kustomize_root).resolve()
  if not kustomize_path.is_dir():
    fail(f"Invalid Kustomize root directory: {kustomize_root}")

  overlay_path = kustomize_path / "overlays" / overlay
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

  apply_cluster_config(overlay_path)


def ensure_namespaces(docs: list[dict]):
  """Extracts namespaces from the provided documents and ensures they exist using kubectl."""
  namespaces = set()

  for doc in docs:
    namespace = k8s.get_namespace(doc)
    if namespace:
      namespaces.add(namespace)

  if not namespaces:
    return

  with begin("Checking namespaces"):
    for namespace in namespaces:
      kubectl.create_namespace_if_not_exists(namespace)
    ok()


def apply_cluster_config(
  overlay_path: Path,
):
  """Builds cluster config via Kustomize and applies via kubectl.
  Replicas will be set to 0 for new Deployments and StatefulSets during application.
  """
  docs = []

  try:
    with begin("Loading cluster configuration"):
      # Resources will be grouped intelligently according to dependencies
      yaml_output = kustomize.build(overlay_path)
      # Load and filter documents, keeping only dictionaries
      all_docs = yaml.safe_load_all(yaml_output)
      docs = [doc for doc in all_docs if isinstance(doc, dict)]
      ok(f"{len(docs)} documents found")
  except ToolError as e:
    fail(f"{e}\n{e.stderr or ''}")
  except yaml.YAMLError as e:
    fail(f"Error parsing YAML: {e}")

  ensure_namespaces(docs)

  with begin("Applying configuration"):
    for doc in docs:
      kind = k8s.get_kind(doc)
      name = k8s.get_name(doc)
      namespace = k8s.get_namespace(doc)
      resource_id = f"{namespace}:{kind}:{name}"

      # Set replicas to 0 for new scalable resources, preserving existing counts
      if k8s.is_scalable(kind):
        existing_replicas = kubectl.get_replicas(name, kind, namespace)
        if existing_replicas is None:
          doc["spec"]["replicas"] = 0
        else:
          doc["spec"]["replicas"] = existing_replicas

      # Apply the individual document to the cluster
      try:
        doc_yaml = k8s.dict_to_yaml(doc)
        kubectl.apply(doc_yaml)

      except ExecutableError:
        fail("Error: 'kubectl' command not found. Is it installed and in PATH?")
      except ToolError as e:
        fail(
          f"Error applying {resource_id}: {e}\nstdout:\n{e.stdout}\nstderr:\n{e.stderr}"
        )
      except Exception as e:
        fail(
          f"An unexpected error occurred during kubectl apply for {resource_id}: {e}"
        )

    ok()
