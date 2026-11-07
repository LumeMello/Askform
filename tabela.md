# Tabela de produções e regras semânticas (SDD) — Askform

Definição Dirigida pela Sintaxe do compilador Askform: para cada uma das **77 produções** da gramática (as mesmas do `parser.py`, na ordem do PLY), a regra semântica que calcula os atributos. Cada linha corresponde a uma função `p_xxx` do `parser.py`: a docstring é a produção, o corpo é a regra semântica.

Todos os atributos são **sintetizados** (calculados de baixo para cima na redução), que é o que o PLY suporta nativamente.

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
| `primitive_type`, `http_verb` | `type`, `val` | lexema do tipo / do verbo |
| `type_reference` | `(is_array, type)` | tipo base e se é array |
| `*_props`, `validation_rules`, `header_list` | `props`, `rules`, `headers` | dicionários acumulados (união, com erro de parser se a chave repete) |
| `*_list`, `form_elements`, `body_declarations` | `lista`, `steps` | listas acumuladas na ordem do código-fonte |
| `field_decl`, `form_decl`, `wizard_decl`, `endpoint_decl`, `api_decl`, `flow_decl` | nó da AST + **`checks`** | verificações semânticas ordenadas (ver seção 4) |
| `program` | `symtab`, `errors` | tabela de símbolos e lista final de erros semânticos |

## 3. Tabela de produções × regras semânticas

Natureza: **cópia** (repassa o atributo do filho), **constrói AST** (monta nó ou estrutura), **erro de parser** (checagem de duplicidade que já existia no parser e que continua igual), **R1–R7** (regras semânticas da seção 4).

