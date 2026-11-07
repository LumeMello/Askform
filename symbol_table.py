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
Symbol Table and Abstract Syntax Tree (AST) node definitions with Theme and Wizard support.
"""
from dataclasses import dataclass, field
from typing import Dict, Any, List, Optional

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
class WizardNode(ASTNode):
    name: str = ""
    steps: List[str] = field(default_factory=list)
    target_api: Optional[str] = None
    target_verb: Optional[str] = None
    # MODIFICADO (SDD): atributo sintetizado `checks`.
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

@dataclass
class FlowNode(ASTNode):
    name: str = ""
    source_form: str = ""
    target_api: str = ""
    target_verb: str = ""
    # MODIFICADO (SDD): atributo sintetizado `checks`.
    checks: List[Any] = field(default_factory=list, repr=False, compare=False)

@dataclass
class ProgramNode(ASTNode):
    theme: Optional[ThemeNode] = None
    forms: Dict[str, FormNode] = field(default_factory=dict)
    wizards: Dict[str, WizardNode] = field(default_factory=dict)
    apis: Dict[str, ApiNode] = field(default_factory=dict)
    flow: Optional[FlowNode] = None
    # MODIFICADO (SDD): atributos sintetizados da produção raiz `program`:
    # tabela de símbolos e lista final de erros semânticos.
    symtab: Any = field(default=None, repr=False, compare=False)
    errors: List[Any] = field(default_factory=list, repr=False, compare=False)

class SymbolTable:
    def __init__(self):
        self.themes: Dict[str, ThemeNode] = {}
        self.forms: Dict[str, FormNode] = {}
        self.wizards: Dict[str, WizardNode] = {}
        self.apis: Dict[str, ApiNode] = {}
        self.flows: Dict[str, FlowNode] = {}

    def insert_theme(self, theme: ThemeNode):
        self.themes[theme.name] = theme

    def insert_form(self, form: FormNode):
        self.forms[form.name] = form

    def insert_wizard(self, wizard: WizardNode):
        self.wizards[wizard.name] = wizard

    def insert_api(self, api: ApiNode):
        self.apis[api.name] = api

    def insert_flow(self, flow: FlowNode):
        self.flows[flow.name] = flow