import time
import collections
 
class EventSlot(object):
	def __init__(self):
		self.listeners = set()

	def subscribe(self, listener):
		self.listeners.add(listener)

	def unsubscribe(self, listener):
		if listener in self.listeners:
			self.listeners.remove(listener)

	def broadcast(self, *args, **kwargs):
		for listener in self.listeners:
			listener(*args, **kwargs)

class EventQueue(object):
	def __init__(self, vsync = 1e-2):
		self.queue = collections.deque()
		self.vsync = vsync
		self.process = True

	def schedule_handler(self, handler):
		def handle(*args, **kwargs):
			self.queue.append(lambda: handler(*args, **kwargs))
		return handle

	def run(self):
		while self.process:
			while self.process and len(self.queue) > 0:
				thunk = self.queue.popleft()
				thunk()
			time.sleep(self.vsync)

