"""
Syntactic Parser module for Askform DSL using PLY.
Supports Theme declarations, File types, Forms, Wizards, and APIs.
"""
import ply.yacc as yacc
from lexer import tokens
from symbol_table import (
    ProgramNode, ThemeNode, FormNode, FormFieldNode, ValidationBlockNode,
    WizardNode, FieldRefNode, ApiNode, EndpointNode, FlowNode
)

def p_program(p):
    '''program : declarations'''
    program_node = ProgramNode()
    for decl in p[1]:
        if isinstance(decl, ThemeNode):
            program_node.themes[decl.name] = decl
        elif isinstance(decl, FormNode):
            program_node.forms[decl.name] = decl
        elif isinstance(decl, WizardNode):
            program_node.wizards[decl.name] = decl
        elif isinstance(decl, ApiNode):
            program_node.apis[decl.name] = decl
        elif isinstance(decl, FlowNode):
            program_node.flows[decl.name] = decl
    p[0] = program_node

def p_declarations(p):
    '''declarations : declarations declaration
                    | declaration'''
    if len(p) == 3:
        p[0] = p[1] + [p[2]]
    else:
        p[0] = [p[1]]

def p_declaration(p):
    '''declaration : theme_decl
                   | form_decl
                   | wizard_decl
                   | api_decl
                   | flow_decl'''
    p[0] = p[1]

# Theme Rules
def p_theme_decl(p):
    '''theme_decl : THEME IDENTIFIER LBRACE theme_props RBRACE'''
    p[0] = ThemeNode(lineno=p.lineno(1), name=p[2], properties=p[4])

def p_theme_props(p):
    '''theme_props : theme_props theme_prop
                   | empty'''
    if len(p) == 3:
        p[1].update(p[2])
        p[0] = p[1]
    else:
        p[0] = {}

def p_theme_prop(p):
    '''theme_prop : IDENTIFIER EQUALS literal_val SEMICOLON'''
    p[0] = {p[1]: p[3]}

# Form Rules
def p_form_decl(p):
    '''form_decl : FORM IDENTIFIER LBRACE form_elements RBRACE'''
    form = FormNode(lineno=p.lineno(1), name=p[2])
    for item in p[4]:
        if isinstance(item, FormFieldNode):
            form.fields[item.name] = item
        elif isinstance(item, ValidationBlockNode):
            form.validations[item.field_name] = item
    p[0] = form

def p_form_elements(p):
    '''form_elements : form_elements form_element
                     | empty'''
    if len(p) == 3:
        p[0] = p[1] + [p[2]]
    else:
        p[0] = []

def p_form_element(p):
    '''form_element : field_decl
                    | validation_block'''
    p[0] = p[1]

def p_field_decl(p):
    '''field_decl : IDENTIFIER COLON type_reference field_props_opt SEMICOLON'''
    is_arr, base_t = p[3]
    p[0] = FormFieldNode(
        lineno=p.lineno(1),
        name=p[1],
        field_type=base_t,
        is_array=is_arr,
        properties=p[4]
    )

def p_type_reference(p):
    '''type_reference : primitive_type
                      | primitive_type LBRACKET RBRACKET'''
    if len(p) == 2:
        p[0] = (False, p[1])
    else:
        p[0] = (True, p[1])

def p_primitive_type(p):
    '''primitive_type : TYPE_STRING
                      | TYPE_INT
                      | TYPE_FLOAT
                      | TYPE_BOOL
                      | TYPE_DATE
                      | TYPE_UUID
                      | FILE'''
    p[0] = p[1]

def p_field_props_opt(p):
    '''field_props_opt : LBRACE field_props RBRACE
                       | empty'''
    p[0] = p[2] if len(p) == 4 else {}

def p_field_props(p):
    '''field_props : field_props field_prop
                   | empty'''
    if len(p) == 3:
        p[1].update(p[2])
        p[0] = p[1]
    else:
        p[0] = {}

def p_field_prop(p):
    '''field_prop : LABEL EQUALS STRING_LIT SEMICOLON
                  | DEFAULT EQUALS literal_val SEMICOLON
                  | REQUIRED EQUALS boolean_literal SEMICOLON'''
    p[0] = {p[1]: p[3]}

def p_field_ref(p):
    '''field_ref : IDENTIFIER DOT IDENTIFIER'''
    p[0] = FieldRefNode(lineno=p.lineno(1), form_name=p[1], field_name=p[3])

def p_validation_block(p):
    '''validation_block : VALIDATE IDENTIFIER LBRACE validation_rules RBRACE'''
    p[0] = ValidationBlockNode(lineno=p.lineno(1), field_name=p[2], rules=p[4])

def p_validation_rules(p):
    '''validation_rules : validation_rules validation_rule
                         | empty'''
    if len(p) == 3:
        p[1].update(p[2])
        p[0] = p[1]
    else:
        p[0] = {}

