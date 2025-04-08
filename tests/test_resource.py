import copy
import json
from unittest.mock import patch

import pytest

from devexy.k8s.models.resource import Resource
from devexy.k8s.utils import STATE_CACHE_ROOT
from devexy.utils.text import quick_hash


@pytest.fixture
def test_doc():
  return {
    "apiVersion": "apps/v1",
    "kind": "Deployment",
    "metadata": {"name": "test-deploy", "namespace": "test-ns"},
    "spec": {
      "replicas": 3,
      "template": {
        "spec": {
          "containers": [
            {
              "name": "nginx",
              "image": "nginx:latest",
              "ports": [{"containerPort": 80}],
            }
          ]
        }
      },
    },
  }


@pytest.fixture
def pod_doc():
  return {
    "apiVersion": "v1",
    "kind": "Pod",
    "metadata": {"name": "test-pod", "namespace": "test-ns"},
    "spec": {
      "containers": [
        {
          "name": "nginx",
          "image": "nginx:latest",
          "ports": [{"containerPort": 8080}],
        }
      ]
    },
  }


@pytest.fixture
def service_doc():
  return {
    "apiVersion": "v1",
    "kind": "Service",
    "metadata": {"name": "test-svc", "namespace": "test-ns"},
    "spec": {
      "selector": {"app": "MyApp"},
      "ports": [{"protocol": "TCP", "port": 80, "targetPort": 9376}],
    },
  }


@pytest.fixture
def no_ports_doc():
  return {
    "apiVersion": "v1",
    "kind": "ConfigMap",
    "metadata": {"name": "test-cm", "namespace": "test-ns"},
    "data": {"key": "value"},
  }


@pytest.fixture
def resource_instance_factory(tmp_path):
  original_cache_root = STATE_CACHE_ROOT
  # Use monkeypatch from pytest to temporarily change the constant
  mpatch = pytest.MonkeyPatch()
  mpatch.setattr("devexy.k8s.utils.STATE_CACHE_ROOT", tmp_path)
  mpatch.setattr("devexy.k8s.models.resource.STATE_CACHE_ROOT", tmp_path)

  def _factory(doc):
    with patch("threading.Thread") as mock_thread:
      resource = Resource(doc)
      return resource

  yield _factory

  # Restore original cache root after test
  mpatch.setattr("devexy.k8s.utils.STATE_CACHE_ROOT", original_cache_root)
  mpatch.setattr("devexy.k8s.models.resource.STATE_CACHE_ROOT", original_cache_root)


@pytest.fixture
def resource_instance(resource_instance_factory, test_doc):
  return resource_instance_factory(test_doc)


@pytest.fixture
def cache_file_path(resource_instance, tmp_path):
  filename = resource_instance._k8s_state_file_name
  return tmp_path / filename


def test_resource_hash_generation(test_doc):
  doc1 = copy.deepcopy(test_doc)
  doc1["spec"]["replicas"] = 0
  with patch("threading.Thread"):
    resource1 = Resource(doc1)

  doc2 = copy.deepcopy(test_doc)
  doc2["spec"]["replicas"] = 1
  with patch("threading.Thread"):
    resource2 = Resource(doc2)

  assert resource1.state_hash != resource2.state_hash


def test_cache_file_path_generation(resource_instance, cache_file_path):
  assert str(resource_instance._k8s_state_file_path) == str(cache_file_path)
  assert str(cache_file_path).endswith(".json")
  assert quick_hash(resource_instance.key) in str(cache_file_path)


def test_load_k8s_state_when_file_does_not_exist(resource_instance, cache_file_path):
  assert not cache_file_path.exists()
  assert resource_instance._k8s_state == {}
  loaded_state = resource_instance._load_k8s_state()
  assert loaded_state == {}


def test_load_k8s_state_with_empty_file(resource_instance, cache_file_path):
  cache_file_path.touch()
  assert cache_file_path.exists()
  with patch("threading.Thread"):
    resource = Resource(resource_instance._doc)
  assert resource._k8s_state == {}


