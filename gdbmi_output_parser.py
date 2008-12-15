from pyparsing import *

ParserElement.setDefaultWhitespaceChars(" \t")

NOTFY_OUT  = Literal("=").suppress()
EXEC_OUT   = Literal("*").suppress()
STATUS_OUT = Literal("+").suppress()
TILDE      = Literal("~").suppress()
AT         = Literal("@").suppress()
HAT        = Literal("^").suppress()
AMPERSAND  = Literal("&").suppress()
EQ         = Literal("=").suppress()
COMMA      = Literal(",").suppress()
LCURLY     = Literal("{").suppress()
RCURLY     = Literal("}").suppress()
LSQUARE    = Literal("[").suppress()
RSQUARE    = Literal("]").suppress()
DQUOTE     = Literal("\"").suppress()
STOP       = Literal("(gdb)")
EOL        = (Literal("\n") | Literal("\n\r") | Literal("\r") | Literal("\r\n")).suppress()
# EOL = Literal("").suppress()

token = Word("0123456789")
optional_token = Optional(token, default="NOTOK")

c_string = dblQuotedString # DQUOTE + Regex(r'[^"]*') + DQUOTE
const = c_string
string = Word("-abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ")
variable = string
value = Forward()
result = Group(variable + EQ + value)
results = Dict(delimitedList(result))
values = delimitedList(value)
tuple_ = (LCURLY + Optional(results) + RCURLY)
list_ = (LSQUARE + Optional(values | results) + RSQUARE)
value << (c_string | tuple_ | list_)
async_class = string
async_output = async_class + Optional(COMMA + results)
result_class = string

# output =  ZeroOrMore(out_of_band_record) + Optional(result_record) + STOP + EOL

# Output Visitor:
# Should support the following methods:
#
# 	onExecAsyncOutput(token, asyncClass, results=None)
# 	onNotifyAsyncOutput(token, asyncClass, results=None)
# 	onStatusAsyncOutput(token, asyncClass, results=None)
# 	onResultRecord(token, resultClass, results=None)
# 	onGdbOutput(string)
#	onGdbErr(string)
#	onTargetOutput(string)
# 

gdbout_stream_output  = lambda V: (TILDE + c_string).setParseAction(lambda s, loc, toks: V.onGdbOutput(toks[0]))
target_stream_output  = lambda V: (AT + c_string).setParseAction(lambda s, loc, toks: V.onTargetOutput(toks[0]))
gdberr_stream_output  = lambda V: (AMPERSAND + c_string).setParseAction(lambda s, loc, toks: V.onGdbErr(toks[0]))

notify_async_output   = lambda V: (optional_token + NOTFY_OUT + async_output).setParseAction(lambda s, loc, toks: V.onNotifyAsyncOutput(toks[0], toks[1:]))
exec_async_output     = lambda V: (optional_token + EXEC_OUT + async_output).setParseAction(lambda s, loc, toks: V.onExecAsyncOutput(toks[0], toks[1:]))
status_async_output   = lambda V: (optional_token + STATUS_OUT + async_output).setParseAction(lambda s, loc, toks: V.onStatusAsyncOutput(toks[0], toks[1:]))

stream_record         = lambda V: gdbout_stream_output(V) | target_stream_output(V) | gdberr_stream_output(V)
async_record          = lambda V: exec_async_output(V) | notify_async_output(V) | status_async_output(V)
result_record         = lambda V: (optional_token + HAT + result_class + Optional(COMMA + results)).setParseAction(lambda s, loc, toks: V.onResultRecord(toks[0], toks[1:]))
out_of_band_record    = lambda V: (async_record(V) | stream_record(V))
output                = lambda V: (out_of_band_record(V) | result_record(V) | STOP) + EOL

