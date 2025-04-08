import subprocess

from devexy.bases.tool import Tool
from devexy.exceptions import ExecutableError


class Kustomize(Tool):
  def __init__(self):
    super().__init__("kustomize")

  @property
  def is_installed(self) -> bool:
    try:
      self.exec("version")
      return True
    except (subprocess.CalledProcessError, ExecutableError):
      return False

  def build(self, path: str) -> str:
    """
    Runs 'kustomize build' on the given path and returns the YAML output.

    Args:
        path: The directory containing kustomization.yaml.

    Returns:
        The YAML output as a string.

    Raises:
        subprocess.CalledProcessError: If kustomize build fails.
        ExecutableError: If the kustomize executable is not found.
    """
    return self.exec("build", path)


kustomize = Kustomize()
