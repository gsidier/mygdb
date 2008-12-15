import pygdb

import curses

class View(object):

	def draw(self, canvas):
		pass

class SourceFileView(View):

	def __init__(self, gdbtui):
		self.app = gdbtui
		self.top_line = 1
		self.current_line = None
		self.line_data = []

		self.app.onBreakpointSet.subscribe(self.onBreakpointSet)
		
	def __del__(self):
		pass
	
	def draw(self, canvas):
		pass

	# Events 
	def onBreakpointSet(self, breakpoint_desc):
		self.draw()
	
class PyGdbTui(object):

	def __init__(self, gdb, topwin):
		self.gdbinst = gdb
		self.gdb = pygdb.GdbSession(gdb)
		self.topwin = topwin
		curses.raw()
		self.topwin.keypad(1)
		

