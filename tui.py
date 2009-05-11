#!/usr/bin/env python
# -*- coding: UTF-8 -*-
import pygdb
from event import EventSlot, EventQueue
import piped_event
from curses_mvc import View, TopLevelView, Controller, KeyboardController, KeyboardActions, BubblingKeyboardController
from curses_mvc_widgets import NamedPanel, LayoutView, CommandPanel, LogView

import sys
import os
import curses
from curses.wrapper import wrapper

import threading
import logging
import time
import subprocess

class Settings(object):
	
	COLOR_DEFAULT = (curses.COLOR_WHITE, curses.COLOR_BLACK)
	COLOR_ACTIVE_BORDER = (curses.COLOR_YELLOW, curses.COLOR_BLACK)
	
	COLOR_LOG_GDBOUT = (curses.COLOR_YELLOW, curses.COLOR_BLACK)
	COLOR_LOG_GDBIN = (curses.COLOR_GREEN, curses.COLOR_BLACK)
	COLOR_LOG_GDBERR = (curses.COLOR_RED, curses.COLOR_BLACK)
	COLOR_LOG_TARGETOUT = (curses.COLOR_CYAN, curses.COLOR_BLACK)
	COLOR_LOG_TARGETERR = (curses.COLOR_MAGENTA, curses.COLOR_BLACK)

	PAIR_DEFAULT       = 1
	PAIR_ACTIVE_BORDER = 2
	PAIR_LOG_GDBOUT    = 3
	PAIR_LOG_GDBIN     = 4
	PAIR_LOG_GDBERR    = 5
	PAIR_LOG_TARGETOUT = 6
	PAIR_LOG_TARGETERR = 7

	ATTR_DEFAULT       = curses.A_NORMAL
	ATTR_ACTIVE_BORDER = curses.A_BOLD
	ATTR_LOG_GDBOUT    = curses.A_NORMAL
	ATTR_LOG_GDBIN     = curses.A_NORMAL
	ATTR_LOG_GDBERR    = curses.A_NORMAL
	ATTR_LOG_TARGETOUT = curses.A_NORMAL
	ATTR_LOG_TARGETERR = curses.A_NORMAL
	
	def apply(self):
		curses.init_pair(self.PAIR_DEFAULT, *self.COLOR_DEFAULT)
		curses.init_pair(self.PAIR_ACTIVE_BORDER, *self.COLOR_ACTIVE_BORDER)
		curses.init_pair(self.PAIR_LOG_GDBOUT, *self.COLOR_LOG_GDBOUT)
		curses.init_pair(self.PAIR_LOG_GDBIN, *self.COLOR_LOG_GDBIN)
		curses.init_pair(self.PAIR_LOG_GDBERR, *self.COLOR_LOG_GDBERR)
		curses.init_pair(self.PAIR_LOG_TARGETOUT, *self.COLOR_LOG_TARGETOUT)
		curses.init_pair(self.PAIR_LOG_TARGETERR, *self.COLOR_LOG_TARGETERR)

	def attr(self, name):
		return getattr(self, "ATTR_%s" % name) | curses.color_pair(getattr(self, "PAIR_%s" % name))
	
