import pickle
import sys

class Stub(object):
	def __init__(self, ostream):
		self.ostream = ostream
	
	def subscribe(self, evt, name):
		def handle(*args, **kwargs):
			msg = EventMessage(name, args, kwargs)
			pickle.dump(msg, self.ostream)
			if hasattr(self.ostream, 'flush'):
				self.ostream.flush()
		evt.subscribe(handle)

class EventMessage(object):
	def __init__(self, name, args, kwargs):
		self.name = name
		self.args = args
		self.kwargs = kwargs
		

class ClientSideObserver(object):
	def __init__(self, istream = sys.stdin):
		self.istream = istream
		self.handlers = {}
	
	def add_handler(self, name, handler):
		self.handlers[name] = handler

	def process(self):
		while True:
			try:
				print "Waiting for msg..."
				msg = pickle.load(self.istream)
				print "Got msg"
			except EOFError:
				break
			if hasattr(msg, 'name'):
				if self.handlers.has_key(msg.name):
					handler = self.handlers[msg.name]
					args = msg.args if hasattr(msg, 'args') else []
					kwargs = msg.kwargs if hasattr(msg, 'kwargs') else {}
					handler(*args, **kwargs)

