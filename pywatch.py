from watch import AbstractVar
from cpptypes import parse_cpptype

class PyWatch(AbstractVar):
	
	pyval = property(lambda self: self._pyval())
	
	@classmethod
	def _wrap(cls, sess, var):
		if var.type is not None:
			# strip var type of irrelevant qualifiers.
			T = parse_cpptype(var.type).value
			T.specifiers = [ spec for spec in T.specifiers if spec not in ('const', 'volatile', 'unsigned', 'signed') ]
			T.declarator_ops = [ op for op in T.declarator_ops if op not in ('const', 'volatile') ]
			type = str(T)
			if type == 'char':
				return CharWatch(sess, var)
			elif type in ('int', 'long', 'long int', 'short', 'short int', 'size_t'):
				return IntWatch(sess, var)
			elif (type.startswith('std::basic_string<') and type[-1] == '>') or type in ('std::string', 'string'):
				return StdStringWatch(sess, var)
			elif type.startswith('std::pair<') and type[-1] == '>':
				return StdPairWatch(sess, var)
			elif type.startswith('std::vector<') and type[-1] == '>':
				return StdVectorWatch(sess, var)
			elif type.startswith('std::map<') and type[-1] == '>':
				return StdMapWatch(sess, var)
			elif type == 'char *':
				return CharPtrWatch(sess, var)
			elif type[-1] == '*':
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
	
		def rec(curr, curr_expr):
			if curr.pyval.addr == 0:
				return
			
			casted_expr = "('std::_Rb_tree_node< " + pair_type + " >' *)(%s)" % curr_expr
			key = self.eval("(%s)._M_value_field.first" % casted_expr)
			value = self.eval("(%s)._M_value_field.second" % casted_expr)
			res[key] = value
			
			ptr_r_expr = "%s._M_right" % curr_expr
			ptr_r = self.register_watch(ptr_r_expr)
			ptr_l_expr = "%s._M_left" % curr_expr
			ptr_l = self.register_watch(ptr_l_expr)

			rec(ptr_r, ptr_r_expr)
			rec(ptr_l, ptr_l_expr)
			
		rec(self.ptr_root, self.ptr_root.path_expr)
		return res