class SourceView(View):

	TABSTOP = 4

	def __init__(self, gdbtui, parent = None, win = None):
		View.__init__(self, parent, win)

		self.app = gdbtui.app
		self.gdbtui = gdbtui
		self.log = logging.getLogger("gdb")

		self.line_off = 0
		self.src_file = None
		self.src_line = None # 1-based
		self.src_line_data = []

		self.dirty = True

		if win is not None:
			maxy, maxx = self.win.getmaxyx()
			self.log.debug("SRC VIEW WIN %d %d" % (maxx, maxy))
			self.draw()

		self.app.sess.onBreakpointSet.subscribe(self.onBreakpointSet)
		self.app.sess.onFrameChange.subscribe(self.onFrameChange)
	
	def __del__(self):
		pass

	def _get_line_from_buffer(self, buf, lineno):
		# just translate between 1-based line numbers in files
		# and 0-based in buffers
		return buf[lineno - 1]

	def draw(self, force = False):
		if (force or self.dirty) and self.win is not None: 
			maxy, maxx = self.win.getmaxyx()
			self.win.clear()
			# if src_line is of the screen then recenter view so that src_line is approx 1/5th down from top of screen
			if self.src_line is not None:
				if self.line_off is None or self.src_line < self.line_off + 1 or self.src_line >= self.line_off + 1 + maxy:
					self.line_off = max(0, self.src_line - 1 - maxy / 5)
				
			startoff = self.line_off if self.line_off is not None else 0
			startline = startoff + 1 # 'offsets' are 0-based, 'lines' are 1-based
			endoff = startoff + maxy
			endline = endoff + 1
			maxndigits = len(str(len(self.src_line_data)))
			self.log.debug("SourceView : size (%d, %d) - startoff %d - endoff %d" % (maxy, maxx, startoff, endoff))
			visible_lines = self.src_line_data[startoff:endoff]
			self.log.debug("SRC LINE : %s" % self.src_line)
			for i in xrange(len(visible_lines)):
				lineno = i + startline 
				line = visible_lines[i].expandtabs(self.TABSTOP)
				if lineno == self.src_line:
					self.win.attron(curses.A_REVERSE)
					self.win.attron(curses.A_BOLD)
					self.log.debug("DRAWING WITH CURRENT LINE : %d" % lineno)
				else:
					self.win.attroff(curses.A_REVERSE)
					self.win.attroff(curses.A_BOLD)
				linedata = [' '] * (maxndigits + 1)
				linedata[:maxndigits] = str(lineno)
				linedata[maxndigits+1:] = line
				linedata = ''.join(linedata).strip()
				linedata = linedata[:maxx]
				self.win.addnstr(i, 0, linedata, maxx)
		self.dirty = False

	def update_src_file(self, path):
		if self.src_file != path:
			self.dirty = True
			self.src_file = path
			f = file(self.src_file, 'r')
			self.src_line_data = f.readlines()
			f.close()
	
	def onBreakpointSet(self, breakpoint_desc):
		log.debug("EVENT : SourceView << onBreakPointSet")
		self.dirty = True

	def onFrameChange(self, frame):
		self.dirty = True
		log.debug("EVENT : SourceView << onFrameChange")
		if hasattr(frame, 'fullname'):
			self.update_src_file(frame.fullname)
		elif hasattr(frame, 'file'):
			self.update_src_file(frame.file)
		if hasattr(frame, 'file'):
			self.gdbtui.src_panel.name = frame.file
		elif hasattr(frame, 'fullname'):
			self.gdbtui.src_panel.name = frame.fullname
		if hasattr(frame, 'line'):
			self.src_line = int(frame.line)
			self.log.debug("CURRENT LINE : %d" % self.src_line)
		else:
			self.src_line = None

	def scroll_down(self):
		self.line_off += 1
		self.draw(True)
		self.refresh()

	def scroll_up(self):
		self.line_off -= 1
		self.line_off = max(0, self.line_off)
		self.draw(True)
		self.refresh()

class SourceViewKbActions(KeyboardActions):
	ACTIONS = {
		'KEY_UP': lambda self: self.src_view.scroll_up(),
		'KEY_DOWN': lambda self: self.src_view.scroll_down()
	}
	def __init__(self, src_view):
		self.src_view = src_view

class WatchView(View):

	TAB = 4

	def __init__(self, gdbtui, parent = None, win = None):
		View.__init__(self, parent, win)
		self.app = gdbtui.app
		self.gdbtui = gdbtui
		self.dirty = False
		self.app.sess.onWatchUpdate.subscribe(self.onWatchUpdate)

	def draw(self, force = False):
		if not (force or self.dirty):
			return
		self.win.erase()
		maxy, maxx = self.win.getmaxyx()
		def rec(children, i, j):
			for name, v in children.iteritems():
				if not v.in_scope:
					continue
				if i > maxy:
					break
				childrenicon = ""
				if v.children is None:
					if v.numchild > 0:
						childrenicon = "[+] " 
				else:
					if v.numchild > 0:
						childrenicon = "[-] "
				s = "%s%s : %s (%s)" % (childrenicon, v.expr, v.value, v.type)
				self.win.addnstr(i, j, s, max(0, maxx - j) )
				i += 1
				if v.children is not None:
					i = rec(v.children, i, j + self.TAB)
			return i
		rec(self.app.sess._watchers, 0, 0)	

	def onWatchUpdate(self, v):
		self.dirty = True

class WatchViewKbActions(KeyboardActions):
	ACTIONS = {
	}
	def __init__(self, watch_view):
		self.watch_view = watch_view

