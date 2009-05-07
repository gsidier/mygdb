from watch import AbstractVar

class PyWatch(AbstractVar):
	
	pyval = property(lambda self: self._pyval())
	
	@classmethod
	def _wrap(cls, sess, var):
		if var.type is not None:
			if var.type.startswith('std::basic_string<') and var.type[-1] == '>':
				return StdStringWatch(sess, var)
			elif var.type.startswith('std::pair<') and var.type[-1] == '>':
				return StdPairWatch(sess, var)
			elif var.type.startswith('std::vector<') and var.type[-1] == '>':
				return StdVectorWatch(sess, var)
			elif var.type == 'char *':
				return CharPtrWatch(sess, var)
			elif var.type == 'int':
				return IntWatch(sess, var)
			elif var.type[-1] == '*':
				return PtrWatch(sess, var)

		return PyWatch(sess, var)
	
	def _pyval(self):
		return self.value
	
	def eval(self, expr, subs = ()):
		var = self.register_watch(expr, subs)
		return var.value

class PtrWatch(object):
	def __init__(self, gdbsess, var):
		PyWatch.__init__(self, gdbsess, var)
	def _pyval(self):
		s = self.value
		addr = int(s[s.rfind('x')+1:], 16)
		type = s[s.find('(')+1:s.rfind(')')]
		return CPtr(addr, type)

class CPtr(object):
	def __init__(self, addr, type):
		self.addr = addr
		self.type = type
	def __str__(self):
		return "(%s) %s" % (self.type, hex(self.addr))
	def __repr__(self):
		return "CPointer(%s, %d)" % (repr(self.type), repr(addr))

class IntWatch(PyWatch):
	def __init__(self, gdbsess, var):
		PyWatch.__init__(self, gdbsess, var)
	def _pyval(self):
		return int(self.value)

class StdPairWatch(PyWatch):
	def __init__(self, gdbsess, var):
		PyWatch.__init__(self, gdbsess, var)
		self.first = self.register_watch(
			"(%s).first",
			(self.var,)
		)
		self.second = self.register_watch(
			"(%s).second",
			(self.var,)
		)
	def _pyval(self):
		return (self.first.pyval, self.second.pyval)

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
		return s[ beg+1:end ]

class CharPtrWatch(PyWatch):
	def __init__(self, gdbsess, var):
		PyWatch.__init__(self, gdbsess, var)
	def _numchild(self):
		return 0
	def _children(self):
		return {}
	
	def _pyval(self):
		s = self.value
		beg = s.find('"')
		end = s.rfind('"')
		return s[ beg+1:end ]

class StdMapWatch(PyWatch):
	def __init__(self, gdbsess, var):
		PyWatch.__init__(self, gdbsess, var)
		self.root = self.register_watch(
			"(%s)._M_t._M_impl._M_header",
			(self.var,))
	
	def _pyval(self):
		res = {}
		curr = self.register_watch("&(%s)", (self.root,))
		
		def rec(curr):
			ptr_p = self.register_watch(
				"(%s)._M_parent",
				(curr,))
			if ptr_p.pyval.addr != 0: # data node
				casted = self.register_watch(
					"('std::_Rb_tree_node<std::pair<%s, %s> >' *)(%s)" % 
			
			ptr_r = self.register_watch(
				"(%s)._M_right",
				(curr,))
			ptr_l = self.register_watch(
				"(%s)._M_left", 
				(curr,))
			if ptr_r.pyval.addr != curr.pyval.addr:
				rec

