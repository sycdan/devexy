from subprocess import CompletedProcess

import pytest
import yaml

from devexy.tools.kubectl import kubectl


def test_apply_success(mocker):
  mocker.patch(
    "devexy.utils.proc.run",
    return_value=CompletedProcess(
      args=["kubectl", "apply", "-f", "-"],
      returncode=0,
      stdout="resource applied",
    ),
  )
  yaml_content = yaml.dump(
    {
      "apiVersion": "v1",
      "kind": "Pod",
      "metadata": {"name": "test-pod"},
    }
  )
  result = kubectl.apply(yaml_content)
  assert result is True


def test_apply_failure(mocker):
  mocker.patch(
    "devexy.utils.proc.run",
    return_value=CompletedProcess(
      args=["kubectl", "apply", "-f", "-"],
      returncode=1,
      stderr="failed to apply",
    ),
  )
  yaml_content = yaml.dump(
    {
      "apiVersion": "v1",
      "kind": "Pod",
      "metadata": {"name": "test-pod"},
    }
  )
  result = kubectl.apply(yaml_content)
  assert result is False


def test_create_namespace_if_not_exists_created(mocker):
  mocker.patch(
    "devexy.utils.proc.run",
    return_value=CompletedProcess(
      args=["kubectl", "create", "namespace", "test-ns"],
      returncode=0,
      stdout="namespace/test-ns created",
    ),
  )
  result = kubectl.create_namespace_if_not_exists("test-ns")
  assert result is True


def test_create_namespace_if_not_exists_already_exists(mocker):
  mocker.patch(
    "devexy.utils.proc.run",
    return_value=CompletedProcess(
      args=["kubectl", "create", "namespace", "test-ns"],
      returncode=1,
      stderr="Error from server (AlreadyExists)",
    ),
  )
  result = kubectl.create_namespace_if_not_exists("test-ns")
  assert result is False


def test_resource_exists_yes(mocker):
  mocker.patch(
    "devexy.utils.proc.run",
    return_value=CompletedProcess(
      args=[
        "kubectl",
        "get",
        "deployment",
        "test-deploy",
        "-o",
        "name",
        "-n",
        "default",
      ],
      returncode=0,
      stdout="deployment/test-deploy",
    ),
  )
  result = kubectl.resource_exists("deployment", "test-deploy")
  assert result is True


def test_resource_exists_no(mocker):
  mocker.patch(
    "devexy.utils.proc.run",
    return_value=CompletedProcess(
      args=[
        "kubectl",
        "get",
        "deployment",
        "test-deploy",
        "-o",
        "name",
        "-n",
        "default",
      ],
      returncode=1,
      stderr='Error from server (NotFound): deployments.apps "test-deploy" not found',
    ),
  )
  result = kubectl.resource_exists("deployment", "test-deploy")
  assert result is False


def test_resource_exists_failure(mocker):
  mocker.patch(
    "devexy.utils.proc.run",
    return_value=CompletedProcess(
      args=[
        "kubectl",
        "get",
        "deployment",
        "test-deploy",
        "-o",
        "name",
        "-n",
        "default",
      ],
      returncode=1,
      stderr="Unexpected error",
    ),
  )
  with pytest.raises(RuntimeError):
    kubectl.resource_exists("deployment", "test-deploy")


def test_get_replicas_success(mocker):
  mocker.patch(
    "devexy.utils.proc.run",
    return_value=CompletedProcess(
      args=[
        "kubectl",
        "get",
        "deployment",
        "test-deploy",
        "-n",
        "default",
        "-o",
        "jsonpath='{.status.replicas}'",
      ],
      returncode=0,
      stdout="3",
    ),
  )
  result = kubectl.get_replicas(
    "test-deploy",
    "deployment",
    "default",
  )
  assert result == 3


def test_get_replicas_not_found(mocker):
  mocker.patch(
    "devexy.utils.proc.run",
    return_value=CompletedProcess(
      args=[
        "kubectl",
        "get",
        "deployment",
        "test-deploy",
        "-n",
        "default",
        "-o",
        "jsonpath='{.status.replicas}'",
      ],
      returncode=1,
      stderr='Error from server (NotFound): deployments.apps "test-deploy" not found',
    ),
  )
  result = kubectl.get_replicas(
    "test-deploy",
    "deployment",
    "default",
  )
  assert result is None


def test_get_replicas_failure(mocker):
  mocker.patch(
    "devexy.utils.proc.run",
    return_value=CompletedProcess(
      args=[
        "kubectl",
        "get",
        "deployment",
        "test-deploy",
        "-n",
        "default",
        "-o",
        "jsonpath='{.status.replicas}'",
      ],
      returncode=1,
      stderr="Unexpected error",
    ),
  )
  with pytest.raises(RuntimeError):
    kubectl.get_replicas(
      "test-deploy",
      "deployment",
      "default",
    )