class TopLevelKeyboardInput(KeyboardActions):
	def __init__(self, gdbtui, win):
		self.app = gdbtui.app
		self.gdbtui = gdbtui
		self.win = win
		self.gdberrlog = logging.getLogger("gdberr") # log gdb errors
		
	ACTIONS = {
		'R': lambda self: self.app.sess.run(),
		'C': lambda self: self.app.sess.cont(),
		'n': lambda self: self.app.sess.next(),
		's': lambda self: self.app.sess.step(),
		'B': lambda self: self.app.sess.setbreak(loc='main'),
		'b': lambda self: self.app.sess.setbreak(),
		'q': lambda self: self.app.quit(),
		'!': lambda self: self.startInput(mode='gdb'),
		';': lambda self: self.startInput(mode='python'),
		':': lambda self: self.startInput(mode='quick'),
		'o': lambda self: self.app.switch_mode('PYSHELL'),
		'KEY_F(2)': lambda self: self.app.switch_mode('SHELL'),
		'KEY_F(5)': lambda self: self.refresh_screen(),
		'KEY_F(8)': lambda self: self.popoutLog("session.log", "session log"),
		'KEY_F(9)': lambda self: self.popoutLog("gdbout.log", "gdb output"),
		'KEY_F(10)': lambda self: self.popoutLog("gdbin.log", "gdb input"),
		'KEY_RESIZE': lambda self: self.gdbtui.handleResize(),
		'\t': lambda self: self.gdbtui.layout.flip_focus(+1, True),
		'KEY_BTAB': lambda self: self.gdbtui.layout.flip_focus(-1, True),
	}

	def startInput(self, mode):
		self.gdbtui.stop_events()
		cmd = self.gdbtui.command_panel.input()
		self.gdbtui.process_events()
		try:
			if mode == 'python':
				res = self.app.sess.runCommand(cmd)
			elif mode == 'gdb':
				res = self.app.sess.runGdbCommand(cmd)
			elif mode == 'quick':
				res = self.app.sess.runQuickCommand(cmd)
		except Exception, e:
			#self.gdbtui.command_panel.disperr(e.message)	
			self.gdberrlog.debug(e.message)
	
	def popoutLog(self, path, title = "mygdb"):
		xterm = subprocess.Popen(["xterm", "-title", title, "+hold", "-e", "tail", "-F", path])	

	def refresh_screen(self):
		self.gdbtui.win.clear()
		self.gdbtui.update(True)
		self.gdbtui.refresh()

	def get_focus(self, function):
		self._process = False
		res = function()
		self._process = True
		return res

	def on_event(self, key):
		KeyboardActions.on_event(self, key)
		self.gdbtui.update()
		self.gdbtui.refresh()


class PyGdbTui(TopLevelView):

	def __init__(self, app, topwin):
		TopLevelView.__init__(self, topwin)
		
		self.app = app	
		self.gdb = app.gdb
		self.sess = app.sess

		self.log = logging.getLogger('gdb')
		self.topwin = topwin
		self.topwin.keypad(1)
		
		# Color Settings
		self.settings = Settings()
		self.settings.apply()
		self.topwin.bkgd( curses.color_pair(self.settings.PAIR_DEFAULT) )
		
		# Views
		self.src_panel = NamedPanel("<source>")
		self.src_view = SourceView(self)
		self.src_panel.set_inner(self.src_view)
		self.src_view_kb = SourceViewKbActions(self.src_view)
	
		self.watch_panel = NamedPanel("watch")
		self.watch_view = WatchView(self)
		self.watch_panel.set_inner(self.watch_view)
		self.watch_view_kb = WatchViewKbActions(self.watch_view)
	
		upper_layout = LayoutView(None, None, 'H')
		upper_layout.layout( 
			(-.6, self.src_panel), 
			(-.4, self.watch_panel) 
		)
		
		self.log_view = LogView()
		self.log_view.addLog(logging.getLogger('gdb'), curses_format = self.settings.attr('DEFAULT'))
		self.log_view.addLog(logging.getLogger('gdbout'), curses_format = self.settings.attr('LOG_GDBOUT'))
		self.log_view.addLog(logging.getLogger('gdbin'), curses_format = self.settings.attr('LOG_GDBIN'))
		self.log_view.addLog(logging.getLogger('gdberr'), curses_format = self.settings.attr('LOG_GDBERR'))
		self.log_view.addLog(logging.getLogger('targetout'), curses_format = self.settings.attr('LOG_TARGETOUT'))

		self.command_panel = CommandPanel()
	
		self.layout = LayoutView(self, self.topwin, 'V')
		self.layout.layout( 
			(-.65, upper_layout),
			(-.35, self.log_view),
			(   1, self.command_panel ) 
		)
		self.toplevel_kb = TopLevelKeyboardInput(self, self.topwin)
	
		### Command handler
		## self.commandHandler = CommandHandler(self, self.sess, self.command_panel)
		
		# Keyboard Input
		self.kbcontroller = BubblingKeyboardController(self.layout)
		self.kbcontroller.process_events(False)
		self.kbcontroller.controllers[self.layout] = self.toplevel_kb
		self.kbcontroller.controllers[self.src_panel] = self.src_view_kb
		self.kbcontroller.controllers[self.watch_panel] = self.watch_view_kb
		
		# Events
		self.onStartCommandInput = EventSlot()
		
		# Event Handlers
		self.sess.onProcessed.subscribe(self.onGdbProcessedResponse)
		#self.scheduled_onGdbProcessedResponse = self.commandHandler.commandQueue.schedule_handler(self._onGdbProcessedResponse)
		
	def onGdbProcessedResponse(self):
		#	self.scheduled_onGdbProcessedResponse()
		#def _onGdbProcessedResponse(self):
		self.log.debug("### REFRESH ###")
		self.update()
		self.refresh()

	def handleResize(self):
		self.layout.resize()


	def process_events(self):
		#self.kb_input._process = True
		#self.commandHandler.commandQueue.process = True
		#self.commandHandler.commandQueue.run()
		self.kbcontroller.process_events(True)

	def stop_events(self):
		#self.kb_input._process = False
		#self.commandHandler.commandQueue.process = False
		self.kbcontroller.process_events(False)

