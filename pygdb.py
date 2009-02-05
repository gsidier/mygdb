# -*- coding: UTF-8 -*-
import os
import pty
import subprocess
import threading
import time
import collections
import logging
from collections import defaultdict

import recparse
import gdbmi_output_parser
from gdb_commands import GdbCommandBuilder
from event import EventSlot, EventQueue
from watch import FilteredWatch

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
	
		self.log = logging.getLogger("gdb") # log everything
		self.gdblog = logging.getLogger("gdbout") # log what comes out of gdb
		self.gdbinlog = logging.getLogger("gdbin") # log what goes into gdb
		self.gdberrlog = logging.getLogger("gdberr") # log gdb errors
	
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
		cmdline = "%s%s" % (str(token), command.strip())
		self.gdbinlog.debug(cmdline)
		self.gdb.gdbin.write(cmdline)
		self.gdb.gdbin.write("\n")

	def _gdb_raw_output_thread(self, stream):
		while True:
			line = stream.readline()
			if line == '': break
			self.gdblog.debug(line)
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
			except Exception, err:
				self.log.error("GDBMI error : %s" % err.message)
	
		self.log.debug("GDB: Finished")
	
	def _gdb_error_thread(self, stream):
		while True:
			line = stream.readline()
			if line == '': break
			self.gdberrlog.debug(line)
		self.log.debug("(GDB stderr : closes)")
	
	def _target_output_thread(self, stream):
		while True:
			line = stream.readline()
			if line == '': break
			self.log.debug("TARGET says: %s" % line)
			self.target_hist.append(line)
		self.log.debug("(TARGET stdout : closes)")

class WatchedVar(object):
	def __init__(self, name, expr, type, value, numchild, in_scope):
		self.name = name
		self.expr = expr
		self.type = type
		self.value = value
		self.numchild = int(numchild)
		self.in_scope = in_scope
		self.children = None

	def __repr__(self):
		return "WatchedVar(name=%s, expr=%s, type=%s, value=%s, numchild=%s)" % (self.name, self.expr, self.type, self.value, self.numchild)

	def __str__(self):
		return self.__repr__()

class VarWatcher(object):
	def __init__(self, gdbsess, var, toplevel = True):
		self.gdbsess = gdbsess
		self.var = var
		self.gdbsess.add_var_watcher(self.var, self, toplevel)

	def __del__(self):
		self.gdbsess.remove_var_watcher(self.var, self)

	def onUpdate(self, var, upd):
		pass

class PlainWatch(VarWatcher):

	def __init__(self, gdbsess, var):
		VarWatcher.__init__(self, gdbsess, var)
	
	def onUpdate(self, var, upd):
		if var is not None:
			if hasattr(upd, 'value'):
				var.value = upd.value
			if hasattr(upd, 'in_scope'):
				var.in_scope = upd.in_scope == 'true'

