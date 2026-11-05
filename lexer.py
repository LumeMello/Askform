"""
Lexer module for Askform DSL.
Defines terminal tokens, reserved words, and regular expression matchers.
"""
import codecs
import sys
import ply.lex as lex

reserved = {
    'form': 'FORM',
    'wizard': 'WIZARD',
    'steps': 'STEPS',
    'submit': 'SUBMIT',
    'api': 'API',
    'flow': 'FLOW',
    'validate': 'VALIDATE',
    'theme': 'THEME',
    'string': 'TYPE_STRING',
    'integer': 'TYPE_INT',
    'float': 'TYPE_FLOAT',
    'boolean': 'TYPE_BOOL',
    'date': 'TYPE_DATE',
    'uuid': 'TYPE_UUID',
    'file': 'FILE',
    'label': 'LABEL',
    'default': 'DEFAULT',
    'required': 'REQUIRED',
    'min': 'MIN',
    'max': 'MAX',
    'pattern': 'PATTERN',
    'message': 'MESSAGE',
    'consumes': 'CONSUMES',
    'produces': 'PRODUCES',
    'headers': 'HEADERS',
    'true': 'TRUE',
    'false': 'FALSE',
    'GET': 'HTTP_GET',
    'POST': 'HTTP_POST',
    'PUT': 'HTTP_PUT',
    'DELETE': 'HTTP_DELETE',
    'PATCH': 'HTTP_PATCH'
}

tokens = [
    'IDENTIFIER',
    'STRING_LIT',
    'INT_LIT',
    'FLOAT_LIT',
    'ARROW',
    'LBRACE',
    'RBRACE',
    'LBRACKET',
    'RBRACKET',
    'COLON',
    'SEMICOLON',
    'COMMA',
    'DOT',
    'EQUALS'
] + list(set(reserved.values()))

t_LBRACE = r'\{'
t_RBRACE = r'\}'
t_LBRACKET = r'\['
t_RBRACKET = r'\]'
t_COLON = r':'
t_SEMICOLON = r';'
t_COMMA = r','
t_DOT = r'\.'
t_EQUALS = r'='
t_ARROW = r'->'

t_ignore = ' \t\r'

def t_FLOAT_LIT(t):
    r'\d+\.\d+'
    t.value = float(t.value)
    return t

def t_INT_LIT(t):
    r'\d+'
    t.value = int(t.value)
    return t

def t_STRING_LIT(t):
    r'\"([^\\\n]|(\\.))*?\"'
    t.value = codecs.decode(t.value[1:-1], 'unicode_escape')
    return t

def t_IDENTIFIER(t):
    r'[a-zA-Z_][a-zA-Z0-9_]*'
    t.type = reserved.get(t.value, 'IDENTIFIER')
    return t

def t_COMMENT(t):
    r'(//.*)|(/\*(.|\n)*?\*/)'
    pass

def t_newline(t):
    r'\n+'
    t.lexer.lineno += len(t.value)

def t_error(t):
    sys.stderr.write(f"Lexical error at line {t.lexer.lineno}: Illegal character '{t.value[0]}'\n")
    t.lexer.skip(1)

def build_lexer():
    return lex.lex()
