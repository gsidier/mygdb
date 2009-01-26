import pygdb
from recparse import *

class PathParser(object):
	"""
	The Var Path Syntax described below describes var path parsers.
	
	A var path is of the form :
		(ID | NUM) '.' (ID | NUM) '.' (ID | NUM) ...
	
	This is first "tokenized" by splitting the input string.

	Then the token stream is passed to the parser, which returns a result having:
	
		* result.list : the list of matched tokens
		* result.dict : the dict of name -> value named tokens matched
	
	as specified by the VarPathSyntax (see below).
	
	"""	
	class Result(object):
		pass
	
class VarPathSyntax(object):

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

		named_atom
		=	atom ('[' ID ']')?

		path
		=	named_atom ('.' path)?
	"""

	lex = Lexer(
		ID        = ( ALPHA | Literal('_') ) + ( ALPHANUM | Literal('_') ) * (0,) >= flatten_chars,
		NUM       = DIGIT * (1,)         >= flatten_chars, 
		VAR       = Literal('%') + ALPHA >= (lambda toks, val: val[1]),
		OPT       = Literal('?'),
		STAR      = Literal('*'),
		PLUS      = Literal('+'),
		LCURLY    = Literal('{'),
		RCURLY    = Literal('}'),
		COMMA     = Literal(','),
		LPAREN    = Literal('('),
		RPAREN    = Literal(')'),
		DOT       = Literal('.'),
		LSQUARE   = Literal('['),
		RSQUARE   = Literal(']')
	)


	multspec = (
			lex.OPT    .set_result (lambda toks, val: (0,1))
		|	lex.STAR   .set_result (lambda toks, val: (0,))
		|	lex.PLUS   .set_result (lambda toks, val: (1,))
		|	(lex.LCURLY + Optional(lex.NUM) + Optional(lex.COMMA) + Optional(lex.NUM) + lex.RCURLY) .set_result (
				lambda toks, val: (None if val[1] is None else int(val[1]), None if val[3] is None else int(val[3])))
	)

	path = Forward()

	atom = (
			lex.ID
		|	lex.NUM
		|	lex.VAR
		|	lex.LPAREN + path + lex.RPAREN + Optional(multspec)
	)

	named_atom = atom + Optional( lex.LSQUARE + lex.ID + lex.RSQUARE >= (lambda toks, val: val[1]))

	path << DelimitedList(named_atom, lex.DOT)
	
if __name__ == '__main__':
	inputstr = 'foo.123.(zob.baz.%d[index])+'
	chars = TokenStream(iter(inputstr))

	tokens = VarPathSyntax.lex.lex(chars)
	toks = list(tokens.unconsumed)
	print toks
	tokstream = TokenStream(iter(toks))

	success, result = VarPathSyntax.path.try_parse(tokstream)
	print success
	if success:
		print result.tokens
		print result.value
