from watch import AbstractVar

class PyWatch(AbstractVar):
	
	pyval = property(lambda self: self._pyval())
	
	@classmethod
	def _wrap(cls, sess, var):
		if var.type is not None:
			if var.type.startswith('std::basic_string<') and var.type[-1] == '>':
				return StdStringWatch(sess, var)
			elif var.type.startswith('std::vector<') and var.type[-1] == '>':
				return StdVectorWatch(sess, var)
		return PyWatch(sess, var)
	
	def _pyval(self):
		return self.value

class StdVectorWatch(PyWatch):
	def __init__(self, gdbsess, var):
		PyWatch.__init__(self, gdbsess, var)
		self.arrlen = self.register_watch(
			"(%s)._M_impl._M_finish - (%s)._M_impl._M_start",
			(self.var, self.var))
		self.array = self.register_watch(
			"(%s)._M_impl._M_start[0]@(%s)", 
			(self.var, self.arrlen))
	
	def _children(self):
		return self.array.children
	
	def _pyval(self):
		kv = sorted( [ (int(k),ch.pyval) for (k,ch) in self.children.iteritems() ], key = lambda (k,v): k )
		return [ v for (k,v) in kv ]
		
class StdStringWatch(PyWatch):
	def __init__(self, gdbsess, var):
		PyWatch.__init__(self, gdbsess, var)
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
	
	def _pyval(self):
		s = self.chars.value
		beg = s.find('"')
		end = s.rfind('"')
		return s[ beg:end+1 ]

