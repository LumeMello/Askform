# Copyright (C) 2026 Luciano Cunha Damaso Mello and João Guilherme de Oliveira Ribeiro Kongevold
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.

"""
Lexer do Askform DSL.

Define tokens, palavras reservadas, literais e comentários. O processamento
de strings preserva caracteres Unicode e interpreta escapes sem converter
bytes UTF-8 por meio de unicode_escape.
"""
import re
import ply.lex as lex


reserved = {
    "form": "FORM",
    "api": "API",
    "flow": "FLOW",
    "when": "WHEN",
    "validate": "VALIDATE",
    "theme": "THEME",
    "string": "TYPE_STRING",
    "integer": "TYPE_INT",
    "float": "TYPE_FLOAT",
    "boolean": "TYPE_BOOL",
    "date": "TYPE_DATE",
    "uuid": "TYPE_UUID",
    "file": "FILE",
    "label": "LABEL",
    "default": "DEFAULT",
    "required": "REQUIRED",
    "min": "MIN",
    "max": "MAX",
    "pattern": "PATTERN",
    "message": "MESSAGE",
    "consumes": "CONSUMES",
    "produces": "PRODUCES",
    "headers": "HEADERS",
    "true": "TRUE",
    "false": "FALSE",
    "GET": "HTTP_GET",
    "POST": "HTTP_POST",
    "PUT": "HTTP_PUT",
    "DELETE": "HTTP_DELETE",
    "PATCH": "HTTP_PATCH",
}

# dict.fromkeys mantém a ordem de declaração e remove duplicatas sem depender
# da ordem variável de um set.
tokens = list(dict.fromkeys([
    "IDENTIFIER",
    "STRING_LIT",
    "INT_LIT",
    "FLOAT_LIT",
    "ARROW",
    "LBRACE",
    "RBRACE",
    "LBRACKET",
    "RBRACKET",
    "COLON",
    "SEMICOLON",
    "COMMA",
    "DOT",
    "EQUALS",
    "EQ",
    "NE",
    "LE",
    "GE",
    "LT",
    "GT",
] + list(reserved.values())))

t_LBRACE = r"\{"
t_RBRACE = r"\}"
t_LBRACKET = r"\["
t_RBRACKET = r"\]"
t_COLON = r":"
t_SEMICOLON = r";"
t_COMMA = r","
t_DOT = r"\."
t_EQUALS = r"="
t_ARROW = r"->"
# Operadores de comparação das condições `when` do flow. O PLY testa as
# expressões regulares mais longas primeiro, então "==" vence "=" e "<=" vence "<".
t_EQ = r"=="
t_NE = r"!="
t_LE = r"<="
t_GE = r">="
t_LT = r"<"
t_GT = r">"

# Espaços horizontais são ignorados. Quebras de linha são contabilizadas
# separadamente por t_newline.
t_ignore = " \t\r"


_ESCAPE_MAP = {
    "\\": "\\",
    '"': '"',
    "'": "'",
    "n": "\n",
    "r": "\r",
    "t": "\t",
    "b": "\b",
    "f": "\f",
    "v": "\v",
    "0": "\0",
}


def _decode_string_literal(raw_value: str) -> str:
    """
    Decodifica o conteúdo de uma string DSL preservando Unicode.

    Escapes reconhecidos: \\\\, \\", \\', \\n, \\r, \\t, \\b, \\f, \\v,
    \\0, \\xHH, \\uHHHH e \\UHHHHHHHH. Escapes desconhecidos são preservados
    literalmente para não descartar barras invertidas silenciosamente.
    """
    result = []
    index = 0
    length = len(raw_value)

    while index < length:
        char = raw_value[index]
        if char != "\\":
            result.append(char)
            index += 1
            continue

        if index + 1 >= length:
            raise ValueError("Escape incompleto no final da string")

        escape_char = raw_value[index + 1]

        if escape_char in _ESCAPE_MAP:
            result.append(_ESCAPE_MAP[escape_char])
            index += 2
            continue

        if escape_char in ("x", "u", "U"):
            digits_count = {"x": 2, "u": 4, "U": 8}[escape_char]
            start = index + 2
            end = start + digits_count
            digits = raw_value[start:end]

            if len(digits) != digits_count or not re.fullmatch(
                rf"[0-9a-fA-F]{{{digits_count}}}", digits
            ):
                raise ValueError(
                    f"Escape Unicode inválido: \\{escape_char}{digits}"
                )

            codepoint = int(digits, 16)
            try:
                result.append(chr(codepoint))
            except ValueError as exc:
                raise ValueError(
                    f"Ponto de código Unicode inválido: U+{codepoint:04X}"
                ) from exc

            index = end
            continue

        # Compatibilidade: sequências não reconhecidas, como \d em regex,
        # continuam com a barra invertida original.
        result.append("\\")
        result.append(escape_char)
        index += 2

    return "".join(result)


def _find_column(input_text: str, lexpos: int) -> int:
    """Calcula a coluna (base 1) de uma posição do lexer."""
    last_newline = input_text.rfind("\n", 0, lexpos)
    return lexpos - last_newline


def t_FLOAT_LIT(t):
    r"\d+\.\d+"
    t.value = float(t.value)
    return t


def t_INT_LIT(t):
    r"\d+"
    t.value = int(t.value)
    return t


def t_STRING_LIT(t):
    r'"([^\\\n]|(\\.))*?"'
    raw_value = t.value[1:-1]
    try:
        t.value = _decode_string_literal(raw_value)
    except ValueError as exc:
        column = _find_column(t.lexer.lexdata, t.lexpos)
        raise SyntaxError(
            f"String inválida na linha {t.lineno}, coluna {column}: {exc}"
        ) from exc
    return t


def t_IDENTIFIER(t):
    r"[a-zA-Z_][a-zA-Z0-9_]*"
    t.type = reserved.get(t.value, "IDENTIFIER")
    return t


def t_COMMENT(t):
    r"(//[^\n]*)|(/\*[\s\S]*?\*/)"
    # O PLY descarta tokens cuja função retorna None.
    pass


def t_newline(t):
    r"\n+"
    t.lexer.lineno += len(t.value)


def t_error(t):
    column = _find_column(t.lexer.lexdata, t.lexpos)
    character = repr(t.value[0])
    raise SyntaxError(
        f"Caractere ilegal {character} na linha {t.lineno}, coluna {column}"
    )


def build_lexer():
    """Constrói e retorna uma instância independente do lexer."""
    lexer = lex.lex()
    lexer.lineno = 1
    return lexer
