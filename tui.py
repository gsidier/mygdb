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
		self._setwin(win)
		self._setparent(parent)
		self._has_focus = False

	def _setwin(self, win):
		"""Sets the window (canvas). Do not redefine this method."""
		self.win = win
		
	def _setparent(self, parent):
		"""Sets the parent view. Do not redefine this method."""
		self.parent = parent
		if self.parent is not None:
			self.parent.components.add(self)

	def setwin(self, win):
		"""Sets the window (canvas). This function may be redefined by subclasses."""
		self._setwin(win)

	def setparent(self, parent):
		"""Sets the parent view. This function may be redefined by subclasses."""
		self._setparent(parent) 

	def delwin(self):
		"""
		Removes this view's window.
		"""
		for c in self.components:
			c.delwin()
		self.win = None

	def update(self):
		"""
		Redraw the view and its subcomponents to the content buffer.
		Recursively calls draw() on this view and it's subviews.
		"""
		for c in self.components:
			c.update()
		self.draw()
	
	def refresh(self):
		"""
		Perform a win.refresh on this view's and it's subviews' windows, displaying the content buffers to the screen.
		"""
		self.win.refresh()
		for c in self.components:
			c.refresh()
	
	def draw(self):
		"""
		Draw the view to the content buffer.
		"""
		pass

	def accept_focus(self):
		return True

	def resize(self):
		"""
		Called when the window size has changed.
		"""
		self.win.erase()
		for c in self.components:
			c.resize()
		self.draw()

class TopLevelView(View):
	def __init__(self, win):
		View.__init__(self, None, win)

class Controller(object):
	pass

class NamedPanel(View):
	def __init__(self, name, parent = None, win = None):
		View.__init__(self, parent, win)
		self.name = name
		self.setwin(win)
		self.inner = None
	
	def setwin(self, win):
		self._setwin(win)
		if self.win is not None:
			maxy, maxx = self.win.getmaxyx()
			self.client_area = self.win.derwin(maxy - 2, maxx - 2, 1, 1)
			self.set_inner(self.inner)
		else:
			self.client_area = None
	
	def set_inner(self, inner):
		if self.inner is not None:
			self.components.remove(self.inner)
		self.inner = inner
		if self.inner is not None:
			self.inner.setparent(self)
			self.inner.setwin(self.client_area)
	
	def refresh(self):
		self.win.refresh()
	
	def draw(self):
		if self._has_focus:
			self.win.attron(curses.A_BOLD)
		self.win.border()
		maxy, maxx = self.win.getmaxyx()
		self.win.addnstr(0, 1, "[ %s ]" % self.name, max(0, maxx - 1))
		self.win.attroff(curses.A_BOLD)
		self.win.attron(curses.A_NORMAL)

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
		self._views = []
		self._in_focus = None
		self._active_view = None
	
	def _layout(self):

		if self.win is None:
			return
		
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
		rel_sz = [ rel_pos[i] - rel_pos[i-1] for i in xrange(1, len(rel_pos)) ]
		
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

		for v, w in zip(self._views, self._subwins):
			v.setparent(self)
			v.setwin(w)
		
	def setwin(self, win):
		self._setwin(win)
		self._layout()
		
	def layout(self, *sz_v):
		self._sz, self._views = zip(*sz_v)
		self._layout()

	def resize(self):
		self._layout()
		View.resize(self)

	def flip_focus(self, dir = +1, loop = True):
		"""
		Flip focus between the inner views.
		If one of the inner views has a 'flip_focus' functionality, then flip its focus in turn.
		'dir' is +1 to flip forward, -1 to flip back, and None to reset.
		'loop' is True if one should flip back to the other end of the stack of views.
		Return True if still flipping, or False.
		"""
		if dir is None:
			self._in_focus = None
			self._active_view = None
			return False
		n = len(self._views)
		for count in xrange(n): # try at most once for each inner view
			if self._in_focus is None:
				self._in_focus = 0 if dir > 0 else n - 1
			elif hasattr(self._views[self._in_focus], 'flip_focus'):
				if not self._views[self._in_focus].flip_focus(dir, False):
					self._in_focus += int(dir)
				else:
					self._active_view = self._views[self._in_focus]._active_view
					return True
			else:
				self._in_focus += int(dir)
			if (not loop) and (self._in_focus >= n or self._in_focus < 0):
				self._in_focus = None
				if self._active_view is not None:
					self._active_view._has_focus = False
					self._active_view = None
				return False
			self._in_focus = self._in_focus % n
			v = self._views[self._in_focus]
			if hasattr(v, 'flip_focus'):
				v.flip_focus(None)
				continue
			elif not v.accept_focus():
				continue
			else:
				if self._active_view is not None:
					self._active_view._has_focus = False
				self._active_view = v
				self._active_view._has_focus = True
			return True
		return False

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

	def draw(self):
		if self.dirty and self.win is not None: 
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
		log.debug("EVENT : SourceFileView << onBreakPointSet")
		self.dirty = True

	def onFrameChange(self, frame):
		self.dirty = True
		log.debug("EVENT : SourceFileView << onFrameChange")
		if hasattr(frame, 'fullname'):
			self.update_src_file(frame.fullname)
		elif hasattr(frame, 'file'):
			self.update_src_file(frame.file)
		if hasattr(frame, 'file'):
			self.gdbtui.src_view_panel.name = frame.file
		elif hasattr(frame, 'fullname'):
			self.gdbtui.src_view_panel.name = frame.fullname
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
		self.app = gdbtui.app
		self.gdbtui = gdbtui
		self.win = win
		
	def input(self):
		self.win.clear()
		curses.curs_set(1)
		curses.echo()
		cmd = self.gdbtui.kb_input.get_focus(lambda: self.win.getstr())
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

	def accept_focus(self):
		return False

