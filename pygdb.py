import os
import pty
import subprocess
import threading
import time
import collections
import logging

import recparse
import gdbmi_output_parser
from gdb_commands import GdbCommandBuilder
from event import EventSlot, EventQueue

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
	
		self.log = logging.getLogger("gdb")
	
		self.output_hist = []
		self.target_hist = []
	
		self.target_output_thread = threading.Thread(target = self._target_output_thread, args = [self.gdb.targetio])
		self.target_output_thread.setDaemon(True)
		self.target_output_thread.start()

		self.gdbmi_output_lexer = gdbmi_output_parser.lex
		self.gdbmi_output_parser = gdbmi_output_parser.gdbmi_output(self.output_handler)
	
		self.gdb_output_thread = threading.Thread(target = self._gdb_raw_output_thread, args = [self.gdb.gdbout])
		self.gdb_output_thread.setDaemon(True)
		self.gdb_output_thread.start()
		
		self.gdb_error_thread = threading.Thread(target = self._gdb_error_thread, args = [self.gdb.gdberr])
		self.gdb_error_thread.setDaemon(True)
		self.gdb_error_thread.start()

	def raw_send(self, command):
		self.gdb.gdbin.write(command.strip())
		self.gdb.gdbin.write("\n")
	
	def _send(self, command, token = None):
		self.log.debug("SENDING[%s]: %s" % (str(token), command))
		self.gdb.gdbin.write(str(token))
		self.gdb.gdbin.write(command.strip())
		self.gdb.gdbin.write("\n")

	def _gdb_raw_output_thread(self, stream):
		while True:
			line = stream.readline()
			if line == '': break
			self.log.debug("GDB says: %s" % line)
			self.output_hist.append(line)

			try:
				charstream = recparse.TokenStream(iter(line))
				tokenstream = self.gdbmi_output_lexer.lex(charstream)
				success, result = self.gdbmi_output_parser.try_parse(tokenstream)
				if not success:
					self.log.error("GDBMI parse error on input : %s" % line)
					continue
			except SyntaxError, err:
				self.log.error("GDBMI syntax error : %s" % err.message)
	
		self.log.debug("GDB: Finished")
	
	def _gdb_error_thread(self, stream):
		while True:
			line = stream.readline()
			if line == '': break
			self.log.debug("GDB error: %s" % line)
		self.log.debug("(GDB stderr : closes)")
	
	def _target_output_thread(self, stream):
		while True:
			line = stream.readline()
			if line == '': break
			self.log.debug("TARGET says: %s" % line)
			self.target_hist.append(line)
		self.log.debug("(TARGET stdout : closes)")

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
		self.log = logging.getLogger("gdb")
		self.controller = self.MyGdbController(self)
		
		self._file = None

		self._response_handlers = {}
		
		# State data
		self.threadid = None
		
		# Events
		self.onError = EventSlot() # token, msg
		self.onFileChanged = EventSlot() # filename
		self.onBreakpointSet = EventSlot() # breakpoint_desc
		self.onThreadSwitch = EventSlot() # threadid
		self.onFrameChange = EventSlot() # frameinfo
		self.onProcessed = EventSlot() # <no args>

	def err_check_response(self, on_response):
		def on_response_or_err(response):
			token, status = response[:2]
			if status == 'error':
				errmsg = response[2]
				self.onError.broadcast(token, errmsg)
				return False
			return on_response(response)
		return on_response_or_err

	LAST_RESULT=None
	
	def _handle_results(self, token, resultClass, results):
		self.LAST_RESULT = results
		if resultClass == 'error':
			self.log.debug("ERROR ENCOUNTERED: %s" % repr(results))
			if self._response_handlers.has_key(token):
				self.log.debug("CANCELLING HANDLER FOR %s" % repr(token))
				self._response_handlers.pop(token)
		else:
			# call custom handler if any
			self.log.debug("CHECK for token: %s" % repr(token))
			if self._response_handlers.has_key(token):
				self.log.debug("TOKEN FOUND: %s" % repr(token))
				handler = self._response_handlers[token]
				more = handler(results)
				if not more:
					self._response_handlers.pop(token)
				return True
			else:
				self.log.debug("TOKEN NOT FOUND: %s" % repr(token))
		
			self.log.debug("RESULTS = %s", results)
	
			# Event based handlers
			if hasattr(results, 'thread-id'):
				self._update_thread_id(results['thread-id'])
			if hasattr(results, 'frame'):
				self._update_frame(results.frame)

			self.onProcessed.broadcast()

	def _update_thread_id(self, threadid):
		threadid = int(threadid)
		if threadid != self.threadid:
			self.threadid = threadid
			self.onThreadSwitch.broadcast(self.threadid)

	def _update_frame(self, frame):
		self.onFrameChange.broadcast(frame)

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
		self.log.debug(">>> GDB OUTPUT >>> %s " % string)
	#
	def onGdbErr(self, string):
		self.log.debug(">>> GDB ERR >>> %s" % string)
	#
	def onTargetOutput(self, string):
		self.log.debug(">>> TARGET OUTPUT >>> %s" % string)

	# ========== SCRIPTING INTERFACE ==========
	#
	def runCommand(self, cmd):
		eval(cmd, { 'gdb': self.controller, 'b': self.setbreak, 'log': lambda str: self.log.debug(str) })
		self.onProcessed.broadcast()
	#
	def runGdbCommand(self, cmd):
		self.controller.raw_send(cmd)
		self.onProcessed.broadcast()

	# ========== MAIN INTERFACE ==========
	#
	def file(self, filename):
		def on_response(response):
			self.onFileChanged.broadcast(filename)
		self.controller.file(filename, on_response=on_response)
	#
	def setbreak(self, loc=None, cond=None, temp=False, hardware=False, count=None, thread=None, force=False):
		def on_response(desc):
			self.onBreakpointSet.broadcast(desc)
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
	def cont(self):
		self.controller.cont()
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
	
