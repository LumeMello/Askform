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
    FieldRefNode,
    ApiNode,
    EndpointNode,
    FlowNode,
    TransitionNode,
    FieldRefExpr, LiteralExpr, CompareExpr, InExpr, EmptyExpr, NotExpr, LogicExpr,
)
# MODIFICADO (SDD): as regras semânticas (R1..R7) ficam em semantic.py e são
# chamadas pelas ações das produções abaixo; ver tabela.md.
from semantic import (
    regra_default,
    regra_form,
    TransitionCheck,
    Aviso,
    EndpointCheck,
    regra_flow,
    construir_tabela_simbolos,
    resolver_programa,
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
        elif isinstance(decl, ApiNode):
            _insert_unique(program_node.apis, decl.name, decl, "API", decl.lineno)

    # MODIFICADO (SDD) — regra R7 (raiz): sintetiza program.symtab e, com a
    # tabela completa, resolve as pendências (R2, R4, R5, R6) gerando
    # program.errors. Todas as checagens locais (R1, R3) já foram feitas.
    program_node.symtab = construir_tabela_simbolos(program_node)
    diagnosticos = resolver_programa(program_node)
    # MODIFICADO (avisos): erros impedem a compilação; avisos só são informados.
    program_node.errors = [d for d in diagnosticos if not isinstance(d, Aviso)]
    program_node.warnings = [d for d in diagnosticos if isinstance(d, Aviso)]

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
    # MODIFICADO (SDD) — regra R3 (local): validate x campos do form.
    # form.checks = checks dos campos (R1/R2, com form_name preenchido aqui)
    # seguidos dos erros do bloco validate.
    form.checks = regra_form(form)
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
    node = FormFieldNode(
        lineno=p.lineno(1),
        name=p[1],
        field_type=base_type,
        is_array=is_array,
        properties=p[4],
    )
    # MODIFICADO (SDD) — regra R1 (local): default compatível com o tipo.
    # Se o default é referência Form.campo, vira pendência R2 (global),
    # resolvida em `program`.
    node.checks = regra_default(node)
    p[0] = node


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
    node = ApiNode(lineno=p.lineno(1), name=p[2], endpoints=p[4])
    # MODIFICADO (SDD): api_decl.checks = concatenação dos checks dos endpoints
    # (atributo sintetizado), na ordem de declaração.
    node.checks = [c for endpoint in node.endpoints for c in endpoint.checks]
    p[0] = node


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
    node = EndpointNode(
        lineno=p.lineno(1),
        method=p[1],
        route=p[2],
        consumes=props.get("consumes"),
        produces=props.get("produces"),
        headers=props.get("headers", {}),
    )
    # MODIFICADO (SDD) — regra R5 (global): consumes e {param} da rota.
    # Obs.: lineno continua p.lineno(1) de um não-terminal (0), como antes.
    node.checks = [EndpointCheck(node)]
    p[0] = node


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
    "flow_decl : FLOW IDENTIFIER LBRACE transition_list RBRACE"
    node = FlowNode(lineno=p.lineno(1), name=p[2], transitions=p[4])
    # MODIFICADO — regra R6 (global): navegação entre etapas (caminhos,
    # ciclos, herança em ordem, envio). As checagens de cada transição (R4)
    # entram antes, na ordem de declaração.
    node.checks = regra_flow(node)
    p[0] = node


def p_transition_list(p):
    """transition_list : transition_list transition
                       | transition"""
    if len(p) == 3:
        p[0] = p[1] + [p[2]]
    else:
        p[0] = [p[1]]


def p_transition(p):
    "transition : IDENTIFIER ARROW flow_target condition_opt SEMICOLON"
    target_form, target_api, target_verb = p[3]
    node = TransitionNode(
        lineno=p.lineno(1),
        source_form=p[1],
        target_form=target_form,
        target_api=target_api,
        target_verb=target_verb,
        condition=p[4],
    )
    # Regra R4 (global): origem, destino (etapa ou API.VERBO) e condição.
    node.checks = [TransitionCheck(node)]
    p[0] = node


def p_flow_target(p):
    """flow_target : IDENTIFIER
                   | IDENTIFIER DOT http_verb"""
    if len(p) == 2:
        p[0] = (p[1], None, None)          # próxima etapa (outra página)
    else:
        p[0] = (None, p[1], p[3])          # envio para a API


def p_condition_opt(p):
    """condition_opt : WHEN expr
                     | empty"""
    p[0] = p[2] if len(p) == 3 else None


# MODIFICADO (expressões nas condições): gramática ESTRATIFICADA. A precedência
# está na estrutura (cada nível chama o seguinte): comparação > not > and > or.
# Todas as ações só sintetizam atributos locais (nó da AST e `deps`).

def _deps(*nodes):
    result = frozenset()
    for node in nodes:
        result |= node.deps
    return result


def p_expr(p):
    """expr : expr OR and_expr
            | and_expr"""
    if len(p) == 4:
        p[0] = LogicExpr(lineno=p[1].lineno, op="or", left=p[1], right=p[3], deps=_deps(p[1], p[3]))
    else:
        p[0] = p[1]


def p_and_expr(p):
    """and_expr : and_expr AND not_expr
                | not_expr"""
    if len(p) == 4:
        p[0] = LogicExpr(lineno=p[1].lineno, op="and", left=p[1], right=p[3], deps=_deps(p[1], p[3]))
    else:
        p[0] = p[1]


def p_not_expr(p):
    """not_expr : NOT not_expr
                | cmp_expr"""
    if len(p) == 3:
        p[0] = NotExpr(lineno=p.lineno(1), operand=p[2], deps=p[2].deps)
    else:
        p[0] = p[1]


def p_cmp_expr(p):
    """cmp_expr : operand comparison_op operand
                | operand
                | LPAREN expr RPAREN
                | field_operand IN LPAREN literal_list RPAREN
                | field_operand NOT IN LPAREN literal_list RPAREN
                | field_operand IS EMPTY
                | field_operand IS NOT EMPTY"""
    n = len(p)
    if n == 4 and p[1] == "(":
        p[0] = p[2]
    elif n == 4 and p[2] == "is":
        p[0] = EmptyExpr(lineno=p[1].lineno, target=p[1], negated=False, deps=p[1].deps)
    elif n == 4:
        p[0] = CompareExpr(lineno=p[1].lineno, op=p[2], left=p[1], right=p[3], deps=_deps(p[1], p[3]))
    elif n == 2:
        p[0] = p[1]
    elif n == 5:
        p[0] = EmptyExpr(lineno=p[1].lineno, target=p[1], negated=True, deps=p[1].deps)
    elif n == 6:
        p[0] = InExpr(lineno=p[1].lineno, target=p[1], values=p[4], negated=False, deps=p[1].deps)
    else:
        p[0] = InExpr(lineno=p[1].lineno, target=p[1], values=p[5], negated=True, deps=p[1].deps)


def p_operand(p):
    """operand : field_operand
               | literal"""
    p[0] = p[1]


def p_field_operand(p):
    """field_operand : IDENTIFIER
                     | IDENTIFIER DOT IDENTIFIER"""
    if len(p) == 2:
        p[0] = FieldRefExpr(lineno=p.lineno(1), form_name=None, field_name=p[1],
                            deps=frozenset({(None, p[1])}))
    else:
        p[0] = FieldRefExpr(lineno=p.lineno(1), form_name=p[1], field_name=p[3],
                            deps=frozenset({(p[1], p[3])}))


def p_literal(p):
    """literal : STRING_LIT
               | number_lit
               | boolean_literal"""
    p[0] = LiteralExpr(lineno=p.lineno(1), value=p[1])


def p_literal_list(p):
    """literal_list : literal_list COMMA literal
                    | literal"""
    p[0] = p[1] + [p[3]] if len(p) == 4 else [p[1]]


def p_comparison_op(p):
    """comparison_op : EQ
                     | NE
                     | LT
                     | LE
                     | GT
                     | GE"""
    p[0] = p[1]


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
    