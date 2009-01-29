# -*- coding: UTF-8 -*-
from curses_mvc import View, Controller
from event import EventSlot, EventQueue
import piped_event

import os
import curses
from curses.wrapper import wrapper
import threading
import time
import logging

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


class LogView(View):
		
	class Handler(logging.Handler):
		def __init__(self, log_view, log, log_format, curses_format):
			logging.Handler.__init__(self)
			self.log_view = log_view
			self.log = log
			self.curses_format = curses_format
			if log_format is not None:			
				self.setFormatter(log_format)
			self.log.addHandler(self)

		def emit(self, record):
			s = self.format(record)
			self.log_view.log(s, self.curses_format)
	
	def __init__(self, parent = None, win = None):
		View.__init__(self, parent, win)
		self.setwin(win)
		self.handlers = {} # log -> handler

	def addLog(self, log, curses_format, log_format = None):
		self.handlers[log] = self.Handler(self, log, log_format, curses_format)
	
	def removeLog(self, log):
		handler = self.handlers.get(log, None)
		if handler is not None:
			log.removeHandler(handler)
		self.handlers.pop(log)
	
	def setwin(self, win):
		if win is not None:
			win.scrollok(1)
			maxy, maxx = win.getmaxyx()
			win.setscrreg(0, maxy - 1)
		self._setwin(win)

	def log(self, text, attr):
		maxy, maxx = self.win.getmaxyx()
		self.win.attron(attr)
		for line in text.splitlines(): 
			self.win.scroll()
			self.win.addnstr(maxy - 1, 0, line, maxx)


