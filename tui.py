#!/usr/bin/env python
# -*- coding: UTF-8 -*-
import pygdb
from event import EventSlot, EventQueue
import piped_event

import os
import curses
from curses.wrapper import wrapper
import threading
import logging
import time
import subprocess

class View(object):

	def __init__(self, parent, win):
		self.win = win
		self.components = set()
		self.parent = parent
		if self.parent is not None:
			self.parent.components.add(self)

	def update(self):
		for c in self.components:
			c.update()
		self.draw()
	
	def refresh(self):
		self.win.refresh()
		for c in self.components:
			c.refresh()
	
	def draw(self):
		pass

class TopLevelView(View):
	def __init__(self, win):
		View.__init__(self, None, win)

class Controller(object):
	pass

class NamedPanel(View):
	def __init__(self, parent, win, name):
		View.__init__(self, parent, win)
		self.name = name
		maxy, maxx = self.win.getmaxyx()
		self.client_area = win.derwin(maxy - 2, maxx - 2, 1, 1)

	def refresh(self):
		self.win.refresh()

	def draw(self):
		self.win.border()
		maxy, maxx = self.win.getmaxyx()
		self.win.addnstr(0, 1, "[ %s ]" % self.name, max(0, maxx - 1))

def acc(func, seq, initial = None):
	if initial is not None:
		yield initial
	acc = initial

	for x in seq:
		if acc is None:
			acc = x
		else:
			acc = func(acc, x)
		yield acc

class LayoutView(View):
	def __init__(self, parent, win, orientation = 'H'):
		View.__init__(self, parent, win)
		self.orientation = orientation.strip().upper()
		self._subviews = [] # [ (size, view) ] where size > 0: abs # cols, size < 0: rel # cols
	
	def _layout(self):
		maxy, maxx = self.win.getmaxyx()
		if self.orientation == 'H':
			maxz = maxx
		else:
			maxz = maxy
		total_abs = sum( + sz for sz,view in self._subviews if sz > 0 )
		total_rel = sum( float(- sz) for sz,view in self._subviews if sz < 0 )
		rel_rem = max(0, maxz - total_abs) # remaining for relative sizes

		rel_pos = acc(lambda x,y: x+y, [ rel_rem * (-sz / total_rel) if sz < 0 else 0 for sz,v in self._subviews ], 0)
		rel_pos = [ int(round(x)) for x in rel_pos ]
		rel_pos[-1] = rel_rem
		rel_sz = [ rel_pos[i] - rel_pos[i-1] for i in xrange(1, len(rel_pos))]

		abs_sz = [ sz if sz > 0 else None for sz,v in self._subviews ]
	
		def subwin(x0, sz):
			maxy, maxx = self.win.getmaxyx()
			if orientation == 'H':
				return self.win.derwin(maxy, sz, 0, x0)
			else:
				return self.win.derwin(sz, maxx, x0, 0)
		
		SZ = [ relsz if abssz is None else abssz for abssz,relsz in zip(abs_sz, rel_sz) ]
		X0 = list(acc(lambda x,y: x+y, sz, 0))[:-1]
		
		subwins = [ subwin(x0, sz) for for sz, x0 in zip(SZ, X0) ]
		
		for ((sz,v),w) in zip(self._subviews, subwins):
			v.win = w
			
	
	def draw(self):
		self.update()

