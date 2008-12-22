from __future__ import with_statement
from collections import deque

class TokenStream(object):
	def __init__(self, stream):
		self.unconsumed = stream
		self.extracted = deque()
		self.nconsumed = 0
		self.stopiter = False

	def eos(self):
		return self.stopiter and self.nconsumed == len(self.extracted)

	def savepoint(self):
		return self.nconsumed

	def backtrack(self, savepoint):
		self.nconsumed = savepoint

	def consume(self):
		if len(self.extracted) > self.nconsumed:
			tok = self.extracted[self.nconsumed]
		else:
			try:
				tok = self.unconsumed.next()
			except StopIteration:
				self.stopiter = True
			self.extracted.append(tok)
		self.nconsumed += 1
		return tok

class Backtracker(object):
	def __init__(self, stream):
		self.success = False
		self.stream = stream
		self.savepoint = stream.savepoint()
		
	def __enter__(self):
		return self

	def __exit__(self, errtype, errval, backtrace):
		if not self.success:
			self.stream.backtrack(self.savepoint)

class ParseResult(object):
	def __init__(self, tokens, value):
		self.tokens = tokens
		self.value = value
	def apply_func(self, func):
		self.value = func(self.tokens, self.value)

class Parser(object):

	result_func = None

	def try_parse(self, stream):
		with Backtracker(stream) as parse_state:
			success, result = self._try_parse(stream)
			parse_state.success = success
		if success and self.result_func is not None:
			result.apply_func(self.result_func)
		return success, result

	def _try_parse(self, stream):
		raise NotImplementedError

	def set_result(self, func):
		self.result_func = func
		return self

	def ignore(self):
		self.result_func = lambda toks, val: None
		return self

	def __or__(self, other):
		return Disj(self, other)

	def __add__(self, other):
		return Seq(self, other)

	def __mul__(self, count):
		if isinstance(count, tuple):
			if len(count) == 1:
				count = count[0]
				if count == 0:
					return Repeat(self)
				return Repeat(self, count)
			else:
				cmin, cmax = count
				return Repeat(self, cmin, cmax)
		else:
			return Seq(*([ self ] * count))

class Forward(Parser):

	parser = None

	def __lshift__(self, parser):
		self.parser = parser
	
	def _try_parse(self, stream):
		if self.parser is None:
			raise "Forgot to set forwarded parser expression."
		return self.parser.try_parse(stream)

class Terminal(Parser):

	def __init__(self, tok):
		self.tok = tok

	def _try_parse(self, stream):
		try:
			tok = stream.consume()
		except:
			return False, None
		if tok == self.tok:
			return True, ParseResult([tok], tok)
		else:
			return False, None

class TokenPredicate(Parser):
	def __init__(self, predicate):
		self.accept = predicate

	def _try_parse(self, stream):
		try:
			tok = stream.consume()
		except:
			return False, None
		if self.accept(tok):
			return True, ParseResult([tok], tok)
		else:
			return False, None

def CharacterClass(string):
	MATCH = set(string)
	return TokenPredicate(lambda c: c in MATCH)

def ExcludeChars(string):
	EXCLUDE = set(string)
	return TokenPredicate(lambda c: c not in EXCLUDE)

def Intersect(*tokenpreds):
	return TokenPredicate(lambda c: all ( P.accept(c) for P in  tokenpreds ))

class Disj(Parser):
	
	def __init__(self, *options):
		self.options = options

	def _try_parse(self, stream):
		success = False
		result = None
		for p in self.options:
			success, result = p.try_parse(stream)
			if success: 
				break
		return success, result

	def __or__(self, other):
		return Disj(*(self.options + (other,)))

class Seq(Parser):
	def __init__(self, *items):
		self.items = items

	def _try_parse(self, stream):
		res = []
		restoks = []
		success = True
		for p in self.items:
			success, result = p.try_parse(stream)
			if not success:
				break
			res.append(result.value)
			restoks.append(result.tokens)

		if not success:
			return False, None
		
		return True, ParseResult(restoks, res)

	def __add__(self, other):
		return Seq(*(self.items + (other,)))

class Repeat(Parser):
	def __init__(self, inner, min = None, max = None):
		self.inner = inner
		self.min = min
		self.max = max

	def _try_parse(self, stream):
		res = []
		restoks = []
		success = True
		count = 0
		while self.max is None or count < self.max:
			success, result = self.inner.try_parse(stream)
			if not success:
				break
			res.append(result.value)
			restoks.append(result.tokens)
			count += 1
		if self.min is not None and count < self.min:
			return False, None
		return True, ParseResult(restoks, res)

def Optional(inner):
	return Repeat(inner, 0, 1)

def ZeroOrMore(inner):
	return Repeat(inner)

def OneOrMore(inner):
	return Repeat(inner, 1)

class Literal(Seq):

	def __init__(self, literal):
		Seq.__init__(self, *[ Terminal(tok) for tok in literal ])
		self.literal = literal
	
	def _try_parse(self, stream):
		success, result = Seq._try_parse(self, stream)
		if success:
			result.value = ''.join(result.value)
		return success, result	

def Word(string):
	return CharacterClass(string) * (1,)

class Lexer(object):

	def __init__(self, *tokens):
		self.tokens = tokens

	def lex(self, stream):
		def gen():
			disj = Disj(*self.tokens)
			while True:
				success, result = disj.try_parse(stream)
				if not success:
					break
				if result.value is not None:
					yield(result.value)
			if not stream.eos():
				raise "Syntax Error"
		return TokenStream(gen())

if __name__ == '__main__':

	WHITESPACE = (Literal(" ") | Literal("\t")) * (1,)
	WHITESPACE.ignore()

	EQ      = Literal("=")
	CSTR    = Literal('"') + ExcludeChars('"') * (0,) + Literal('"')
	VAR     = Word("-abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ")
	LCURLY  = Literal("{")
	RCURLY  = Literal("}")
	LSQUARE = Literal("[")
	RSQUARE = Literal("]")

	lexer = Lexer(
		WHITESPACE,
		EQ,
		CSTR,
		VAR,
		LCURLY,
		RCURLY,
		LSQUARE,
		RSQUARE
	)

	string = '{x = "13" }'
	chars = TokenStream(iter(string))
	tokens = lexer.lex(chars)
	toks = list(tokens.unconsumed)

"""	
	value = Forward()
	
	result = VAR + EQ + value
	result_list = result * (1,)
	results = result * (0,)	
	values = value * (1,)
	tuple = LCURLY + results + RCURLY
	list_ = LSQUARE + Optional(values | result_list) + RSQUARE
	value << (CSTR | tuple | list_)

	toks = [ "{", "VAR", "=", '"bla"', "VAR", "=", "[", "VAR", "=", '"bla"', "]", "}" ]
	stream = TokenStream(iter(toks))
	success, result = value.try_parse(stream)
	print success
	print result
"""
