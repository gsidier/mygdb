
# ########## LEXER ##########

tokens = [
	'EQ', 'STAR', 'PLUS', 'TILDE', 'AT', 'HAT', 'AMPERSAND',
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

def tuple_(p):
	'tuple : LCURLY results RCURLY'
	p[0] = p[2]

def list_void(p):
	'list : LSQUARE RSQUARE'
	p[0] = []

def list_values(p):
	'list : LSQUARE values RSQUARE'
	p[0] = p[2]

def list_results(p):
	'list : LSQUARE results RSQUARE '
	p[0] = p[2]

def value(p):
	'value : CSTR | tuple | list'
	p[0] = p[1]

def async_output(p):
	'async_output : IDENT'
	p[0] = (p[1], [])

def async_output(p):
	'async_output : IDENT results'
	p[0] = (p[1], p[2])

