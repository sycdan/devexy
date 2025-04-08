import hashlib
import io
import json
from argparse import Namespace
from typing import Any, Dict, Optional, Tuple

import yaml

from devexy import settings
from devexy.settings import APP_DIR, KUSTOMIZE_ROOT
from devexy.utils.text import quick_hash, secure_hash

DEFAULT_RESOURCE_KIND = "__unspecified_kind__"
DEFAULT_NAMESPACE = "default"
CLUSTER_HASH = secure_hash(str(KUSTOMIZE_ROOT.resolve()))
HASH_CACHE_FILE = APP_DIR / "k8s_cache" / CLUSTER_HASH / "hashes.json"
HASH_CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)


def get_metadata(doc: dict):
  return doc.get("metadata", {})


def get_resource_name(doc: dict):
  name = get_metadata(doc).get("name")
  if name is None:
    return quick_hash(dict_to_yaml(doc))
  return name


def get_resource_kind(doc: str):
  return doc.get("kind", DEFAULT_RESOURCE_KIND)


def get_namespace(doc: dict, default=DEFAULT_NAMESPACE):
  return get_metadata(doc).get("namespace", default)


def kind_is_scalable(kind: str):
  return kind.lower() in ["deployment", "replicaset", "statefulset"]


def is_scalable(doc: dict):
  return kind_is_scalable(get_resource_kind(doc))


def get_key_fields(doc: dict):
  return dict(
    namespace=get_namespace(doc),
    resource_kind=get_resource_kind(doc),
    resource_name=get_resource_name(doc),
  )


def dict_to_yaml(doc: dict):
  doc_yaml_stream = io.StringIO()
  yaml.dump(doc, doc_yaml_stream, sort_keys=True, default_flow_style=False)
  doc_yaml = doc_yaml_stream.getvalue()
  doc_yaml_stream.close()
  return doc_yaml


def get_resource_key(doc: Dict[str, Any]) -> str:
  """
  Generates a unique key for a Kubernetes resource within the cluster.
  """
  if not isinstance(doc, dict):
    raise ValueError(
      f"Attempted to get resource key from non-dictionary item: {type(doc)}"
    )

  key_fields = get_key_fields(doc)
  return "/".join(
    (
      key_fields["namespace"],
      key_fields["resource_kind"],
      key_fields["resource_name"],
    )
  ).lower()


def _load_cache() -> dict:
  """Loads the hash cache from the file."""
  if HASH_CACHE_FILE.exists():
    try:
      with open(HASH_CACHE_FILE, "r") as f:
        content = f.read()
        if not content:
          return {}
        return json.loads(content)
    except (json.JSONDecodeError, IOError, TypeError) as e:
      print(
        f"Warning: Could not load kubectl cache ({HASH_CACHE_FILE}): {e}. Starting with empty cache."
      )
      return {}
  return {}


def _save_cache(cache_data: dict):
  """Saves the hash cache to the file."""
  try:
    with open(HASH_CACHE_FILE, "w") as f:
      json.dump(cache_data, f, indent=2)
  except IOError as e:
    print(f"Warning: Could not save kubectl cache ({HASH_CACHE_FILE}): {e}")


def check_cache(resource_key: str, doc: Dict[str, Any]) -> Tuple[bool, Optional[str]]:
  """
  Checks if a resource needs applying based purely on the cached hash of its content.

  Args:
      resource_key: The unique identifier for the resource (e.g., Kind/Namespace/Name).
      doc: The dictionary representing the parsed YAML document.

  Returns:
      A tuple: (should_apply: bool, current_hash: str | None).
               current_hash is the hash calculated for the content,
               to be stored in the cache upon successful apply. Returns None for hash
               if hashing fails or doc is invalid.
  """
  if not isinstance(doc, dict):
    print(
      f"Warning: Invalid document structure passed to check_cache for {resource_key}. Skipping."
    )
    return False, None

  cache = _load_cache()
  cached_hash = cache.get(resource_key)
  current_hash = None

  try:
    # Serialize the doc consistently for hashing
    # Use sort_keys=True for deterministic output
    serialized_doc_for_hash = yaml.dump(doc, sort_keys=True, default_flow_style=False)
    current_hash = secure_hash(serialized_doc_for_hash)

    should_apply = current_hash != cached_hash
    return should_apply, current_hash

  except Exception as e:  # Catch errors during serialization or hashing
    print(
      f"Warning: Could not calculate hash or process doc for {resource_key}: {e}. Skipping."
    )
    return False, None  # Apply should not proceed if hashing fails


def update_cache(resource_key: str, hash_to_store: str):
  """Updates the cache file with the new hash for a given resource."""
  if not resource_key or not hash_to_store:
    print("Warning: Attempted to update cache with invalid key or hash. Skipping.")
    return

  # Ensure we don't store None hash
  if hash_to_store is None:
    print(
      f"Warning: Attempted to update cache with None hash for key {resource_key}. Skipping."
    )
    return

  cache = _load_cache()
  cache[resource_key] = hash_to_store
  _save_cache(cache)
  if settings.NOISY:
    print(f"Cache updated for resource: {resource_key}")
