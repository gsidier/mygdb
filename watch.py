import pygdb
from recparse import *


"""
var path syntax:


	ID = [a-zA-Z_0-9]+
	VAR = '%' [a-zA-Z]

	multspec
	=	'?'
	|	'*'
	|	'+'
	|	'{' num? ','? num? '}'

	atom 
	= 	ID
	|	VAR
	|	'(' path ')' multspec?

	path
	=	atom ('.' path)?

"""

lex = Lexer(
	ID        = ( ALPHA | Literal('_') ) + ( ALPHANUM | Literal('_') ) * (0,),
	NUM       = DIGIT * (1,), 
	VAR       = Literal('%') + ALPHA,
	OPT       = Literal('?'),
	STAR      = Literal('*'),
	PLUS      = Literal('+'),
	LCURLY    = Literal('{'),
	RCURLY    = Literal('}'),
	COMMA     = Literal(','),
	LPAREN    = Literal('('),
	RPAREN    = Literal(')'),
	DOT       = Literal('.')
)


multspec = (
		lex.OPT
	|	lex.STAR
	|	lex.PLUS
	|	lex.LCURLY + Optional(lex.NUM) + Optional(lex.COMMA) + Optional(lex.NUM) + lex.RCURLY
)

path = Forward()

atom = (
		lex.ID
	|	lex.VAR
	|	lex.LPAREN + path + lex.RPAREN + Optional(multspec)
)

path << DelimitedList(atom, lex.DOT)

class FilteredWatch(pygdb.VarWatcher):
	def __init__(self, gdbsess, var):
		VarWatcher.__init__(self, gdbsess, var, 'default')
	
if __name__ == '__main__':
	inputstr = 'foo.(zob.baz.%d)+'
	chars = TokenStream(iter(inputstr))

	tokens = lex.lex(chars)
	toks = list(tokens.unconsumed)
	print toks
	tokstream = TokenStream(iter(toks))

	success, result = path.try_parse(tokstream)
	print success
	if success:
		print result.tokens
		print result.value

