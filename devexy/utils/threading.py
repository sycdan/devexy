import signal


class Cleanup:
  def __init__(self):
    self.registry = []
    signal.signal(signal.SIGTERM, lambda *_: self.cleanup())
    signal.signal(signal.SIGINT, lambda *_: self.cleanup())

  def register(self, cleanup_function):
    self.registry.append(cleanup_function)

  def cleanup(self):
    for callback in self.registry:
      callback()


cleanup = Cleanup()
