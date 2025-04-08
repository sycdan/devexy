from subprocess import CompletedProcess

from devexy.tools.minikube import minikube


def test_is_installed_returns_false_when_minikube_exe_not_found(mocker):
  mocker.patch(
    "devexy.utils.proc.run",
    side_effect=FileNotFoundError,
  )
  assert not minikube.is_installed


def test_is_installed_returns_true(mocker):
  mocker.patch(
    "devexy.utils.proc.run",
    return_value=CompletedProcess(
      args=["minikube", "version"],
      returncode=0,
      stdout="minikube version v1.23.0",
    ),
  )
  assert minikube.is_installed


def test_is_initialized_returns_true(mocker):
  mocker.patch(
    "devexy.utils.proc.run",
    return_value=CompletedProcess(
      args=["minikube", "status"],
      returncode=0,
      stdout="minikube\nhost: Running",
    ),
  )
  assert minikube.is_initialized


def test_is_initialized_returns_false(mocker):
  mocker.patch(
    "devexy.utils.proc.run",
    return_value=CompletedProcess(
      args=["minikube", "status"],
      returncode=1,
      stderr="minikube\nhost: Stopped",
    ),
  )
  assert not minikube.is_initialized


def test_start_returns_true(mocker):
  mocker.patch(
    "devexy.utils.proc.run",
    return_value=CompletedProcess(
      args=["minikube", "start"],
      returncode=0,
      stdout="minikube\nDone!",
    ),
  )
  assert minikube.start()


def test_start_returns_false(mocker):
  mocker.patch(
    "devexy.utils.proc.run",
    return_value=CompletedProcess(
      args=["minikube", "start"],
      returncode=1,
      stderr="failed to start",
    ),
  )
  assert not minikube.start()


def test_delete_returns_true(mocker):
  mocker.patch(
    "devexy.utils.proc.run",
    return_value=CompletedProcess(
      args=["minikube", "delete"],
      returncode=0,
      stdout="removed all traces of minikube",
    ),
  )
  assert minikube.delete()


def test_delete_returns_false(mocker):
  mocker.patch(
    "devexy.utils.proc.run",
    return_value=CompletedProcess(
      args=["minikube", "delete"],
      returncode=1,
      stderr="failed to delete",
    ),
  )
  assert not minikube.delete()
