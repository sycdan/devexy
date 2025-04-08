import atexit
import copy
import datetime
import functools
import json
import random
import subprocess
import threading
import time
from pathlib import Path
from typing import Any

from devexy.constants import K8S_REVERSE_PROXY_CONTAINER_NAME
from devexy.k8s.utils import (
  SCALABLE_KINDS,
  STATE_CACHE_ROOT,
  dict_to_yaml,
  get_first_container,
  get_key,
  get_kind,
  get_local_port,
  get_name,
  get_namespace,
  get_replicas,
  get_reverse_proxy_container,
)
from devexy.tools.kubectl import kubectl
from devexy.utils.logging import get_logger
from devexy.utils.safe_dict import SafeDict
from devexy.utils.text import quick_hash
from devexy.utils.threading import cleanup

logger = get_logger(__name__)


class Resource:
  _monitor_thread: threading.Thread = None
  _forwarding_thread: threading.Thread = None
  _forwarding_process: subprocess.Popen = None

  def __init__(self, doc: dict):
    self._original_doc = doc
    self._doc = copy.deepcopy(doc)

    self._k8s_state = SafeDict()
    try:
      loaded_state = self._load_k8s_state()
      self._k8s_state.update(loaded_state)
    except Exception as e:
      logger.warning("Failed to load state cache: %s", e, exc_info=True)
    self._k8s_state["key"] = self.key

  def __str__(self):
    return self.name

  def __repr__(self):
    return self.key

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
    return get_key(self._doc)

  @functools.cached_property
  def is_scalable(self):
    return self.kind.lower() in SCALABLE_KINDS

  @property
  def is_monitoring(self):
    return self._monitor_thread is not None

  @property
  def is_proxying(self):
    return bool(self._k8s_state.get("proxy_installed"))

  @property
  def local_port(self):
    port = get_local_port(self._doc)
    return port

  @property
  def k8s_status(self):
    return self._k8s_state.get("status") or {}

  @property
  def replicas(self):
    return get_replicas(self._doc)

  def set_replicas(self, replicas: int, apply=False):
    logger.info("Setting replicas for %s to %d", self.key, replicas)
    if "spec" not in self._doc:
      self._doc["spec"] = {}
    self._doc["spec"]["replicas"] = replicas
    if apply:
      self.apply()

  @property
  def yaml(self):
    return dict_to_yaml(self._doc)

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

  def _set_state(self, key: str, value: Any, commit=True):
    self._k8s_state[key] = value
    logger.debug("Set key '%s' in state to %s for %s", key, value, self.key)
    if commit:
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
      logger.debug(
        "Saved state cache for %s to %s", self.key, self._k8s_state_file_path
      )
    except (IOError, TypeError, ValueError) as e:
      logger.error(
        "Failed to save state cache for %s to %s: %s",
        self.key,
        self._k8s_state_file_path,
        e,
      )

  def enable_services(self):
    if not self.is_scalable:
      return

    if not self.is_monitoring:
      self.start_monitoring()

    if not self.is_proxying and not self.is_forwarding:
      self.start_forwarding()

  def start_monitoring(self):
    try:
      self._monitor_thread = threading.Thread(target=self._monitor_state, daemon=True)
      self._monitor_thread.start()
      return True
    except Exception as e:
      logger.error(
        "Failed to start monitoring thread for %s: %s", self.key, e, exc_info=True
      )
      return False

  def _monitor_state(self):
    if threading.current_thread() is threading.main_thread():
      raise RuntimeError("State monitor must not be started from the main thread.")

    while True:
      try:
        current_state = kubectl.get_current_state(self.kind, self.name, self.namespace)
      except Exception as e:
        logger.warning("Failed to get current state for %s: %s", self.key, e)
        continue

      try:
        status = current_state.get("status", {})
        self._set_state("status", status, commit=False)

        container = get_first_container(current_state) or {}
        proxy_installed = container.get("name") == K8S_REVERSE_PROXY_CONTAINER_NAME
        self._set_state("proxy_installed", proxy_installed)

        now = datetime.datetime.now(datetime.timezone.utc)
        self._set_state("observed_at", now.isoformat(), commit=True)
      except Exception as e:
        logger.warning("Failed to update state cache for %s: %s", self.key, e)

      time.sleep(random.uniform(1, 2))

  def apply(self):
    logger.info("Applying resource %s", self.key)
    try:
      return kubectl.apply(self.yaml)
    except Exception as e:
      logger.error("Failed to apply resource %s: %s", self.key, e)

  def _infer_target_port(self) -> int | None:
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
              logger.debug(
                "Inferred target port %d from containerPort", port_info["containerPort"]
              )
              return int(port_info["containerPort"])
      elif kind_lower in ["deployment", "statefulset", "replicaset"]:
        containers = spec.get("template", {}).get("spec", {}).get("containers", [])
        for container in containers:
          ports = container.get("ports", [])
          for port_info in ports:
            if "containerPort" in port_info:
              logger.debug(
                "Inferred target port %d from containerPort", port_info["containerPort"]
              )
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
  def is_forwarding(self) -> bool:
    if process := self._forwarding_process:
      return process.poll() is None
    return False

  def _forwarding_cleanup(self):
    if process := self._forwarding_process:
      try:
        logger.info("Terminating port forward process for %s", self.key)
        process.terminate()
      except Exception as e:
        logger.warning("Error while terminating port forward process: %s", e)

  def start_forwarding(self):
    try:
      self._forwarding_thread = threading.Thread(
        target=self._start_forwarding_process, daemon=True
      )
      self._forwarding_thread.start()
      return True
    except Exception as e:
      logger.error(
        "Failed to start forwarding thread for %s: %s", self.key, e, exc_info=True
      )
      return False

  def _start_forwarding_process(self, local_port: int = None) -> bool:
    if threading.current_thread() is threading.main_thread():
      raise RuntimeError(
        "Port forwarding process must not be started from the main thread."
      )

    if self.is_forwarding:
      logger.warning("Port forwarding is already active for %s", self)
      return True

    local_port = self.local_port
    if not local_port:
      logger.warning("Skipping port forwarding - No local port defined for %s.", self)
      return False

    try:
      target_port = self._infer_target_port()
      self._forwarding_process = kubectl.port_forward(
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
      atexit.register(self._forwarding_cleanup)
      cleanup.register(lambda *_: self._forwarding_cleanup())
    except Exception as e:
      logger.error("Failed to set port forwarding cleanup hooks - %s", e, exc_info=True)

    return self.is_forwarding

  def stop_forwarding(self) -> bool:
    """Stops the active port forwarding process for this resource."""
    if not self.is_forwarding:
      logger.debug("Port forwarding is not active for %s, nothing to stop.", self.key)
      return False

    self._forwarding_cleanup()

  def _get_container_port(self):
    container = get_first_container(self._doc)
    if container:
      ports = container.get("ports") or []
      if ports:
        return int(ports[0].get("containerPort"))
    return 80

  def _inject_reverse_proxy(self):
    if not self.is_scalable:
      logger.warning("Cannot apply reverse proxy to non-scalable resource %s", self.key)
      return False

    local_port = self.local_port
    if not local_port:
      logger.warning(
        "No local port defined for %s, cannot apply reverse proxy", self.key
      )
      return False

    container_port = self._get_container_port()

    reverse_proxy_container = get_reverse_proxy_container(
      local_port=local_port,
      container_port=container_port,
    )

    self._doc["spec"]["template"]["spec"]["containers"] = [reverse_proxy_container]

    logger.info("Injected reverse proxy container for %s", self.key)

  def _remove_reverse_proxy(self):
    try:
      current_replicas = self.replicas
      self._doc = copy.deepcopy(self._original_doc)
      self.set_replicas(current_replicas, apply=True)
      logger.info("Removed reverse proxy for %s", self.key)
      return True
    except Exception as e:
      logger.error("Failed to remove reverse proxy for %s: %s", self.key, e)
      return False

  def toggle_forwarding_mode(self):
    if self.is_proxying:
      self._remove_reverse_proxy()
    else:
      self._inject_reverse_proxy()
      self.apply()
    self.enable_services()
