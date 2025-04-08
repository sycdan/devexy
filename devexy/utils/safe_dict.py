import threading


class SafeDict(dict):
  def __init__(self, *args, **kwargs):
    super().__init__(*args, **kwargs)
    self._lock = threading.Lock()

  def __setitem__(self, key, value):
    with self._lock:
      super().__setitem__(key, value)

  def __delitem__(self, key):
    with self._lock:
      super().__delitem__(key)

  def update(self, *args, **kwargs):
    with self._lock:
      super().update(*args, **kwargs)

  def pop(self, key, default=None):
    with self._lock:
      return super().pop(key, default)

  def popitem(self):
    with self._lock:
      return super().popitem()

  def clear(self):
    with self._lock:
      super().clear()

  def setdefault(self, key, default=None):
    with self._lock:
      return super().setdefault(key, default)
