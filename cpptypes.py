from recparse import *
"""
Grossly simplified parser for C++ type specifications, for parsing
type info as output by gdb.
"""

# ========== LEXER ==========

ALPHA = CharacterClass('_' + ascrange('a','z') + ascrange('A', 'Z'))
ALPHANUM = CharacterClass('_' + ascrange('a','z') + ascrange('A', 'Z') + ascrange('0','9'))

lex = Lexer(
	WHITESPACE = (Literal(' ') | Literal("\t")).ignore(),
	
	CONST      = Literal('const'),
	VOLATILE   = Literal('volatile'),
	STRUCT     = Literal('struct'),
	CLASS      = Literal('class'),
	UNION      = Literal('union'),
	LONG       = Literal('long'),
	SHORT      = Literal('short'),
	UNSIGNED   = Literal('unsigned'),
	SIGNED     = Literal('signed'),

	STAR       = Literal('*'),
	AMPERSAND  = Literal('&'),
	IDENT      = (ALPHA + ALPHANUM * (0,)).set_result(flatten_chars),
	COMMA      = Literal(','),
	LPOINTY    = Literal('<'),
	RPOINTY    = Literal('>'),
	SCOPE      = Literal('::'),
)

# ========== TYPE OBJECT ==========

class CppScope(object):
	
	def __init__(self, name, template_args = None):
		self.name = name
		self.template_args = template_args

	def __repr__(self):
		return "CppScope(name=%s, template_args=%s)" % (repr(self.name), repr(self.template_args))
	
	def __str__(self):
		if self.template_args is None:
			return self.name
		else:
			return "%s< %s >" % (
				self.name,
				", ".join([ str(t) for t in self.template_args]))
	
class CppType(object):
	
	scope = ()
	
	def __init__(self, local, scope, specifiers, declarator_ops):
		self.local = local
		self.scope = scope
		self.specifiers = specifiers
		self.declarator_ops = declarator_ops

	def __repr__(self):
		return "CppType(local=%s, scope=%s, specifiers=%s, declarator_ops=%s)" % (repr(self.local), repr(self.scope), repr(self.specifiers), repr(self.declarator_ops))

	def __str__(self):
		return ("%s %s %s" % (
			" ".join([ str(spec) for spec in self.specifiers ]),
			"::".join([ str(s) for s in self.scope] + [str(self.local)]),
			" ".join([ str(m) for m in self.declarator_ops]))).strip()

# ========== PARSER ==========

type = Forward() 

template_scope    = lex.IDENT + lex.LPOINTY + DelimitedList(type, lex.COMMA) + lex.RPOINTY   >= (lambda tok,val: CppScope(val[0], val[2]))
nontemplate_scope = lex.IDENT                                                                >= (lambda tok, val: CppScope(val))
scope             = template_scope | nontemplate_scope
scoped_type       = Optional(lex.SCOPE) + DelimitedList(scope, lex.SCOPE)                    >= (lambda tok,val: val[1])
cv_qualifier      = lex.CONST | lex.VOLATILE
specifier         = lex.SHORT | lex.LONG | lex.SIGNED | lex.UNSIGNED
ptr_operator      = (lex.STAR | lex.AMPERSAND) + cv_qualifier * (0,)                       >= (lambda tok,val: [val[0]] + val[1])

type << (cv_qualifier | specifier) * (0,) + scoped_type + ptr_operator * (0,)
type.set_result(lambda tok,val: CppType(val[1][-1], val[1][:-1], val[0], sum(val[2], []) ))


def parse_cpptype(inputstr):
	
	chars = TokenStream(iter(inputstr))
	tokens = lex.lex(chars)
	toks = list(tokens.unconsumed)
	tokstream = TokenStream(iter(toks))

	success, result = type.try_parse(tokstream)
	
	if success:
		return result
	else:
		raise SyntaxError
	
if __name__ == '__main__':
	
	import sys
	
	if len(sys.argv) > 1:
		inputstr = ' '.join(sys.argv[1:])
	else:
		inputstr = "std::map<std::basic_string<char, std::char_traits<char>, std::allocator<char> >, int, std::less<std::basic_string<char, std::char_traits<char>, std::allocator<char> > >, std::allocator<std::pair<const std::basic_string<char, std::char_traits<char>, std::allocator<char> >, int> > >"
	print inputstr
	
	result = parse_cpptype(inputstr)
	
	print result.tokens
	print
	print result.value
	print
	print repr(result.value)


