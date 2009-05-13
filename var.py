from lazy import lazy

class Var(object):
	
	path_expr = lazy(lambda self: self._path_expr())
	children = lazy(lambda self: self._children())
	
	def __init__(self, gdbsess, name, expr, type, value, numchild, in_scope):
		self.gdbsess = gdbsess
		self.name = name
		self.expr = expr
		self.type = type
		self.value = value
		self.numchild = int(numchild)
		self.in_scope = in_scope
		_children_computing = False
		
	def __repr__(self):
		return "Var(name=%s, expr=%s, type=%s, value=%s, numchild=%s)" % (self.name, self.expr, self.type, self.value, self.numchild)

	def __str__(self):
		return self.__repr__()
	
	def _path_expr(self):
		return self.gdbsess.var_path_expr(self.name, sync = True)
	
	def _children(self):
		if self._children_computing:
			return {}
		
		if self.numchild == 0:
			return {}
		
		self._children_computing = True
		res = self.gdbsess.var_list_children(self.name, sync = True)
		self._children_computing = False
		return res

