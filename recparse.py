from __future__ import with_statement
from collections import deque
from StringIO import StringIO

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
		if self.result_func is None:
			self.result_func = func
		else:
			prev_func = self.result_func
			self.result_func = lambda tok,val: func(tok, prev_func(tok, val))
		return self

	def ignore(self):
		self.result_func = lambda toks, val: None
		return self

	def __ge__(self, func):
		"""
		Return a *new* parser matching the same inputs, but with the provided result func.
		"""
		return Group(self).set_result(func)

	def __or__(self, other):
		"""
		Build a parser that matches "self _or_ other".
		"""
		return Disj(self, other)

	def __add__(self, other):
		"""
		Return a parser that matches "self _then_ other".
		"""
		return Seq(self, other)

	def __mul__(self, count):
		"""
		If P is a parser, then:
			P * n : matches n times P
			P * (n,) : matches at least n times P
			P * (n,m) : matches at least n and at most m times P
		"""
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

	def __getitem__(self, *key):
		"""
		Indexing a parser will select some values from the result.
		The following indexing schemes are allowed:
			P[i] : returns just token #i 
			P[slice] : selects the values indexed by the slice
			P[iterable] : selects the values indexed by the iterable
			P[k1, ...] : selects the concatenation of the P[k_j]
		"""
		if len(key) == 1 and isinstance(key[0], int):
			return self.set_result(lambda tok,val: val[key[0]])
		else:
			def build_result(tok,val):
				res = []
				for k in key:
					if hasattr(k, '__iter__'):
						res += [ val[i] for i in k ]
					elif isinstance(k, slice):
						res += val[k]
					else:
						res.append(val[k])
			return self.set_result(build_result)

class Forward(Parser):

	parser = None

	def __lshift__(self, parser):
		self.parser = parser
	
	def set_result(self, func):
		self.parser.set_result(func)

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

def AnyToken():
	return TokenPredicate(lambda c: True)

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
		if self.result_func is not None:
			return Parser.__add__(self, other)
		else:
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

def Optional(inner, default_val = None):
	return Repeat(inner, 0, 1).set_result(lambda tok,val: default_val if len(val) == 0 else val[0])

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

def ascrange(start, end):
	return ''.join([ chr(i) for i in range(ord(start), ord(end)+1) ])

def Word(string):
	return (CharacterClass(string) * (1,)).set_result(lambda tok,res: ''.join(res))

class Lexer(object):

	def __init__(self, **tokens):
		def token_matcher(name):
			return TokenPredicate(lambda tok: tok[0] == name).set_result(lambda tok,val: val[1])
		for tokname, tokparser in tokens.iteritems():
			match_token = token_matcher(tokname)
			setattr(self, tokname, match_token)
		# Keep literals apart from the rest -- they are always tried first
		self.tokens = (
			  [ (tokname, tokparser) for (tokname, tokparser) in tokens.iteritems() if isinstance(tokparser, Literal) ] 
			+ [ (tokname, tokparser) for (tokname, tokparser) in tokens.iteritems() if not isinstance(tokparser, Literal) ])
		
	def lex(self, stream):
		def gen():
			while True:
				for tokname, tokparser in self.tokens:
					success, result = tokparser.try_parse(stream)
					if success:
						break
				if not success:
					break
				if result.value is not None:
					yield(tokname, result.value)
			if not stream.eos():
				raise SyntaxError("")
		return TokenStream(gen())

class Group(Parser):
	def __init__(self, base):
		self.base = base
		self.result_func = base.result_func
	def _try_parse(self, stream):
		return self.base._try_parse(stream)
	

def DelimitedList(parser, sep):
	return (Group(parser) + (sep + Group(parser)) * (0,)).set_result(lambda tok,val: [val[0]] + [ val[1][i][1] for i in xrange(len(val[1])) ])

def CharRange(a, z):
	return CharacterClass(''.join(chr(i) for i in xrange(ord(a), ord(z) + 1)))


def flatten_chars(toks, value):
	buf = StringIO()
	def rec(val):
		if isinstance(val, str):
			buf.write(val)
		else:
			for item in val:
				rec(item)
	rec(value)
	return buf.getvalue()

ALPHA_LOWER = CharRange('a', 'z')
ALPHA_UPPER = CharRange('A', 'Z')
ALPHA = ALPHA_LOWER | ALPHA_UPPER
DIGIT = CharRange('0', '9')
ALPHANUM = ALPHA | DIGIT

if __name__ == '__main__':
	pass

