# Tabela de produções e regras semânticas (SDD) — Askform

Definição Dirigida pela Sintaxe do compilador Askform: para cada uma das **109 produções** da gramática (as mesmas do `parser.py`, na ordem do PLY), a regra semântica que calcula os atributos. Cada linha corresponde a uma função `p_xxx` do `parser.py`: a docstring é a produção, o corpo é a regra semântica.

Todos os atributos são **sintetizados** (calculados de baixo para cima na redução), que é o que o PLY suporta nativamente.

## 0. Alfabeto da linguagem

**Σ (fora de comentários e strings)** = letras `a–z A–Z`, dígitos `0–9`, sublinhado `_`, os símbolos `{ } [ ] ( ) : ; , . = < > ! - "` e os separadores espaço, tabulação, retorno de carro (`\r`) e quebra de linha (`\n`) (`/` só aparece abrindo comentário). Qualquer outro caractere fora de comentário ou string é **erro léxico** (`Caractere ilegal ... na linha L, coluna C`). Dentro de comentários e de strings entra qualquer caractere Unicode (a string só não pode conter quebra de linha crua; `\"`, `\\` etc. são escapes).

| Classe | Expressão regular (`lexer.py`) | Símbolos de Σ usados |
|---|---|---|
| `IDENTIFIER` (e palavras reservadas) | `[a-zA-Z_][a-zA-Z0-9_]*` (depois consulta a tabela `reserved`) | letras, dígitos, `_` |
| `INT_LIT` | `\d+` (erro léxico se > 2⁶³−1) | dígitos |
| `FLOAT_LIT` | `\d+\.\d+` (erro léxico se virar infinito) | dígitos, `.` |
| `STRING_LIT` | `"([^\\\n]\|(\\.))*?"` | `"` e qualquer caractere (com escapes) |
| comentário (descartado) | `//[^\n]*` ou `/* ... */` | `/`, `*` e qualquer caractere |
| `ARROW` | `->` | `-`, `>` |
| `EQ` `NE` `LE` `GE` `LT` `GT` | `==` `!=` `<=` `>=` `<` `>` | `= ! < >` |
| `EQUALS` | `=` | `=` |
| `LBRACE` `RBRACE` `LBRACKET` `RBRACKET` `LPAREN` `RPAREN` | `{ } [ ] ( )` | delimitadores |
| `COLON` `SEMICOLON` `COMMA` `DOT` | `: ; , .` | pontuação |

**Palavras reservadas** (viram token próprio em vez de `IDENTIFIER`):

- estrutura: `form` `api` `flow` `theme` `database` `validate` `when`
- tipos: `string` `integer` `float` `boolean` `date` `uuid` `file`
- propriedades: `label` `default` `required` `min` `max` `pattern` `message` `consumes` `produces` `headers`
- valores e condições: `true` `false` `and` `or` `not` `in` `is` `empty`
- verbos HTTP (maiúsculas): `GET` `POST` `PUT` `DELETE` `PATCH`

Novas na extensão do trabalho: `and or not in is empty` (expressões), `database` (persistência), os operadores `== != <= >= < >` e `(` `)`.

## 1. Notação

- `X₁` é a ocorrência de `X` do lado direito quando `X` também aparece à esquerda (recursão).
- `IDENT.lexval` é o texto do token; `IDENT.line` é a linha do token.
- Ocorrências numeradas (`IDENT₁`, `IDENT₂`) seguem a ordem do lado direito.
- `agrupar`, `concat`, `∪` são operações sobre listas e dicionários.

## 2. Atributos

| Símbolo | Atributo | Significado |
|---|---|---|
| tokens | `lexval`, `line` | texto e linha do token |
| `number_lit`, `boolean_literal`, `literal_val`, `field_ref` | `val` | valor Python (`int`, `float`, `str`, `bool`) ou `FieldRefNode` para `Form.campo` |
| `primitive_type`, `http_verb`, `comparison_op` | `type`, `val` | lexema do tipo / do verbo / do operador |
| `flow_target` | `(form, api, verb)` | destino da transição: próxima etapa **ou** API + verbo |
| `condition_opt`, `expr`, `and_expr`, `not_expr`, `cmp_expr` | `ExprNode` ou `None` | condição `when` da transição (AST de expressão) + **`deps`**: conjunto sintetizado `{(form, campo)}` dos campos usados |
| `operand`, `field_operand`, `literal`, `literal_list` | `FieldRefExpr` / `LiteralExpr` / lista | folhas e lista de literais da expressão |
| `type_reference` | `(is_array, type)` | tipo base e se é array |
| `*_props`, `validation_rules`, `header_list` | `props`, `rules`, `headers` | dicionários acumulados (união, com erro de parser se a chave repete) |
| `*_list`, `form_elements`, `body_declarations` | `lista` | listas acumuladas na ordem do código-fonte |
| `field_decl`, `form_decl`, `transition`, `endpoint_decl`, `api_decl`, `flow_decl` | nó da AST + **`checks`** | verificações semânticas ordenadas (ver seção 4) |
| `program` | `symtab`, `errors`, `warnings` | tabela de símbolos, erros semânticos e avisos (`Aviso`, não impedem a compilação) |

