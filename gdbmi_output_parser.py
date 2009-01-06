from recparse import *

# ========== LEXER ==========

ESC_SEQ    = (Literal('\\') + AnyToken()).set_result(lambda tok, res: eval("'%s%s'" % (res[0], res[1])))

lex = Lexer(
	WHITESPACE = (Literal(' ') | Literal("\t")).ignore(),
	EQ         = Literal('='),
	STAR       = Literal('*'),
	PLUS       = Literal('+'),
	TILDE      = Literal('~'),
	AT         = Literal('@'),
	HAT        = Literal('^'),
	AMPERSAND  = Literal('&'),
	LCURLY     = Literal('{'),
	RCURLY     = Literal('}'),
	LSQUARE    = Literal('['),
	RSQUARE    = Literal(']'),
	COMMA      = Literal(','),
	ESC_SEQ    = ESC_SEQ,
	CSTR       = (Literal('"') + (ExcludeChars('"\\') | ESC_SEQ) * (0,) + Literal('"')).set_result(lambda tok,res: ''.join(res[1])),
	IDENT      = Word('-_abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ'),
	TOKEN      = Word('0123456789'),
	STOP       = Literal('(gdb)'),
	EOL        = CharacterClass('\n\r') * (1,)
)

# ========== RESULT STRUCTURES ==========
class struct(object):
	def __init__(self, dikt):
		self._data = dict(dikt)
		self.__dict__.update(dict(dikt))
	def __repr__(self):
		return "struct(%s)" % repr(self._data)
	def __getitem__(self, i):
		return self._data[i]
	def get(self, name, default = None):
		return self._data.get(name, default)

# ========== PARSER ==========

value = Forward()

result      = lex.IDENT + lex.EQ + value                                  >= (lambda tok,val: (val[0], val[2]))
result_list = DelimitedList(result, lex.COMMA)
results     = DelimitedList(result, lex.COMMA)                            >= (lambda tok,val: struct(dict(val)))
values      = DelimitedList(value, lex.COMMA)
tuple_      = lex.LCURLY + results + lex.RCURLY                           >= (lambda tok,val: val[1])
list_       = lex.LSQUARE + Optional(values | result_list) + lex.RSQUARE  >= (lambda tok,val: val[1])
value      << (lex.CSTR | tuple_ | list_)
async_class = lex.IDENT
optional_results = Optional((lex.COMMA + results)[1])
async_output = async_class + optional_results
result_class = lex.IDENT

gdbout      = lambda V: (lex.TILDE + lex.CSTR)[1]     >= (lambda tok,val: V.onGdbOutput(val))
targetout   = lambda V: (lex.AT + lex.CSTR)[1]        >= (lambda tok,val: V.onTargetOutput(val))
gdberr      = lambda V: (lex.AMPERSAND + lex.CSTR)[1] >= (lambda tok,val: V.onGdbErr(val))

notify_msg  = lambda V: (Optional(lex.TOKEN) + lex.EQ + async_output)    >= (lambda tok,val: V.onNotifyAsyncOutput(val[0], *val[2]))
exec_msg    = lambda V: (Optional(lex.TOKEN) + lex.STAR + async_output)  >= (lambda tok,val: V.onExecAsyncOutput(val[0], *val[2]))
status_msg  = lambda V: (Optional(lex.TOKEN) + lex.PLUS + async_output)  >= (lambda tok,val: V.onStatusAsyncOutput(val[0], *val[2]))

result_rec  = lambda V: (Optional(lex.TOKEN) + lex.HAT + result_class + optional_results) >= (lambda tok,val: V.onResultRecord(val[0], val[2], val[3]))

stream_rec  = lambda V: (gdbout(V) | targetout(V) | gdberr(V))
async_rec   = lambda V: (exec_msg(V) | notify_msg(V) | status_msg(V))

gdbmi_output = lambda V: (async_rec(V) | stream_rec(V) | result_rec(V) | lex.STOP) + lex.EOL

if __name__ == '__main__':

	class Visitor(object):
		def __getattr__(self, name):
			def handler(*args):
				print "GOT: %s %s" % (name, repr(args))
			return handler

	v = Visitor()

	# inputstr = '{x = "13" , y = ["1"  "2" "foo"] }'
	# inputstr = 'asyncclass , x = { a = "42", pi = "3.14" }, y = "False"'
	inputstr = '& "Foobar Error!"\n'
	inputstr = '1000003*stopped,reason="breakpoint-hit",bkptno="1",thread-id="0",frame={addr="0x08048428",func="main",args=[{name="argc",value="1"},{name="argv",value="0xbfbb3cb4"}],file="hello.c",fullname="/home/greg/code/mygdb/hello.c",line="16"}\n'
	chars = TokenStream(iter(inputstr))

	tokens = lex.lex(chars)
	toks = list(tokens.unconsumed)
	print toks
	tokstream = TokenStream(iter(toks))

	success, result = gdbmi_output(v).try_parse(tokstream)
	print success
	if success:
		print result.tokens
		print result.value

