"""
Lexer module for Forms and APIs DSL (ASCII Only / No Accents).
"""
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
    'string': 'TYPE_STRING',
    'integer': 'TYPE_INT',
    'float': 'TYPE_FLOAT',
    'boolean': 'TYPE_BOOL',
    'date': 'TYPE_DATE',
    'uuid': 'TYPE_UUID',
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
    # Aceita apenas caracteres ASCII dentro da string (barra acentos e caracteres UTF-8 estendidos)
    r'\"([^\\\"\n]|[^\x00-\x7F])*?\"'
    t.value = t.value[1:-1]
    return t

def t_IDENTIFIER(t):
    # Restringe estritamente a identificadores ASCII sem acentos (a-z, A-Z, 0-9, _)
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
    sys.stderr.write(f"Lexical error at line {t.lexer.lineno}: Illegal character or accent '{t.value[0]}'\n")
    t.lexer.skip(1)

def build_lexer():
    return lex.lex()