class App(object):
	def __init__(self, gdb):
		self.gdb = gdb
		self.sess = pygdb.GdbSession(gdb)
		
		self.log = logging.getLogger('gdb')
		self.appmode = 'TUI' # one of: TUI, PYSHELL, SHELL, ...

		self.gdbtui = None
	
	def run(self):
		while self.appmode != 'QUIT':
			if self.appmode == 'TUI':
				wrapper(self.run_tui)
			elif self.appmode == 'PYSHELL':
				self.run_pyshell()
			elif self.appmode == 'SHELL':
				self.run_shell()

	def quit(self):
		self.switch_mode('QUIT')
	
	def run_tui(self, win):
		curses.curs_set(0)
		if self.gdbtui is None:
			self.gdbtui = PyGdbTui(self, win)
		else:
			self.gdbtui.setwin(win)
		self.gdbtui.process_events()
		while self.appmode == 'TUI':
			time.sleep(.1)

	def run_pyshell(self):
		from IPython.Shell import IPShellEmbed
		ipshell = IPShellEmbed({
			'confirm_exit': 0,
		})
		ipshell()
		self.appmode = 'TUI' # return to TUI mode

	def run_shell(self):
		shell = os.environ['SHELL']
		os.system(shell)
		self.appmode = 'TUI'

	def switch_mode(self, mode):
		if self.appmode == 'TUI' and mode <> 'TUI':
			self.gdbtui.stop_events()
		self.appmode = mode

if __name__ == '__main__':

	sessionlog_path = "session.log"
	
	log = logging.getLogger("gdb")
	log_handler = logging.FileHandler(sessionlog_path)
	log_handler.setFormatter(logging.Formatter('%(created)f\t%(message)s'))
	log.addHandler(log_handler)
	log.setLevel(logging.DEBUG)

	gdbout_path = "gdbout.log"
	gdblog = logging.getLogger("gdbout")
	gdblog_handler = logging.FileHandler(gdbout_path)
	gdblog_handler.setFormatter(logging.Formatter('%(created)f\t%(message)s'))
	gdblog.addHandler(gdblog_handler)
	gdblog2session = logging.FileHandler(sessionlog_path)
	gdblog2session.setFormatter(logging.Formatter('GDB OUT> %(message)s'))
	gdblog.addHandler(gdblog2session)
	gdblog.setLevel(logging.DEBUG)

	gdbin_path = "gdbin.log"
	gdbinlog = logging.getLogger("gdbin")
	gdbinlog_handler = logging.FileHandler(gdbin_path)
	gdbinlog_handler.setFormatter(logging.Formatter('%(created)f\t%(message)s'))
	gdbinlog.addHandler(gdbinlog_handler)
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

	## Redirect stderr to file
	
	#errlog = file("err.log", "w")
	#sys.stderr = errlog	
		
	## Startup app

	gdb = pygdb.GdbMI()
	app = App(gdb)
	
	if len(sys.argv) > 1:
		app.sess.file(*sys.argv[1:])
	else:
		app.sess.file('hello')

	app.run()


	"""
	fifo_path = 'fifo1'
	log.debug("MAKING FIFO")
	os.mkfifo(fifo_path)

	log.debug("SPAWNING OBS")
	xterm = subprocess.Popen(["xterm", "+hold", "-e", "python", "obstest.py", fifo_path])
	log.debug("SPAWNED OBS")
	log.debug("CREATING FIFO")
	fifo = file(fifo_path, 'w')
	log.debug("CREATED FIFO")

	stub = piped_event.Stub(fifo)
	stub.subscribe(app.sess.onProcessed, 'onProcessed')
	"""

