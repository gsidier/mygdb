
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
t_C_STR   = r'"[^"]*"'
t_IDENT   = r'[a-zA-Z_-]+'
t_TOKEN   = r'[0-9]+'
t_STOP    = r'(gdb)'
t_EOL     = r'[\n\r]+'

t_ignore = " \t"

import ply.lex as lex
lex.lex()

# ########## PARSER ##########
def p_optional_TOKEN_0(p):
	'optional_TOKEN : '
	p[0] = None
def p_optional_TOKEN_1(p):
	'optional_TOKEN : TOKEN'
	p[0] = p[1]

# Stream Records
def p_gdbout(p):
	'gdbout : TILDE C_STR'
	print "GDB OUTPUT: ", p[2]
	p[0] = p[2]
def p_targetout(p):
	'targetout : AT C_STR'
	print "TARGET OUTPUT: ", p[2]
	p[0] = p[2]
def p_gdberr(p):
	'gdberr : AMPERS C_STR'
	print "GDB ERR: ", p[2]
	p[0] = p[2]
def p_stream_rec(p):
	"""stream_rec : gdbout
	              | targetout
	              | gdberr
	"""
	p[0] = p[1]

# Async records
def p_async_output1(p):
	'async_output : IDENT'
	p[0] = (p[1], [])
def p_async_output2(p):
	'async_output : IDENT results'
	p[0] = (p[1], p[2])
def p_notify_msg(p):
	'notify_msg : optional_TOKEN EQ async_output'
	print "Notify Msg:", p[3]
	p[0] = p[3]
def p_exec_msg(p):
	'exec_msg : optional_TOKEN STAR async_output'
	print "Exec Msg:", p[3]
	p[0] = p[3]
def p_status_msg(p):
	'status_msg : optional_TOKEN PLUS async_output'
	print "Status Msg:", p[3]
	p[0] = p[3]
def p_async_rec(p):
	"""async_rec : notify_msg
	             | exec_msg
	             | status_msg
	"""
	p[0] = p[1]

# Result Records
def p_result(p):
	'result : IDENT EQ value'
	p[0] = (p[1], p[3])
def p_results_1(p):
	'results : result'
	p[0] = [p[1]]
def p_results_n(p):
	'results : result COMMA results'
	p[0] = [p[1]] + p[3] # TODO this has n^2 running time ...
def p_values_1(p):
	'values : value'
	p[0] = [p[1]]
def p_values_n(p):
	'values : value COMMA values'
	p[0] = [p[1]] + p[3] # TODO n^2 complextity
def p_tuple(p):
	'tuple : LCURLY results RCURLY'
	p[0] = p[2]
def p_list_void(p):
	'list : LSQUARE RSQUARE'
	p[0] = []
def p_list_values(p):
	'list : LSQUARE values RSQUARE'
	p[0] = p[2]
def p_list_results(p):
	'list : LSQUARE results RSQUARE '
	p[0] = p[2]
def p_value(p):
	"""value : C_STR 
	         | tuple 
	         | list
	"""
	p[0] = p[1]
def p_optional_results_0(p):
	'optional_results : '
	p[0] = None
def p_optional_results_1(p):
	'optional_results : results'
	p[0] = p[1]
def p_result_rec(p):
	'result_rec : optional_TOKEN HAT IDENT optional_results'
	print "Result Rec[", p[1], "] :", p[4]

# Start Rule:
def p_gdbmi_output(p):
	"""gdbmi_output : async_rec EOL
	                | stream_rec EOL
	                | result_rec EOL
			| STOP EOL
	"""
	p[0] = p[1]

import ply.yacc as yacc
yacc.yacc(start = 'gdbmi_output')

