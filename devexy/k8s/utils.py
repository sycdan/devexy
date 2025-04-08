import yaml

from devexy.constants import (
  K8S_DEFAULT_NAMESPACE,
  K8S_DEFAULT_RESOURCE_KIND,
  K8S_DEFAULT_RESOURCE_NAME,
)
from devexy.settings import APP_DIR, KUSTOMIZE_ROOT
from devexy.utils.logging import get_logger
from devexy.utils.text import secure_hash

logger = get_logger(__name__)

CLUSTER_HASH = secure_hash(str(KUSTOMIZE_ROOT.resolve()))
STATE_CACHE_ROOT = APP_DIR / "k8s_cache" / CLUSTER_HASH
STATE_CACHE_ROOT.mkdir(parents=True, exist_ok=True)


def dict_to_yaml(doc: dict):
  """
  Serialize the doc consistently for hashing.
  """
  return yaml.dump(doc, sort_keys=True, default_flow_style=False)


def get_metadata(doc: dict):
  return doc.get("metadata", {})


def get_namespace(doc: dict, default=K8S_DEFAULT_NAMESPACE):
  return get_metadata(doc).get("namespace", default)


def get_kind(doc: dict, default=K8S_DEFAULT_RESOURCE_KIND):
  return doc.get("kind", default)


def get_name(doc: dict, default=K8S_DEFAULT_RESOURCE_NAME):
  return get_metadata(doc).get("name", default)
