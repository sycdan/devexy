import threading
import time
from os import sep
from pathlib import Path
from turtle import st
from typing import Iterator, List

import typer
import yaml
from blessed import Terminal

from devexy import settings
from devexy.exceptions import ToolError
from devexy.k8s.models.resource import Resource
from devexy.k8s.utils import (
  SCALABLE_KINDS,
  clear_cache,
  get_key,
  get_last_applied_configuration,
  get_replicas,
  yaml_to_dicts,
)
from devexy.settings import KUSTOMIZE_OVERLAY_DIR, KUSTOMIZE_ROOT
from devexy.tools.kubectl import kubectl
from devexy.tools.kustomize import kustomize
from devexy.utils.cli import begin, fail, ok, say
from devexy.utils.logging import get_logger

logger = get_logger(__name__)
app = typer.Typer()
term = Terminal()


class ClusterTable:
  columns = (
    ("Namespace", 15),
    ("Kind", 15),
    ("Name", 20),
    ("Local Port", 15),
    ("Status", 15),
  )

  @property
  def selected_resource(self) -> Resource:
    return self.resources[self.selected_index]

  def __init__(self, resources):
    self.resources = [*resources]
    self.row_count = len(resources)
    self.selected_index = 0
    self.running = True
    self.input_thread = None

  @staticmethod
  def get_status(res: Resource):
    status = res.k8s_status

    unavailable_replicas = status.get("unavailableReplicas", 0)
    available_replicas = status.get("availableReplicas", 0)
    current_replicas = status.get("currentReplicas", 0)
    ready_replicas = status.get("readyReplicas", 0)

    if current_replicas > ready_replicas:
      return "starting"

    if available_replicas:
      if res.is_proxying:
        text = "☸ -> 💻"
      elif res.is_forwarding:
        text = "💻 -> ☸"
      else:
        text = "running"
      return text

    if unavailable_replicas and not available_replicas:
      return "unavailable"

    if not current_replicas:
      return "stopped"

    return "unknown"

  def render_table(self):
    row_template = "|".join(f"{{:^{x[1]}}}" for x in self.columns)

    def _clear_terminal():
      print(term.home + term.clear)

    def _render_header():
      header = row_template.format(*(x[0] for x in self.columns))
      print(term.bold(term.white(header)))

    def _render_separator():
      separator = "|".join("-" * x[1] for x in self.columns)
      print(term.bold(term.white(separator)))

    def _render_footer():
      footer = "[↑/↓] Move  [s] Start/Stop  [m] Remote/Local Mode  [q] Quit"
      print(
        term.move_xy(0, term.height - 1) + term.center(term.bold(term.cyan(footer))),
        end="",
        flush=True,
      )

    def _render_rows():
      for i, resource in enumerate(self.resources):
        row_values = _get_row_values(resource)
        _render_row(i, row_values)

    def _get_row_values(res: Resource):
      local_port = res.local_port or "undefined"
      status = self.get_status(res)

      return (
        res.namespace,
        res.kind,
        res.name,
        local_port,
        status,
      )

    def _render_row(i, row_values):
      row = row_template.format(*row_values)

      if i == self.selected_index:
        row = term.reverse(row)

      print(term.move_xy(0, 3 + i) + row)

    with term.fullscreen(), term.cbreak(), term.hidden_cursor():
      _clear_terminal()
      _render_header()
      _render_separator()
      _render_footer()

      while self.running:
        _render_rows()
        time.sleep(0.05)

  def handle_input(self):
    while self.running:
      key = term.inkey()
      if not key:
        continue

      logger.debug(f"key pressed: {key}")

      if key.code == term.KEY_UP:
        self.selected_index = (self.selected_index - 1) % self.row_count
      elif key.code == term.KEY_DOWN:
        self.selected_index = (self.selected_index + 1) % self.row_count
      elif key == "s":
        res = self.selected_resource
        if res.replicas:
          res.set_replicas(0, apply=True)
        else:
          res.set_replicas(1, apply=True)
          res.enable_services()
      elif key == "m":
        self.selected_resource.toggle_forwarding_mode()
      elif key == "q":
        self.running = False

  def run(self):
    self.input_thread = threading.Thread(target=self.handle_input, daemon=True)
    self.input_thread.start()
    self.render_table()
    self.input_thread.join()


