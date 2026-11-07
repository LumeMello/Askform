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
Analisador Semântico estendido para validação de Wizards, APIs, Flows e Herança de Valores.
"""
import re
from typing import Any
from symbol_table import ProgramNode, SymbolTable, FieldRefNode

class SemanticAnalyzer:
    def __init__(self):
        self.symbol_table = SymbolTable()
        self.errors = []

    def log_error(self, message: str, lineno: int):
        self.errors.append(f"Erro Semântico [Linha {lineno}]: {message}")

    def analyze(self, ast: ProgramNode) -> bool:
        self.build_symbols(ast)
        self.check_forms()
        self.check_wizards()
        self.check_apis()
        self.check_flows(ast.flow)
        return len(self.errors) == 0

    def build_symbols(self, ast: ProgramNode):
        for form in ast.forms.values():
            try:
                self.symbol_table.insert_form(form)
            except KeyError as ex:
                self.log_error(str(ex), form.lineno)
        for wizard in ast.wizards.values():
            try:
                self.symbol_table.insert_wizard(wizard)
            except KeyError as ex:
                self.log_error(str(ex), wizard.lineno)
        for api in ast.apis.values():
            try:
                self.symbol_table.insert_api(api)
            except KeyError as ex:
                self.log_error(str(ex), api.lineno)
        if ast.theme is not None:
            try:
                self.symbol_table.insert_theme(ast.theme)
            except KeyError as ex:
                self.log_error(str(ex), ast.theme.lineno)

        if ast.flow is not None:
            try:
                self.symbol_table.insert_flow(ast.flow)
            except KeyError as ex:
                self.log_error(str(ex), ast.flow.lineno)

    def check_forms(self):
        for form in self.symbol_table.forms.values():
            for field in form.fields.values():
                if 'default' in field.properties:
                    val = field.properties['default']
                    if isinstance(val, FieldRefNode):
                        self._check_field_reference(form.name, field, val)
                    elif not self._is_type_compatible(field.field_type, val):
                        self.log_error(
                            f"Valor padrão '{val}' é incompatível com o tipo '{field.field_type}' do campo '{field.name}'.",
                            field.lineno
                        )
            for target_field, v_block in form.validations.items():
                if target_field not in form.fields:
                    self.log_error(f"Validação referencia campo inexistente '{target_field}'.", v_block.lineno)
                    continue
                f_type = form.fields[target_field].field_type
                for rule, val in v_block.rules.items():
                    if rule in ('min', 'max'):
                        if f_type not in ('integer', 'float', 'string'):
                            self.log_error(f"Regra '{rule}' é incompatível com campo '{target_field}' do tipo '{f_type}'.", v_block.lineno)
                    elif rule == 'pattern':
                        if f_type != 'string':
                            self.log_error(f"Regra pattern aplicada a campo não-string '{target_field}'.", v_block.lineno)
                        try:
                            re.compile(val)
                        except re.error as e:
                            self.log_error(f"Expressão regular inválida no pattern: {str(e)}", v_block.lineno)

    def _check_field_reference(self, current_form_name: str, target_field: Any, ref: FieldRefNode):
        if ref.form_name not in self.symbol_table.forms:
            self.log_error(f"Referência inter-etapas para formulário inexistente '{ref.form_name}'.", ref.lineno)
            return
        source_form = self.symbol_table.forms[ref.form_name]
        if ref.field_name not in source_form.fields:
            self.log_error(f"Campo '{ref.field_name}' não existe na etapa de origem '{ref.form_name}'.", ref.lineno)
            return
        src_type = source_form.fields[ref.field_name].field_type
        if src_type != target_field.field_type:
            self.log_error(
                f"Incompatibilidade de tipos na herança: {ref.form_name}.{ref.field_name} ({src_type}) -> {current_form_name}.{target_field.name} ({target_field.field_type}).",
                target_field.lineno
            )

    def check_wizards(self):
        for wizard in self.symbol_table.wizards.values():
            seen_steps = []
            for step_form in wizard.steps:
                if step_form not in self.symbol_table.forms:
                    self.log_error(f"Wizard '{wizard.name}' referencia etapa indefinida '{step_form}'.", wizard.lineno)
                    continue
                form_obj = self.symbol_table.forms[step_form]
                for field in form_obj.fields.values():
                    val = field.properties.get('default')
                    if isinstance(val, FieldRefNode):
                        if val.form_name not in seen_steps:
                            self.log_error(
                                f"A etapa '{step_form}' tenta herdar o valor de '{val.form_name}' antes de ele ser renderizado no Wizard.",
                                field.lineno
                            )
                seen_steps.append(step_form)
            if wizard.target_api:
                if wizard.target_api not in self.symbol_table.apis:
                    self.log_error(f"Wizard '{wizard.name}' aponta para API inexistente '{wizard.target_api}'.", wizard.lineno)
                else:
                    api = self.symbol_table.apis[wizard.target_api]
                    if not any(ep.method == wizard.target_verb for ep in api.endpoints):
                        self.log_error(f"API '{wizard.target_api}' não suporta o verbo '{wizard.target_verb}'.", wizard.lineno)

    def check_apis(self):
        for api in self.symbol_table.apis.values():
            for ep in api.endpoints:
                if ep.consumes:
                    is_form = ep.consumes in self.symbol_table.forms
                    is_wizard = ep.consumes in self.symbol_table.wizards
                    if not (is_form or is_wizard):
                        self.log_error(f"Endpoint '{ep.method} {ep.route}' consome formulário ou wizard inexistente '{ep.consumes}'.", ep.lineno)
                    elif is_form:
                        form = self.symbol_table.forms[ep.consumes]
                        params = re.findall(r'\{([a-zA-Z_][a-zA-Z0-9_]*)\}', ep.route)
                        for p in params:
                            if p not in form.fields:
                                self.log_error(f"Parâmetro de rota '{{{p}}}' não declarado no formulário '{form.name}'.", ep.lineno)

    def check_flows(self, flow):
        if flow is None:
            return

        valid_source = (
            flow.source_form in self.symbol_table.forms
            or flow.source_form in self.symbol_table.wizards
        )
        if not valid_source:
            self.log_error(
                f"Flow '{flow.name}' referencia origem inexistente '{flow.source_form}'.",
                flow.lineno,
            )
        if flow.target_api not in self.symbol_table.apis:
            self.log_error(
                f"Flow '{flow.name}' referencia API inexistente '{flow.target_api}'.",
                flow.lineno,
            )
        else:
            target = self.symbol_table.apis[flow.target_api]
            if not any(ep.method == flow.target_verb for ep in target.endpoints):
                self.log_error(
                    f"API destino '{flow.target_api}' não suporta o verbo '{flow.target_verb}' no flow.",
                    flow.lineno,
                )

    def _is_type_compatible(self, declared_type: str, val: Any) -> bool:
        if declared_type == 'string' and isinstance(val, str):
            return True
        if declared_type == 'integer' and isinstance(val, int) and not isinstance(val, bool):
            return True
        if declared_type == 'float' and isinstance(val, (float, int)):
            return True
        if declared_type == 'boolean' and isinstance(val, bool):
            return True
        return False
