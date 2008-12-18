import pygdb
from event import EventSlot, EventQueue

import curses
from curses.wrapper import wrapper

class View(object):

	def draw(self, canvas):
		pass

class Controller(object):
	pass

class SourceFileView(View):

	def __init__(self, gdbtui, win):
		self.app = gdbtui
		self.win = win
		maxx, maxy = self.win.getmaxyx()
		self.client_area = win.subwin(maxy-2, maxx-2, 1, 1)
		self.top_line = 1
		self.src_file = None
		self.src_line = None
		self.src_line_data = []

		self.dirty = True

		self.app.onProcessedResponse.subscribe(self.onProcessedResponse)
		self.app.onBreakpointSet.subscribe(self.onBreakpointSet)
		self.app.onFrameChange.subscribe(self.onFrameChange)
		
	def __del__(self):
		pass
	
	def draw(self):
		self.win.border()
		maxy, maxx = self.client_area.getmaxyx()
		self.client_area.clear()
		startline = self.src_line if self.src_line is not None else 0
		endline = startline + maxy
		maxndigits = len(str(len(self.src_line_data)))
		visible_lines = self.src_line_data[startline:endline]
		for i in xrange(len(visible_lines)):
			line = visible_lines[i]
			lineno = i + startline
			if line == self.src_line:
				self.client_area.attron(curses.A_REVERSE)
			else:
				self.client_area.attroff(curses.A_REVERSE)
			linedata = [' '] * maxx
			linedata[:maxndigits] = str(lineno)
			linedata[maxndigits+1:] = line
			window.addnstr(i, 0, linedata, maxx)

	def update_src_file(self, path):
		if self.src_file != path:
			self.dirty = True
			self.src_file = path
			f = file(self.src_file, 'r')
			self.src_ine_data = f.read_lines()
			f.close()

	# Events 
	def onProcessResponse(self, session):
		if dirty:
			draw()
		dirty = False
	
	def onBreakpointSet(self, session, breakpoint_desc):
		dirty = True		

	def onFrameChange(self, session, frame):
		self.update_src_file(frame.fullname)

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
		'R': lambda: self.app.commandHandler.onRun(),
		'C': lambda: self.app.commandHandler.onContinue(),
		'n': lambda: self.app.commandHandler.onNext(),
		's': lambda: self.app.commandHandler.onStep(),
		'b': lambda: self.app.commandHandler.onBreak(),
		'q': lambda: self.app.commandHandler.onQuit()	
	}

	def _poll(self):
		while True:
			c = self.win.getkey()
			if self.ACTIONS.has_key(c):
				self.ACTIONS[c]()	

class CommandHandler(object):
	def __init__(self, gdb):
		self.commandQueue = EventQueue()
		self.onRun = self.commandQueue.schedule_handler(self._onRun)
		self.onContinue = self.commandQueue.schedule_handler(self._onContinue)
		self.onNext = self.commandQueue.schedule_handler(self._onNext)
		self.onStep = self.commandQueue.schedule_handler(self._onStep)
		self.onBreak = self.commandQueue.schedule_handler(self._onBreak)

	def _onRun(self):
		gdb.run()
	def _onContinue(self):
		gdb.cont()
	def _onStep(self):
		gdb.step()
	def _onNext(self):
		gdb.next()
	def _onBreak(self):
		gdb.setbreak(loc='main')
	def _onQuit(self):
		self.commandQueue.process = False

class PyGdbTui(object):

	def __init__(self, gdb, topwin):
		self.gdb = gdb
		self.sess = pygdb.GdbSession(gdb)
		self.topwin = topwin
		curses.raw()
		self.topwin.keypad(1)
	
		# Command handler
		self.commandHandler = CommandHandler(self.gdb)
		
		# Events
		self.onStartCommandInput = EventSlot()		

if __name__ == '__main__':
	
	def run(win):
		gdb = pygdb.GdbMI()
		app = PyGdbTui(gdb, win)
		app.commandHandler.commandQueue.run()

	wrapper(run)

