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
  R4  transition            origem, destino e condição `when`    (global, TransitionCheck)
  R5  endpoint_decl         consumes e {param} da rota           (global, EndpointCheck)
  R6  flow_decl             caminhos entre etapas e envio        (global, FlowCheck)
  R7  program               tabela de símbolos e resolução       (raiz)

MODIFICADO (flow multi-etapas): o bloco `wizard` foi removido. Formulários de
várias páginas e caminhos condicionais agora são declarados no `flow`; as
regras R4 e R6 cobrem o que antes era do wizard (etapas existentes, herança
em ordem e API de envio). Programas sem wizard mantêm as mesmas mensagens.
"""
import datetime
import re
from dataclasses import dataclass, field
from typing import Any, List, Optional

from symbol_table import ProgramNode, SymbolTable, FieldRefNode
from flow_graph import FlowGraph
from expressions import Escopo, checar_condicao, referencias


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


@dataclass
class Aviso(Erro):
    """MODIFICADO (avisos): diagnóstico que NÃO impede a compilação."""

    def __str__(self) -> str:
        return f"Aviso Semântico [Linha {self.lineno}]: {self.msg}"


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
# R4 — transition (GLOBAL): `Origem -> Destino [when cond];`
# ---------------------------------------------------------------------------

@dataclass
class TransitionCheck(Verificacao):
    transition: Any
    flow_name: Optional[str] = None     # preenchido por flow_decl (regra_flow)

    def resolver(self, st: SymbolTable) -> List[Erro]:
        t = self.transition
        flow = self.flow_name
        erros: List[Erro] = []
        if t.source_form not in st.forms:
            erros.append(Erro(t.lineno, f"Flow '{flow}' referencia origem inexistente '{t.source_form}'."))
        if t.target_form is not None:
            if t.target_form not in st.forms:
                erros.append(Erro(t.lineno, f"Flow '{flow}' referencia etapa inexistente '{t.target_form}'."))
        elif t.target_api not in st.apis:
            erros.append(Erro(t.lineno, f"Flow '{flow}' referencia API inexistente '{t.target_api}'."))
        else:
            target = st.apis[t.target_api]
            if not any(ep.method == t.target_verb for ep in target.endpoints):
                erros.append(Erro(t.lineno, f"API destino '{t.target_api}' não suporta o verbo '{t.target_verb}' no flow."))
        if t.condition is not None:
            erros.extend(self._resolver_condicao(st))
        return erros

    def _resolver_condicao(self, st: SymbolTable) -> List[Erro]:
        """
        MODIFICADO (expressões nas condições): a checagem de tipos da expressão
        está em expressions.py (atributo `tipo`, resolvido aqui por precisar da
        tabela de símbolos). Erros primeiro; avisos só se não houve erro.
        """
        t = self.transition
        erros, avisos = checar_condicao(t.condition, Escopo(self.flow_name, t.source_form), st.forms)
        return [Erro(l, m) for l, m in erros] + [Aviso(l, m) for l, m in avisos]


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
        is_flow = ep.consumes in st.flows
        if not (is_form or is_flow):
            return [Erro(ep.lineno, f"Endpoint '{ep.method} {ep.route}' consome formulário ou flow inexistente '{ep.consumes}'.")]
        erros: List[Erro] = []
        params = re.findall(r'\{([a-zA-Z_][a-zA-Z0-9_]*)\}', ep.route)
        if is_form:
            form = st.forms[ep.consumes]
            for p in params:
                if p not in form.fields:
                    erros.append(Erro(ep.lineno, f"Parâmetro de rota '{{{p}}}' não declarado no formulário '{form.name}'."))
        else:
            # Endpoint que recebe o flow inteiro: a rota pode usar campos de
            # qualquer etapa.
            flow = st.flows[ep.consumes]
            campos = set()
            for step in FlowGraph(flow).steps:
                if step in st.forms:
                    campos.update(st.forms[step].fields)
            for p in params:
                if p not in campos:
                    erros.append(Erro(ep.lineno, f"Parâmetro de rota '{{{p}}}' não declarado em nenhuma etapa do flow '{flow.name}'."))
        return erros


# ---------------------------------------------------------------------------
# R6 — flow_decl (GLOBAL): navegação entre etapas
# ---------------------------------------------------------------------------

def regra_flow(flow) -> List[Verificacao]:
    """
    Atributo sintetizado flow_decl.checks. Assim como em regra_form, completa
    o nome do flow nas verificações das transições (atributo herdado simulado).
    """
    for t in flow.transitions:
        for c in t.checks:
            if isinstance(c, TransitionCheck):
                c.flow_name = flow.name
    return [FlowCheck(flow)]


@dataclass
class FlowCheck(Verificacao):
    flow: Any

    def resolver(self, st: SymbolTable) -> List[Erro]:
        flow = self.flow
        erros: List[Erro] = []
        for form_name in st.forms:
            if form_name.lower() == flow.name.lower():
                erros.append(Erro(flow.lineno, f"Flow '{flow.name}' tem o mesmo nome do formulário '{form_name}'."))
        transicoes: List[Erro] = []
        for t in flow.transitions:
            for c in t.checks:
                transicoes.extend(c.resolver(st))
        erros.extend(transicoes)
        if any(not isinstance(e, Aviso) for e in transicoes):
            # Com etapas ou APIs inexistentes, a análise do grafo só geraria ruído.
            return erros
        if FlowGraph(flow).is_simple():
            # Flow de uma linha (`Form -> Api.VERBO;`): página única, mesmas
            # regras de antes; não há navegação para verificar.
            return erros
        erros.extend(self._resolver_grafo(st))
        return erros

    def _resolver_grafo(self, st: SymbolTable) -> List[Erro]:
        flow = self.flow
        g = FlowGraph(flow)
        erros: List[Erro] = []

        # Saídas de cada etapa: precisa existir um caminho padrão (sem `when`),
        # e ele deve ser o último, já que as transições são testadas em ordem.
        for step in g.steps:
            outs = g.outgoing.get(step, [])
            if not outs:
                linha = next(t.lineno for t in flow.transitions if t.target_form == step)
                erros.append(Erro(linha, f"Etapa '{step}' do flow '{flow.name}' não tem transição de saída."))
                continue
            for i, t in enumerate(outs):
                if t.condition is None and i < len(outs) - 1:
                    for morta in outs[i + 1:]:
                        erros.append(Erro(
                            morta.lineno,
                            f"Transição de '{step}' nunca é usada: a transição sem 'when' da linha {t.lineno} já é o caminho padrão."
                        ))
                    break
            if all(t.condition is not None for t in outs):
                erros.append(Erro(
                    outs[-1].lineno,
                    f"Etapa '{step}' do flow '{flow.name}' só tem transições com 'when'; adicione uma transição sem 'when' como caminho padrão."
                ))

        ciclo = g.find_cycle()
        if ciclo:
            erros.append(Erro(flow.lineno, f"Flow '{flow.name}' tem um ciclo entre as etapas: {' -> '.join(ciclo)}."))
            return erros

        alcancaveis = g.reachable()
        for step in g.steps:
            if step not in alcancaveis:
                linha = next(t.lineno for t in flow.transitions if step in (t.source_form, t.target_form))
                erros.append(Erro(linha, f"Etapa '{step}' do flow '{flow.name}' não é alcançável a partir da etapa inicial '{g.start}'."))

        # Os dados de todas as etapas são enviados juntos: nomes de campo únicos.
        dono = {}
        for step in g.steps:
            for campo in st.forms[step].fields.values():
                if campo.name in dono:
                    erros.append(Erro(
                        campo.lineno,
                        f"Campo '{campo.name}' aparece nas etapas '{dono[campo.name]}' e '{step}' do flow '{flow.name}'; os nomes de campo precisam ser únicos no flow."
                    ))
                else:
                    dono[campo.name] = step

        # Herança (`default = Form.campo`) e condições sobre `Form.campo` só
        # podem usar etapas visitadas antes, em todos os caminhos.
        dom = g.dominators()
        for step in g.steps:
            if step not in dom:
                continue
            for campo in st.forms[step].fields.values():
                ref = campo.properties.get('default')
                if isinstance(ref, FieldRefNode) and ref.form_name in st.forms and ref.form_name not in dom[step]:
                    erros.append(Erro(
                        campo.lineno,
                        f"A etapa '{step}' tenta herdar o valor de '{ref.form_name}', mas '{ref.form_name}' não vem antes dela em todos os caminhos do flow '{flow.name}'."
                    ))
        for t in flow.transitions:
            if t.condition is None or t.source_form not in dom:
                continue
            # MODIFICADO (expressões): vale para TODA referência `Etapa.campo`
            # da expressão, em qualquer ponto (and/or/not/in...).
            vistos = set()
            for ref in referencias(t.condition):
                if ref.form_name is None or ref.form_name == t.source_form:
                    continue
                if (ref.form_name, ref.field_name) in vistos:
                    continue
                vistos.add((ref.form_name, ref.field_name))
                if ref.form_name not in dom[t.source_form]:
                    erros.append(Erro(
                        ref.lineno,
                        f"A condição da transição de '{t.source_form}' usa '{ref.form_name}.{ref.field_name}', mas '{ref.form_name}' não vem antes de '{t.source_form}' em todos os caminhos do flow '{flow.name}'."
                    ))

        # Envio depois de várias etapas: a API precisa receber o flow inteiro.
        for t in g.submits():
            if t.source_form not in alcancaveis or not g.ancestors(t.source_form):
                continue
            api = st.apis[t.target_api]
            if not any(ep.method == t.target_verb and ep.consumes == flow.name for ep in api.endpoints):
                erros.append(Erro(
                    t.lineno,
                    f"A transição de '{t.source_form}' envia os dados de várias etapas para '{t.target_api}.{t.target_verb}', mas nenhum endpoint {t.target_verb} de '{t.target_api}' consome o flow (use consumes = {flow.name};)."
                ))
        return erros


# ---------------------------------------------------------------------------
# R7 — program (raiz): tabela de símbolos e resolução das pendências
# ---------------------------------------------------------------------------

def construir_tabela_simbolos(ast: ProgramNode) -> SymbolTable:
    """Atributo sintetizado program.symtab."""
    st = SymbolTable()
    for form in ast.forms.values():
        st.insert_form(form)
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
    A ordem das mensagens é: forms, apis, flow.
    """
    st = ast.symtab
    erros: List[Erro] = []
    for form in st.forms.values():
        erros.extend(_resolver_lista(form.checks, st))
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
        self.warnings: List[str] = []

    def analyze(self, ast: ProgramNode) -> bool:
        if ast.symtab is not None:
            self.symbol_table = ast.symtab
        self.errors = [str(e) for e in ast.errors]
        self.warnings = [str(w) for w in ast.warnings]
        return len(self.errors) == 0