| # | Produção | Regra semântica | Natureza | Implementação |
|---|---|---|---|---|
| 1 | `program → theme_opt body_declarations flow_opt` | `program.forms/wizards/apis = agrupar(body_declarations.lista)` (erro de parser se nome repetido no mesmo tipo); `program.symtab = construir_tabela_simbolos(program)`; `program.errors = resolver_programa(program)` — resolve as pendências R2, R4, R5, R6 na ordem forms → wizards → apis → flow | **R7 (raiz)** | `p_program` + `semantic.construir_tabela_simbolos`, `semantic.resolver_programa` |
| 2 | `theme_opt → theme_decl` | `theme_opt.val = theme_decl.val` | cópia | `p_theme_opt` |
| 3 | `theme_opt → empty` | `theme_opt.val = None` | cópia | `p_theme_opt` |
| 4 | `body_declarations → body_declarations body_declaration` | `lista = body_declarations₁.lista + [body_declaration.val]` | constrói AST | `p_body_declarations` |
| 5 | `body_declarations → body_declaration` | `lista = [body_declaration.val]` | constrói AST | `p_body_declarations` |
| 6 | `body_declaration → form_decl` | `val = form_decl.form` | cópia | `p_body_declaration` |
| 7 | `body_declaration → wizard_decl` | `val = wizard_decl.wizard` | cópia | `p_body_declaration` |
| 8 | `body_declaration → api_decl` | `val = api_decl.api` | cópia | `p_body_declaration` |
| 9 | `flow_opt → flow_decl` | `flow_opt.val = flow_decl.flow` | cópia | `p_flow_opt` |
| 10 | `flow_opt → empty` | `flow_opt.val = None` | cópia | `p_flow_opt` |
| 11 | `theme_decl → THEME IDENT { theme_props }` | `val = ThemeNode(IDENT.lexval, theme_props.props)` | constrói AST | `p_theme_decl` |
| 12 | `theme_props → theme_props theme_prop` | `props = theme_props₁.props ∪ theme_prop.props`; erro (parser) se a chave repete | constrói AST + erro de parser | `p_theme_props` |
| 13 | `theme_props → empty` | `props = {}` | constrói AST | `p_theme_props` |
| 14 | `theme_prop → IDENT = literal_val ;` | `props = {IDENT.lexval: literal_val.val}` | constrói AST | `p_theme_prop` |
| 15 | `form_decl → FORM IDENT { form_elements }` | `form = FormNode(IDENT.lexval, fields, validations)` agrupando `form_elements.lista` (erro de parser se campo ou `validate` repete); `form.checks = regra_form(form)` = `checks` dos campos (R1/R2) + **R3** (`validate` × campos do form, local); preenche `RefCheck.form_name = IDENT.lexval` (atributo herdado simulado) | **R3 (local)** | `p_form_decl` + `semantic.regra_form`, `semantic.regra_validate` |
| 16 | `form_elements → form_elements form_element` | `lista = form_elements₁.lista + [form_element.val]` | constrói AST | `p_form_elements` |
| 17 | `form_elements → empty` | `lista = []` | constrói AST | `p_form_elements` |
| 18 | `form_element → field_decl` | `val = field_decl.field` | cópia | `p_form_element` |
| 19 | `form_element → validation_block` | `val = validation_block.vb` | cópia | `p_form_element` |
| 20 | `field_decl → IDENT : type_reference field_props_opt ;` | `field = FormFieldNode(IDENT.lexval, type_reference.type, type_reference.is_array, field_props_opt.props)`; `field.checks = regra_default(field)`: **R1** se há `default` literal e `!compatível(type, default)` → erro local; **R2** se o `default` é `Form.campo` → pendência `RefCheck` (resolvida em `program`) | **R1 (local)** / **R2 (pendência)** | `p_field_decl` + `semantic.regra_default`, `semantic.RefCheck` |
| 21 | `type_reference → primitive_type` | `type_reference = (False, primitive_type.type)` | constrói AST | `p_type_reference` |
| 22 | `type_reference → primitive_type [ ]` | `type_reference = (True, primitive_type.type)` | constrói AST | `p_type_reference` |
| 23 | `primitive_type → TYPE_STRING` | `type = 'string'` (lexema) | cópia | `p_primitive_type` |
| 24 | `primitive_type → TYPE_INT` | `type = 'integer'` | cópia | `p_primitive_type` |
| 25 | `primitive_type → TYPE_FLOAT` | `type = 'float'` | cópia | `p_primitive_type` |
| 26 | `primitive_type → TYPE_BOOL` | `type = 'boolean'` | cópia | `p_primitive_type` |
| 27 | `primitive_type → TYPE_DATE` | `type = 'date'` | cópia | `p_primitive_type` |
| 28 | `primitive_type → TYPE_UUID` | `type = 'uuid'` | cópia | `p_primitive_type` |
| 29 | `primitive_type → FILE` | `type = 'file'` | cópia | `p_primitive_type` |
| 30 | `field_props_opt → { field_props }` | `props = field_props.props` | cópia | `p_field_props_opt` |
| 31 | `field_props_opt → empty` | `props = {}` | constrói AST | `p_field_props_opt` |
| 32 | `field_props → field_props field_prop` | `props = field_props₁.props ∪ field_prop.props`; erro (parser) se a chave repete | constrói AST + erro de parser | `p_field_props` |
| 33 | `field_props → empty` | `props = {}` | constrói AST | `p_field_props` |
| 34 | `field_prop → LABEL = STRING_LIT ;` | `props = {'label': STRING_LIT.lexval}` | constrói AST | `p_field_prop` |
| 35 | `field_prop → DEFAULT = literal_val ;` | `props = {'default': literal_val.val}` (valor literal ou `FieldRefNode`; a checagem é feita em `field_decl`) | constrói AST | `p_field_prop` |
| 36 | `field_prop → REQUIRED = boolean_literal ;` | `props = {'required': boolean_literal.val}` | constrói AST | `p_field_prop` |
| 37 | `field_ref → IDENT . IDENT` | `val = FieldRefNode(form=IDENT₁.lexval, campo=IDENT₂.lexval, line=IDENT₁.line)` | constrói AST | `p_field_ref` |
| 38 | `validation_block → VALIDATE IDENT { validation_rules }` | `vb = ValidationBlockNode(IDENT.lexval, validation_rules.rules, line=VALIDATE.line)` (a checagem R3 é feita em `form_decl`, que conhece os campos) | constrói AST | `p_validation_block` |
| 39 | `validation_rules → validation_rules validation_rule` | `rules = validation_rules₁.rules ∪ validation_rule.rules`; erro (parser) se a regra repete | constrói AST + erro de parser | `p_validation_rules` |
| 40 | `validation_rules → empty` | `rules = {}` | constrói AST | `p_validation_rules` |
| 41 | `validation_rule → MIN = number_lit ;` | `rules = {'min': number_lit.val}` | constrói AST | `p_validation_rule` |
| 42 | `validation_rule → MAX = number_lit ;` | `rules = {'max': number_lit.val}` | constrói AST | `p_validation_rule` |
| 43 | `validation_rule → PATTERN = STRING_LIT ;` | `rules = {'pattern': STRING_LIT.lexval}` | constrói AST | `p_validation_rule` |
| 44 | `validation_rule → MESSAGE = STRING_LIT ;` | `rules = {'message': STRING_LIT.lexval}` | constrói AST | `p_validation_rule` |
| 45 | `wizard_decl → WIZARD IDENT { wizard_elements }` | `wizard = WizardNode(IDENT.lexval, steps, target_api, target_verb)`; `wizard.checks = [WizardCheck(wizard)]` → **R4** (global: etapas, herança em ordem e API/verbo) | **R4 (pendência)** | `p_wizard_decl` + `semantic.WizardCheck` |
| 46 | `wizard_elements → wizard_elements wizard_element` | `props = wizard_elements₁.props ∪ wizard_element.props`; erro (parser) se a propriedade repete | constrói AST + erro de parser | `p_wizard_elements` |
| 47 | `wizard_elements → empty` | `props = {}` | constrói AST | `p_wizard_elements` |
| 48 | `wizard_element → STEPS = [ step_list ] ;` | `props = {'steps': step_list.steps}` | constrói AST | `p_wizard_element` |
| 49 | `wizard_element → SUBMIT = IDENT . http_verb ;` | `props = {'target_api': IDENT.lexval, 'target_verb': http_verb.val}` | constrói AST | `p_wizard_element` |
| 50 | `step_list → step_list , IDENT` | `steps = step_list₁.steps + [IDENT.lexval]`; erro (parser) se a etapa repete | constrói AST + erro de parser | `p_step_list` |
| 51 | `step_list → IDENT` | `steps = [IDENT.lexval]` | constrói AST | `p_step_list` |
| 52 | `api_decl → API IDENT { endpoint_list }` | `api = ApiNode(IDENT.lexval, endpoint_list.lista)`; erro (parser) se `(verbo, rota)` repete; `api.checks = concat(ep.checks para ep em endpoints)` | constrói AST + erro de parser | `p_api_decl` |
| 53 | `endpoint_list → endpoint_list endpoint_decl` | `lista = endpoint_list₁.lista + [endpoint_decl.endpoint]` | constrói AST | `p_endpoint_list` |
| 54 | `endpoint_list → empty` | `lista = []` | constrói AST | `p_endpoint_list` |
| 55 | `endpoint_decl → http_verb STRING_LIT { endpoint_props }` | `endpoint = EndpointNode(http_verb.val, STRING_LIT.lexval, consumes, produces, headers)` (`line = 0`, como antes); `endpoint.checks = [EndpointCheck(endpoint)]` → **R5** (global: `consumes` existe e `{param}` ∈ campos do form) | **R5 (pendência)** | `p_endpoint_decl` + `semantic.EndpointCheck` |
| 56 | `http_verb → HTTP_GET` | `val = 'GET'` (lexema) | cópia | `p_http_verb` |
| 57 | `http_verb → HTTP_POST` | `val = 'POST'` | cópia | `p_http_verb` |
| 58 | `http_verb → HTTP_PUT` | `val = 'PUT'` | cópia | `p_http_verb` |
| 59 | `http_verb → HTTP_DELETE` | `val = 'DELETE'` | cópia | `p_http_verb` |
| 60 | `http_verb → HTTP_PATCH` | `val = 'PATCH'` | cópia | `p_http_verb` |
| 61 | `endpoint_props → endpoint_props endpoint_prop` | `props = endpoint_props₁.props ∪ endpoint_prop.props`; erro (parser) se a propriedade repete | constrói AST + erro de parser | `p_endpoint_props` |
| 62 | `endpoint_props → empty` | `props = {}` | constrói AST | `p_endpoint_props` |
| 63 | `endpoint_prop → CONSUMES = IDENT ;` | `props = {'consumes': IDENT.lexval}` | constrói AST | `p_endpoint_prop` |
| 64 | `endpoint_prop → PRODUCES = primitive_type ;` | `props = {'produces': primitive_type.type}` | constrói AST | `p_endpoint_prop` |
| 65 | `endpoint_prop → HEADERS { header_list } ;` | `props = {'headers': header_list.headers}` | constrói AST | `p_endpoint_prop` |
| 66 | `header_list → header_list STRING_LIT : STRING_LIT ;` | `headers = header_list₁.headers ∪ {STRING_LIT₁.lexval: STRING_LIT₂.lexval}`; erro (parser) se o cabeçalho repete | constrói AST + erro de parser | `p_header_list` |
| 67 | `header_list → empty` | `headers = {}` | constrói AST | `p_header_list` |
| 68 | `flow_decl → FLOW IDENT { IDENT -> IDENT . http_verb ; }` | `flow = FlowNode(IDENT₁.lexval, IDENT₂.lexval, IDENT₃.lexval, http_verb.val)`; `flow.checks = [FlowCheck(flow)]` → **R6** (global: origem, API e verbo) | **R6 (pendência)** | `p_flow_decl` + `semantic.FlowCheck` |
| 69 | `number_lit → INT_LIT` | `val = INT_LIT.lexval` | cópia | `p_number_lit` |
| 70 | `number_lit → FLOAT_LIT` | `val = FLOAT_LIT.lexval` | cópia | `p_number_lit` |
| 71 | `boolean_literal → TRUE` | `val = True` | constrói AST | `p_boolean_literal` |
| 72 | `boolean_literal → FALSE` | `val = False` | constrói AST | `p_boolean_literal` |
| 73 | `literal_val → STRING_LIT` | `val = STRING_LIT.lexval` | cópia | `p_literal_val` |
| 74 | `literal_val → number_lit` | `val = number_lit.val` | cópia | `p_literal_val` |
| 75 | `literal_val → boolean_literal` | `val = boolean_literal.val` | cópia | `p_literal_val` |
| 76 | `literal_val → field_ref` | `val = field_ref.val` | cópia | `p_literal_val` |
| 77 | `empty → ε` | `val = None` | cópia | `p_empty` |

