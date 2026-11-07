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
Análise semântica do Askform como Definição Dirigida pela Sintaxe (SDD).

MODIFICADO (SDD): antes, este módulo era uma passada separada sobre a AST
(classe SemanticAnalyzer com check_forms/check_wizards/check_apis/check_flows).
Agora cada regra semântica é uma função daqui chamada pela AÇÃO de uma
produção em parser.py, e calcula atributos SINTETIZADOS (bottom-up):

  * regras LOCAIS  (precisam só dos filhos da produção)  -> resolvidas na hora;
  * regras GLOBAIS (precisam de outros blocos, pois o programa permite
    referências para frente) -> viram PENDÊNCIAS no atributo `checks` e são
    resolvidas na produção raiz `program`, quando a tabela de símbolos está
    completa.

O mapa produção -> regra está em tabela.md. Identificadores das regras:

  R1  field_decl            default compatível com o tipo        (local)
  R2  field_decl            herança `default = Form.campo`       (global, RefCheck)
  R3  form_decl             regras do bloco `validate`           (local)
  R4  wizard_decl           etapas, herança em ordem e API       (global, WizardCheck)
  R5  endpoint_decl         consumes e {param} da rota           (global, EndpointCheck)
  R6  flow_decl             origem, API e verbo                  (global, FlowCheck)
  R7  program               tabela de símbolos e resolução       (raiz)

