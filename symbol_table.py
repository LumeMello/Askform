"""
Symbol Table e nós de AST atualizados para suporte a Wizards e Propagação Inter-etapas.
"""
from dataclasses import dataclass, field
from typing import Dict, Any, List, Optional

@dataclass
class ASTNode:
    lineno: int = 0

@dataclass
class FieldRefNode(ASTNode):
    """Representa uma referência cruzada: EtapaOrigem.campoOrigem"""
    form_name: str = ""
    field_name: str = ""

@dataclass
class FormFieldNode(ASTNode):
    name: str = ""
    field_type: str = ""
    is_array: bool = False
    properties: Dict[str, Any] = field(default_factory=dict)

@dataclass
class ValidationBlockNode(ASTNode):
    field_name: str = ""
    rules: Dict[str, Any] = field(default_factory=dict)

@dataclass
class FormNode(ASTNode):
    name: str = ""
    fields: Dict[str, FormFieldNode] = field(default_factory=dict)
    validations: Dict[str, ValidationBlockNode] = field(default_factory=dict)

@dataclass
class WizardNode(ASTNode):
    name: str = ""
    steps: List[str] = field(default_factory=list)
    target_api: Optional[str] = None
    target_verb: Optional[str] = None

@dataclass
class EndpointNode(ASTNode):
    method: str = ""
    route: str = ""
    consumes: Optional[str] = None
    produces: Optional[str] = None

@dataclass
class ApiNode(ASTNode):
    name: str = ""
    endpoints: List[EndpointNode] = field(default_factory=list)

@dataclass
class FlowNode(ASTNode):
    name: str = ""
    source_form: str = ""
    target_api: str = ""
    target_verb: str = ""

@dataclass
class ProgramNode(ASTNode):
    forms: Dict[str, FormNode] = field(default_factory=dict)
    wizards: Dict[str, WizardNode] = field(default_factory=dict)
    apis: Dict[str, ApiNode] = field(default_factory=dict)
    flows: Dict[str, FlowNode] = field(default_factory=dict)

class SymbolTable:
    def __init__(self):
        self.forms: Dict[str, FormNode] = {}
        self.wizards: Dict[str, WizardNode] = {}
        self.apis: Dict[str, ApiNode] = {}
        self.flows: Dict[str, FlowNode] = {}

    def insert_form(self, form: FormNode):
        if form.name in self.forms:
            raise KeyError(f"Form '{form.name}' já declarado na linha {self.forms[form.name].lineno}.")
        self.forms[form.name] = form

    def insert_wizard(self, wizard: WizardNode):
        if wizard.name in self.wizards:
            raise KeyError(f"Wizard '{wizard.name}' já declarado na linha {self.wizards[wizard.name].lineno}.")
        self.wizards[wizard.name] = wizard

    def insert_api(self, api: ApiNode):
        if api.name in self.apis:
            raise KeyError(f"API '{api.name}' já declarada na linha {self.apis[api.name].lineno}.")
        self.apis[api.name] = api

    def insert_flow(self, flow: FlowNode):
        if flow.name in self.flows:
            raise KeyError(f"Flow '{flow.name}' já declarado na linha {self.flows[flow.name].lineno}.")
        self.flows[flow.name] = flow