## 4. Regras semânticas R1–R7

Há dois tipos de regra:

- **Local:** só precisa dos filhos da própria produção, então é resolvida na hora da redução.
- **Global:** precisa de outros blocos. Como o programa permite **referências para frente** (por exemplo, `api` antes do `form` que ela consome), a produção apenas sintetiza uma **pendência** no atributo `checks`. A produção raiz `program` resolve as pendências quando a tabela de símbolos já está completa (R7).

| Regra | Produção onde ocorre | Tipo | Condição → erro | Linha do erro |
|---|---|---|---|---|
| **R1** | `field_decl` (#20) | local | há `default` literal e `!compatível(tipo, default)` → `Valor padrão '…' é incompatível com o tipo '…' do campo '…'.` | linha do campo |
| **R2** | `field_decl` (#20) → resolvida em `program` | global | `default = Form.campo`: form de origem inexistente → `Referência inter-etapas para formulário inexistente '…'.`; campo inexistente → `Campo '…' não existe na etapa de origem '…'.`; tipos diferentes → `Incompatibilidade de tipos na herança: A.x (t1) -> B.y (t2).` | linha da referência (os dois primeiros) / linha do campo (o terceiro) |
| **R3** | `form_decl` (#15) | local | `validate` de campo inexistente → `Validação referencia campo inexistente '…'.`; `min`/`max` em tipo fora de integer/float/string → `Regra '…' é incompatível com campo '…' do tipo '…'.`; `pattern` em campo não-string → `Regra pattern aplicada a campo não-string '…'.`; regex inválida → `Expressão regular inválida no pattern: …` | linha do `validate` |
| **R4** | `wizard_decl` (#45) → `program` | global | etapa inexistente → `Wizard '…' referencia etapa indefinida '…'.`; herança de etapa que não veio antes → `A etapa '…' tenta herdar o valor de '…' antes de ele ser renderizado no Wizard.`; API inexistente → `Wizard '…' aponta para API inexistente '…'.`; verbo ausente na API → `API '…' não suporta o verbo '…'.` | linha do wizard, exceto a herança fora de ordem (linha do campo) |
| **R5** | `endpoint_decl` (#55) → `program` | global | `consumes` não é form nem wizard → `Endpoint '… …' consome formulário ou wizard inexistente '…'.`; `{param}` não é campo do form consumido → `Parâmetro de rota '{…}' não declarado no formulário '…'.` | `0` (mantém o comportamento anterior: `lineno` de não-terminal) |
| **R6** | `flow_decl` (#68) → `program` | global | origem inexistente → `Flow '…' referencia origem inexistente '…'.`; API inexistente → `Flow '…' referencia API inexistente '…'.`; verbo ausente → `API destino '…' não suporta o verbo '…' no flow.` | linha do flow |
| **R7** | `program` (#1) | raiz | monta `symtab` e resolve as pendências de R2, R4, R5 e R6 na ordem: forms (campos, depois `validate`) → wizards → apis → flow | — |

### Ordem das mensagens

`program.errors` sai sempre na mesma ordem: para cada form (na ordem do código) os checks dos campos e em seguida os do `validate`; depois os wizards; depois as APIs (endpoint a endpoint); por fim o flow. Isso é o que mantém a saída idêntica à da versão anterior.

### Atributo herdado simulado

R2 precisa do **nome do form** que contém o campo para montar a mensagem de herança, mas `field_decl` está dentro de `form_decl` e ainda não o conhece (em uma SDD pura isso seria um atributo **herdado**, descendo do pai para os filhos, o que o PLY não faz bem). A solução usa só atributos sintetizados: `field_decl` cria o `RefCheck` com `form_name = None` e `form_decl` (#15) o preenche ao montar o form.

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
program  [symtab={apis:{A}}, errors=[Erro(0, "Endpoint 'POST /a' consome formulário ou wizard inexistente 'Nope'.")]]
└─ body_declarations → body_declaration → api_decl
        [api=A, checks=[EndpointCheck(POST /a)]]          ← pendência sintetizada
        └─ endpoint_decl [endpoint=(POST, "/a", consumes=Nope), checks=[EndpointCheck]]
program resolve: "Nope" ∉ symtab.forms ∪ symtab.wizards → Erro(0, ...)
```

## 6. Correspondência com a versão anterior

| Antes (`semantic.py` antigo) | Agora |
|---|---|
| `check_forms`, 1º laço (default de cada campo) | R1 em `field_decl` (local) e R2 resolvida em `program` |
| `check_forms`, 2º laço (`validate`) | R3 em `form_decl` (local) |
| `check_wizards` | R4 (`WizardCheck`) |
| `check_apis` | R5 (`EndpointCheck`) |
| `check_flows` | R6 (`FlowCheck`) |
| `analyze` + `build_symbols` | R7 em `program` (`construir_tabela_simbolos`, `resolver_programa`) |
| classe `SemanticAnalyzer` | mantida só como fachada para o `main.py` (`analyze`, `errors`, `symbol_table`) |

## 7. Comportamentos preservados (inclusive os incomuns)

- `default` em campos `date`, `uuid` e `file` sempre é erro (`is_type_compatible` só aceita string, integer, float e boolean).
- `float` aceita `default = true` (em Python `bool` é `int`).
- Arrays: a mensagem usa o tipo base (`string`), e `is_array` não interfere.
- `pattern` em campo não-string com regex inválida gera duas mensagens para o mesmo bloco.
- Referência a form inexistente dentro de um wizard gera duas mensagens (R2 e R4).
- Etapa inexistente em um wizard não entra na lista de etapas já vistas.
- Endpoint que consome um wizard não tem os parâmetros de rota conferidos.
- Endpoint sem `consumes` não é verificado; o `wizard.submit` confere só o verbo (não a rota); o `flow` não confere se o endpoint consome a origem.
- O tema não tem nenhuma checagem semântica; nomes iguais em tipos diferentes (um `form` e uma `api`, por exemplo) são aceitos.
- Os erros de endpoint saem com `Linha 0`.
