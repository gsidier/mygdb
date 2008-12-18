import os
import pty
import subprocess
import threading
import time
import collections

import gdbmi_output_parser
from gdb_commands import GdbCommandBuilder

class GdbMI(object):
	def __init__(self):	
		master, slave = pty.openpty()
		self.targetio = os.fdopen(master, 'rw')
		tty = os.ttyname(slave)
		self.proc = subprocess.Popen(["gdb", "--tty=%s" % tty, "--interpreter=mi"], 0, None, subprocess.PIPE, subprocess.PIPE, subprocess.PIPE)
		self.gdbin = self.proc.stdin
		self.gdbout = self.proc.stdout
		self.gdberr = self.proc.stderr

class GdbController(GdbCommandBuilder):
	def __init__(self, gdb_instance, output_handler):
		self.gdb = gdb_instance
		self.output_handler = output_handler
		
		self.output_hist = []
		self.target_hist = []
	
		self.target_output_thread = threading.Thread(target = self._target_output_thread, args = [self.gdb.targetio])
		self.target_output_thread.setDaemon(True)
		self.target_output_thread.start()

		self.gdbmi_output_parser = gdbmi_output_parser.output(self.output_handler)
	
		self.gdb_output_thread = threading.Thread(target = self._gdb_raw_output_thread, args = [self.gdb.gdbout])
		self.gdb_output_thread.setDaemon(True)
		self.gdb_output_thread.start()
		
		self.gdb_error_thread = threading.Thread(target = self._gdb_error_thread, args = [self.gdb.gdberr])
		self.gdb_error_thread.setDaemon(True)
		self.gdb_error_thread.start()
	
	def _send(self, command, token = None):
		print("SENDING[%s]: %s" % (str(token), command))
		self.gdb.gdbin.write(str(token))
		self.gdb.gdbin.write(command.strip())
		self.gdb.gdbin.write("\n")

	def _gdb_raw_output_thread(self, stream):
		while True:
			line = stream.readline()
			if line == '': break
			print("GDB says: " + line)
			self.output_hist.append(line)

			self.gdbmi_output_parser.parseString(line, parseAll=True)
		
		print("GDB: Finished")
	
	def _gdb_error_thread(self, stream):
		while True:
			line = stream.readline()
			if line == '': break
			print("GDB error: " + line)
		print("(GDB stderr : closes)")
	
	def _target_output_thread(self, stream):
		while True:
			line = stream.readline()
			if line == '': break
			print("TARGET says: " + line)
			self.target_hist.append(line)
		print("(TARGET stdout : closes)")


class EventSlot(object):
	def __init__(self):
		self.listeners = set()
	
	def subscribe(self, listener):
		self.listeners.add(listener)
	
	def unsubscribe(self, listener):
		self.listeners.remove(foo)

	def broadcast(self, *args, **kwargs):
		print "BROADCASTING: %s, %s" % (args, kwargs)
		for listener in self.listeners:
			listener(*args, **kwargs)

def EventQueue(object):
	def __init__(self, handler = None, vsync = 1e-2):
		self.queue = collections.deque()
		self.vsync = vsync
		if handler = None:
			self.handler = lambda *args, **kwargs: None
		else
			self.handler = handler
		
				
	# Override or pass in ctor
	def _handle(self, *args, **kwargs):
		return self.handler(*args, **kwargs)
	
	def __call__(self, *args, **kwargs):
		"""
		Schedule the event for handling by the handler thread.
		"""
		self.queue.append((args, kwargs))
	
	def run(self):
		while True:
			while len(self.queue > 0):
				args, kwargs = self.queue.popleft()
				self._handle(*args, **kwargs)
			time.sleep(self.vsync)