O comportamento (mensagens, linhas e ordem) é idêntico ao da versão anterior.
"""
import re
from dataclasses import dataclass, field
from typing import Any, List, Optional

from symbol_table import ProgramNode, SymbolTable, FieldRefNode


# ---------------------------------------------------------------------------
# Representação de erros e de verificações
# ---------------------------------------------------------------------------

@dataclass
class Erro:
    """Erro semântico; str() mantém o formato histórico das mensagens."""
    lineno: int
    msg: str

    def __str__(self) -> str:
        return f"Erro Semântico [Linha {self.lineno}]: {self.msg}"


class Verificacao:
    """Item do atributo sintetizado `checks` (lista ordenada)."""

    def resolver(self, st: SymbolTable) -> List[Erro]:
        raise NotImplementedError


@dataclass
class Resolvida(Verificacao):
    """Verificação LOCAL: o resultado já foi calculado pela ação da produção."""
    erros: List[Erro] = field(default_factory=list)

    def resolver(self, st: SymbolTable) -> List[Erro]:
        return list(self.erros)


# ---------------------------------------------------------------------------
# R1 — field_decl: default compatível com o tipo declarado (LOCAL)
# ---------------------------------------------------------------------------

def is_type_compatible(declared_type: str, val: Any) -> bool:
    # Mesma lógica da versão anterior (inclusive seus detalhes: date, uuid e
    # file nunca são compatíveis com um default; bool conta como int em float).
    if declared_type == 'string' and isinstance(val, str):
        return True
    if declared_type == 'integer' and isinstance(val, int) and not isinstance(val, bool):
        return True
    if declared_type == 'float' and isinstance(val, (float, int)):
        return True
    if declared_type == 'boolean' and isinstance(val, bool):
        return True
    return False


def regra_default(campo) -> List[Verificacao]:
    """
    Atributo sintetizado field_decl.checks.
    Retorna [] (sem default ou default compatível), [Resolvida] (erro local)
    ou [RefCheck] (default é referência Form.campo: R2, resolvida na raiz).
    """
    if 'default' not in campo.properties:
        return []
    val = campo.properties['default']
    if isinstance(val, FieldRefNode):
        # form_name fica None: o form_decl preenche (atributo herdado simulado).
        return [RefCheck(None, campo.name, campo.field_type, campo.lineno, val)]
    if not is_type_compatible(campo.field_type, val):
        return [Resolvida([Erro(
            campo.lineno,
            f"Valor padrão '{val}' é incompatível com o tipo '{campo.field_type}' do campo '{campo.name}'."
        )])]
    return []


# ---------------------------------------------------------------------------
# R2 — field_decl: herança `default = Form.campo` (GLOBAL)
# ---------------------------------------------------------------------------

@dataclass
class RefCheck(Verificacao):
    form_name: Optional[str]    # preenchido por form_decl
    field_name: str
    field_type: str
    field_lineno: int
    ref: FieldRefNode

    def resolver(self, st: SymbolTable) -> List[Erro]:
        ref = self.ref
        if ref.form_name not in st.forms:
            return [Erro(ref.lineno, f"Referência inter-etapas para formulário inexistente '{ref.form_name}'.")]
        source_form = st.forms[ref.form_name]
        if ref.field_name not in source_form.fields:
            return [Erro(ref.lineno, f"Campo '{ref.field_name}' não existe na etapa de origem '{ref.form_name}'.")]
        src_type = source_form.fields[ref.field_name].field_type
        if src_type != self.field_type:
            return [Erro(
                self.field_lineno,
                f"Incompatibilidade de tipos na herança: {ref.form_name}.{ref.field_name} ({src_type}) -> {self.form_name}.{self.field_name} ({self.field_type})."
            )]
        return []


# ---------------------------------------------------------------------------
# R3 — form_decl: regras do bloco `validate` (LOCAL: campos e validate são
# filhos da mesma produção form_decl)
# ---------------------------------------------------------------------------

def regra_validate(form) -> List[Erro]:
    erros: List[Erro] = []
    for target_field, v_block in form.validations.items():
        if target_field not in form.fields:
            erros.append(Erro(v_block.lineno, f"Validação referencia campo inexistente '{target_field}'."))
            continue
        f_type = form.fields[target_field].field_type
        for rule, val in v_block.rules.items():
            if rule in ('min', 'max'):
                if f_type not in ('integer', 'float', 'string'):
                    erros.append(Erro(v_block.lineno, f"Regra '{rule}' é incompatível com campo '{target_field}' do tipo '{f_type}'."))
            elif rule == 'pattern':
                if f_type != 'string':
                    erros.append(Erro(v_block.lineno, f"Regra pattern aplicada a campo não-string '{target_field}'."))
                try:
                    re.compile(val)
                except re.error as e:
                    erros.append(Erro(v_block.lineno, f"Expressão regular inválida no pattern: {str(e)}"))
    return erros


def regra_form(form) -> List[Verificacao]:
    """
    Atributo sintetizado form_decl.checks (ordem: campos, depois validate).
    Também completa o nome do form nas RefCheck dos campos: o field_decl não
    conhece o form que o contém (seria um atributo HERDADO), então ele deixa
    form_name vazio e o form_decl preenche aqui, subindo na árvore.
    """
    checks: List[Verificacao] = []
    for campo in form.fields.values():
        for c in campo.checks:
            if isinstance(c, RefCheck):
                c.form_name = form.name
            checks.append(c)
    erros = regra_validate(form)
    if erros:
        checks.append(Resolvida(erros))
    return checks


# ---------------------------------------------------------------------------
# R4 — wizard_decl (GLOBAL)
# ---------------------------------------------------------------------------

@dataclass
class WizardCheck(Verificacao):
    wizard: Any

    def resolver(self, st: SymbolTable) -> List[Erro]:
        wizard = self.wizard
        erros: List[Erro] = []
        seen_steps: List[str] = []
        for step_form in wizard.steps:
            if step_form not in st.forms:
                erros.append(Erro(wizard.lineno, f"Wizard '{wizard.name}' referencia etapa indefinida '{step_form}'."))
                continue
            form_obj = st.forms[step_form]
            for campo in form_obj.fields.values():
                val = campo.properties.get('default')
                if isinstance(val, FieldRefNode):
                    if val.form_name not in seen_steps:
                        erros.append(Erro(
                            campo.lineno,
                            f"A etapa '{step_form}' tenta herdar o valor de '{val.form_name}' antes de ele ser renderizado no Wizard."
                        ))
            seen_steps.append(step_form)
        if wizard.target_api:
            if wizard.target_api not in st.apis:
                erros.append(Erro(wizard.lineno, f"Wizard '{wizard.name}' aponta para API inexistente '{wizard.target_api}'."))
            else:
                api = st.apis[wizard.target_api]
                if not any(ep.method == wizard.target_verb for ep in api.endpoints):
                    erros.append(Erro(wizard.lineno, f"API '{wizard.target_api}' não suporta o verbo '{wizard.target_verb}'."))
        return erros


# ---------------------------------------------------------------------------
# R5 — endpoint_decl (GLOBAL)
# ---------------------------------------------------------------------------

@dataclass
class EndpointCheck(Verificacao):
    endpoint: Any

    def resolver(self, st: SymbolTable) -> List[Erro]:
        ep = self.endpoint
        if not ep.consumes:
            return []
        is_form = ep.consumes in st.forms
        is_wizard = ep.consumes in st.wizards
        if not (is_form or is_wizard):
            return [Erro(ep.lineno, f"Endpoint '{ep.method} {ep.route}' consome formulário ou wizard inexistente '{ep.consumes}'.")]
        erros: List[Erro] = []
        if is_form:
            form = st.forms[ep.consumes]
            params = re.findall(r'\{([a-zA-Z_][a-zA-Z0-9_]*)\}', ep.route)
            for p in params:
                if p not in form.fields:
                    erros.append(Erro(ep.lineno, f"Parâmetro de rota '{{{p}}}' não declarado no formulário '{form.name}'."))
        return erros


# ---------------------------------------------------------------------------
# R6 — flow_decl (GLOBAL)
# ---------------------------------------------------------------------------

@dataclass
class FlowCheck(Verificacao):
    flow: Any

    def resolver(self, st: SymbolTable) -> List[Erro]:
        flow = self.flow
        erros: List[Erro] = []
        valid_source = (
            flow.source_form in st.forms
            or flow.source_form in st.wizards
        )
        if not valid_source:
            erros.append(Erro(flow.lineno, f"Flow '{flow.name}' referencia origem inexistente '{flow.source_form}'."))
        if flow.target_api not in st.apis:
            erros.append(Erro(flow.lineno, f"Flow '{flow.name}' referencia API inexistente '{flow.target_api}'."))
        else:
            target = st.apis[flow.target_api]
            if not any(ep.method == flow.target_verb for ep in target.endpoints):
                erros.append(Erro(flow.lineno, f"API destino '{flow.target_api}' não suporta o verbo '{flow.target_verb}' no flow."))
        return erros


# ---------------------------------------------------------------------------
# R7 — program (raiz): tabela de símbolos e resolução das pendências
# ---------------------------------------------------------------------------

def construir_tabela_simbolos(ast: ProgramNode) -> SymbolTable:
    """Atributo sintetizado program.symtab."""
    st = SymbolTable()
    for form in ast.forms.values():
        st.insert_form(form)
    for wizard in ast.wizards.values():
        st.insert_wizard(wizard)
    for api in ast.apis.values():
        st.insert_api(api)
    if ast.theme is not None:
        st.insert_theme(ast.theme)
    if ast.flow is not None:
        st.insert_flow(ast.flow)
    return st


def _resolver_lista(checks: List[Verificacao], st: SymbolTable) -> List[Erro]:
    erros: List[Erro] = []
    for c in checks:
        erros.extend(c.resolver(st))
    return erros


def resolver_programa(ast: ProgramNode) -> List[Erro]:
    """
    Atributo sintetizado program.errors.
    A ordem das mensagens é a mesma de antes: forms, wizards, apis, flow.
    """
    st = ast.symtab
    erros: List[Erro] = []
    for form in st.forms.values():
        erros.extend(_resolver_lista(form.checks, st))
    for wizard in st.wizards.values():
        erros.extend(_resolver_lista(wizard.checks, st))
    for api in st.apis.values():
        erros.extend(_resolver_lista(api.checks, st))
    if ast.flow is not None:
        erros.extend(_resolver_lista(ast.flow.checks, st))
    return erros


# ---------------------------------------------------------------------------
# Compatibilidade com main.py
# ---------------------------------------------------------------------------

class SemanticAnalyzer:
    """
    MODIFICADO (SDD): a análise já foi feita pelas ações das produções (ver
    parser.py). Esta classe só expõe o resultado com a mesma interface de antes
    (analyze, errors, symbol_table), para o main.py continuar igual.
    """

    def __init__(self):
        self.symbol_table = SymbolTable()
        self.errors: List[str] = []

    def analyze(self, ast: ProgramNode) -> bool:
        if ast.symtab is not None:
            self.symbol_table = ast.symtab
        self.errors = [str(e) for e in ast.errors]
        return len(self.errors) == 0