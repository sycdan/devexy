from devexy.bases.tool import Tool
from devexy.exceptions import ToolError


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

  def resource_exists(self, kind: str, name: str, namespace: str = "default") -> bool:
    try:
      # Use '-o name' for a lightweight check that doesn't fetch the full resource
      args = [
        "get",
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

  def get_replicas(
    self,
    resource_name: str,
    resource_kind: str,
    namespace: str,
  ) -> int | None:
    try:
      # Using jsonpath directly might fail if the resource doesn't exist or lacks the field.
      # A simple 'get' first might be safer, but this is more direct.
      output = self.exec(
        "get",
        resource_kind.lower(),
        resource_name,
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
        raise RuntimeError(
          f"Error getting replicas for {resource_kind}/{resource_name} in namespace {namespace}: {e.stderr}"
        ) from e


kubectl = Kubectl()