class GdbSession(object):

	class MyGdbController(GdbController):
		def __init__(self, session):
			self.session = session
			self.next_token = 1000001
			# MUST come last
			GdbController.__init__(self, session.gdb, session)

		def _send(self, command, token = None, on_response = None, sync = False):
			if token is None:
				token = self.next_token
				self.next_token += 1
			if on_response is not None:
				if not sync:
					self.session._response_handlers[str(token)] = on_response
				else:
					def on_response_sync(*args, **kwargs):
						on_response_sync.response = on_response(*args, **kwargs)
						on_response_sync.got_response = True
					on_response_sync.response = None
					on_response_sync.got_response = False
					self.session._response_handlers[str(token)] = on_response_sync
						
			# MUST come last
			GdbController._send(self, command, token=token)
			if sync:
				while self.session._response_handlers.has_key(str(token)) :#and not on_response_sync.got_response:
					time.sleep(0.01)
				return on_response_sync.response
	
	def __init__(self, gdbinst):
		self.gdb = gdbinst
		self.log = logging.getLogger("gdb")
		self.controller = self.MyGdbController(self)
		
		self._file = None

		self._response_handlers = {}
		
		self._watch = {}
		self._vars = {} # name -> var
		self._watchers = defaultdict(lambda: {})
		self._watcher_slots = defaultdict(lambda: EventSlot())
		
		# State data
		self.threadid = None
		
		# Events
		self.onError = EventSlot() # token, msg
		self.onFileChanged = EventSlot() # filename
		self.onBreakpointSet = EventSlot() # breakpoint_desc
		self.onThreadSwitch = EventSlot() # threadid
		self.onFrameChange = EventSlot() # frameinfo
		self.onProcessed = EventSlot() # <no args>
		self.onWatchUpdate = EventSlot() # var

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
				def thread_func():
					more = handler(results)
					if not more:
						self._response_handlers.pop(token)
				handler_thread = threading.Thread(target = thread_func, args = [])
				handler_thread.setDaemon(True)
				handler_thread.start()
			else:
				self.log.debug("TOKEN NOT FOUND: %s" % repr(token))
		
			self.log.debug("[%s] RESULTS = %s", resultClass, results)
			
			# Event based handlers
			if hasattr(results, 'thread-id'):
				self._update_thread_id(results['thread-id'])
			if hasattr(results, 'frame'):
				self._update_frame(results.frame)
			
			self.onProcessed.broadcast()
			
			if resultClass == 'stopped':
				self.var_update()

	def _update_thread_id(self, threadid):
		threadid = int(threadid)
		if threadid != self.threadid:
			self.threadid = threadid
			self.onThreadSwitch.broadcast(self.threadid)

	def _update_frame(self, frame):
		self.onFrameChange.broadcast(frame)

	def get_watched_var(self, path):
		return self._vars.get(path, None)

	def _update_watch(self, v):
		self.onWatchUpdate.broadcast(v)

	def _update_var(self, v, upd):
		root = v.name.split('.')[0]
		if root in self._watcher_slots:
			self._watcher_slots[root].broadcast(v, upd)
		self._update_watch(v)
	
	def add_var_watcher(self, var, watcher, toplevel = True):
		root = var.name.split('.')[0]
		self._watcher_slots[root].subscribe(watcher.onUpdate)
		if toplevel:
			self._watchers[root] = watcher

	def remove_var_watcher(self, var, watcher):
		root = var.name.split('.')[0]
		if root in self._watcher_slots:
			self._watcher_slots.unsubscribe(watcher.onUpdate)
		if root in self._watchers:
			self._watchers.pop(root)

	def add_watch(self, expr):
		var = self.var_create(expr, sync = True)
		self.add_var_watcher(var, FilteredWatch(self, var))

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
		eval(cmd, {
			'app': self, 
			'gdb': self.controller, 
			'att': self.attach,
			'b': self.setbreak,
			'f': self.file, 
			'w': self.add_watch, # self.var_create, 
			'log': lambda str: self.log.debug(str) 
		})
		self.onProcessed.broadcast()
	#
	def runQuickCommand(self, cmd):
		items = cmd.split()
		if items == []:
			raise Exception("Syntax error: Empty command")
		func = items[0]
		args = items[1:]
		pycmd = "%s(%s)" % (func, ', '.join(repr(arg) for arg in args) )
		self.runCommand(pycmd)
	#
	def runGdbCommand(self, cmd):
		self.controller.raw_send(cmd)
		self.onProcessed.broadcast()

	# ========== MAIN INTERFACE ==========
	#
	def file(self, filename, *args):
		self.controller.set_args(args)
		def on_response(response):
			self.onFileChanged.broadcast(filename)
		return self.controller.file(filename, on_response=on_response)
	def attach(self, what):
		return self.controller.target_attach(what)
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
		return self.controller.run()
	def cont(self):
		return self.controller.cont()
	def step(self):
		return self.controller.step()
	def stepi(self):
		return self.controller.stepi()
	def next(self):
		return self.controller.next()
	def nexti(self):
		return self.controller.nexti()
	#
	def var_create(self, expr, sync = False):
		def on_response(response):
			self.log.debug("VAR CREATE : %s" % response)
			v = WatchedVar(name = response.name, expr = expr, type = response.type, value = response.get('value'), numchild = response.numchild, in_scope = True)
			w = PlainWatch(self, v)
			self._watch[v.name] = v
			self._vars[v.name] = v
			self.log.debug("WATCHLIST : %s" % self._watch)
			if v.value is None:
				self.var_eval(v.name)
			self.var_path_expr(v.name, sync = sync)
			self.var_list_children(v.name, sync = sync)
			self._update_watch(v)
			return v
		return self.controller.var_create(expr, on_response = on_response, sync = sync)
	def var_update(self):
		def on_response(response):
			self.log.debug("VAR UPDATE : %s" % response)
			if hasattr(response, 'changelist') and hasattr(response.changelist, '__iter__'):
				for upd in response.changelist:
					v = self.get_watched_var(upd.name)
					self._update_var(v, upd)
		return self.controller.var_update(on_response = on_response)
	def var_list_children(self, name, sync = False):
		def on_response(response):
			v = self.get_watched_var(name)
			if v is not None and hasattr(response, 'children'):
				v.children = {}
				for tag,child in response.children:
					childv = WatchedVar(name = child.name, expr = child.exp, type = child.get('type', None), value = None, numchild = child.numchild, in_scope = True)
					v.children[child.exp] = childv
					self._vars[childv.name] = childv 
					self.var_path_expr(child.name, sync = sync)
					self.var_eval(child.name, sync = sync)
		return self.controller.var_list_children(name, on_response = on_response, sync = sync)
	def var_eval(self, name, sync = False):
		def on_response(response):
			v = self.get_watched_var(name)
			if v is not None:
				v.value = response.value
				self._update_var(v, response)
				return v.value
		return self.controller.var_eval(name, on_response = on_response, sync = sync)
	def var_path_expr(self, name, sync = False):
		def on_response(response):
			v = self.get_watched_var(name)
			v.path_expr = response.get('path_expr', None)
			return v.path_expr
		return self.controller.var_path_expr(name, on_response = on_response, sync = sync)

