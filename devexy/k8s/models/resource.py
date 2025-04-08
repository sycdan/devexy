import functools
import json
import random
import threading
import time
from pathlib import Path
from typing import Any

from devexy.k8s import utils
from devexy.k8s.utils import STATE_CACHE_ROOT
from devexy.tools.kubectl import kubectl
from devexy.utils.logging import get_logger
from devexy.utils.safe_dict import SafeDict
from devexy.utils.text import quick_hash

logger = get_logger(__name__)


class Resource:
  def __init__(self, doc: dict):
    self._doc = doc
    self._state_cache = SafeDict()
    try:
      self._state_cache.update(self._load_state_cache())
    except Exception as e:
      logger.warning("Failed to load state cache: %s", e, exc_info=True)

    if self.is_scalable:
      thread = threading.Thread(target=self._monitor_state, daemon=True)
      thread.start()

  @functools.cached_property
  def name(self):
    return self._doc.get("metadata", {}).get("name")

  @functools.cached_property
  def kind(self):
    return self._doc.get("kind")

  @functools.cached_property
  def namespace(self):
    return self._doc.get("metadata", {}).get("namespace", "default")

  @functools.cached_property
  def key(self):
    return f"{self.namespace}/{self.kind}/{self.name}".lower()

  @functools.cached_property
  def is_scalable(self):
    return self.kind.lower() in ["deployment", "replicaset", "statefulset"]

  def set_replicas(self, replicas: int):
    if "spec" not in self._doc:
      self._doc["spec"] = {}
    self._doc["spec"]["replicas"] = replicas

  def __str__(self):
    return self.name

  def __repr__(self):
    return self.key

  @property
  def yaml(self):
    return utils.dict_to_yaml(self._doc)

  @property
  def state_hash(self):
    return utils.quick_hash(self.yaml)

  @functools.cached_property
  def key_hash(self):
    if not self.key:
      # This should ideally not happen if used after __init__ sets up the doc
      raise ValueError("Resource key is not available to generate state file path.")
    return quick_hash(self.key)

  @functools.cached_property
  def _state_file_path(self) -> Path:
    """Generates the path to the state cache file for this resource."""
    filename = f"{self.key_hash}.json"
    # Cache root should be created on first run
    return STATE_CACHE_ROOT / filename

  def _load_state_cache(self):
    """Loads the state cache from this resource's JSON file."""
    state_file = self._state_file_path

    if not state_file.exists():
      logger.debug("Cache file for %s does not exist: %s", self.key, state_file)
      return {}

    with open(state_file, "r") as f:
      content = f.read()
      if content:
        state = json.loads(content)
        logger.info("Loaded state cache for %s from %s", self.key, state_file)
        logger.debug("State for %s: %s", self.key, state)
        return state
      else:
        logger.debug("Cache file for %s is empty: %s", self.key, state_file)
        return {}

  def _set_state(self, key: str, value: Any):
    self._state_cache[key] = value
    self._dump_state_cache()

  def _get_cache(self, key: str, default: Any = None):
    return self._state_cache.get(key, default)

  def _del_state(self, key: str):
    try:
      del self._state_cache[key]
    except KeyError:
      pass

  def _dump_state_cache(self):
    """Saves the current state cache to this resource's JSON file."""
    try:
      with open(self._state_file_path, "w") as f:
        json.dump(self._state_cache, f, indent=2)
      logger.debug("Saved state cache for %s to %s", self.key, self._state_file_path)
    except (IOError, TypeError, ValueError) as e:
      logger.error(
        "Failed to save state cache for %s to %s: %s",
        self.key,
        self._state_file_path,
        e,
      )

  def _monitor_state(self):
    """Runs in a thread to keep the local state cache warm."""
    while True:
      try:
        replicas = kubectl.get_replicas(self.kind, self.name, self.namespace)
        self._set_state("replicas", replicas)
      except Exception as e:
        self._del_state("replicas")
        logger.warning("Failed to get replica count for %s: %s", self.key, e)
      time.sleep(random.uniform(1, 2))

  def apply(self):
    current_hash = self.state_hash
    last_applied_hash = self._get_cache("last_applied_hash")

    if current_hash != last_applied_hash:
      logger.info("Applying resource %s (hash changed)", self.key)
      try:
        if kubectl.apply(self.yaml):
          self._set_state("last_applied_hash", current_hash)
          return True
        return None
      except Exception as e:
        logger.error("Failed to apply resource %s: %s", self.key, e)
        return None
    else:
      logger.debug("No changes detected for %s, skipping apply", self.key)
      return False
