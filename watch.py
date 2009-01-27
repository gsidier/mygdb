import pygdb
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
class AbstractVar(object):

	type = property(lambda self: self._type())
	value = property(lambda self: self._value())
	name = property(lambda self: self._name())
	expr = property(lambda self: self._expr())
	children = property(lambda self: self._children())
	numchild = property(lambda self: self._numchild())
	in_scope = property(lambda self: self._in_scope())
	path_expr = property(lambda self: self._path_expr())
	

	def __init__(self, gdbsess, var):
		self.gdbsess = gdbsess
		self.var = var
	
	def _children(self):
		if self.var.children is None:
			self.gdbsess.var_list_children(self.var.name, sync = True)
		
		if self.var.children is None: # still
			raise Exception, "Var get children failed."

		return dict( (k, self._wrap(v)) for k, v in self.var.children )
	
	def __getitem__(self, idx):
		return self.children[str(idx)]
	
	def _type(self):
		return self.var.type
	
	def _name(self):
		return self.var.name
		
	def _expr(self):
		return self.var.expr
	
	def _value(self):
		return self.var.value
	
	def _numchild(self):
		return self.var.numchild
	
	def _in_scope(self):
		return self.var._in_scope
	
	def _wrap(self, var):
		return type(self)(self.gdbsess, var)
	
	def _path_expr(self):
		return self.gdbsess.var_path_expr(self.var.name, sync = True)
	
	def register_watch(self, expr, depends):
		e = expr % tuple(v.var_path for v in depends)
			
		v = self.gdbsess.var_create(e, sync = True)
		self.gdbsess.add_var_watcher(v, self)
		return self._wrap(v)

	def onUpdate(self, var, upd):
		pass

class StdVectorWatch(AbstractVar):
	def __init__(self, gdbsess, var):
		AbstractVar.__init__(self, gdbsess, var)
		self.arrlen = self.register_watch(
			"(%s)._M_impl._M_finish - (%s)._M_impl._M_start",
			(self.var, self.var))
		self.array = self.register_watch(
			"(%s)._M_impl._M_start[0]@(%s)", 
			(self.var, self.arrlen))
	
	def _children(self):
		return self.array.children
		

