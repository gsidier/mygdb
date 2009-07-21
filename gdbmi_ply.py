import ply.lex as lex
import ply.yacc as yacc

# ########## LEXER ##########

tokens = [
	'EQ', 'STAR', 'PLUS', 'TILDE', 'AT', 'HAT', 'AMPERS',
	'LCURLY', 'RCURLY', 'LSQUARE', 'RSQUARE', 'COMMA', 'ESC_SEQ',
	'C_STR', 'IDENT', 'TOKEN', 'STOP', 'EOL'
]


t_EQ      = r'='
t_STAR    = r'\*'
t_PLUS    = r'\+'
t_TILDE   = r'\~'
t_AT      = r'@'
t_HAT     = r'\^'
t_AMPERS  = r'&'
t_LCURLY  = r'\{'
t_RCURLY  = r'\}'
t_LSQUARE = r'\['
t_RSQUARE = r'\]'
t_COMMA   = r','
t_ESC_SEQ = r'\.'
#def t_C_STR(t):
#	#r'"([^"\\]|\\.)*"'
#	t.value = t.value[1:-1]
t_C_STR   = r'"[^"]*"'
t_IDENT   = r'[a-zA-Z_-]+'
t_TOKEN   = r'[0-9]+'
t_STOP    = r'(gdb)'
t_EOL     = r'[\n\r]+'

t_ignore = " \t"

lex.lex()

# ########## PARSER ##########

class GdbMIParser:
	
	V = None
	tokens = tokens

	def __init__(self, visitor):
		self.V = visitor
	
	def build(self):
		self.parser = yacc.yacc(module = self, start = 'gdbmi_output')
	
	def p_optional_TOKEN_0(self, p):
		'optional_TOKEN : '
		p[0] = None
	def p_optional_TOKEN_1(self, p):
		'optional_TOKEN : TOKEN'
		p[0] = p[1]
	def p_optional_results_0(self, p):
		'optional_results : '
		p[0] = None
	def p_optional_results_1(self, p):
		'optional_results : results'
		p[0] = p[1]

	# Stream Records
	def p_gdbout(self, p):
		'gdbout : TILDE C_STR'
		p[0] = p[2]
		self.V.onGdbOutput(p[2])
	def p_targetout(self, p):
		'targetout : AT C_STR'
		p[0] = p[2]
		self.V.onTargetOutput(p[2])
	def p_gdberr(self, p):
		'gdberr : AMPERS C_STR'
		p[0] = p[2]
		self.V.onGdbErr(p[2])
	def p_stream_rec(self, p):
		"""stream_rec : gdbout
			      | targetout
			      | gdberr
		"""
		p[0] = p[1]

	# Async records
	def p_async_output1(self, p):
		'async_output : IDENT'
		p[0] = (p[1], [])
	def p_async_output2(self, p):
		'async_output : IDENT COMMA results'
		p[0] = (p[1], p[3])
	def p_notify_msg(self, p):
		'notify_msg : optional_TOKEN EQ async_output'
		p[0] = p[3]
		self.V.onNotifyAsyncOutput(p[1], *p[3])
	def p_exec_msg(self, p):
		'exec_msg : optional_TOKEN STAR async_output'
		p[0] = p[3]
		self.V.onExecAsyncOutput(p[1], *p[3])
	def p_status_msg(self, p):
		'status_msg : optional_TOKEN PLUS async_output'
		p[0] = p[3]
		self.V.onStatusAsyncOutput(p[1], *p[3])
	def p_async_rec(self, p):
		"""async_rec : notify_msg
			     | exec_msg
			     | status_msg
		"""
		p[0] = p[1]

	# Result Records
	def p_result(self, p):
		'result : IDENT EQ value'
		p[0] = (p[1], p[3])
	def p_results_1(self, p):
		'results : result'
		p[0] = [p[1]]
	def p_results_n(self, p):
		'results : result COMMA results'
		p[0] = [p[1]] + p[3] # TODO this has n^2 running time ...
	def p_values_1(self, p):
		'values : value'
		p[0] = [p[1]]
	def p_values_n(self, p):
		'values : value COMMA values'
		p[0] = [p[1]] + p[3] # TODO n^2 complextity
	def p_tuple(self, p):
		'tuple : LCURLY results RCURLY'
		p[0] = p[2]
	def p_list_void(self, p):
		'list : LSQUARE RSQUARE'
		p[0] = []
	def p_list_values(self, p):
		'list : LSQUARE values RSQUARE'
		p[0] = p[2]
	def p_list_results(self, p):
		'list : LSQUARE results RSQUARE '
		p[0] = p[2]
	def p_value(self, p):
		"""value : C_STR 
			 | tuple 
			 | list
		"""
		p[0] = p[1]
	def p_result_rec(self, p):
		'result_rec : optional_TOKEN HAT IDENT optional_results'
		self.V.onResultRecord(p[1], p[3], p[4])

	# Start Rule:
	def p_gdbmi_output(self, p):
		"""gdbmi_output : async_rec EOL
				| stream_rec EOL
				| result_rec EOL
				| STOP EOL
		"""
		p[0] = p[1]

#yacc.yacc(start = 'gdbmi_output', module = GdbMIParser)

if __name__ == '__main__':
	
	class Visitor(object):
		def __getattr__(self, name):
			def handler(*args):
				#print "GOT: %s %s" % (name, repr(args))
				pass
			return handler

	inputstr = '1000003*stopped,reason="breakpoint-hit",bkptno="1",thread-id="0",frame={addr="0x08048428",func="main",args=[{name="argc",value="1"},{name="argv",value="0xbfbb3cb4"}],file="hello.c",fullname="/some/path/to/hello.c",line="16"}\n'
	# p = yacc.parser
	# p.V = Visitor()
	p = GdbMIParser(Visitor())
	p.build()
	p.parser.parse(inputstr)
	
	from timeit import Timer
	
	timer = Timer(lambda: p.parser.parse(inputstr))
	print timer.timeit(number = 1000)

