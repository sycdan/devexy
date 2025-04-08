import json
import os
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from devexy.k8s.models.resource import Resource
from devexy.k8s.utils import STATE_CACHE_ROOT, secure_hash


@pytest.fixture
def test_doc():
  return {
    "apiVersion": "apps/v1",
    "kind": "Deployment",
    "metadata": {"name": "test-deploy", "namespace": "test-ns"},
    "spec": {"replicas": 3},
  }


@pytest.fixture
def resource_instance(test_doc, tmp_path):
  # Ensure STATE_CACHE_ROOT points to a temporary directory for testing
  original_cache_root = STATE_CACHE_ROOT
  # Use monkeypatch from pytest to temporarily change the constant
  # This requires importing monkeypatch fixture
  pytest.MonkeyPatch().setattr("devexy.k8s.utils.STATE_CACHE_ROOT", tmp_path)
  pytest.MonkeyPatch().setattr("devexy.k8s.models.resource.STATE_CACHE_ROOT", tmp_path)

  # Mock the monitoring thread started in __init__
  with patch("threading.Thread") as mock_thread:
    resource = Resource(test_doc)
    mock_thread.assert_called_once()  # Ensure thread was initiated for scalable resource
    yield resource  # Provide the resource to the test

  # Restore original cache root after test (though tmp_path handles cleanup)
  pytest.MonkeyPatch().setattr("devexy.k8s.utils.STATE_CACHE_ROOT", original_cache_root)
  pytest.MonkeyPatch().setattr(
    "devexy.k8s.models.resource.STATE_CACHE_ROOT", original_cache_root
  )


@pytest.fixture
def cache_file_path(resource_instance, tmp_path):
  # Calculate the expected cache file path within the temp directory
  expected_filename = f"{secure_hash(resource_instance.key)}.json"
  return tmp_path / expected_filename


def test_resource_hash(test_doc):
  base_doc = test_doc.copy()
  del base_doc["spec"]  # Start without spec for this specific test

  doc1 = base_doc.copy()
  doc1["spec"] = {"replicas": 0}
  # Mock thread for non-caching test
  with patch("threading.Thread"):
    resource1 = Resource(doc1)

  doc2 = base_doc.copy()
  doc2["spec"] = {"replicas": 1}
  with patch("threading.Thread"):
    resource2 = Resource(doc2)

  assert resource1.state_hash != resource2.state_hash


def test_state_file_path_generation(resource_instance, cache_file_path):
  """Verify the state cache file path is generated correctly."""
  assert resource_instance._state_file_path == cache_file_path
  assert str(cache_file_path).endswith(".json")
  assert secure_hash(resource_instance.key) in str(cache_file_path)


def test_load_state_cache_file_not_exist(resource_instance, cache_file_path):
  """Test loading cache when the file doesn't exist."""
  assert not cache_file_path.exists()
  # _load_state_cache is called during init, access the result via _state_cache
  assert resource_instance._state_cache == {}
  # Call again explicitly to ensure it handles missing file correctly
  loaded_state = resource_instance._load_state_cache()
  assert loaded_state == {}


def test_load_state_cache_empty_file(resource_instance, cache_file_path):
  """Test loading cache when the file is empty."""
  cache_file_path.touch()
  assert cache_file_path.exists()
  # Re-initialize resource to trigger load with the empty file
  with patch("threading.Thread"):
    resource = Resource(resource_instance._doc)
  assert resource._state_cache == {}


def test_load_state_cache_invalid_json(resource_instance, cache_file_path):
  """Test loading cache when the file contains invalid JSON."""
  cache_file_path.write_text("this is not json")
  assert cache_file_path.exists()
  # Re-initialize resource to trigger load
  with patch("threading.Thread"):
    resource = Resource(resource_instance._doc)
  assert resource._state_cache == {}


def test_load_state_cache_valid_json(resource_instance, cache_file_path):
  """Test loading cache when the file contains valid JSON."""
  expected_state = {"last_applied_hash": "somehash123", "replicas": 5}
  cache_file_path.write_text(json.dumps(expected_state))
  assert cache_file_path.exists()
  # Re-initialize resource to trigger load
  with patch("threading.Thread"):
    resource = Resource(resource_instance._doc)
  assert resource._state_cache == expected_state


def test_save_state_cache(resource_instance, cache_file_path):
  """Test saving the state cache to a file."""
  test_state = {"foo": "bar", "count": 10}
  resource_instance._state_cache = test_state
  resource_instance._save_state_cache()

  assert cache_file_path.exists()
  with open(cache_file_path, "r") as f:
    saved_state = json.load(f)
  assert saved_state == test_state


@patch("devexy.k8s.models.resource.kubectl")
def test_apply_updates_cache_on_change_success(
  mock_kubectl, resource_instance, cache_file_path
):
  """Test that apply updates and saves cache when hash changes and apply succeeds."""
  mock_kubectl.apply.return_value = True  # Simulate successful apply
  resource_instance._state_cache = {}  # Start with empty cache

  current_hash = resource_instance.hash
  assert "last_applied_hash" not in resource_instance._state_cache

  result = resource_instance.apply()

  assert result is True
  mock_kubectl.apply.assert_called_once_with(resource_instance.yaml)
  assert resource_instance._state_cache.get("last_applied_hash") == current_hash

  # Verify cache was saved
  assert cache_file_path.exists()
  with open(cache_file_path, "r") as f:
    saved_state = json.load(f)
  assert saved_state.get("last_applied_hash") == current_hash


@patch("devexy.k8s.models.resource.kubectl")
def test_apply_does_not_update_cache_on_no_change(
  mock_kubectl, resource_instance, cache_file_path
):
  """Test that apply does nothing if hash hasn't changed."""
  current_hash = resource_instance.hash
  resource_instance._state_cache = {"last_applied_hash": current_hash}
  resource_instance._save_state_cache()  # Save initial state

  initial_mtime = cache_file_path.stat().st_mtime

  result = resource_instance.apply()

  assert result is False
  mock_kubectl.apply.assert_not_called()
  assert resource_instance._state_cache.get("last_applied_hash") == current_hash

  # Verify cache was NOT saved again
  assert cache_file_path.stat().st_mtime == initial_mtime


@patch("devexy.k8s.models.resource.kubectl")
def test_apply_does_not_update_cache_on_failure(
  mock_kubectl, resource_instance, cache_file_path
):
  """Test that apply does not update cache if kubectl apply fails."""
  mock_kubectl.apply.return_value = False  # Simulate failed apply
  initial_hash = "oldhash123"
  resource_instance._state_cache = {"last_applied_hash": initial_hash}
  resource_instance._save_state_cache()  # Save initial state

  result = resource_instance.apply()

  assert result is None  # Indicates failure
  mock_kubectl.apply.assert_called_once()
  # Cache should NOT be updated with the new hash on failure
  assert resource_instance._state_cache.get("last_applied_hash") == initial_hash

  # Verify cache file still contains the old hash
  with open(cache_file_path, "r") as f:
    saved_state = json.load(f)
  assert saved_state.get("last_applied_hash") == initial_hash
