from devexy.bases.tool import Tool
from devexy.exceptions import ExecutableError, ToolError


class Minikube(Tool):
  def __init__(self):
    super().__init__("minikube")

  @property
  def is_installed(self) -> bool:
    try:
      self.exec("version")
      return True
    except (ExecutableError, ToolError):
      return False

  @property
  def is_initialized(self) -> bool:
    try:
      self.exec("status")
      return True
    except (ExecutableError, ToolError):
      return False

  def delete(self) -> bool:
    try:
      self.exec("delete")
      return True
    except (ExecutableError, ToolError):
      return False

  def start(self) -> bool:
    try:
      self.exec("start")
      return True
    except (ExecutableError, ToolError):
      return False

  def stop(self) -> bool:
    try:
      self.exec("stop")
      return True
    except (ExecutableError, ToolError):
      return False


minikube = Minikube()
