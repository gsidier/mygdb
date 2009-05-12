from watch import AbstractVar
from cpptypes import parse_cpptype

class PyWatch(AbstractVar):
	
	pyval = property(lambda self: self._pyval())
	
	@classmethod
	def _wrap(cls, sess, var):
		if var.type is not None:
			if var.type == 'char' or var.type == 'const char':
				return CharWatch(sess, var)
			elif var.type == 'int' or var.type == 'const int' or var.type == 'size_t' or var.type == 'const size_t':
				return IntWatch(sess, var)
			elif (var.type.startswith('std::basic_string<') and var.type[-1] == '>') or var.type == 'std::string' or var.type == 'string' :
				return StdStringWatch(sess, var)
			elif var.type.startswith('std::pair<') and var.type[-1] == '>':
				return StdPairWatch(sess, var)
			elif var.type.startswith('std::vector<') and var.type[-1] == '>':
				return StdVectorWatch(sess, var)
			elif var.type.startswith('std::map<') and var.type[-1] == '>':
				return StdMapWatch(sess, var)
			elif var.type == 'char *' or var.type == 'const char *' or var.type == 'char const *':
				return CharPtrWatch(sess, var)
			elif var.type[-1] == '*':
				return PtrWatch(sess, var)

		return PyWatch(sess, var)
	
	def _pyval(self):
		return self.value
	
	def eval(self, expr, subs = ()):
		var = self.register_watch(expr, subs)
		return var.pyval

class CppChar(object):
	
	char = property(lambda self: chr(self.num))

	def __init__(self, num):
		self.num = num % 256
	def __str__(self):
		return self.char
	def __repr__(self):
		return "'%s' (%d)" % (self.char, self.num)

class CharWatch(PyWatch):
	def __init__(self, gdbsess, var):
		PyWatch.__init__(self, gdbsess, var)
	def _pyval(self):
		return CppChar(int(self.value.split(" ")[0]))

class CppPtr(object):
	def __init__(self, addr, type):
		self.addr = addr
		self.type = type
	def __str__(self):
		return "(%s) %s" % (self.type, hex(self.addr))
	def __repr__(self):
		return "CPointer(%s, %d)" % (repr(self.type), repr(addr))

class PtrWatch(PyWatch):
	def __init__(self, gdbsess, var):
		PyWatch.__init__(self, gdbsess, var)
	def _pyval(self):
		s = self.value
		addr = int(s[s.rfind('x')+1:], 16)
		type = s[s.find('(')+1:s.rfind(')')]
		return CppPtr(addr, type)

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
		self.ptr_root = self.register_watch(
			"(%s)._M_t._M_impl._M_header._M_parent",
			(self.var,))
		self.cpptype = parse_cpptype(self.type).value
	
	def _pyval(self):
		res = {}
	
		pair_type = "std::pair< const %s, %s >" % (
			self.cpptype.local.template_args[0],
			self.cpptype.local.template_args[1])
	
		def rec(curr):
			if curr.pyval.addr == 0:
				return
			
			casted = self.register_watch(
				"('std::_Rb_tree_node< " + pair_type + " >' *)(%s)",
				(curr,))
			key = self.eval("(%s)._M_value_field.first", (casted,))
			value = self.eval("(%s)._M_value_field.second", (casted,))
			res[key] = value
			
			ptr_r = self.register_watch(
				"(%s)._M_right",
				(curr,))
			ptr_l = self.register_watch(
				"(%s)._M_left", 
				(curr,))
			rec(ptr_r)
			rec(ptr_l)
			
		rec(self.ptr_root)
		return res

