#!/usr/bin/env python
# -*- coding: UTF-8 -*-
import pygdb
from pygdb import GdbMI, GdbSession
from term import TerminalController

import logging
from collections import deque
from time import sleep

class CLI(object):
	
	NLINES_BEFORE = 3
	NLINES_AFTER = 3
	
	LINE_STATUS_NCHARS = 1
	LINE_STATUS_POS_CURR = 0
	LINE_STATUS_CHAR_CURR = '>'
	
	LINE_STYLE = "${NORMAL}"
	CURR_LINE_STYLE = "${BOLD}${YELLOW}"
	
	GDB_OUT_STYLE = "${CYAN}"
	GDB_ERR_STYLE = "${RED}"
	TARGET_OUT_STYLE = "${GREEN}"
	
	def __init__(self, gdbsess):
		self.gdbsess = gdbsess
		
		self._term = TerminalController()
		
		self.COMMANDS = self.commands()
		
		self._sync_q = deque()
		
		self._src_lines = []
		
		self.gdbsess.onFrameChange.subscribe(self.onFrameChange)
		self.gdbsess.eventGdbOutput.subscribe(self.onGdbOutput)
		self.gdbsess.eventGdbError.subscribe(self.onGdbErr)
		self.gdbsess.eventTargetOutput.subscribe(self.onTargetOutput)
		
	def commands(self):
		cmds = {}
		cmds.update(self.gdbsess.commands())
		cmds.update({
			'l': self.list,
			'disp': self.disp
		})
	
	def list(self):
		line = self.gdbsess.src_line or 1
		first = max(1, line - self.NLINES_BEFORE)
		last = min(len(self._src_lines), line + self.NLINES_AFTER)
		ndigits = len(str(last))
		format = "%(status)s %(lineno)" + str(ndigits) + "d  %(style)s%(line)s${NORMAL}"
		def printit():
			print
			for i in xrange(first, last + 1):
				line = self._src_lines[i - 1]
				line_status = [' '] * self.LINE_STATUS_NCHARS
				if i == self.gdbsess.src_line:
					line_status[self.LINE_STATUS_POS_CURR] = self.LINE_STATUS_CHAR_CURR
					style = self.CURR_LINE_STYLE
				else:
					style = self.LINE_STYLE
				line_status = ''.join(line_status)
				print self._term.render(format % {
					'status': line_status, 
					'lineno': i, 
					'style': style,
					'line': line[:-1]
				})
		self._sync(printit)
	
	def disp(self):
		pass
	
	def interpreter(self):
		last_cmd = None
		while True:
			idle = True
			while len(self._sync_q) > 0:
				action = self._sync_q.popleft()
				action()
				idle = False
			if self.gdbsess.accept_input:
				idle = False
				cmd = None
				try:
					cmd = raw_input("mygdb ?> ")
				except EOFError:
					break
				except KeyboardInterrupt:
					print "Use EOF (CONTROL-D) to quit command mode"
					cmd = None
				if cmd == '':
					cmd = last_cmd
				if cmd:
					try:
						self.gdbsess.runQuickCommand(cmd)
						last_cmd = cmd
					except Exception, e:
						print "Error: ", e.message
			if idle:
				sleep(0.001)
	
	def _sync(self, action):
		self._sync_q.append(action)
	
	# Event Handlers
	def onFrameChange(self, frame):
		if self.gdbsess.src_path is not None:
			f = file(self.gdbsess.src_path, 'r')
			self._src_lines = f.readlines()
			f.close()
		self.list()
	def onGdbOutput(self, string):
		def printGdbOutput():
			print self._term.render("%s%s${NORMAL}" % (self.GDB_OUT_STYLE, string[:-1]))
		self._sync(printGdbOutput)
	def onGdbErr(self, string):
		def printGdbErr():
			print self._term.render("%s%s${NORMAL}" % (self.GDB_ERR_STYLE, string[:-1]))
		self._sync(printGdbErr)
	def onTargetOutput(self, string):
		def printTargetOutput():
			print self._term.render("%s%s${NORMAL}" % (self.TARGET_OUT_STYLE, string[:-1]))
		self._sync(printTargetOutput)


class Interpreter(object):
	
	def __init__(self, gdbsess):
		self.gdbsess = gdbsess	

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

	targetout_path = "targetout.log"
	targetoutlog = logging.getLogger("targetout")
	targetoutlog.addHandler(logging.FileHandler(targetout_path))
	targetoutlog2session = logging.FileHandler(sessionlog_path)
	targetoutlog2session.setFormatter(logging.Formatter('TARGET OUT> %(message)s'))
	targetoutlog.addHandler(targetoutlog2session)
	targetoutlog.setLevel(logging.DEBUG)

	g = GdbMI()
	gin,gout,gerr = g.gdbin,g.gdbout,g.gdberr
	S = GdbSession(g)
	G = S.controller

	def echo(msg):
		print msg
	S.onError.subscribe(lambda tok, msg: echo( "ERR: %s" % msg))
	
	cli = CLI(S)
	
	def quick():
		cli.interpreter()
	
	try:
		import IPython
		IPython.iplib.InteractiveShell.magic_q = lambda *args: quick()
	except:
		print "note: couldn't set magic quick input function"
		q = quick()
	
	quick()

