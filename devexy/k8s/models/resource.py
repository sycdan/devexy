import atexit
import functools
import json
import random
import threading
import time
from pathlib import Path
from typing import Any, Optional

from devexy import settings
from devexy.k8s import utils
from devexy.k8s.utils import (
  STATE_CACHE_ROOT,
  get_kind,
  get_metadata,
  get_name,
  get_namespace,
)
from devexy.tools.kubectl import kubectl
from devexy.utils.logging import get_logger
from devexy.utils.safe_dict import SafeDict
from devexy.utils.text import quick_hash
from devexy.utils.threading import cleanup

logger = get_logger(__name__)


class Resource:
  _port_forward_process = None

  def __init__(self, doc: dict):
    self._doc = doc
    self._k8s_state = SafeDict()

    try:
      loaded_state = self._load_k8s_state()
      self._k8s_state.update(loaded_state)
    except Exception as e:
      logger.warning("Failed to load state cache: %s", e, exc_info=True)

    if self.is_scalable:
      self._monitor_thread = threading.Thread(target=self._monitor_state, daemon=True)
      self._monitor_thread.start()

      if self.replicas:
        self.start_port_forward()

  @functools.cached_property
  def name(self):
    return get_name(self._doc)

  @functools.cached_property
  def kind(self):
    return get_kind(self._doc)

  @functools.cached_property
  def namespace(self):
    return get_namespace(self._doc)

  @functools.cached_property
  def key(self):
    return f"{self.namespace}/{self.kind}/{self.name}".lower()

  @functools.cached_property
  def is_scalable(self):
    return self.kind.lower() in ["deployment", "replicaset", "statefulset"]

  @property
  def replicas(self):
    try:
      return self._k8s_state.get("replicas") or 0
    except Exception as e:
      logger.warning("Error fetching replicas for %s: %s", self.key, e)
      return None

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
    return quick_hash(self.yaml)

  @functools.cached_property
  def key_hash(self):
    return quick_hash(self.key)

  @functools.cached_property
  def _k8s_state_file_name(self) -> Path:
    filename = f"{self.key_hash}.json"
    return filename

  @functools.cached_property
  def _k8s_state_file_path(self) -> Path:
    filepath = STATE_CACHE_ROOT / self._k8s_state_file_name
    return filepath

  def _load_k8s_state(self):
    state_file = self._k8s_state_file_path

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
    self._k8s_state[key] = value
    logger.debug("Set key '%s' in state to %s for %s", key, value, self.key)
    self._dump_k8s_state()

  def _del_state(self, key: str):
    if key in self._k8s_state:
      del self._k8s_state[key]
      logger.debug("Removed key '%s' from state for %s", key, self.key)
      self._dump_k8s_state()

  def _dump_k8s_state(self):
    try:
      with open(self._k8s_state_file_path, "w") as f:
        json.dump(self._k8s_state, f, indent=2)
      logger.debug("Saved state cache for %s to %s", self.key, self._k8s_state_file_path)
    except (IOError, TypeError, ValueError) as e:
      logger.error(
        "Failed to save state cache for %s to %s: %s",
        self.key,
        self._k8s_state_file_path,
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
    last_applied_hash = self._k8s_state.get("last_applied_hash")

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

  def get_local_port(self, force=False):
    if not force:
      if cached_port := self._k8s_state.get("local_port"):
        return int(cached_port)

    annotation_name = settings.LOCAL_PORT_ANNOTATION
    annotations = get_metadata(self._doc).get("annotations", {})
    if annotation_name in annotations:
      try:
        return int(annotations[annotation_name])
      except ValueError:
        logger.warning(
          f"Invalid port value '{annotations[annotation_name]}' in annotation '{annotation_name}' for {self.key}."
        )

    return None

  def _infer_target_port(self) -> Optional[int]:
    """Tries to infer a suitable target port from the resource spec."""
    kind_lower = self.kind.lower()
    spec = self._doc.get("spec", {})

    try:
      if kind_lower == "pod":
        containers = spec.get("containers", [])
        for container in containers:
          ports = container.get("ports", [])
          for port_info in ports:
            if "containerPort" in port_info:
              logger.debug("Inferred target port %d from containerPort", port_info["containerPort"])
              return int(port_info["containerPort"])
      elif kind_lower in ["deployment", "statefulset", "replicaset"]:
        containers = spec.get("template", {}).get("spec", {}).get("containers", [])
        for container in containers:
          ports = container.get("ports", [])
          for port_info in ports:
            if "containerPort" in port_info:
              logger.debug("Inferred target port %d from containerPort", port_info["containerPort"])
              return int(port_info["containerPort"])
      elif kind_lower == "service":
        ports = spec.get("ports", [])
        for port_info in ports:
          if "port" in port_info:
            logger.debug("Inferred target port %d from service port", port_info["port"])
            return int(port_info["port"])
    except (TypeError, ValueError, KeyError, AttributeError) as e:
      logger.warning("Could not parse ports from spec for %s: %s", self.key, e)

    logger.warning("Could not infer target port for %s", self.key)
    return None

  @property
  def is_port_forwarding(self) -> bool:
    if process := self._port_forward_process:
      return process.poll() is None
    return False

  def _port_forward_cleanup(self):
    if process := self._port_forward_process:
      try:
        logger.info("Terminating port forward process for %s", self.key)
        process.terminate()
      except Exception as e:
        logger.warning("Error while terminating port forward process: %s", e)

  def start_port_forward(self):
    try:
      self._forward_thread = threading.Thread(target=self._port_forward, daemon=True)
      self._forward_thread.start()
      return True
    except Exception as e:
      logger.error("Failed to start port forward thread: %s", e, exc_info=True)
      return False

  def _port_forward(self, local_port: int = None) -> bool:
    """Starts port forwarding for this resource. Call from a thread."""
    if self.is_port_forwarding:
      logger.warning("Port forwarding is already active for %s", self)
      return False

    local_port = self.get_local_port()
    if not local_port:
      logger.warning("Skipping port forwarding - No local port defined for %s.", self)
      return False

    try:
      target_port = self._infer_target_port()
      self._port_forward_process = kubectl.port_forward(
        self.kind,
        self.name,
        self.namespace,
        local_port,
        target_port,
      )
      logger.info("Started port forwarding for %s on %s", self, local_port)
    except Exception as e:
      logger.error("Failed to start port forwarding - %s", e, exc_info=True)

    try:
      atexit.register(self._port_forward_cleanup)
      cleanup.register(lambda *_: self._port_forward_cleanup())
    except Exception as e:
      logger.error("Failed to set port forwarding cleanup hooks - %s", e, exc_info=True)

    return self.is_port_forwarding

  def stop_port_forward(self) -> bool:
    """Stops the active port forwarding process for this resource."""
    if not self.is_port_forwarding:
      logger.debug("Port forwarding is not active for %s, nothing to stop.", self.key)
      return False

    self._port_forward_cleanup()