## 3. Tabela de produções × regras semânticas

As **109 produções** da gramática, numeradas na ordem em que o PLY as registra (`yacc.yacc(...).productions`; o PLY ainda acrescenta a regra interna `S' → program`, que aqui não é contada). Estão todas numa única tabela: lexer e parser reconhecem tokens e sentenças, e cada linha abaixo diz qual regra semântica a função `p_xxx` executa quando a produção é reduzida.

Natureza: **cópia** (repassa o atributo do filho), **constrói AST** (monta nó ou estrutura), **acumula** (lista ou dicionário em construção), **união** (`deps` ou props unidos), **erro de parser** (checagem de duplicidade feita no parser), **R1–R11** (regras semânticas da seção 4: *local* = verificada na redução; *pendência* = objeto `Verificacao` resolvido na raiz, em `program`).

| # | Produção | Regra semântica | Natureza | Implementação |
|---|---|---|---|---|
| 1 | `program → theme_opt body_declarations flow_opt` | `program.forms/apis = agrupar(body_declarations.lista)` (erro de parser se nome repetido no mesmo tipo); `program.symtab = construir_tabela_simbolos(program)`; `program.errors = resolver_programa(program)` — resolve as pendências R2, R4, R5, R6 na ordem forms → apis → flow | **R7 (raiz)** | `p_program` + `semantic.construir_tabela_simbolos`, `semantic.resolver_programa` |
| 2 | `theme_opt → theme_decl` | `theme_opt.val = theme_decl.val` | cópia | `p_theme_opt` |
| 3 | `theme_opt → empty` | `theme_opt.val = None` | cópia | `p_theme_opt` |
| 4 | `body_declarations → body_declarations body_declaration` | `lista = body_declarations₁.lista + [body_declaration.val]` | constrói AST | `p_body_declarations` |
| 5 | `body_declarations → body_declaration` | `lista = [body_declaration.val]` | constrói AST | `p_body_declarations` |
| 6 | `body_declaration → form_decl` | `val = form_decl.form` | cópia | `p_body_declaration` |
| 7 | `body_declaration → api_decl` | `val = api_decl.api` | cópia | `p_body_declaration` |
| 8 | `body_declaration → database_decl` | `val = database_decl.node` (o bloco `database` é só mais uma alternativa de `body_declaration`: a árvore dos programas sem o bloco não muda) | cópia | `p_body_declaration` |
| 9 | `flow_opt → flow_decl` | `flow_opt.val = flow_decl.flow` | cópia | `p_flow_opt` |
| 10 | `flow_opt → empty` | `flow_opt.val = None` | cópia | `p_flow_opt` |
| 11 | `theme_decl → THEME IDENT { theme_props }` | `val = ThemeNode(IDENT.lexval, theme_props.props)` | constrói AST | `p_theme_decl` |
| 12 | `theme_props → theme_props theme_prop` | `props = theme_props₁.props ∪ theme_prop.props`; erro (parser) se a chave repete | constrói AST + erro de parser | `p_theme_props` |
| 13 | `theme_props → empty` | `props = {}` | constrói AST | `p_theme_props` |
| 14 | `theme_prop → IDENT = literal_val ;` | `props = {IDENT.lexval: literal_val.val}` | constrói AST | `p_theme_prop` |
| 15 | `database_decl → DATABASE IDENT { database_props }` | `node = DatabaseNode(IDENT.lexval, database_props.props)`; `node.checks = regra_database(node)` → **R8** (local: `engine`, `path`, `schema` e seus valores) | constrói AST + **R8 (local)** | `p_database_decl` + `semantic.regra_database` |
| 16 | `database_props → database_props database_prop` | `props = database_props₁.props ∪ database_prop.props`; erro (parser) se a chave repete | constrói AST + erro de parser | `p_database_props` |
| 17 | `database_props → empty` | `props = {}` | constrói AST | `p_database_props` |
| 18 | `database_prop → IDENT = literal_val ;` | `props = {IDENT.lexval: literal_val.val}` | constrói AST | `p_database_prop` |
| 19 | `form_decl → FORM IDENT { form_elements }` | `form = FormNode(IDENT.lexval, fields, validations)` agrupando `form_elements.lista` (erro de parser se campo ou `validate` repete); `form.checks = regra_form(form)` = `checks` dos campos (R1/R2) + **R3** (`validate` × campos do form, local); preenche `RefCheck.form_name = IDENT.lexval` (atributo herdado simulado) | **R3 (local)** | `p_form_decl` + `semantic.regra_form`, `semantic.regra_validate` |
| 20 | `form_elements → form_elements form_element` | `lista = form_elements₁.lista + [form_element.val]` | constrói AST | `p_form_elements` |
| 21 | `form_elements → empty` | `lista = []` | constrói AST | `p_form_elements` |
| 22 | `form_element → field_decl` | `val = field_decl.field` | cópia | `p_form_element` |
| 23 | `form_element → validation_block` | `val = validation_block.vb` | cópia | `p_form_element` |
| 24 | `field_decl → IDENT : type_reference field_props_opt ;` | `field = FormFieldNode(IDENT.lexval, type_reference.type, type_reference.is_array, field_props_opt.props)`; `field.checks = regra_default(field)`: **R1** se há `default` literal e `!compatível(type, default)` → erro local; **R2** se o `default` é `Form.campo` → pendência `RefCheck` (resolvida em `program`) | **R1 (local)** / **R2 (pendência)** | `p_field_decl` + `semantic.regra_default`, `semantic.RefCheck` |
| 25 | `type_reference → primitive_type` | `type_reference = (False, primitive_type.type)` | constrói AST | `p_type_reference` |
| 26 | `type_reference → primitive_type [ ]` | `type_reference = (True, primitive_type.type)` | constrói AST | `p_type_reference` |
| 27 | `primitive_type → TYPE_STRING` | `type = 'string'` (lexema) | cópia | `p_primitive_type` |
| 28 | `primitive_type → TYPE_INT` | `type = 'integer'` | cópia | `p_primitive_type` |
| 29 | `primitive_type → TYPE_FLOAT` | `type = 'float'` | cópia | `p_primitive_type` |
| 30 | `primitive_type → TYPE_BOOL` | `type = 'boolean'` | cópia | `p_primitive_type` |
| 31 | `primitive_type → TYPE_DATE` | `type = 'date'` | cópia | `p_primitive_type` |
| 32 | `primitive_type → TYPE_UUID` | `type = 'uuid'` | cópia | `p_primitive_type` |
| 33 | `primitive_type → FILE` | `type = 'file'` | cópia | `p_primitive_type` |
| 34 | `field_props_opt → { field_props }` | `props = field_props.props` | cópia | `p_field_props_opt` |
| 35 | `field_props_opt → empty` | `props = {}` | constrói AST | `p_field_props_opt` |
| 36 | `field_props → field_props field_prop` | `props = field_props₁.props ∪ field_prop.props`; erro (parser) se a chave repete | constrói AST + erro de parser | `p_field_props` |
| 37 | `field_props → empty` | `props = {}` | constrói AST | `p_field_props` |
| 38 | `field_prop → LABEL = STRING_LIT ;` | `props = {'label': STRING_LIT.lexval}` | constrói AST | `p_field_prop` |
| 39 | `field_prop → DEFAULT = literal_val ;` | `props = {'default': literal_val.val}` (valor literal ou `FieldRefNode`; a checagem é feita em `field_decl`) | constrói AST | `p_field_prop` |
| 40 | `field_prop → REQUIRED = boolean_literal ;` | `props = {'required': boolean_literal.val}` | constrói AST | `p_field_prop` |
| 41 | `field_ref → IDENT . IDENT` | `val = FieldRefNode(form=IDENT₁.lexval, campo=IDENT₂.lexval, line=IDENT₁.line)` | constrói AST | `p_field_ref` |
| 42 | `validation_block → VALIDATE IDENT { validation_rules }` | `vb = ValidationBlockNode(IDENT.lexval, validation_rules.rules, line=VALIDATE.line)` (a checagem R3 é feita em `form_decl`, que conhece os campos) | constrói AST | `p_validation_block` |
| 43 | `validation_rules → validation_rules validation_rule` | `rules = validation_rules₁.rules ∪ validation_rule.rules`; erro (parser) se a regra repete | constrói AST + erro de parser | `p_validation_rules` |
| 44 | `validation_rules → empty` | `rules = {}` | constrói AST | `p_validation_rules` |
| 45 | `validation_rule → MIN = number_lit ;` | `rules = {'min': number_lit.val}` | constrói AST | `p_validation_rule` |
| 46 | `validation_rule → MAX = number_lit ;` | `rules = {'max': number_lit.val}` | constrói AST | `p_validation_rule` |
| 47 | `validation_rule → PATTERN = STRING_LIT ;` | `rules = {'pattern': STRING_LIT.lexval}` | constrói AST | `p_validation_rule` |
| 48 | `validation_rule → MESSAGE = STRING_LIT ;` | `rules = {'message': STRING_LIT.lexval}` | constrói AST | `p_validation_rule` |
| 49 | `api_decl → API IDENT { endpoint_list }` | `api = ApiNode(IDENT.lexval, endpoint_list.lista)`; erro (parser) se `(verbo, rota)` repete; `api.checks = concat(ep.checks para ep em endpoints)` | constrói AST + erro de parser | `p_api_decl` |
| 50 | `endpoint_list → endpoint_list endpoint_decl` | `lista = endpoint_list₁.lista + [endpoint_decl.endpoint]` | constrói AST | `p_endpoint_list` |
| 51 | `endpoint_list → empty` | `lista = []` | constrói AST | `p_endpoint_list` |
| 52 | `endpoint_decl → http_verb STRING_LIT { endpoint_props }` | `endpoint = EndpointNode(http_verb.val, STRING_LIT.lexval, consumes, produces, headers)` (`line = 0`, como antes); `endpoint.checks = [EndpointCheck(endpoint)]` → **R5** (global: `consumes` é um form ou o flow e `{param}` ∈ campos do form ou de alguma etapa do flow) | **R5 (pendência)** | `p_endpoint_decl` + `semantic.EndpointCheck` |
| 53 | `http_verb → HTTP_GET` | `val = 'GET'` (lexema) | cópia | `p_http_verb` |
| 54 | `http_verb → HTTP_POST` | `val = 'POST'` | cópia | `p_http_verb` |
| 55 | `http_verb → HTTP_PUT` | `val = 'PUT'` | cópia | `p_http_verb` |
| 56 | `http_verb → HTTP_DELETE` | `val = 'DELETE'` | cópia | `p_http_verb` |
| 57 | `http_verb → HTTP_PATCH` | `val = 'PATCH'` | cópia | `p_http_verb` |
| 58 | `endpoint_props → endpoint_props endpoint_prop` | `props = endpoint_props₁.props ∪ endpoint_prop.props`; erro (parser) se a propriedade repete | constrói AST + erro de parser | `p_endpoint_props` |
| 59 | `endpoint_props → empty` | `props = {}` | constrói AST | `p_endpoint_props` |
| 60 | `endpoint_prop → CONSUMES = IDENT ;` | `props = {'consumes': IDENT.lexval}` | constrói AST | `p_endpoint_prop` |
| 61 | `endpoint_prop → PRODUCES = primitive_type ;` | `props = {'produces': primitive_type.type}` | constrói AST | `p_endpoint_prop` |
| 62 | `endpoint_prop → HEADERS { header_list } ;` | `props = {'headers': header_list.headers}` | constrói AST | `p_endpoint_prop` |
| 63 | `header_list → header_list STRING_LIT : STRING_LIT ;` | `headers = header_list₁.headers ∪ {STRING_LIT₁.lexval: STRING_LIT₂.lexval}`; erro (parser) se o cabeçalho repete | constrói AST + erro de parser | `p_header_list` |
| 64 | `header_list → empty` | `headers = {}` | constrói AST | `p_header_list` |
| 65 | `flow_decl → FLOW IDENT { transition_list }` | `flow = FlowNode(IDENT.lexval, transition_list.lista)`; `flow.checks = regra_flow(flow)` = `[FlowCheck(flow)]` → **R6** (global: caminhos entre etapas e envio); preenche `TransitionCheck.flow_name = IDENT.lexval` (atributo herdado simulado) | **R6 (pendência)** | `p_flow_decl` + `semantic.regra_flow`, `semantic.FlowCheck` |
| 66 | `transition_list → transition_list transition` | `lista = transition_list₁.lista + [transition.node]` | constrói AST | `p_transition_list` |
| 67 | `transition_list → transition` | `lista = [transition.node]` (o flow tem pelo menos uma transição) | constrói AST | `p_transition_list` |
| 68 | `transition → IDENT -> flow_target condition_opt ;` | `node = TransitionNode(IDENT.lexval, flow_target.(form, api, verb), condition_opt.val)`; `node.checks = [TransitionCheck(node)]` → **R4** (global: origem, destino e condição) | **R4 (pendência)** | `p_transition` + `semantic.TransitionCheck` |
| 69 | `flow_target → IDENT` | `val = (IDENT.lexval, None, None)` — próxima etapa (outra página) | constrói AST | `p_flow_target` |
| 70 | `flow_target → IDENT . http_verb` | `val = (None, IDENT.lexval, http_verb.val)` — envio para a API | constrói AST | `p_flow_target` |
| 71 | `condition_opt → WHEN expr` | `val = expr.node`; `deps = expr.deps` (campos usados na condição, conferidos em R4/R6) | cópia | `p_condition_opt` |
| 72 | `condition_opt → empty` | `val = None` (transição padrão) | cópia | `p_condition_opt` |
| 73 | `expr → expr OR and_expr` | `node = LogicExpr('or', expr₁.node, and_expr.node)`; `deps = expr₁.deps ∪ and_expr.deps` | constrói AST + união | `p_expr` |
| 74 | `expr → and_expr` | `node = and_expr.node`; `deps = and_expr.deps` | cópia | `p_expr` |
| 75 | `and_expr → and_expr AND not_expr` | `node = LogicExpr('and', and_expr₁.node, not_expr.node)`; `deps` = união dos dois | constrói AST + união | `p_and_expr` |
| 76 | `and_expr → not_expr` | `node = not_expr.node` | cópia | `p_and_expr` |
| 77 | `not_expr → NOT not_expr` | `node = NotExpr(not_expr₁.node)`; `deps = not_expr₁.deps` | constrói AST | `p_not_expr` |
| 78 | `not_expr → cmp_expr` | `node = cmp_expr.node` | cópia | `p_not_expr` |
| 79 | `cmp_expr → operand comparison_op operand` | `node = CompareExpr(comparison_op.val, operand₁.node, operand₂.node)`; `deps = operand₁.deps ∪ operand₂.deps`; tipos conferidos em R4 (`expressions.checar_condicao`) | constrói AST + união | `p_cmp_expr` |
| 80 | `cmp_expr → operand` | `node = operand.node` (booleano sozinho; o tipo é conferido em R4) | cópia | `p_cmp_expr` |
| 81 | `cmp_expr → ( expr )` | `node = expr.node` (parênteses só mudam a forma da árvore) | cópia | `p_cmp_expr` |
| 82 | `cmp_expr → field_operand IN ( literal_list )` | `node = InExpr(field_operand.node, literal_list.lista, negated=False)` | constrói AST | `p_cmp_expr` |
| 83 | `cmp_expr → field_operand NOT IN ( literal_list )` | `node = InExpr(field_operand.node, literal_list.lista, negated=True)` | constrói AST | `p_cmp_expr` |
| 84 | `cmp_expr → field_operand IS EMPTY` | `node = EmptyExpr(field_operand.node, negated=False)` | constrói AST | `p_cmp_expr` |
| 85 | `cmp_expr → field_operand IS NOT EMPTY` | `node = EmptyExpr(field_operand.node, negated=True)` | constrói AST | `p_cmp_expr` |
| 86 | `operand → field_operand` | `node = field_operand.node` | cópia | `p_operand` |
| 87 | `operand → literal` | `node = literal.node` | cópia | `p_operand` |
| 88 | `field_operand → IDENT` | `node = FieldRefExpr(None, IDENT.lexval)`; `deps = {(None, IDENT.lexval)}` | constrói AST | `p_field_operand` |
| 89 | `field_operand → IDENT . IDENT` | `node = FieldRefExpr(IDENT₁.lexval, IDENT₂.lexval)`; `deps = {(IDENT₁.lexval, IDENT₂.lexval)}` | constrói AST | `p_field_operand` |
| 90 | `literal → STRING_LIT` | `node = LiteralExpr(STRING_LIT.lexval)`; `deps = ∅` | constrói AST | `p_literal` |
| 91 | `literal → number_lit` | `node = LiteralExpr(number_lit.val)`; `deps = ∅` | constrói AST | `p_literal` |
| 92 | `literal → boolean_literal` | `node = LiteralExpr(boolean_literal.val)`; `deps = ∅` | constrói AST | `p_literal` |
| 93 | `literal_list → literal_list , literal` | `lista = literal_list₁.lista + [literal.node]` | acumula | `p_literal_list` |
| 94 | `literal_list → literal` | `lista = [literal.node]` | acumula | `p_literal_list` |
| 95 | `comparison_op → EQ` | `val = '=='` (lexema) | cópia | `p_comparison_op` |
| 96 | `comparison_op → NE` | `val = '!='` | cópia | `p_comparison_op` |
| 97 | `comparison_op → LT` | `val = '<'` | cópia | `p_comparison_op` |
| 98 | `comparison_op → LE` | `val = '<='` | cópia | `p_comparison_op` |
| 99 | `comparison_op → GT` | `val = '>'` | cópia | `p_comparison_op` |
| 100 | `comparison_op → GE` | `val = '>='` | cópia | `p_comparison_op` |
| 101 | `number_lit → INT_LIT` | `val = INT_LIT.lexval` | cópia | `p_number_lit` |
| 102 | `number_lit → FLOAT_LIT` | `val = FLOAT_LIT.lexval` | cópia | `p_number_lit` |
| 103 | `boolean_literal → TRUE` | `val = True` | constrói AST | `p_boolean_literal` |
| 104 | `boolean_literal → FALSE` | `val = False` | constrói AST | `p_boolean_literal` |
| 105 | `literal_val → STRING_LIT` | `val = STRING_LIT.lexval` | cópia | `p_literal_val` |
| 106 | `literal_val → number_lit` | `val = number_lit.val` | cópia | `p_literal_val` |
| 107 | `literal_val → boolean_literal` | `val = boolean_literal.val` | cópia | `p_literal_val` |
| 108 | `literal_val → field_ref` | `val = field_ref.val` | cópia | `p_literal_val` |
| 109 | `empty → ε` | `val = None` | cópia | `p_empty` |