class GdbSession(object):

	class MyGdbController(GdbController):
		def __init__(self, session):
			self.session = session
			self.next_token = 1000001
			# MUST come last
			GdbController.__init__(self, session.gdb, session)
	
		def _send(self, command, token = None, on_response = None):
			if token is None:
				token = self.next_token
				self.next_token += 1
			if on_response is not None:
				self.session._response_handlers[str(token)] = on_response
			# MUST come last
			GdbController._send(self, command, token=token)
	
	def __init__(self, gdbinst):
		self.gdb = gdbinst
		self.controller = self.MyGdbController(self)
		self._file = None

		self._response_handlers = {}
		
		# State data
		self.threadid = None
		
		# Events
		self.onError = EventSlot() # GdbSession, token, msg
		self.onFileChanged = EventSlot() # GdbSession, filename
		self.onBreakpointSet = EventSlot() # GdbSession, breakpoint_desc
		self.onThreadSwitch = EventSlot() # GdbSession, threadid
		self.onFrameChange = EventSlot() # GdbSession, frameinfo
		self.onProcessedResponse = EventSlot() # GdbSession

	def err_check_response(self, on_response):
		def on_response_or_err(response):
			token, status = response[:2]
			if status == 'error':
				errmsg = response[2]
				self.onError.broadcast(self, token, errmsg)
				return False
			return on_response(response)
		return on_response_or_err

	LAST_RESULT=None
	
	def _handle_results(self, token, resultClass, results):
		self.LAST_RESULT = results
		if resultClass == 'error':
			print "ERROR ENCOUNTERED: ", results
			if self._response_handlers.has_key(token):
				print "CANCELLING HANDLER FOR ", token
				self._response_handlers.pop(token)
		else:
			# call custom handler if any
			print "CHECK for token: ", token	
			if self._response_handlers.has_key(token):
				print "TOKEN FOUND: ", repr(token)
				handler = self._response_handlers[token]
				more = handler(results)
				if not more:
					self._response_handlers.pop(token)
				return True
			else:
				print "TOKEN NOT FOUND: ", repr(token)
				return False
			
			# Event based handlers
			if hasattr(results, 'thread-id'):
				self._update_thread_id(results['thread-id'])
			if hasattr(results, 'frame'):
				self._update_frame(results.frame)

			self.onProcessedResponse.broadcast(self)

	def _update_thread_id(self, threadid):
		threadid = int(threadid)
		if threadid != self.threadid:
			self.threadid = threadid
			self.onThreadSwitch(self, self.threadid)

	def _update_frame(self, frame):
		self.onFrameChange(self, frame)

	# ========== GDB OUTPUT VISITOR ==========
	#
	def onExecAsyncOutput(self, token, asyncClass, results=None):
		self._handle_results(token, asyncClass, results)
	#
	def onNotifyAsyncOutput(self, token, asyncClass, results=None):
		self._handle_results(token, asyncClass, results)
	#
	def onStatusAsyncOutput(self, token, asyncClass, results=None):
		self._handle_results(token, asyncClass, results)
	#
	def onResultRecord(self, token, resultClass, results=None):
		self._handle_results(token, resultClass, results)
	#
	def onGdbOutput(self, string):
		print ">>> GDB OUTPUT >>> ", string
	#
	def onGdbErr(self, string):
		print ">>>! GDB ERR ! >>> ", string
	#
	def onTargetOutput(self, string):
		print ">>> TARGET OUTPUT >>> ", string

	# ========== MAIN INTERFACE ==========
	def file(self, filename):
		def on_response(response):
			self.onFileChanged.broadcast(self, filename)
		self.controller.file(filename, on_response=on_response)
	#
	def setbreak(self, loc=None, cond=None, temp=False, hardware=False, count=None, thread=None, force=False):
		def on_response(desc):
			self.onBreakpointSet.broadcast(self, desc)
		self.controller.break_insert(loc, cond, temp, hardware, count, force, on_response=on_response)
	def tbreak(self, loc=None, cond=None, count=None, thread=None, force=False):
		return self.setbreak(loc=loc, cond=cond, count=count, thread=thread, force=force, temp=True)
	def hbreak(self, loc=None, cond=None, count=None, thread=None, force=False):	
		return self.setbreak(loc=loc, cond=cond, count=count, thread=thread, force=force, hardware=True)
	def thbreak(self, loc=None, cond=None, count=None, thread=None, force=False):
		return self.setbreak(loc=loc, cond=cond, count=count, thread=thread, force=force, temp=True, hardware=True)
	#
	def run(self):
		self.controller.run()
	#
	def step(self):
		self.controller.step()
	def stepi(self):
		self.controller.stepi()
	def next(self):
		self.controller.next()
	def nexti(self):
		self.controller.nexti()

if __name__ == '__main__':
	g = GdbMI()
	gin,gout,gerr = g.gdbin,g.gdbout,g.gdberr
	S = GdbSession(g)
	G = S.controller

	def echo(msg):
		print msg
	S.onError.subscribe(lambda sess, tok, msg: echo( "ERR: %s" % msg))
	S.onFileChanged.subscribe(lambda sess, fname: echo("File changed! %s" % fname))
	