class SourceFileView(View):

	TABSTOP = 4

	def __init__(self, gdbtui, win):
		View.__init__(self, gdbtui.src_view_panel, win)

		self.app = gdbtui
		self.log = logging.getLogger("gdb")
		
		maxy, maxx = self.win.getmaxyx()
		self.log.debug("SRC VIEW WIN %d %d" % (maxx, maxy))
		self.line_off = 0
		self.src_file = None
		self.src_line = None # 1-based
		self.src_line_data = []

		self.dirty = True
		self.draw()

		self.app.sess.onBreakpointSet.subscribe(self.onBreakpointSet)
		self.app.sess.onFrameChange.subscribe(self.onFrameChange)
		
	def __del__(self):
		pass

	def _get_line_from_buffer(self, buf, lineno):
		# just translate between 1-based line numbers in files
		# and 0-based in buffers
		return buf[lineno - 1]

	def draw(self):
		if self.dirty: 
			curses.curs_set(0)
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
			self.log.debug("SourceFileView : size (%d, %d) - startoff %d - endoff %d" % (maxy, maxx, startoff, endoff))
			visible_lines = self.src_line_data[startoff:endoff]
			self.log.debug("SRC LINE : %s" % self.src_line)
			for i in xrange(len(visible_lines)):
				lineno = i + startline 
				line = visible_lines[i].replace('\t', ' ' * self.TABSTOP)
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
				# self.log.debug("Gonna paste str (len %d at %d, %d) '%s'" % (len(linedata), 0, i, linedata))
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
		log.debug("EVENT : SourceFileView << onBreakPointSet")
		self.dirty = True

	def onFrameChange(self, frame):
		self.dirty = True
		log.debug("EVENT : SourceFileView << onFrameChange")
		if hasattr(frame, 'file'):
			self.update_src_file(frame.file)
			self.app.src_view_panel.name = frame.file
		if hasattr(frame, 'line'):
			self.src_line = int(frame.line)
			self.log.debug("CURRENT LINE : %d" % self.src_line)
		else:
			self.src_line = None

class CommandPanel(View):
	def __init__(self, gdbtui, win):
		View.__init__(self, gdbtui, win)
		self.app = gdbtui
		self.win = win
		
	def input(self):
		self.win.clear()
		curses.curs_set(1)
		curses.echo()
		cmd = self.app.kb_input.get_focus(lambda: self.win.getstr())
		curses.noecho()
		curses.curs_set(0)
		return cmd
	
	def draw(self):
		pass #self.win.clear()

	def disperr(self, errmsg):
		self.win.clear()
		maxy, maxx = self.win.getmaxyx()
		self.win.addnstr(0, 0, errmsg, max(len(errmsg), maxx))
		self.win.refresh()

class LogView(View, logging.Handler):
		
	def __init__(self, gdbtui, win, log):
		View.__init__(self, gdbtui, win)
		self.win.scrollok(1)
		maxy, maxx = self.win.getmaxyx()
		self.win.setscrreg(0, maxy - 1)
		logging.Handler.__init__(self)
		self.log = log
		self.log.addHandler(self)

	def emit(self, record):
		maxy, maxx = self.win.getmaxyx()
		s = self.format(record)
		for line in s.splitlines():
			self.win.scroll()
			self.win.addnstr(maxy - 1, 0, s, maxx)

class TopLevelKeyboardInput(Controller):
	def __init__(self, gdbtui, win):
		self.app = gdbtui
		self.win = win
		self._process = True
		self.kb_poll_thread = threading.Thread(target = self._poll)
		self.kb_poll_thread.setDaemon(True)
		self.kb_poll_thread.start()

	ACTIONS = {
		'R': lambda self: self.app.commandHandler.onRun(),
		'C': lambda self: self.app.commandHandler.onContinue(),
		'n': lambda self: self.app.commandHandler.onNext(),
		's': lambda self: self.app.commandHandler.onStep(),
		'b': lambda self: self.app.commandHandler.onBreak(),
		'q': lambda self: self.app.commandHandler.onQuit(),
		':': lambda self: self.app.commandHandler.onStartInput(mode='python'),
		'!': lambda self: self.app.commandHandler.onStartInput(mode='gdb'),
		'KEY_UP': lambda self: self.app.commandHandler.scrollUp(),
		'KEY_DOWN': lambda self: self.app.commandHandler.scrollDown(),
		'KEY_F(1)': lambda self: None
	}

	def _poll(self):
		while True:
			if self._process:
				curses.halfdelay(2)
				try:
					c = self.win.getkey()
					log.debug("KEY PRESSED : '%s'" % c)
					if self.ACTIONS.has_key(c):
						self.ACTIONS[c](self)
						self.app.commandHandler.onProcessed()
				except:
					pass
			else:
				time.sleep(.2)

	def get_focus(self, function):
		self._process = False
		res = function()
		self._process = True
		return res