class LogView(View, logging.Handler):
		
	def __init__(self, log, parent = None, win = None):
		View.__init__(self, parent, win)
		self.setwin(win)
		logging.Handler.__init__(self)
		self.log = log
		self.log.addHandler(self)

	def setwin(self, win):
		if win is not None:
			win.scrollok(1)
			maxy, maxx = win.getmaxyx()
			win.setscrreg(0, maxy - 1)
		self._setwin(win)

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
		self.app = gdbtui.app
		self.gdbtui = gdbtui
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
				"""
				else:
					if v.numchild > 0:
						if i > maxy:
							break
						j2 = j + self.TAB
						s = "<%s children>" % v.numchild
						self.win.addnstr(i, j2, s, max(0, maxx - j2))	
				"""
			return i
		rec(self.app.sess._watch, 0, 0)	

	def onWatchUpdate(self, v):
		self.dirty = True

class TopLevelKeyboardInput(Controller):
	def __init__(self, gdbtui, win):
		self.app = gdbtui.app
		self.gdbtui = gdbtui
		self.win = win
		self._process = True
		self.kb_poll_thread = threading.Thread(target = self._poll)
		self.kb_poll_thread.setDaemon(True)
		self.kb_poll_thread.start()

	ACTIONS = {
		'R': lambda self: self.gdbtui.commandHandler.onRun(),
		'C': lambda self: self.gdbtui.commandHandler.onContinue(),
		'n': lambda self: self.gdbtui.commandHandler.onNext(),
		's': lambda self: self.gdbtui.commandHandler.onStep(),
		'b': lambda self: self.gdbtui.commandHandler.onBreak(),
		'q': lambda self: self.gdbtui.commandHandler.onQuit(),
		';': lambda self: self.gdbtui.commandHandler.onStartInput(mode='python'),
		'!': lambda self: self.gdbtui.commandHandler.onStartInput(mode='gdb'),
		':': lambda self: self.gdbtui.commandHandler.onStartInput(mode='quick'),
		'o': lambda self: self.gdbtui.commandHandler.onStartPythonShell(),
		'KEY_F(2)': lambda self: self.gdbtui.commandHandler.onStartShell(),
		'KEY_F(10)': lambda self: self.gdbtui.commandHandler.onPopoutLog(),
		'KEY_RESIZE': lambda self: self.gdbtui.commandHandler.onResize(),
		'KEY_UP': lambda self: self.gdbtui.commandHandler.onScrollUp(),
		'KEY_DOWN': lambda self: self.gdbtui.commandHandler.onScrollDown(),
		'KEY_F(1)': lambda self: None,
		'\t': lambda self: self.gdbtui.commandHandler.onFlipFocus(+1),
		'KEY_BTAB': lambda self: self.gdbtui.commandHandler.onFlipFocus(-1),
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
						self.gdbtui.commandHandler.onProcessed()
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
		self.app = gdbtui.app
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
		self.onStartPythonShell = self.commandQueue.schedule_handler(self._onStartPythonShell)
		self.onStartShell = self.commandQueue.schedule_handler(self._onStartShell)

		self.onProcessed = self.commandQueue.schedule_handler(self._onProcessed)

		self.onResize = self.commandQueue.schedule_handler(self._onResize)
	
		self.onScrollUp = self.commandQueue.schedule_handler(self._onScrollUp)
		self.onScrollDown = self.commandQueue.schedule_handler(self._onScrollDown)
		
		self.onFlipFocus = self.commandQueue.schedule_handler(self._onFlipFocus)

		self.onPopoutLog = self.commandQueue.schedule_handler(self._onPopoutLog)

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
		self.app.quit()
	def _onStartInput(self, mode):
		cmd = self.commandPanel.input()
		try:
			if mode == 'python':
				res = self.gdb.runCommand(cmd)
			elif mode == 'gdb':
				res = self.gdb.runGdbCommand(cmd)
			elif mode == 'quick':
				res = self.gdb.runQuickCommand(cmd)
		except Exception, e:
			self.commandPanel.disperr(e.message)
	
	def _onProcessed(self):
		self.gdb.onProcessed.broadcast()
	
	def _onResize(self):
		self.gdbtui.handleResize()

	def _onScrollDown(self):
		self.gdbtui.src_view.scroll_down()
	def _onScrollUp(self):
		self.gdbtui.src_view.scroll_up()

	def _onFlipFocus(self, dir):
		self.gdbtui.log.debug("TOGGLING FOCUS")
		self.gdbtui.layout.flip_focus(dir, True)
		self.gdbtui.log.debug("ACTIVE VIEW : %s" % self.gdbtui.layout._active_view)

	def _onStartPythonShell(self):
		self.app.switch_mode('PYSHELL')

	def _onStartShell(self):
		self.app.switch_mode('SHELL')

	def _onPopoutLog(self):
		xterm = subprocess.Popen(["xterm", "+hold", "-e", "tail", "-f", "session.log"])

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
		self.src_view_panel = NamedPanel("<source>")
		self.src_view = SourceFileView(self)
		self.src_view_panel.set_inner(self.src_view)
	
		self.watch_panel = NamedPanel("watch")
		self.watch_view = WatchView(self)
		self.watch_panel.set_inner(self.watch_view)
	
		upper_layout = LayoutView(None, None, 'H')
		upper_layout.layout( 
			(-.6, self.src_view_panel), 
			(-.4, self.watch_panel) 
		)
		
		self.log_view = LogView(self.log)

		self.command_panel = CommandPanel(self)
	
		self.layout = LayoutView(self, self.topwin, 'V')
		self.layout.layout( 
			(-.65, upper_layout),
			(-.35, self.log_view),
			(   1, self.command_panel ) 
		)
	
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

	def handleResize(self):
		self.layout.resize()


	def process_events(self):
		self.kb_input._process = True
		self.commandHandler.commandQueue.process = True
		self.commandHandler.commandQueue.run()

	def stop_events(self):
		self.kb_input._process = False
		self.commandHandler.commandQueue.process = False

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
		if self.appmode == 'TUI':
			self.gdbtui.stop_events()
		self.appmode = 'QUIT'
	
	def run_tui(self, win):
		curses.curs_set(0)
		if self.gdbtui is None:
			self.gdbtui = PyGdbTui(self, win)
		else:
			self.gdbtui.setwin(win)
		self.gdbtui.process_events()

	def run_pyshell(self):
		from IPython.Shell import IPShellEmbed
		ipshell = IPShellEmbed()
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
	
	log = logging.getLogger("gdb")
	log.addHandler(logging.FileHandler("session.log"))
	log.setLevel(logging.DEBUG)


	gdb = pygdb.GdbMI()
	app = App(gdb)
	#
	app.sess.file('hello')
	#
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