### Notas sobre a tabela

- **Expressões (#71–#94):** a gramática é **estratificada** (um nível por precedência, sem `%precedence`): comparação > `not` > `and` > `or`; `and`/`or` associam à esquerda e os parênteses (#81) reabrem a hierarquia. As ações só sintetizam o nó da AST e o conjunto `deps` de campos usados. As regras semânticas da condição (campo/formulário inexistente, `file` e lista proibidos, valor incompatível, operador de ordem só em integer/float/date, operando solto precisa ser boolean, avisos de campo opcional, condição constante, valor repetido em `in`, `is empty` em boolean) rodam dentro de **R4** (`expressions.checar_condicao`); a regra dos dominadores em **R6** percorre as referências `Etapa.campo` da expressão.
- **Bloco `database` (#8, #15–#18):** entra como mais uma alternativa de `body_declaration` (e não como filho novo de `program`), então os programas sem o bloco reduzem exatamente as mesmas produções de antes (conferido por `tests/golden/teste_reducoes.txt`). `p_program` guarda o bloco em `ProgramNode.database` e levanta `CompileError` se houver um segundo. As chaves são `IDENTIFIER` genéricos (como no `theme`): `engine`, `path` e `schema` não são palavras reservadas; só `database` é.
- **`empty → ε` (#109):** produção vazia usada por todas as listas e opcionais.

## 4. Regras semânticas R1–R11

Há dois tipos de regra:

- **Local:** só precisa dos filhos da própria produção, então é resolvida na hora da redução.
- **Global:** precisa de outros blocos. Como o programa permite **referências para frente** (por exemplo, `api` antes do `form` que ela consome), a produção apenas sintetiza uma **pendência** no atributo `checks`. A produção raiz `program` resolve as pendências quando a tabela de símbolos já está completa (R7).

| Regra | Produção onde ocorre | Tipo | Condição → erro | Linha do erro |
|---|---|---|---|---|
| **R1** | `field_decl` (#24) | local | há `default` literal e `!compatível(tipo, default)` → `Valor padrão '…' é incompatível com o tipo '…' do campo '…'.` | linha do campo |
| **R2** | `field_decl` (#24) → resolvida em `program` | global | `default = Form.campo`: form de origem inexistente → `Referência inter-etapas para formulário inexistente '…'.`; campo inexistente → `Campo '…' não existe na etapa de origem '…'.`; tipos diferentes → `Incompatibilidade de tipos na herança: A.x (t1) -> B.y (t2).` | linha da referência (os dois primeiros) / linha do campo (o terceiro) |
| **R3** | `form_decl` (#19) | local | `validate` de campo inexistente → `Validação referencia campo inexistente '…'.`; `min`/`max` em tipo fora de integer/float/string → `Regra '…' é incompatível com campo '…' do tipo '…'.`; `pattern` em campo não-string → `Regra pattern aplicada a campo não-string '…'.`; regex inválida → `Expressão regular inválida no pattern: …` | linha do `validate` |
| **R4** | `transition` (#68) → `program` | global | origem inexistente → `Flow '…' referencia origem inexistente '…'.`; etapa destino inexistente → `Flow '…' referencia etapa inexistente '…'.`; API inexistente → `Flow '…' referencia API inexistente '…'.`; verbo ausente → `API destino '…' não suporta o verbo '…' no flow.`; condição: form/campo inexistente, campo `file` ou lista, valor de tipo incompatível, data/uuid inválido, operador de ordem (`<`, `<=`, `>`, `>=`) fora de integer/float/date, campos de tipos incompatíveis numa comparação, operando solto não booleano (ver as notas da seção 3); **avisos** (`Aviso Semântico`) só se não houve erro na condição | linha da transição |
| **R5** | `endpoint_decl` (#52) → `program` | global | `consumes` não é form nem o flow → `Endpoint '… …' consome formulário ou flow inexistente '…'.`; `{param}` não é campo do form consumido → `Parâmetro de rota '{…}' não declarado no formulário '…'.`; se consome o flow, `{param}` não é campo de nenhuma etapa → `Parâmetro de rota '{…}' não declarado em nenhuma etapa do flow '…'.` | linha do token `STRING_LIT` da rota (`endpoint_decl` usa `p.lineno(2)`; antes `p.lineno(1)` era o não-terminal `http_verb` e dava `0`) |
| **R6** | `flow_decl` (#65) → `program` | global | nome do flow igual ao de um form (sem diferenciar maiúsculas) → erro; depois resolve os R4 das transições, na ordem. Se não houve erro e o flow não é de uma linha só, analisa o grafo (`flow_graph.FlowGraph`): etapa sem saída; transição depois do caminho padrão (nunca usada); etapa só com transições `when`; ciclo; etapa inalcançável a partir da inicial; campo repetido entre etapas; herança `default = Etapa.campo` ou condição `Etapa.campo` de etapa que não vem antes em **todos** os caminhos (dominadores); envio depois de várias etapas para endpoint que não consome o flow | linha da transição (ou do campo); ciclo e nome na linha do flow |
| **R7** | `program` (#1) | raiz | monta `symtab` e resolve as pendências de R2, R4, R5, R6, R9, R10 e R11 na ordem: database (R8, já calculada) → forms (campos, `validate`, R10/R11) → apis (R5/R9) → flow | — |
| **R8** | `database_decl` (#15) | local | propriedade fora de `engine`/`path`/`schema` → `Propriedade desconhecida '…' no bloco database '…' (use engine, path ou schema).`; valor que não é texto; `engine` fora de `sqlite`/`memory`; `schema` fora de `auto`/`manual`; `path` vazio; `memory` com `path` (`…que não tem arquivo: remova 'path'.`) ou com `schema = \"manual\"` | linha do bloco |
| **R9** | `endpoint_decl` (#52) → `program` (dentro de `EndpointCheck`) | global | todo `{param}` da rota, já declarado, precisa ser campo `required = true` (do form consumido ou, se consome o flow, de alguma etapa) → `Parâmetro de rota '{…}' precisa ser um campo obrigatório (required = true) do formulário '…': ele identifica o registro.` (vira índice `UNIQUE` no banco) | linha da rota |
| **R10** | `form_decl` (#19) → `program` (`TabelaCheck`) | global | dois forms gravados por algum endpoint cujos nomes só diferem em maiúsculas → `Os formulários 'A' e 'a' usam a mesma tabela 'a' (nomes que só diferem em maiúsculas).` (erro no segundo) | linha do form |
| **R11** | `form_decl` (#19) → `program` (`TabelaCheck`) | global | campo `id` (sem diferenciar maiúsculas) em form gravado por endpoint → `O campo '…' do formulário '…' conflita com a chave primária automática 'id' da tabela; renomeie o campo.` | linha do campo |

### Ordem das mensagens

`program.errors` sai sempre na mesma ordem: para cada form (na ordem do código) os checks dos campos, em seguida os do `validate` e por fim R10/R11; depois as APIs (endpoint a endpoint); por fim o flow (nome, transições na ordem e depois o grafo). Para programas sem os recursos novos, a saída é idêntica à da versão anterior (verificado por `oracle/test_oracle.py`).

### Atributo herdado simulado

R2 precisa do **nome do form** que contém o campo para montar a mensagem de herança, mas `field_decl` está dentro de `form_decl` e ainda não o conhece (em uma SDD pura isso seria um atributo **herdado**, descendo do pai para os filhos, o que o PLY não faz bem). A solução usa só atributos sintetizados: `field_decl` cria o `RefCheck` com `form_name = None` e `form_decl` (#19) o preenche ao montar o form. O mesmo vale para `transition` (#68), que não conhece o nome do flow: o `TransitionCheck` nasce com `flow_name = None` e `flow_decl` (#65) o preenche em `regra_flow`.

## 5. Árvore de derivação anotada (exemplo)

Sentença com erro local (R1): dentro de um `form`, o campo `age: integer { default = "x"; };`

```
field_decl  [field=(age, integer, props={default:"x"}),
             checks=[Resolvida([Erro(2, "Valor padrão 'x' é incompatível com o tipo 'integer' do campo 'age'.")])]]
├─ IDENT age            [lexval="age", line=2]
├─ COLON
├─ type_reference       [(is_array=False, type=integer)]
│   └─ primitive_type   [type=integer]            ← TYPE_INT
├─ field_props_opt      [props={default:"x"}]
│   ├─ LBRACE
│   ├─ field_props      [props={default:"x"}]
│   │   ├─ field_props  [props={}]                ← ε
│   │   └─ field_prop   [props={default:"x"}]
│   │        ├─ DEFAULT, EQUALS
│   │        ├─ literal_val [val="x"]             ← STRING_LIT
│   │        └─ SEMICOLON
│   └─ RBRACE
└─ SEMICOLON
```

Sentença com referência para frente (R5 pendente, resolvida na raiz): `api A { POST "/a" { consumes = Nope; produces = uuid; } }`

```
program  [symtab={apis:{A}}, errors=[Erro(0, "Endpoint 'POST /a' consome formulário ou flow inexistente 'Nope'.")]]
└─ body_declarations → body_declaration → api_decl
        [api=A, checks=[EndpointCheck(POST /a)]]          ← pendência sintetizada
        └─ endpoint_decl [endpoint=(POST, "/a", consumes=Nope), checks=[EndpointCheck]]
program resolve: "Nope" ∉ symtab.forms ∪ symtab.flows → Erro(0, ...)
```

### Documentação gerada (sem produções novas)

`dist/API.md` e `dist/openapi.json` (`generator_docs.py`) são só mais um gerador da fase 3: leem a AST **já validada** e não acrescentam produção, ação semântica nem regra. A gramática continua com **109 produções, 0 conflitos**, e a árvore de derivação (e a anotada) do `teste.fad` é a mesma (`tests/golden/teste_reducoes.txt`; `tests/test_docs.py` confere). O único código novo no caminho da compilação é a chamada `generate_docs(ast)` em `main.py`, depois de `generate_html` e `generate_flask`.

## 6. Correspondência com a versão anterior

| Antes (`semantic.py` antigo) | Agora |
|---|---|
| `check_forms`, 1º laço (default de cada campo) | R1 em `field_decl` (local) e R2 resolvida em `program` |
| `check_forms`, 2º laço (`validate`) | R3 em `form_decl` (local) |
| `check_wizards` | removido junto com o bloco `wizard`; o equivalente é R4 (`TransitionCheck`) + R6 (`FlowCheck`) |
| `check_apis` | R5 (`EndpointCheck`) |
| `check_flows` | R6 (`FlowCheck`) |
| `analyze` + `build_symbols` | R7 em `program` (`construir_tabela_simbolos`, `resolver_programa`) |
| classe `SemanticAnalyzer` | mantida só como fachada para o `main.py` (`analyze`, `errors`, `symbol_table`) |

## 7. Comportamentos preservados (inclusive os incomuns)

- `default` em campos `date`, `uuid` e `file` sempre é erro (`is_type_compatible` só aceita string, integer, float e boolean).
- `float` aceita `default = true` (em Python `bool` é `int`).
- Arrays: a mensagem usa o tipo base (`string`), e `is_array` não interfere.
- `pattern` em campo não-string com regex inválida gera duas mensagens para o mesmo bloco.
- Endpoint sem `consumes` não é verificado; um flow de uma linha só (`Form -> Api.VERBO;`) confere só o verbo, não se o endpoint consome a origem, e não passa pela análise de grafo de R6 (um form dele pode herdar de outro form, como antes).
- O tema não tem nenhuma checagem semântica; nomes iguais em tipos diferentes (um `form` e uma `api`, por exemplo) são aceitos. A exceção nova é o `flow`, que não pode ter o nome de um `form`, porque os dois podem aparecer em `consumes`.
- **Corrigido (era "Linha 0"):** os erros de endpoint agora saem com a linha da rota.
- **Nomes duplicados** (campo, form, api, endpoint, bloco `validate`, propriedades, cabeçalho) levantam `parser.CompileError` com a linha. Antes usavam `SyntaxError` dentro da ação, que o PLY engole (só "Failed to construct AST" e, com declarações depois do duplicado, formulários descartados em silêncio). `CompileError` herda de `Exception` de propósito. A compilação para no primeiro duplicado.
- A árvore de derivação do `teste.fad` não mudou com as expressões: ele só usa `condition_opt → empty`, e `tests/golden/teste_reducoes.txt` (sequência de reduções) é conferida por `tests/test_expressions.py`.
- **Persistência (fase 1):** nenhuma produção nova (a gramática passou a 109 com as expressões e o bloco `database`; veja a tabela da seção 3). R9–R11 são verificações pendentes (`EndpointCheck`, `TabelaCheck`) resolvidas em `program`. O esquema SQL (`generator_sql.py`) é gerado a partir dos mesmos campos, `required`, `default`, `min` e `max` que a validação do `app.py` usa, para o banco nunca rejeitar o que a aplicação aceita. Detalhes: `README.md` (seção Persistência).
- **Números fora do intervalo (F.3):** `INT_LIT` acima de 2⁶³−1 e `FLOAT_LIT` que vira infinito são **erros léxicos** (com linha e coluna), tratados no analisador léxico; nenhuma produção muda. O servidor confere o intervalo de `integer` e recusa decimal não inteiro. Em condições, inteiro acima de 2⁵³ gera `Aviso` (precisão do JavaScript).
- **Persistência (fase 2):** o bloco `database` (#15, R8) escolhe `engine` (`sqlite` ou `memory`), `path` e `schema` (`auto` ou `manual`); o `app.py` embute a escolha em `DATABASE`. O gerador de HTML ignora o bloco.