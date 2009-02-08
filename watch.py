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
		if self.var.numchild == 0:
			return {}
		
		if self.var.children is None:
			self.gdbsess.var_list_children(self.var.name, sync = True)
		
		if self.var.children is None: # still
			raise Exception, "Var get children failed."

		return dict( (k, self.wrap(v)) for k, v in self.var.children.iteritems() )
	
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
		return self.var.in_scope
	
	@classmethod
	def _wrap(cls, sess, var):
		return AbstractVar(sess, var)
	
	def wrap(self, var):
		return self._wrap(self.gdbsess, var)
	
	def _path_expr(self):
		return self.gdbsess.var_path_expr(self.var.name, sync = True)
	
	def register_watch(self, expr, depends):
		e = expr % tuple(v.path_expr for v in depends)
			
		v = self.gdbsess.var_create(e, sync = True)
		self.gdbsess.add_var_watcher(v, self, toplevel = False)
		return self.wrap(v)

	def onUpdate(self, var, upd):
		pass

	def __str__(self):
		return "(%s) %s: %s" % (type(self).__name__, self.expr, self.value)

	def __repr__(self):
		return self.__str__()

class FilteredWatch(AbstractVar):
	@classmethod
	def _wrap(cls, sess, var):
		if var.type is not None:
			if var.type.startswith('std::basic_string<') and var.type[-1] == '>':
				return StdStringWatch(sess, var)
			elif var.type.startswith('std::vector<') and var.type[-1] == '>':
				return StdVectorWatch(sess, var)
		return FilteredWatch(sess, var)


class StdVectorWatch(FilteredWatch):
	def __init__(self, gdbsess, var):
		FilteredWatch.__init__(self, gdbsess, var)
		self.arrlen = self.register_watch(
			"(%s)._M_impl._M_finish - (%s)._M_impl._M_start",
			(self.var, self.var))
		self.array = self.register_watch(
			"(%s)._M_impl._M_start[0]@(%s)", 
			(self.var, self.arrlen))
	
	def _children(self):
		return self.array.children
		
class StdStringWatch(FilteredWatch):
	def __init__(self, gdbsess, var):
		FilteredWatch.__init__(self, gdbsess, var)
		self.chars = self.register_watch(
			"(%s)._M_dataplus._M_p",
			(self.var,)
		)
	def _value(self):
		return self.chars.value
	def _numchild(self):
		return 0
	def _children(self):
		return {}


