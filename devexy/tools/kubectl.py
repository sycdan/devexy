import subprocess
from typing import Optional

from devexy.tools.tool import Tool
from devexy.exceptions import ToolError
from devexy.utils import logging

logger = logging.get_logger(__name__)


class Kubectl(Tool):
  def __init__(self):
    super().__init__("kubectl")

  def apply(self, yaml_content: str) -> bool:
    try:
      self.exec("apply", "-f", "-", input=yaml_content)
      return True
    except ToolError:
      return False

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
    resource_kind: str,
    resource_name: str,
    namespace: str = "default",
  ) -> bool:
    try:
      # Use '-o name' for a lightweight check that doesn't fetch the full resource
      args = [
        "kubectl",
        resource_kind.lower(),
        resource_name,
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
        raise RuntimeError(f"Error checking resource {namespace}/{resource_kind}/{resource_name}: {e.stderr}") from e

  def get_replicas(
    self,
    kind: str,
    name: str,
    namespace: str = "default",
  ) -> int | None:
    """
    Returns:
      None if the resource does not, otherwise the replica count as an integer.
    """
    try:
      # Using jsonpath directly might fail if the resource doesn't exist or lacks the field.
      # A simple 'get' first might be safer, but this is more direct.
      output = self.exec(
        "get",
        kind,
        name,
        "-n",
        namespace,
        "-o",
        "jsonpath='{.spec.replicas}'",
      )
      # The output might have single quotes around it from jsonpath
      return int(output.strip("'"))
    except ToolError as e:
      # Check if the error indicates "NotFound"
      if "NotFound" in e.stderr:
        return None  # Resource does not exist
      else:
        raise RuntimeError(f"Error getting replicas for {kind}/{name} in namespace {namespace}: {e.stderr}") from e

  def port_forward(
    self,
    kind: str,
    name: str,
    namespace: str,
    local_port: int,
    target_port: int,
  ) -> Optional[subprocess.Popen]:
    """Starts 'kubectl port-forward' in the background.

    Args:
        kind: The resource kind (e.g., 'Service').
        name: The resource name.
        namespace: The resource namespace.
        local_port: The local port to forward from.
        target_port: The target port on the resource to forward to.

    Returns:
        A subprocess.Popen object representing the running port-forward command,
        or None if the command failed to start. Raises ToolError on failure.
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


kubectl = Kubectl()