def test_load_k8s_state_invalid_json(resource_instance, cache_file_path):
  cache_file_path.write_text("this is not json")
  assert cache_file_path.exists()
  with patch("threading.Thread"):
    resource = Resource(resource_instance._doc)
  assert resource._k8s_state == {}


def test_load_k8s_state_valid_json(resource_instance, cache_file_path):
  expected_state = {"last_applied_hash": "somehash123", "replicas": 5}
  cache_file_path.write_text(json.dumps(expected_state))
  assert cache_file_path.exists()
  with patch("threading.Thread"):
    resource = Resource(resource_instance._doc)
  assert resource._k8s_state == expected_state


def test_dump_k8s_state(resource_instance, cache_file_path):
  test_state = {"foo": "bar", "count": 10}
  resource_instance._k8s_state = test_state
  resource_instance._dump_k8s_state()
  assert cache_file_path.exists()
  with open(cache_file_path, "r") as f:
    saved_state = json.load(f)
  assert saved_state == test_state


@patch("devexy.k8s.models.resource.kubectl")
def test_apply_updates_cache_on_change_success(mock_kubectl, resource_instance, cache_file_path):
  mock_kubectl.apply.return_value = True
  resource_instance._k8s_state = {}

  current_hash = resource_instance.state_hash
  assert "last_applied_hash" not in resource_instance._k8s_state

  result = resource_instance.apply()
  assert result is True

  mock_kubectl.apply.assert_called_once_with(resource_instance.yaml)
  assert resource_instance._k8s_state.get("last_applied_hash") == current_hash

  assert cache_file_path.exists()
  with open(cache_file_path, "r") as f:
    saved_state = json.load(f)
  assert saved_state.get("last_applied_hash") == current_hash


@patch("devexy.k8s.models.resource.kubectl")
def test_apply_does_not_update_cache_on_no_change(mock_kubectl, resource_instance, cache_file_path):
  current_hash = resource_instance.state_hash
  resource_instance._k8s_state = {"last_applied_hash": current_hash}
  resource_instance._dump_k8s_state()

  initial_mtime = cache_file_path.stat().st_mtime

  result = resource_instance.apply()
  assert result is False

  mock_kubectl.apply.assert_not_called()
  assert resource_instance._k8s_state.get("last_applied_hash") == current_hash

  assert cache_file_path.stat().st_mtime == initial_mtime


@patch("devexy.k8s.models.resource.kubectl")
def test_apply_does_not_update_cache_on_failure(mock_kubectl, resource_instance, cache_file_path):
  """Test that apply does not update cache if kubectl apply fails."""
  mock_kubectl.apply.return_value = False
  initial_hash = "oldhash123"
  resource_instance._k8s_state = {"last_applied_hash": initial_hash}
  resource_instance._dump_k8s_state()

  result = resource_instance.apply()
  assert result is None

  mock_kubectl.apply.assert_called_once()
  assert resource_instance._k8s_state.get("last_applied_hash") == initial_hash

  with open(cache_file_path, "r") as f:
    saved_state = json.load(f)
  assert saved_state.get("last_applied_hash") == initial_hash


def test_infer_target_port_deployment(resource_instance_factory, test_doc):
  resource = resource_instance_factory(test_doc)
  assert resource._infer_target_port() == 80


def test_infer_target_port_pod(resource_instance_factory, pod_doc):
  resource = resource_instance_factory(pod_doc)
  assert resource._infer_target_port() == 8080


def test_infer_target_port_service(resource_instance_factory, service_doc):
  resource = resource_instance_factory(service_doc)
  assert resource._infer_target_port() == 80


def test_infer_target_port_no_ports(resource_instance_factory, no_ports_doc):
  resource = resource_instance_factory(no_ports_doc)
  assert resource._infer_target_port() is None
