# -*- coding: UTF-8 -*-
from event import EventSlot, EventQueue
import piped_event

import os
import curses
from curses.wrapper import wrapper
import threading
import time


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
	
	def handle_key(self, k):
		"""
		Handle a key press event.
		Return True if the view is designed to respond to this key, otherwise False.
		This function will call this instance's _handle_key, and if it fails, 
		will bubble the event up to its parent container if any.
		"""
		return False

	def _handle_key(self, k):
		return False


class TopLevelView(View):
	def __init__(self, win):
		View.__init__(self, None, win)


class Controller(object):
	pass