@app.command()
def workon(
  apply: bool = typer.Option(
    False,
    help="Apply the current YAML sate to the cluster.",
  ),
):
  """Forward ports between localhost and the cluster, or vice-versa."""
  if apply:
    with begin("clearing state cache"):
      print("")  # dumb hack to make the message appear
      clear_cache()
      ok()
    apply_cluster_config()

  namespaces = kubectl.get_namespaces()
  scalable_resources = []

  with begin("querying cluster for scalable resources"):
    for namespace in namespaces:
      for kind in SCALABLE_KINDS:
        try:
          docs = kubectl.get_resource_docs(kind=kind, namespace=namespace)
          for doc in docs:
            last_applied = get_last_applied_configuration(doc)
            if last_applied:
              scalable_resources.append(Resource(last_applied))
            else:
              logger.warning(
                f"resource {get_key(doc)} has no last applied configuration."
              )
        except Exception as e:
          fail(f"failed while querying {kind} resources: {e}")
    scalable_count = len(scalable_resources)
    if scalable_count:
      ok(f"found {scalable_count} scalable resources")
    else:
      fail("no scalable resources found in the cluster")

  for resource in scalable_resources:
    resource.enable_services()

  ClusterTable(scalable_resources).run()


def ensure_namespaces(resources: list[Resource]):
  """Extracts namespaces from the provided documents and ensures they exist using kubectl."""
  namespaces = set()

  for resource in resources:
    namespace = resource.namespace
    if namespace:
      namespaces.add(namespace)

  if not namespaces:
    return

  with begin("checking namespaces"):
    for namespace in namespaces:
      kubectl.create_namespace_if_not_exists(namespace)
      ok(namespace)


def _iter_resources(yaml_content: str) -> Iterator[Resource]:
  for doc in yaml_to_dicts(yaml_content):
    yield Resource(doc)


def _set_initial_replicas(res: Resource):
  if res.is_scalable:
    last_applied = kubectl.get_last_applied_doc(
      kind=res.kind,
      name=res.name,
      namespace=res.namespace,
    )
    res.set_replicas(get_replicas(last_applied) if last_applied else 0)


def apply_cluster_config():
  """Builds cluster config via Kustomize and applies via kubectl.
  Scalable resources will be set to 0 replicas when deployed for the first time.
  Unchanged resources will not be re-deployed.
  """
  resources: List[Resource] = []
  changed_count = 0
  skipped_count = 0
  unchanged_count = 0

  if not kustomize.is_installed:
    fail("kustomize is not installed")

  kustomize_path = Path(KUSTOMIZE_ROOT).resolve()
  if not kustomize_path.is_dir():
    fail(f"invalid kustomize root directory: {KUSTOMIZE_ROOT}")

  overlay_path = KUSTOMIZE_OVERLAY_DIR.resolve()
  if not overlay_path.is_dir():
    fail(f"invalid overlay directory: {overlay_path}")
  if settings.DEBUG:
    say(f"using overlay {str(overlay_path)}")

  try:
    with begin("loading cluster configuration"):
      yaml_output = kustomize.build(overlay_path)
      # Resources will be grouped according to dependencies, so process in receive order
      for resource in _iter_resources(yaml_output):
        resources.append(resource)
      ok(f"{len(resources)} resources found")
  except ToolError as e:
    fail(f"{e}\n{e.stderr or ''}")
    return []
  except yaml.YAMLError as e:
    fail(f"error parsing YAML: {e}")
    return []

  ensure_namespaces(resources)

  with begin("applying configuration"):
    for resource in resources:
      try:
        _set_initial_replicas(resource)
      except Exception as e:
        logger.exception(f"error setting replicas for {resource.key}: {e}")

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
      fail(f"{summary} (encountered errors during apply)")
    else:
      ok(summary)


if __name__ == "__main__":
  app()