if __name__ == '__main__':
	
	sessionlog_path = "session.log"
	
	log = logging.getLogger("gdb")
	log.addHandler(logging.FileHandler(sessionlog_path))
	log.setLevel(logging.DEBUG)

	gdbout_path = "gdbout.log"
	gdblog = logging.getLogger("gdbout")
	gdblog.addHandler(logging.FileHandler(gdbout_path))
	gdblog2session = logging.FileHandler(sessionlog_path)
	gdblog2session.setFormatter(logging.Formatter('GDB OUT> %(message)s'))
	gdblog.addHandler(gdblog2session)
	gdblog.setLevel(logging.DEBUG)

	gdbin_path = "gdbin.log"
	gdbinlog = logging.getLogger("gdbin")
	gdbinlog.addHandler(logging.FileHandler(gdbin_path))
	gdbinlog2session = logging.FileHandler(sessionlog_path)
	gdbinlog2session.setFormatter(logging.Formatter('SENDING CMD> %(message)s'))
	gdbinlog.addHandler(gdbinlog2session)
	gdbinlog.setLevel(logging.DEBUG)

	gdberr_path = "gdberr.log"
	gdberrlog = logging.getLogger("gdberr")
	gdberrlog.addHandler(logging.FileHandler(gdberr_path))
	gdberrlog2session = logging.FileHandler(sessionlog_path)
	gdberrlog2session.setFormatter(logging.Formatter('GDB ERR> %(message)s'))
	gdberrlog.addHandler(gdberrlog2session)
	gdberrlog.setLevel(logging.DEBUG)

	g = GdbMI()
	gin,gout,gerr = g.gdbin,g.gdbout,g.gdberr
	S = GdbSession(g)
	G = S.controller

	def echo(msg):
		print msg
	S.onError.subscribe(lambda tok, msg: echo( "ERR: %s" % msg))
	
