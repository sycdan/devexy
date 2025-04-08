import hashlib


def secure_hash(text: str) -> str:
  """Calculates the SHA256 hash of the string."""
  return hashlib.sha256(text.encode("utf-8")).hexdigest()


def quick_hash(text: str) -> str:
  """Calculates the SHA1 hash of the string."""
  return hashlib.sha1(text.encode("utf-8")).hexdigest()
