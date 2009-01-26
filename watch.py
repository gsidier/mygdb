import pygdb

class WrappedWatch(object):
	def __init__(self, gdbsess, var):
		self.gdbsess = gdbsess
		self.var = var
	
	def __wrap(self, var):
		"""
		Take a plain var and wrap it. To be implemented by subclasses.
		"""
		pass

	def __children(self):
		if self.var.children is None:
			children = self.gdbsess.var_list_children(var.name, sync = True)
			return dict( (k, self.__wrap(v)) for k, v in children )
		
		if self.var.children is None: # still
			raise Exception, "Var get children failed."
	
	def __getchild(self, chld):
		if chld in self.__children:
			return self.__wrap(self.var.children[chld])
		else:
			raise Exception, "Var subitem not found."
	
	def __getattr__(self, attr):
		return self.__getchild(attr)

	def __getitem__(self, idx):
		return self.__getchild(str(idx))

	def __value(self):
		return self.var.value

	def __type(self):
		return self.var.type

class FilteredWatch():
	def __init__(self, gdbsess, var):
		WrappedWatch.__init__(self, gdbsess, var)
		self.children = {}
		self.pyval = None
		self.w = WrappedWatch(gdbsess, var)
	
	def register_watch(self, expr, depends, toplevel = True):
		e = expr % tuple(v.name for v in depends)
			
		v = gdbsess.var_create(e, sync = True)
		self.gdbsess.add_var_watcher(v, self, toplevel)
		return WrappedWatch(self.gdbsess, v)
	
	def _pyval(self):
		pass
	
	def _children(self):
		pass
	
	def onUpdate(self, var, upd):
		self.children = self._children()
		self.pyval = self._pyval()


class StdVectorWatch(FilteredWatch):
	def __init__(self, gdbsess, var):
		FilteredWatch.__init__(gdbsess, var)
		self.array = self.register_watch(
			"(%s)._M_impl._M_start[0]@((%s)._M_impl._M_finish - (%s)._M_impl._M_start)", 
			(self.var, self.var, self.var), toplevel = False)
	
	def _pyval(self):
		idx = sorted( int(k) for k in self.array.__children.keys() )
		return [ self.array[k].__value for k in idx ]

	def _children(self):
		return self.array.__children()

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
