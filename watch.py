import pygdb

class WatchedVar(object):
	def __init__(self, gdbsess, var):
		self.gdbsess = gdbsess
		self.var = var
	
	def _getchild(self, chld):
		if self.var.children is None:
			self.gdbsess.var_list_children(var.name)
			return None
		elif chld in self.var.children:
			return self.var.children[

	def __getattr__(self, attr):
		return self._getchild(attr)

	def __getitem__(self, idx):
		return self._getchild(str(idx))

class FilteredWatch(pygdb.VarWatcher):
	def __init__(self, gdbsess, var):
		VarWatcher.__init__(self, gdbsess, var, 'default')
		self.children = {}
		self.pyval = None
		self.w = WatchedVar(gdbsess, var)

	def _pyval(self):
		pass
	
	def _children(self):
		pass
	
	def onUpdate(self, var, upd):
		self.children = self._children()
		self.pyval = self._pyval()



"""
Common interface for watchable variables:

var v,

	v.name : var name eg "var1.foo.bar"
	v.expr : var expr eg "bar"
	v.type = var type eg "int", "struct {...}*", ...
	v.value = string 
	v.numchild = int
	v.in_scope = in_scope
	v.children = None

"""
