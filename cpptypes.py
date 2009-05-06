from recparse import *
"""
Grossly simplified parser for C++ type specifications, for parsing
type info output by gdb.
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

	STAR       = Literal('*'),
	AMPERSAND  = Literal('&'),
	IDENT      = ALPHA + ALPHANUM * (0,),
	COMMA      = Literal(','),
	LPOINTY    = Literal('<'),
	RPOINTY    = Literal('>'),
	SCOPE      = Literal('::'),
)

# ========== PARSER ==========

type = Forward()

unscoped_template = lex.IDENT + lex.LPOINTY + DelimitedList(type, lex.COMMA) + lex.RPOINTY

scope = (
	  unscoped_template 
	| lex.IDENT
)

scoped_type = Optional(lex.SCOPE) + DelimitedList(scope, lex.SCOPE)

cv_qualifier = lex.CONST | lex.VOLATILE

ptr_operator = (
	  lex.STAR + cv_qualifier * (0,) 
	| lex.AMPERSAND 
)

type << cv_qualifier * (0,) + scoped_type + ptr_operator * (0,)

if __name__ == '__main__':
	
	inputstr = "std::map<std::basic_string<char, std::char_traits<char>, std::allocator<char> >, int, std::less<std::basic_string<char, std::char_traits<char>, std::allocator<char> > >, std::allocator<std::pair<const std::basic_string<char, std::char_traits<char>, std::allocator<char> >, int> > >"

	chars = TokenStream(iter(inputstr))

	tokens = lex.lex(chars)
	toks = list(tokens.unconsumed)
	print tokens
	tokstream = TokenStream(iter(toks))
	
	success, result = type.try_parse(tokstream)
	print success
	if success:
		print result.tokens
		print result.value


