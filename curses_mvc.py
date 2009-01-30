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

	def on_event(self, evt):
		"""
		This method should be redefined by subclasses to handle the events
		captured by this controller.
		The type of the evt parameter will depend on the type of Controller.
		Return True if the event was handled, False otherwise.
		"""
		return False

class BubblingController(Controller):
	"""
	This is a controller combiner that takes 
		* a LayoutView
		* a set of controllers attached to descendent views of the layout
	and implements a bubbling mechanism, where an event is first sent to the active view,
	then to it's parent if it wasn't handled, then to the parent's parent etc, stopping 
	at the level of the layout.
	"""
	def __init__(self, layout_view):
		self.controllers = {} # view -> controller
		self.layout_view = layout_view
	
	def on_event(self, evt):
		V = self.layout_view.active_view
		handled = False
		while V is not None and not handled:
			C = self.controllers.get(V, None)
			if C is not None:
				handled = C.on_event(evt)
			if handled or V == self.layout_view: 
				# don't bubble higher than original layout view
				break
			V = V.parent
		return handled
	
def KeyboardController(Controller):
	"""
	Starts a thread to poll for keyboard events.
	This class should be subclassed to define the event handling function on_event.
	"""
	
	def __init__(self):
		self._process = True
		self.kb_poll_thread = threading.Thread(target = self._poll)
		self.kb_poll_thread.setDaemon(True)
		self.kb_poll_thread.start()

	def _poll(self):
		while True:
			if self._process:
				curses.halfdelay(2)
				try:
					c = self.win.getkey()
					self.on_event(c)
				except:
					pass
			else:
				time.sleep(.2)

	def get_focus(self, function):
		self._process = False
		res = function()
		self._process = True
		return res	


class KeyboardActions(Controller):
	"""
	Should be subclassed, the subclass defining an ACTIONS
	attribute, either as a class member or instance member.

	ACTIONS = { key: lambda self: ...  }
	"""
	

	def on_event(self, evt):
		handler = self.ACTIONS.get(evt, None)
		if handler is not None:
			handler(self)

