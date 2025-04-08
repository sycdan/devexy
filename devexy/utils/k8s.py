import io

import yaml


def get_name(doc: dict):
  return doc.get("metadata", {}).get("name")


def get_kind(doc: str):
  return doc.get("kind")


def get_namespace(doc: dict, default=None):
  return doc.get("metadata", {}).get("namespace", default)


def is_scalable(kind: str):
  return kind.lower() in ["deployment", "statefulset"]


def dict_to_yaml(doc: dict):
  doc_yaml_stream = io.StringIO()
  yaml.dump(doc, doc_yaml_stream, default_flow_style=False)
  doc_yaml = doc_yaml_stream.getvalue()
  doc_yaml_stream.close()
  return doc_yaml
