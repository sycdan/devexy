from typing import Iterator

import yaml

from devexy.constants import (
  K8S_DEFAULT_NAMESPACE,
  K8S_DEFAULT_RESOURCE_KIND,
  K8S_DEFAULT_RESOURCE_NAME,
  K8S_REVERSE_PROXY_CONTAINER_NAME,
)
from devexy.settings import APP_DIR, KUSTOMIZE_ROOT, LOCAL_PORT_ANNOTATION
from devexy.utils.logging import get_logger
from devexy.utils.text import secure_hash

logger = get_logger(__name__)

CLUSTER_HASH = secure_hash(str(KUSTOMIZE_ROOT.resolve()))
STATE_CACHE_ROOT = APP_DIR / "k8s_cache" / CLUSTER_HASH
STATE_CACHE_ROOT.mkdir(parents=True, exist_ok=True)
SCALABLE_KINDS = ["deployment", "replicaset", "statefulset"]


def yaml_to_dicts(yaml_content: str) -> Iterator[dict]:
  """Parses YAML content and yields only valid dictionary documents as Resource instances."""
  all_docs = yaml.safe_load_all(yaml_content)
  for doc in all_docs:
    if isinstance(doc, dict):
      yield doc
    elif doc is not None:
      logger.warning("Skipping non-dictionary item in YAML stream: %s", type(doc))


def dict_to_yaml(doc: dict):
  """
  Serialize the doc consistently for hashing.
  """
  return yaml.dump(doc, sort_keys=True, default_flow_style=False)


def get_kind(doc: dict, default=K8S_DEFAULT_RESOURCE_KIND):
  return str(doc.get("kind", default))


def get_spec(doc: dict):
  return dict(doc.get("spec", {}))


def get_metadata(doc: dict):
  return dict(doc.get("metadata", {}))


def get_annotations(doc: dict):
  return dict(get_metadata(doc).get("annotations", {}))


def get_namespace(doc: dict, default=K8S_DEFAULT_NAMESPACE):
  return str(get_metadata(doc).get("namespace", default))


def get_name(doc: dict, default=K8S_DEFAULT_RESOURCE_NAME):
  return str(get_metadata(doc).get("name", default))


def get_key(doc: dict):
  return f"{get_namespace(doc)}/{get_kind(doc)}/{get_name(doc)}".lower()


def get_spec_template(doc: dict):
  return dict(get_spec(doc).get("template", {}))


def get_spec_containers(doc: dict):
  return list(get_spec(doc).get("containers", []))


def get_first_container(doc: dict):
  containers = get_spec_containers(get_spec_template(doc))
  if containers:
    return containers[0]
  return None


def get_replicas(doc: dict, default=None):
  return get_spec(doc).get("replicas", default)


def get_local_port(doc: dict):
  annotations = get_annotations(doc)
  annotation = annotations.get(LOCAL_PORT_ANNOTATION)
  if annotation is not None:
    return int(annotation)
  return None


def is_proxy_installed(doc: dict):
  container = get_first_container(doc) or {}
  installed = container.get("name") == K8S_REVERSE_PROXY_CONTAINER_NAME
  return installed


def get_reverse_proxy_container(
  local_port: int,
  local_protocol: str = "http",
  local_host: str = "host.minikube.internal",
  container_port: int = 80,
) -> dict:
  """Returns an nginx reverse proxy deployment document with embedded nginx configuration."""
  nginx_config = (
    "events {}\n"
    "http {\n"
    "  server {\n"
    f"    listen {container_port};\n"
    "    location / {\n"
    f"      proxy_pass {local_protocol}://{local_host}:{local_port};\n"
    "      proxy_set_header Host $host;\n"
    "      proxy_set_header X-Real-IP $remote_addr;\n"
    "      proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;\n"
    "      proxy_set_header X-Forwarded-Proto $scheme;\n"
    "    }\n"
    "  }\n"
    "}\n"
  )

  return {
    "name": K8S_REVERSE_PROXY_CONTAINER_NAME,
    "image": "nginx:latest",
    "ports": [{"containerPort": container_port}],
    "command": ["sh", "-c"],
    "args": [
      f"echo '{nginx_config}' > /etc/nginx/nginx.conf && nginx -g 'daemon off;'"
    ],
  }


def clear_cache():
  try:
    for item in STATE_CACHE_ROOT.iterdir():
      if item.is_dir():
        item.rmdir()
      else:
        item.unlink()
  except Exception as e:
    logger.error("Failed to clear cache: %s", e)


def get_last_applied_configuration(doc: dict) -> dict | None:
  annotations = get_annotations(doc)
  last_applied = annotations.get("kubectl.kubernetes.io/last-applied-configuration")
  if last_applied:
    try:
      return yaml.safe_load(last_applied)
    except yaml.YAMLError as e:
      logger.error("Failed to parse last applied configuration: %s", e)
  return None
