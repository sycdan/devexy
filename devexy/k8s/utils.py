import yaml

from devexy.settings import APP_DIR, KUSTOMIZE_ROOT
from devexy.utils.logging import get_logger
from devexy.utils.text import quick_hash, secure_hash

logger = get_logger(__name__)

DEFAULT_RESOURCE_KIND = "__unspecified_kind__"
DEFAULT_NAMESPACE = "default"
CLUSTER_HASH = secure_hash(str(KUSTOMIZE_ROOT.resolve()))
STATE_CACHE_ROOT = APP_DIR / "k8s_cache" / CLUSTER_HASH
STATE_CACHE_ROOT.mkdir(parents=True, exist_ok=True)


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


def get_key_fields(doc: dict):
  return dict(
    namespace=get_namespace(doc),
    kind=get_resource_kind(doc),
    name=get_resource_name(doc),
  )


def dict_to_yaml(doc: dict):
  """
  Serialize the doc consistently for hashing.
  """
  return yaml.dump(doc, sort_keys=True, default_flow_style=False)


def get_resource_key(doc: dict) -> str:
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
      key_fields["kind"],
      key_fields["name"],
    )
  ).lower()
