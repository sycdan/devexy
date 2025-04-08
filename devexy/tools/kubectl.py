import json
import subprocess

from devexy.constants import K8S_DEFAULT_NAMESPACE
from devexy.exceptions import ToolError
from devexy.k8s.utils import get_last_applied_configuration, get_name
from devexy.tools.tool import Tool
from devexy.utils import logging
from devexy.utils.text import quick_hash

logger = logging.get_logger(__name__)


class Kubectl(Tool):
  def __init__(self):
    super().__init__("kubectl")

  def apply(self, yaml_content: str) -> bool:
    response = self.exec("apply", "-f", "-", input=yaml_content)
    hash = quick_hash(yaml_content)
    logger.debug(f"kubectl apply response for {hash}: %s", response)
    if response:
      if response.strip().endswith("unchanged"):
        return False
      return True

  def create_namespace_if_not_exists(self, namespace: str) -> str:
    """Safely creates a namespace.

    Args:
        namespace (str): The namespace to create.

    Returns:
        str: True if created, else False.
    """
    try:
      self.exec("create", "namespace", namespace)
      return True
    except ToolError as e:
      if "AlreadyExists" in e.stderr:
        return False
      else:
        raise RuntimeError(f"Error creating {namespace}: {e.stderr}") from e

  def resource_exists(
    self,
    kind: str,
    name: str,
    namespace: str = "default",
  ) -> bool:
    try:
      # Use '-o name' for a lightweight check that doesn't fetch the full resource
      args = [
        "kubectl",
        kind.lower(),
        name,
        "-o",
        "name",
      ]
      if namespace:
        args.extend(["-n", namespace])
      self.exec(*args)
      return True
    except ToolError as e:
      if "NotFound" in e.stderr:
        return False
      else:
        raise RuntimeError(
          f"Error checking resource {namespace}/{kind}/{name}: {e.stderr}"
        ) from e

  def get_last_applied_doc(
    self,
    kind: str,
    name: str,
    namespace: str = "default",
  ) -> dict | None:
    doc = self.get_current_state(
      kind=kind,
      name=name,
      namespace=namespace,
    )
    if doc:
      return get_last_applied_configuration(doc)

  def get_current_state(
    self,
    kind: str,
    name: str,
    namespace: str = "default",
  ) -> dict | None:
    try:
      return json.loads(self.exec("get", kind, name, "-n", namespace, "-o", "json"))
    except ToolError as e:
      if "NotFound" in e.stderr:
        return None
      else:
        raise RuntimeError(
          f"Error getting current state for {kind}/{name} in namespace {namespace}: {e.stderr}"
        ) from e

  def port_forward(
    self,
    kind: str,
    name: str,
    namespace: str,
    local_port: int,
    target_port: int,
  ) -> subprocess.Popen:
    """Starts 'kubectl port-forward' in the background.

    Args:
        kind: The resource kind (e.g., 'Service').
        name: The resource name.
        namespace: The resource namespace.
        local_port: The local port to forward from.
        target_port: The target port on the resource to forward to.

    Returns:
        A subprocess.Popen object representing the running port-forward command.
    """
    resource_key = f"{kind.lower()}/{name}"
    port_mapping = f"{local_port}:{target_port}"
    command_args = [
      resource_key,
      port_mapping,
      "-n",
      namespace,
    ]
    process = self.start("port-forward", *command_args)
    logger.info(
      "Started port-forward %s for %s (PID: %d)",
      port_mapping,
      resource_key,
      process.pid,
    )
    return process

  def get_resource_docs(
    self,
    kind: str,
    namespace: str = K8S_DEFAULT_NAMESPACE,
  ) -> list[dict]:
    """
    Fetches all resources of a specific kind from the Kubernetes cluster.

    Args:
        kind (str): The kind of resource to fetch (e.g., 'Deployment', 'Pod').

    Returns:
        list[dict]: A list of resources represented as dictionaries.

    Raises:
        RuntimeError: If fetching resources fails.
    """
    try:
      output = self.exec("get", kind, "-n", namespace, "-o", "json")
      resources = json.loads(output).get("items", [])
      return resources
    except ToolError as e:
      raise RuntimeError(f"Error fetching resources of kind {kind}: {e.stderr}") from e

  def get_namespaces(self) -> list[str]:
    """
    Fetches all namespaces from the Kubernetes cluster.

    Returns:
        list[str]: A list of namespace names.

    Raises:
        RuntimeError: If fetching namespaces fails.
    """
    try:
      output = self.exec("get", "namespaces", "-o", "json")
      namespaces = [get_name(item) for item in json.loads(output).get("items", [])]
      return namespaces
    except ToolError as e:
      raise RuntimeError(f"Error fetching namespaces: {e.stderr}") from e


kubectl = Kubectl()