def p_validation_rule(p):
    '''validation_rule : MIN EQUALS number_lit SEMICOLON
                       | MAX EQUALS number_lit SEMICOLON
                       | PATTERN EQUALS STRING_LIT SEMICOLON
                       | MESSAGE EQUALS STRING_LIT SEMICOLON'''
    p[0] = {p[1]: p[3]}

# Wizard Rules
def p_wizard_decl(p):
    '''wizard_decl : WIZARD IDENTIFIER LBRACE wizard_elements RBRACE'''
    node = WizardNode(lineno=p.lineno(1), name=p[2])
    props = p[4]
    node.steps = props.get('steps', [])
    node.target_api = props.get('target_api')
    node.target_verb = props.get('target_verb')
    p[0] = node

def p_wizard_elements(p):
    '''wizard_elements : wizard_elements wizard_element
                       | empty'''
    if len(p) == 3:
        p[1].update(p[2])
        p[0] = p[1]
    else:
        p[0] = {}

def p_wizard_element(p):
    '''wizard_element : STEPS EQUALS LBRACKET step_list RBRACKET SEMICOLON
                      | SUBMIT EQUALS IDENTIFIER DOT http_verb SEMICOLON'''
    if p[1] == 'steps':
        p[0] = {'steps': p[4]}
    else:
        p[0] = {'target_api': p[3], 'target_verb': p[5]}

def p_step_list(p):
    '''step_list : step_list COMMA IDENTIFIER
                 | IDENTIFIER'''
    if len(p) == 4:
        p[0] = p[1] + [p[3]]
    else:
        p[0] = [p[1]]

# API Rules
def p_api_decl(p):
    '''api_decl : API IDENTIFIER LBRACE endpoint_list RBRACE'''
    p[0] = ApiNode(lineno=p.lineno(1), name=p[2], endpoints=p[4])

def p_endpoint_list(p):
    '''endpoint_list : endpoint_list endpoint_decl
                     | empty'''
    if len(p) == 3:
        p[0] = p[1] + [p[2]]
    else:
        p[0] = []

def p_endpoint_decl(p):
    '''endpoint_decl : http_verb STRING_LIT LBRACE endpoint_props RBRACE'''
    node = EndpointNode(lineno=p.lineno(1), method=p[1], route=p[2])
    props = p[4]
    node.consumes = props.get('consumes')
    node.produces = props.get('produces')
    node.headers = props.get('headers', {})
    p[0] = node

def p_http_verb(p):
    '''http_verb : HTTP_GET
                 | HTTP_POST
                 | HTTP_PUT
                 | HTTP_DELETE
                 | HTTP_PATCH'''
    p[0] = p[1]

def p_endpoint_props(p):
    '''endpoint_props : endpoint_props endpoint_prop
                      | empty'''
    if len(p) == 3:
        p[1].update(p[2])
        p[0] = p[1]
    else:
        p[0] = {}

def p_endpoint_prop(p):
    '''endpoint_prop : CONSUMES EQUALS IDENTIFIER SEMICOLON
                     | PRODUCES EQUALS primitive_type SEMICOLON
                     | HEADERS LBRACE header_list RBRACE SEMICOLON'''
    if p[1] == 'consumes':
        p[0] = {'consumes': p[3]}
    elif p[1] == 'produces':
        p[0] = {'produces': p[3]}
    else:
        p[0] = {'headers': p[3]}

def p_header_list(p):
    '''header_list : header_list STRING_LIT COLON STRING_LIT SEMICOLON
                   | empty'''
    if len(p) == 6:
        p[1][p[2]] = p[4]
        p[0] = p[1]
    else:
        p[0] = {}

# Flow Rules
def p_flow_decl(p):
    '''flow_decl : FLOW IDENTIFIER LBRACE IDENTIFIER ARROW IDENTIFIER DOT http_verb SEMICOLON RBRACE'''
    p[0] = FlowNode(
        lineno=p.lineno(1),
        name=p[2],
        source_form=p[4],
        target_api=p[6],
        target_verb=p[8]
    )

def p_number_lit(p):
    '''number_lit : INT_LIT
                  | FLOAT_LIT'''
    p[0] = p[1]

def p_boolean_literal(p):
    '''boolean_literal : TRUE
                       | FALSE'''
    p[0] = (p[1] == 'true')

def p_literal_val(p):
    '''literal_val : STRING_LIT
                   | number_lit
                   | boolean_literal
                   | field_ref'''
    p[0] = p[1]

def p_empty(p):
    '''empty :'''
    pass

def p_error(p):
    if p:
        raise SyntaxError(f"Syntax error at '{p.value}', line {p.lineno}")
    else:
        raise SyntaxError("Unexpected end of input (EOF)")

def build_parser():
    return yacc.yacc()