class CommandHandler(object):
	def __init__(self, gdb, commandPanel):
		self.gdb = gdb
		self.commandPanel = commandPanel
		self.commandQueue = EventQueue(vsync = 1e-3)
		self.onRun = self.commandQueue.schedule_handler(self._onRun)
		self.onContinue = self.commandQueue.schedule_handler(self._onContinue)
		self.onNext = self.commandQueue.schedule_handler(self._onNext)
		self.onStep = self.commandQueue.schedule_handler(self._onStep)
		self.onBreak = self.commandQueue.schedule_handler(self._onBreak)
		self.onQuit = self.commandQueue.schedule_handler(self._onQuit)
		self.onStartInput = self.commandQueue.schedule_handler(self._onStartInput)
	
		self.onProcessed = self.commandQueue.schedule_handler(self._onProcessed)
	
		self.onScrollUp = self.commandQueue.schedule_handler(self._onScrollUp)
		self.onScrollDown = self.commandQueue.schedule_handler(self._onScrollDown)
		
	def _onRun(self):
		self.gdb.run()
	def _onContinue(self):
		self.gdb.cont()
	def _onStep(self):
		self.gdb.step()
	def _onNext(self):
		self.gdb.next()
	def _onBreak(self):
		self.gdb.setbreak(loc='main')
	def _onQuit(self):
		self.commandQueue.process = False
	def _onStartInput(self, mode):
		cmd = self.commandPanel.input()
		try:
			if mode == 'python':
				res = self.gdb.runCommand(cmd)
			elif mode == 'gdb':
				res = self.gdb.runGdbCommand(cmd)
		except Exception, e:
			self.commandPanel.disperr(e.message)
	
	def _onProcessed(self):
		self.gdb.onProcessed.broadcast()
	
	def _onScrollDown(self):
		pass
	def _onScrollUp(self):
		pass

class PyGdbTui(TopLevelView):

	def __init__(self, gdb, topwin):
		TopLevelView.__init__(self, topwin)
		
		self.gdb = gdb
		self.sess = pygdb.GdbSession(gdb)
		self.log = logging.getLogger('gdb')
		self.topwin = topwin
		curses.raw()
		self.topwin.keypad(1)
	
		# Views
		maxy, maxx = self.topwin.getmaxyx()
		y1 = int(.65 * maxy)
		src_view_win = self.topwin.derwin(y1, maxx, 0, 0)
		self.src_view_panel = NamedPanel(self, src_view_win, "<source>")
		self.src_view = SourceFileView(self, self.src_view_panel.client_area)
		log_view_win = self.topwin.derwin(maxy - y1 - 1, maxx, y1, 0)
		self.log_view = LogView(self, log_view_win, self.log)
		command_panel_win = self.topwin.derwin(1, maxx, maxy - 1, 0)
		self.command_panel = CommandPanel(self, command_panel_win)

		# Command handler
		self.commandHandler = CommandHandler(self.sess, self.command_panel)
		
		# Events
		self.onStartCommandInput = EventSlot()
		
		# Event Handlers
		self.sess.onProcessed.subscribe(self.onGdbProcessedResponse)
		self.scheduled_onGdbProcessedResponse = self.commandHandler.commandQueue.schedule_handler(self._onGdbProcessedResponse)

		# Input
		self.kb_input = TopLevelKeyboardInput(self, self.topwin)

	def onGdbProcessedResponse(self):
		self.scheduled_onGdbProcessedResponse()
	def _onGdbProcessedResponse(self):
		self.log.debug("### REFRESH ###")
		self.update()
		#self.src_view.draw()
		#self.topwin.refresh()
		#self.src_view.win.refresh()
		#self.log_view.win.refresh()
		
		self.refresh()
		"""
		self.topwin.refresh()
		self.src_view_panel.win.refresh()
		self.log_view.win.refresh()
		self.command_panel.win.refresh()
		"""

if __name__ == '__main__':
	
	log = logging.getLogger("gdb")
	log.addHandler(logging.FileHandler("session.log"))
	log.setLevel(logging.DEBUG)


	def run(win):
		gdb = pygdb.GdbMI()
		app = PyGdbTui(gdb, win)
		#
		app.sess.file('hello')
		#
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
		#
		app.commandHandler.commandQueue.run()

	wrapper(run)

