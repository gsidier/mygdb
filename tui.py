import pygdb
from event import EventSlot, EventQueue

import curses
from curses.wrapper import wrapper
import threading
import logging

class View(object):

	def __init__(self, win, parent):
		self.win = win
		components = set()
		if parent is not None:
			self.parent.components.add(self)

	def update(self):
		for c in components:
			c.update()
		self.draw()
	
	def draw(self, canvas):
		pass

class TopLevelView(View):
	def __init__(self, win):
		View.__init__(self, win, None)

class Controller(object):
	pass

class SourceFileView(View):

	def __init__(self, gdbtui, win):
		self.app = gdbtui
		self.win = win	
		self.log = logging.getLogger("gdb")
		
		maxy, maxx = self.win.getmaxyx()
		self.client_area = win.subwin(maxy-2, maxx-2, 1, 1)
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
			self.win.border()
			maxy, maxx = self.client_area.getmaxyx()
			self.client_area.clear()
			startoff = self.line_off if self.line_off is not None else 0
			startline = startoff + 1 # 'offsets' are 0-based, 'lines' are 1-based
			endoff = startoff + maxy
			endline = endoff + 1
			maxndigits = len(str(len(self.src_line_data)))
			self.log.debug("SourceFileView : size (%d, %d) - startoff %d - endoff %d" % (maxy, maxx, startoff, endoff))
			visible_lines = self.src_line_data[startoff:endoff]
			for i in xrange(len(visible_lines)):
				lineno = i + startline 
				line = visible_lines[i]
				if lineno == self.src_line:
					self.client_area.attron(curses.A_REVERSE)
					self.client_area.attron(curses.A_BOLD)
					self.log.debug("DRAWING WITH CURRENT LINE : %d" % lineno)
				else:
					self.client_area.attroff(curses.A_REVERSE)
					self.client_area.attroff(curses.A_BOLD)
				linedata = [' '] * maxx
				linedata[:maxndigits] = str(lineno)
				linedata[maxndigits+1:] = line
				linedata = ''.join(linedata)
				self.client_area.addnstr(i, 0, linedata, maxx)
		self.dirty = False

	def update_src_file(self, path):
		if self.src_file != path:
			self.dirty = True
			self.src_file = path
			f = file(self.src_file, 'r')
			self.src_line_data = f.readlines()
			f.close()
	
	def onBreakpointSet(self, session, breakpoint_desc):
		log.debug("EVENT : SourceFileView << onBreakPointSet")
		self.dirty = True

	def onFrameChange(self, session, frame):
		self.dirty = True
		log.debug("EVENT : SourceFileView << onFrameChange")
		if hasattr(frame, 'file'):
			self.update_src_file(frame.file)
		if hasattr(frame, 'line'):
			self.src_line = int(frame.line)
			self.log.debug("CURRENT LINE : %d" % self.src_line)
		else:
			self.src_line = None

class CommandInput(Controller):
	def __init__(self, gdbtui, win):
		self.app = gdbtui
		self.win = win
	
	def onStartCommandInput(self):
		curses.echo()
		cmd = self.win.getstr()
		curses.noecho()

class CommandPanel(View):
	def __init__(self, gdbtui, win):
		self.app = gdbtui
		self.win = win
		
	def draw(self):
		self.win.clear()

class TopLevelKeyboardInput(Controller):
	def __init__(self, gdbtui, win):
		self.app = gdbtui
		self.win = win
		self.kb_poll_thread = threading.Thread(target = self._poll)
		self.kb_poll_thread.setDaemon(True)
		self.kb_poll_thread.start()

	ACTIONS = {
		'R': lambda self: self.app.commandHandler.onRun(),
		'C': lambda self: self.app.commandHandler.onContinue(),
		'n': lambda self: self.app.commandHandler.onNext(),
		's': lambda self: self.app.commandHandler.onStep(),
		'b': lambda self: self.app.commandHandler.onBreak(),
		'q': lambda self: self.app.commandHandler.onQuit()	
	}

	def _poll(self):
		while True:
			c = self.win.getkey()
			if self.ACTIONS.has_key(c):
				self.ACTIONS[c](self)

class CommandHandler(object):
	def __init__(self, gdb):
		self.gdb = gdb
		self.commandQueue = EventQueue(vsync = 1e-3)
		self.onRun = self.commandQueue.schedule_handler(self._onRun)
		self.onContinue = self.commandQueue.schedule_handler(self._onContinue)
		self.onNext = self.commandQueue.schedule_handler(self._onNext)
		self.onStep = self.commandQueue.schedule_handler(self._onStep)
		self.onBreak = self.commandQueue.schedule_handler(self._onBreak)
		self.onQuit = self.commandQueue.schedule_handler(self._onQuit)

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

class PyGdbTui(TopLevelView):

	def __init__(self, gdb, topwin):
		self.gdb = gdb
		self.sess = pygdb.GdbSession(gdb)
		self.log = logging.getLogger('gdb')
		self.topwin = topwin
		curses.raw()
		self.topwin.keypad(1)
	
		# Command handler
		self.commandHandler = CommandHandler(self.sess)
		
		# Events
		self.onStartCommandInput = EventSlot()
		
		# Event Handlers
		self.sess.onProcessedResponse.subscribe(self.onGdbProcessedResponse)
		self.scheduled_onGdbProcessedResponse = self.commandHandler.commandQueue.schedule_handler(self._onGdbProcessedResponse)

		# Views
		self.src_view = SourceFileView(self, self.topwin)

		# Input
		self.kb_input = TopLevelKeyboardInput(self, self.topwin)

	def onGdbProcessedResponse(self, sess):
		self.scheduled_onGdbProcessedResponse()
	def _onGdbProcessedResponse(self):
		self.log.debug("### REFRESH ###")
		self.src_view.draw()
		self.topwin.refresh()
		self.src_view.client_area.refresh()

if __name__ == '__main__':
	
	def run(win):
		gdb = pygdb.GdbMI()
		app = PyGdbTui(gdb, win)
		#
		app.sess.file('hello')
		#
		app.commandHandler.commandQueue.run()

	log = logging.getLogger("gdb")
	log.addHandler(logging.FileHandler("session.log"))
	log.setLevel(logging.DEBUG)

	wrapper(run)

