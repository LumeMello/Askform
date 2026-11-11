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
Symbol Table and Abstract Syntax Tree (AST) node definitions with Theme and Flow support.
"""
from dataclasses import dataclass, field
from typing import Dict, Any, FrozenSet, List, Optional, Tuple

@dataclass
class ASTNode:
    lineno: int = 0

@dataclass
class ThemeNode(ASTNode):
    name: str = ""
    properties: Dict[str, Any] = field(default_factory=dict)

@dataclass
class FieldRefNode(ASTNode):
    form_name: str = ""
    field_name: str = ""

@dataclass
class FormFieldNode(ASTNode):
    name: str = ""
    field_type: str = ""
    is_array: bool = False
    properties: Dict[str, Any] = field(default_factory=dict)
    # MODIFICADO (SDD): atributo sintetizado `checks` (verificações semânticas
    # calculadas pela ação da produção field_decl; ver semantic.py e tabela.md).
    checks: List[Any] = field(default_factory=list, repr=False, compare=False)

@dataclass
class ValidationBlockNode(ASTNode):
    field_name: str = ""
    rules: Dict[str, Any] = field(default_factory=dict)

@dataclass
class FormNode(ASTNode):
    name: str = ""
    fields: Dict[str, FormFieldNode] = field(default_factory=dict)
    validations: Dict[str, ValidationBlockNode] = field(default_factory=dict)
    # MODIFICADO (SDD): atributo sintetizado `checks` (ordenado).
    checks: List[Any] = field(default_factory=list, repr=False, compare=False)

@dataclass
class EndpointNode(ASTNode):
    method: str = ""
    route: str = ""
    consumes: Optional[str] = None
    produces: Optional[str] = None
    headers: Dict[str, str] = field(default_factory=dict)
    # MODIFICADO (SDD): atributo sintetizado `checks`.
    checks: List[Any] = field(default_factory=list, repr=False, compare=False)

@dataclass
class ApiNode(ASTNode):
    name: str = ""
    endpoints: List[EndpointNode] = field(default_factory=list)
    # MODIFICADO (SDD): atributo sintetizado `checks` (concatena os dos endpoints).
    checks: List[Any] = field(default_factory=list, repr=False, compare=False)

# MODIFICADO (expressões nas condições): `ConditionNode` (uma comparação) foi
# substituído por uma árvore de expressão. `deps` é um atributo SINTETIZADO
# local: conjunto de (etapa|None, campo) usados na subárvore.
@dataclass
class ExprNode(ASTNode):
    """Raiz das expressões de `when`."""
    deps: FrozenSet[Tuple[Optional[str], str]] = field(default_factory=frozenset, compare=False)

@dataclass
class FieldRefExpr(ExprNode):
    """`campo` (etapa de origem) ou `Etapa.campo`."""
    form_name: Optional[str] = None
    field_name: str = ""

@dataclass
class LiteralExpr(ExprNode):
    value: Any = None

@dataclass
class CompareExpr(ExprNode):
    op: str = ""                      # ==, !=, <, <=, >, >=
    left: Optional[ExprNode] = None
    right: Optional[ExprNode] = None

@dataclass
class InExpr(ExprNode):
    """`campo in (v1, v2)` / `campo not in (...)`."""
    target: Optional[FieldRefExpr] = None   # (nome `field` colidiria com dataclasses.field)
    values: List[LiteralExpr] = field(default_factory=list)
    negated: bool = False

@dataclass
class EmptyExpr(ExprNode):
    """`campo is empty` / `campo is not empty`."""
    target: Optional[FieldRefExpr] = None
    negated: bool = False

@dataclass
class NotExpr(ExprNode):
    operand: Optional[ExprNode] = None

@dataclass
class LogicExpr(ExprNode):
    op: str = ""                      # 'and' | 'or'
    left: Optional[ExprNode] = None
    right: Optional[ExprNode] = None

@dataclass
class TransitionNode(ASTNode):
    """
    Uma linha do flow: `Origem -> Destino [when ...];`.
    O destino é outra etapa (target_form) ou o envio para uma API
    (target_api + target_verb); nunca os dois.
    """
    source_form: str = ""
    target_form: Optional[str] = None
    target_api: Optional[str] = None
    target_verb: Optional[str] = None
    condition: Optional[ExprNode] = None
    # Atributo sintetizado `checks` (regra R4).
    checks: List[Any] = field(default_factory=list, repr=False, compare=False)

    @property
    def is_submit(self) -> bool:
        return self.target_api is not None

@dataclass
class FlowNode(ASTNode):
    """Fluxo da aplicação: etapas (formulários), caminhos e envio para a API."""
    name: str = ""
    transitions: List[TransitionNode] = field(default_factory=list)
    # MODIFICADO (SDD): atributo sintetizado `checks`.
    checks: List[Any] = field(default_factory=list, repr=False, compare=False)

@dataclass
class ProgramNode(ASTNode):
    theme: Optional[ThemeNode] = None
    forms: Dict[str, FormNode] = field(default_factory=dict)
    apis: Dict[str, ApiNode] = field(default_factory=dict)
    flow: Optional[FlowNode] = None
    # MODIFICADO (SDD): atributos sintetizados da produção raiz `program`:
    # tabela de símbolos e lista final de erros semânticos.
    symtab: Any = field(default=None, repr=False, compare=False)
    errors: List[Any] = field(default_factory=list, repr=False, compare=False)
    # MODIFICADO (avisos): diagnósticos que não impedem a compilação.
    warnings: List[Any] = field(default_factory=list, repr=False, compare=False)

class SymbolTable:
    def __init__(self):
        self.themes: Dict[str, ThemeNode] = {}
        self.forms: Dict[str, FormNode] = {}
        self.apis: Dict[str, ApiNode] = {}
        self.flows: Dict[str, FlowNode] = {}

    def insert_theme(self, theme: ThemeNode):
        self.themes[theme.name] = theme

    def insert_form(self, form: FormNode):
        self.forms[form.name] = form

    def insert_api(self, api: ApiNode):
        self.apis[api.name] = api

    def insert_flow(self, flow: FlowNode):
        self.flows[flow.name] = flow