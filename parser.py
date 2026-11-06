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
Parser sintático do Askform DSL usando PLY.

Constrói a AST e rejeita declarações/propriedades duplicadas para evitar
sobrescritas silenciosas. Mantém a interface pública build_parser().
"""
import ply.yacc as yacc

from lexer import tokens
from symbol_table import (
    ProgramNode,
    ThemeNode,
    FormNode,
    FormFieldNode,
    ValidationBlockNode,
    WizardNode,
    FieldRefNode,
    ApiNode,
    EndpointNode,
    FlowNode,
)


def _insert_unique(mapping, key, value, description, lineno=None):
    """Insere um item em um dicionário ou informa uma duplicidade."""
    if key in mapping:
        location = f" na linha {lineno}" if lineno else ""
        raise SyntaxError(f"{description} duplicado{location}: {key!r}")
    mapping[key] = value


def _merge_unique(target, incoming, description, lineno=None):
    """Mescla propriedades sem permitir que uma chave seja sobrescrita."""
    for key, value in incoming.items():
        _insert_unique(target, key, value, description, lineno)


def p_program(p):
    "program : theme_opt body_declarations flow_opt"
    program_node = ProgramNode(theme=p[1], flow=p[3])

    for decl in p[2]:
        if isinstance(decl, FormNode):
            _insert_unique(program_node.forms, decl.name, decl, "Formulário", decl.lineno)
        elif isinstance(decl, WizardNode):
            _insert_unique(program_node.wizards, decl.name, decl, "Wizard", decl.lineno)
        elif isinstance(decl, ApiNode):
            _insert_unique(program_node.apis, decl.name, decl, "API", decl.lineno)

    p[0] = program_node


def p_theme_opt(p):
    """theme_opt : theme_decl
                 | empty"""
    p[0] = p[1]


def p_body_declarations(p):
    """body_declarations : body_declarations body_declaration
                         | body_declaration"""
    if len(p) == 3:
        p[0] = p[1] + [p[2]]
    else:
        p[0] = [p[1]]


def p_body_declaration(p):
    """body_declaration : form_decl
                        | wizard_decl
                        | api_decl"""
    p[0] = p[1]


def p_flow_opt(p):
    """flow_opt : flow_decl
                 | empty"""
    p[0] = p[1]


# ---------------------------------------------------------------------------
# Temas
# ---------------------------------------------------------------------------

def p_theme_decl(p):
    "theme_decl : THEME IDENTIFIER LBRACE theme_props RBRACE"
    p[0] = ThemeNode(lineno=p.lineno(1), name=p[2], properties=p[4])


def p_theme_props(p):
    """theme_props : theme_props theme_prop
                   | empty"""
    if len(p) == 3:
        props = dict(p[1])
        _merge_unique(props, p[2], "Propriedade de tema", p.lineno(2))
        p[0] = props
    else:
        p[0] = {}


def p_theme_prop(p):
    "theme_prop : IDENTIFIER EQUALS literal_val SEMICOLON"
    p[0] = {p[1]: p[3]}


# ---------------------------------------------------------------------------
# Formulários e campos
# ---------------------------------------------------------------------------

def p_form_decl(p):
    "form_decl : FORM IDENTIFIER LBRACE form_elements RBRACE"
    form = FormNode(lineno=p.lineno(1), name=p[2])
    for item in p[4]:
        if isinstance(item, FormFieldNode):
            _insert_unique(form.fields, item.name, item, "Campo", item.lineno)
        elif isinstance(item, ValidationBlockNode):
            _insert_unique(
                form.validations, item.field_name, item,
                "Bloco de validação", item.lineno
            )
    p[0] = form


def p_form_elements(p):
    """form_elements : form_elements form_element
                     | empty"""
    if len(p) == 3:
        p[0] = p[1] + [p[2]]
    else:
        p[0] = []


def p_form_element(p):
    """form_element : field_decl
                    | validation_block"""
    p[0] = p[1]


def p_field_decl(p):
    "field_decl : IDENTIFIER COLON type_reference field_props_opt SEMICOLON"
    is_array, base_type = p[3]
    p[0] = FormFieldNode(
        lineno=p.lineno(1),
        name=p[1],
        field_type=base_type,
        is_array=is_array,
        properties=p[4],
    )


def p_type_reference(p):
    """type_reference : primitive_type
                      | primitive_type LBRACKET RBRACKET"""
    p[0] = (len(p) == 4, p[1])


def p_primitive_type(p):
    """primitive_type : TYPE_STRING
                      | TYPE_INT
                      | TYPE_FLOAT
                      | TYPE_BOOL
                      | TYPE_DATE
                      | TYPE_UUID
                      | FILE"""
    p[0] = p[1]


def p_field_props_opt(p):
    """field_props_opt : LBRACE field_props RBRACE
                       | empty"""
    p[0] = p[2] if len(p) == 4 else {}


def p_field_props(p):
    """field_props : field_props field_prop
                   | empty"""
    if len(p) == 3:
        props = dict(p[1])
        _merge_unique(props, p[2], "Propriedade de campo", p.lineno(2))
        p[0] = props
    else:
        p[0] = {}


def p_field_prop(p):
    """field_prop : LABEL EQUALS STRING_LIT SEMICOLON
                  | DEFAULT EQUALS literal_val SEMICOLON
                  | REQUIRED EQUALS boolean_literal SEMICOLON"""
    p[0] = {p[1]: p[3]}


def p_field_ref(p):
    "field_ref : IDENTIFIER DOT IDENTIFIER"
    p[0] = FieldRefNode(
        lineno=p.lineno(1),
        form_name=p[1],
        field_name=p[3],
    )


# ---------------------------------------------------------------------------
# Validações
# ---------------------------------------------------------------------------

def p_validation_block(p):
    "validation_block : VALIDATE IDENTIFIER LBRACE validation_rules RBRACE"
    p[0] = ValidationBlockNode(
        lineno=p.lineno(1),
        field_name=p[2],
        rules=p[4],
    )


def p_validation_rules(p):
    """validation_rules : validation_rules validation_rule
                        | empty"""
    if len(p) == 3:
        rules = dict(p[1])
        _merge_unique(rules, p[2], "Regra de validação", p.lineno(2))
        p[0] = rules
    else:
        p[0] = {}


def p_validation_rule(p):
    """validation_rule : MIN EQUALS number_lit SEMICOLON
                       | MAX EQUALS number_lit SEMICOLON
                       | PATTERN EQUALS STRING_LIT SEMICOLON
                       | MESSAGE EQUALS STRING_LIT SEMICOLON"""
    p[0] = {p[1]: p[3]}


# ---------------------------------------------------------------------------
# Wizards
# ---------------------------------------------------------------------------

def p_wizard_decl(p):
    "wizard_decl : WIZARD IDENTIFIER LBRACE wizard_elements RBRACE"
    props = p[4]
    p[0] = WizardNode(
        lineno=p.lineno(1),
        name=p[2],
        steps=props.get("steps", []),
        target_api=props.get("target_api"),
        target_verb=props.get("target_verb"),
    )


def p_wizard_elements(p):
    """wizard_elements : wizard_elements wizard_element
                       | empty"""
    if len(p) == 3:
        props = dict(p[1])
        _merge_unique(props, p[2], "Propriedade de wizard", p.lineno(2))
        p[0] = props
    else:
        p[0] = {}


def p_wizard_element(p):
    """wizard_element : STEPS EQUALS LBRACKET step_list RBRACKET SEMICOLON
                      | SUBMIT EQUALS IDENTIFIER DOT http_verb SEMICOLON"""
    if p.slice[1].type == "STEPS":
        p[0] = {"steps": p[4]}
    else:
        p[0] = {"target_api": p[3], "target_verb": p[5]}


def p_step_list(p):
    """step_list : step_list COMMA IDENTIFIER
                 | IDENTIFIER"""
    if len(p) == 4:
        if p[3] in p[1]:
            raise SyntaxError(
                f"Etapa duplicada no wizard na linha {p.lineno(3)}: {p[3]!r}"
            )
        p[0] = p[1] + [p[3]]
    else:
        p[0] = [p[1]]


# ---------------------------------------------------------------------------
# APIs e endpoints
# ---------------------------------------------------------------------------

def p_api_decl(p):
    "api_decl : API IDENTIFIER LBRACE endpoint_list RBRACE"
    seen = set()
    for endpoint in p[4]:
        identity = (endpoint.method, endpoint.route)
        if identity in seen:
            raise SyntaxError(
                f"Endpoint duplicado na linha {endpoint.lineno}: "
                f"{endpoint.method} {endpoint.route}"
            )
        seen.add(identity)
    p[0] = ApiNode(lineno=p.lineno(1), name=p[2], endpoints=p[4])


def p_endpoint_list(p):
    """endpoint_list : endpoint_list endpoint_decl
                     | empty"""
    if len(p) == 3:
        p[0] = p[1] + [p[2]]
    else:
        p[0] = []


def p_endpoint_decl(p):
    "endpoint_decl : http_verb STRING_LIT LBRACE endpoint_props RBRACE"
    props = p[4]
    p[0] = EndpointNode(
        lineno=p.lineno(1),
        method=p[1],
        route=p[2],
        consumes=props.get("consumes"),
        produces=props.get("produces"),
        headers=props.get("headers", {}),
    )


def p_http_verb(p):
    """http_verb : HTTP_GET
                 | HTTP_POST
                 | HTTP_PUT
                 | HTTP_DELETE
                 | HTTP_PATCH"""
    p[0] = p[1]


def p_endpoint_props(p):
    """endpoint_props : endpoint_props endpoint_prop
                      | empty"""
    if len(p) == 3:
        props = dict(p[1])
        _merge_unique(props, p[2], "Propriedade de endpoint", p.lineno(2))
        p[0] = props
    else:
        p[0] = {}


def p_endpoint_prop(p):
    """endpoint_prop : CONSUMES EQUALS IDENTIFIER SEMICOLON
                     | PRODUCES EQUALS primitive_type SEMICOLON
                     | HEADERS LBRACE header_list RBRACE SEMICOLON"""
    if p.slice[1].type == "CONSUMES":
        p[0] = {"consumes": p[3]}
    elif p.slice[1].type == "PRODUCES":
        p[0] = {"produces": p[3]}
    else:
        p[0] = {"headers": p[3]}


def p_header_list(p):
    """header_list : header_list STRING_LIT COLON STRING_LIT SEMICOLON
                   | empty"""
    if len(p) == 6:
        headers = dict(p[1])
        _insert_unique(
            headers, p[2], p[4], "Cabeçalho HTTP", p.lineno(2)
        )
        p[0] = headers
    else:
        p[0] = {}


# ---------------------------------------------------------------------------
# Fluxos
# ---------------------------------------------------------------------------

def p_flow_decl(p):
    "flow_decl : FLOW IDENTIFIER LBRACE IDENTIFIER ARROW IDENTIFIER DOT http_verb SEMICOLON RBRACE"
    p[0] = FlowNode(
        lineno=p.lineno(1),
        name=p[2],
        source_form=p[4],
        target_api=p[6],
        target_verb=p[8],
    )


# ---------------------------------------------------------------------------
# Literais e regras auxiliares
# ---------------------------------------------------------------------------

def p_number_lit(p):
    """number_lit : INT_LIT
                  | FLOAT_LIT"""
    p[0] = p[1]


def p_boolean_literal(p):
    """boolean_literal : TRUE
                       | FALSE"""
    p[0] = p[1] == "true"


def p_literal_val(p):
    """literal_val : STRING_LIT
                   | number_lit
                   | boolean_literal
                   | field_ref"""
    p[0] = p[1]


def p_empty(p):
    "empty :"
    p[0] = None


def p_error(p):
    """Produz erros sintáticos com linha e coluna quando há token inválido."""
    if p is None:
        raise SyntaxError("Fim inesperado do arquivo: declaração incompleta.")

    lexer = getattr(p, "lexer", None)
    input_text = getattr(lexer, "lexdata", "") if lexer else ""
    last_newline = input_text.rfind("\n", 0, p.lexpos)
    column = p.lexpos - last_newline
    raise SyntaxError(
        f"Erro de sintaxe na linha {p.lineno}, coluna {column}: "
        f"token inesperado {p.value!r} ({p.type})."
    )


def build_parser():
    """Constrói o parser sem gravar tabelas ou arquivos auxiliares."""
    return yacc.yacc(
        start="program",
        write_tables=False,
        debug=False,
        errorlog=yacc.NullLogger(),
    )
