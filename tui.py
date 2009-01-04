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
		self.components = set()
		self._set_win(parent, win)

	def _set_win(self, parent, win):
		"""Sets the parent component and the window (canvas). Do not override."""
		self.win = win
		self.parent = parent
		if self.parent is not None:
			self.parent.components.add(self)

	def set_win(self, parent, win):
		"""Resets the parent component and the window (canvas). This function may be overridden."""
		self._set_win(parent, win)

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
		self.set_win(parent, win)
		self.inner = None
	
	def set_win(self, parent, win):
		self._set_win(parent, win)
		maxy, maxx = self.win.getmaxyx()
		self.client_area = self.win.derwin(maxy - 2, maxx - 2, 1, 1)
	
	def set_inner(self, inner):
		if self.inner is not None:
			self.components.remove(self.inner)
		self.inner = inner
		if self.inner is not None:
			self.inner.set_win(self, self.client_area)
	
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
		self._sz = []
	
	def _layout(self):
		maxy, maxx = self.win.getmaxyx()
		if self.orientation == 'H':
			maxz = maxx
		else:
			maxz = maxy
		total_abs = sum( + sz for sz in self._sz if sz > 0 )
		total_rel = sum( float(- sz) for sz in self._sz if sz < 0 )
		rel_rem = max(0, maxz - total_abs) # remaining for relative sizes
		
		rel_pos = acc(lambda x,y: x+y, [ rel_rem * (-sz / total_rel) if sz < 0 else 0 for sz in self._sz ], 0)
		rel_pos = [ int(round(x)) for x in rel_pos ]
		rel_pos[-1] = rel_rem
		rel_sz = [ rel_pos[i] - rel_pos[i-1] for i in xrange(1, len(rel_pos))]
		
		abs_sz = [ sz if sz > 0 else None for sz in self._sz ]
		
		def subwin(x0, sz):
			maxy, maxx = self.win.getmaxyx()
			if self.orientation == 'H':
				return self.win.derwin(maxy, sz, 0, x0)
			else:
				return self.win.derwin(sz, maxx, x0, 0)
		
		SZ = [ relsz if abssz is None else abssz for abssz,relsz in zip(abs_sz, rel_sz) ]
		X0 = list(acc(lambda x,y: x+y, SZ, 0))[:-1]
		
		self._subwins = [ subwin(x0, sz) for sz, x0 in zip(SZ, X0) ]
		
	def layout(self, *sz):
		self._sz = list(sz)
		self._layout()

class Settings(object):
	
	COLOR_DEFAULT = (curses.COLOR_WHITE, curses.COLOR_BLACK)
	COLOR_ACTIVE_BORDER = (curses.COLOR_YELLOW, curses.COLOR_BLACK)

	PAIR_DEFAULT = 1
	PAIR_ACTIVE_BORDER = 2

	def apply(self):
		curses.init_pair(self.PAIR_DEFAULT, *self.COLOR_DEFAULT)
		curses.init_pair(self.PAIR_ACTIVE_BORDER, *self.COLOR_ACTIVE_BORDER)


class SourceFileView(View):

	TABSTOP = 4

	def __init__(self, gdbtui, parent = None, win = None):
		View.__init__(self, parent, win)

		self.app = gdbtui
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

	def draw(self):
		if self.dirty and self.win is not None: 
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

	def scroll_down(self):
		self.line_off += 1
		self.dirty = True
		self.draw()
		self.refresh()

	def scroll_up(self):
		self.line_off -= 1
		self.line_off = max(0, self.line_off)
		self.dirty = True
		self.draw()
		self.refresh()

class CommandPanel(View):
	def __init__(self, gdbtui, parent = None, win = None):
		View.__init__(self, parent, win)
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
		
	def __init__(self, log, parent = None, win = None):
		View.__init__(self, parent, win)
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

class WatchView(View):

	TAB = 4

	def __init__(self, gdbtui, parent = None, win = None):
		View.__init__(self, parent, win)
		self.app = gdbtui
		self.dirty = False
		self.app.sess.onWatchUpdate.subscribe(self.onWatchUpdate)
	
	def draw(self):
		if not self.dirty:
			return
		self.win.erase()
		maxy, maxx = self.win.getmaxyx()
		def rec(children, i, j):
			for name, v in children.iteritems():
				if not v.in_scope:
					continue
				if i > maxy:
					break
				s = "%s : %s" % (v.expr, v.value)
				self.win.addnstr(i, j, s, max(0, maxx - j) )
				i += 1
				if v.children is not None:
					i = rec(v.children, i, j + self.TAB)
				else:
					if v.numchild > 0:
						if i > maxy:
							break
						j2 = j + self.TAB
						s = "<%s children>" % v.numchild
						self.win.addnstr(i, j2, s, max(0, maxx - j2))
			return i
		rec(self.app.sess._watch, 0, 0)	

	def onWatchUpdate(self, v):
		self.dirty = True

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
		'KEY_UP': lambda self: self.app.commandHandler.onScrollUp(),
		'KEY_DOWN': lambda self: self.app.commandHandler.onScrollDown(),
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
	def __init__(self, gdbtui, gdb, commandPanel):
		self.gdbtui = gdbtui
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
		self.gdbtui.src_view.scroll_down()
	def _onScrollUp(self):
		self.gdbtui.src_view.scroll_up()

class PyGdbTui(TopLevelView):

	def __init__(self, gdb, topwin):
		TopLevelView.__init__(self, topwin)
		
		self.gdb = gdb
		self.sess = pygdb.GdbSession(gdb)
		self.log = logging.getLogger('gdb')
		self.topwin = topwin
		curses.raw()
		self.topwin.keypad(1)
		
		# Color Settings
		self.settings = Settings()
		self.settings.apply()
		self.topwin.bkgd( curses.color_pair(self.settings.PAIR_DEFAULT) )
		
		# Views
		self.layout = LayoutView(self, self.topwin, 'V')
		self.layout.layout( -.65, -.35, 1 )
		upper_panel, log_view_win, command_panel_win = self.layout._subwins
		
		upper_layout = LayoutView(self.layout, upper_panel, 'H')
		upper_layout.layout( -.6, -.4 )
		src_view_win, watch_win = upper_layout._subwins
		
		self.src_view_panel = NamedPanel(upper_layout, src_view_win, "<source>")
		self.src_view = SourceFileView(self)
		self.src_view_panel.set_inner(self.src_view)
		
		self.log_view = LogView(self.log, self.layout, log_view_win)
		
		self.command_panel = CommandPanel(self, self.layout, command_panel_win)
		self.watch_panel = NamedPanel(upper_layout, watch_win, "watch")
		self.watch_view = WatchView(self)
		self.watch_panel.set_inner(self.watch_view)
		
		# Command handler
		self.commandHandler = CommandHandler(self, self.sess, self.command_panel)
		
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
		self.refresh()

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

