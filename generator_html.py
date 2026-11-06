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
Gerador HTML do Askform.

Gera formulários HTML com escaping contextual, configuração de tema validada,
fallback automático de URL base do servidor (localhost:5000) e chamadas fetch.
"""
import html
import json
import os
import re
from typing import Any, Dict, List, Tuple

from symbol_table import ProgramNode, FormNode


class CodeWriter:
    def __init__(self, indent_size: int = 2):
        self.indent_size = indent_size
        self._indent_level = 0
        self.lines: List[str] = []

    def indent(self):
        self._indent_level += 1

    def dedent(self):
        if self._indent_level > 0:
            self._indent_level -= 1

    def write_line(self, line: str = ""):
        if not line:
            self.lines.append("")
        else:
            prefix = " " * (self._indent_level * self.indent_size)
            self.lines.append(f"{prefix}{line}")

    def get_code(self) -> str:
        return "\n".join(self.lines) + "\n"


_ALLOWED_METHODS = {"GET", "POST", "PUT", "PATCH", "DELETE"}
_IDENTIFIER_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_ROUTE_PARAM_RE = re.compile(r"\{([A-Za-z_][A-Za-z0-9_]*)\}")
_COLOR_RE = re.compile(
    r"^(#[0-9a-fA-F]{3,8}|[a-zA-Z]{1,24}|"
    r"rgba?\([0-9.,% ]+\)|hsla?\([0-9.,% ]+\))$"
)
_LENGTH_RE = re.compile(r"^(0|[0-9]+(?:\.[0-9]+)?(?:px|rem|em|%|vw|vh))$")
_FONT_RE = re.compile(r"^[A-Za-z0-9 ,_'\"-]{1,160}$")


def _escape(value: Any) -> str:
    """Escapa texto/atributos HTML; não deve ser usado para JavaScript ou CSS."""
    return html.escape(str(value), quote=True)


def _js_string(value: Any) -> str:
    """Serializa uma string como literal JavaScript seguro."""
    return json.dumps(str(value), ensure_ascii=False).replace("</", "<\\/")


def _identifier(value: Any, description: str) -> str:
    if not isinstance(value, str) or not _IDENTIFIER_RE.fullmatch(value):
        raise ValueError(f"{description} inválido: {value!r}")
    return value


def _safe_css_value(value: Any, kind: str, default: str) -> str:
    """Aceita apenas subconjuntos simples de valores CSS, sem blocos/URLs."""
    candidate = str(value).strip()
    if kind == "color":
        valid = bool(_COLOR_RE.fullmatch(candidate))
    elif kind == "length":
        valid = bool(_LENGTH_RE.fullmatch(candidate))
    elif kind == "font":
        valid = bool(_FONT_RE.fullmatch(candidate))
    else:
        valid = False
    if not valid or any(token in candidate.lower() for token in ("url(", "expression", "javascript:")):
        return default
    return candidate


def _resolve_form_endpoint(form_name: str, ast: ProgramNode) -> Tuple[str, str]:
    """Resolve rota e verbo do endpoint que efetivamente consome o formulário."""
    flow = ast.flow
    if (
        flow is not None
        and flow.source_form == form_name
        and flow.target_api in ast.apis
    ):
        api = ast.apis[flow.target_api]
        desired_method = str(flow.target_verb).upper()
        for endpoint in api.endpoints:
            if (
                endpoint.consumes == form_name
                and str(endpoint.method).upper() == desired_method
            ):
                return endpoint.route, desired_method

    for api in ast.apis.values():
        for endpoint in api.endpoints:
            if endpoint.consumes == form_name:
                return endpoint.route, str(endpoint.method).upper()

    return f"/api/{form_name.lower()}/submit", "POST"


def _validate_route(route: Any, method: str, field_names: set) -> Tuple[str, List[str]]:
    if not isinstance(route, str) or not route.startswith("/") or len(route) > 500:
        raise ValueError(f"Rota inválida: {route!r}")
    if "?" in route or "#" in route or "\\" in route:
        raise ValueError(f"Rota deve ser um caminho sem query string ou fragmento: {route!r}")

    params = _ROUTE_PARAM_RE.findall(route)
    stripped = _ROUTE_PARAM_RE.sub("", route)
    if "{" in stripped or "}" in stripped:
        raise ValueError(f"Parâmetro de rota inválido: {route!r}")
    if len(params) != len(set(params)):
        raise ValueError(f"Parâmetro de rota repetido: {route!r}")
    missing = set(params) - field_names
    if missing:
        raise ValueError(
            "Parâmetros de rota sem campo correspondente no formulário: "
            + ", ".join(sorted(missing))
        )
    if method in {"PUT", "PATCH", "DELETE"} and not params:
        raise ValueError(
            f"O método {method} exige ao menos um parâmetro na rota para identificar o registro."
        )
    return route, params


def _field_type(field: Any) -> str:
    return str(getattr(field, "field_type", "string")).lower()


def _render_form_html(form: FormNode, ast: ProgramNode) -> str:
    route_template, http_method = _resolve_form_endpoint(form.name, ast)
    http_method = str(http_method).upper()
    if http_method not in _ALLOWED_METHODS:
        raise ValueError(f"Método HTTP não suportado para o formulário {form.name}: {http_method}")

    field_names = set(form.fields.keys())
    for field_name in field_names:
        _identifier(field_name, "Nome de campo")
    _identifier(form.name, "Nome de formulário")

    route_template, route_params = _validate_route(route_template, http_method, field_names)

    theme_props: Dict[str, Any] = ast.theme.properties if ast.theme else {}

    bg_color = _safe_css_value(theme_props.get("background", "#f8fafc"), "color", "#f8fafc")
    card_bg = _safe_css_value(theme_props.get("card_background", "#ffffff"), "color", "#ffffff")
    text_color = _safe_css_value(theme_props.get("text_color", "#1e293b"), "color", "#1e293b")
    accent = _safe_css_value(theme_props.get("accent_color", "#2563eb"), "color", "#2563eb")
    font = _safe_css_value(
        theme_props.get("font_family", "Arial, sans-serif"), "font", "Arial, sans-serif"
    )
    radius = _safe_css_value(theme_props.get("border_radius", "8px"), "length", "8px")

    form_id = f"askform-{form.name}"
    w = CodeWriter(indent_size=2)
    w.write_line("<!DOCTYPE html>")
    w.write_line('<html lang="pt-BR">')
    w.write_line("<head>")
    w.indent()
    w.write_line('<meta charset="UTF-8">')
    w.write_line('<meta name="viewport" content="width=device-width, initial-scale=1.0">')
    w.write_line(f"<title>{_escape(form.name)}</title>")
    w.write_line("<style>")
    w.indent()
    w.write_line(
        f"body {{ font-family: {font}; margin: 2rem; background: {bg_color}; color: {text_color}; }}"
    )
    w.write_line(
        f".card {{ max-width: 520px; margin: 0 auto; background: {card_bg}; "
        f"padding: 2rem; border-radius: {radius}; box-shadow: 0 4px 6px -1px rgb(0 0 0 / 0.1); }}"
    )
    w.write_line(".form-group { margin-bottom: 1.25rem; }")
    w.write_line("label { display: block; margin-bottom: 0.375rem; font-weight: 600; font-size: 0.875rem; }")
    w.write_line(
        'input, textarea, select { width: 100%; box-sizing: border-box; padding: 0.5rem 0.75rem; '
        'border: 1px solid #cbd5e1; border-radius: 4px; font-size: 0.875rem; }'
    )
    w.write_line('input[type="checkbox"] { width: auto; }')
    w.write_line(
        f"button {{ width: 100%; padding: 0.75rem; font-weight: 600; border-radius: {radius}; "
        f"cursor: pointer; border: none; background: {accent}; color: #fff; margin-top: 1rem; }}"
    )
    w.write_line("button:disabled { opacity: .65; cursor: wait; }")
    w.write_line(".response-output { margin-top: 1rem; padding: 0.75rem; border-radius: 4px; font-family: monospace; font-size: 0.75rem; display: none; white-space: pre-wrap; word-break: break-word; }")
    w.write_line(".response-success { background: #f0fdf4; border: 1px solid #bbf7d0; color: #166534; }")
    w.write_line(".response-error { background: #fef2f2; border: 1px solid #fecaca; color: #991b1b; }")
    w.dedent()
    w.write_line("</style>")
    w.dedent()
    w.write_line("</head>")
    w.write_line("<body>")
    w.indent()
    w.write_line('<main class="card">')
    w.indent()
    w.write_line(f"<h2>{_escape(form.name)}</h2>")
    w.write_line(
        f'<form id="{_escape(form_id)}" enctype="multipart/form-data" novalidate>'
    )
    w.indent()

    for field_name, field in form.fields.items():
        properties = getattr(field, "properties", {}) or {}
        label = _escape(properties.get("label", field_name))
        field_id = _escape(field_name)
        field_type = _field_type(field)
        required = bool(properties.get("required", False))
        required_attr = " required" if required else ""
        default = properties.get("default")
        default_attr = f' value="{_escape(default)}"' if default is not None and field_type != "file" else ""
        validation = getattr(form, "validations", {}).get(field_name)
        rules = getattr(validation, "rules", {}) if validation else {}
        min_value = rules.get("min", properties.get("min"))
        max_value = rules.get("max", properties.get("max"))
        min_attr = f' min="{_escape(min_value)}"' if min_value is not None and field_type in ("integer", "float", "date") else ""
        max_attr = f' max="{_escape(max_value)}"' if max_value is not None and field_type in ("integer", "float", "date") else ""
        if field_type in ("string", "uuid"):
            min_attr = f' minlength="{_escape(min_value)}"' if min_value is not None else ""
            max_attr = f' maxlength="{_escape(max_value)}"' if max_value is not None else ""
        pattern = rules.get("pattern", properties.get("pattern"))
        pattern_attr = f' pattern="{_escape(pattern)}"' if pattern and field_type in ("string", "uuid") else ""

        if field_type == "file":
            input_type = "file"
            accept_attr = ""
        elif field_type in ("integer", "float"):
            input_type = "number"
            accept_attr = ' step="1"' if field_type == "integer" else ' step="any"'
        elif field_type == "date":
            input_type = "date"
            accept_attr = ""
        elif field_type == "boolean":
            input_type = "checkbox"
            accept_attr = ""
        else:
            input_type = "text"
            accept_attr = ""

        w.write_line('<div class="form-group">')
        w.indent()
        w.write_line(f'<label for="{field_id}">{label}</label>')
        checked_attr = (
            " checked" if field_type == "boolean" and bool(default) else ""
        )
        w.write_line(
            f'<input type="{input_type}" id="{field_id}" name="{field_id}"'
            f'{accept_attr}{required_attr}{min_attr}{max_attr}{pattern_attr}{default_attr}{checked_attr}>'
        )
        w.dedent()
        w.write_line("</div>")

    w.write_line('<button id="askform-submit" type="submit">Enviar dados</button>')
    w.dedent()
    w.write_line("</form>")
    w.write_line('<div id="responseOutput" class="response-output" role="status" aria-live="polite"></div>')
    w.dedent()
    w.write_line("</main>")
    w.write_line("<script>")
    w.indent()
    w.write_line("'use strict';")
    w.write_line(f"const formElement = document.getElementById({_js_string(form_id)});")
    w.write_line("const outputDiv = document.getElementById('responseOutput');")
    w.write_line("const submitButton = document.getElementById('askform-submit');")
    w.write_line(f"const routeTemplate = {_js_string(route_template)};")
    w.write_line(f"const httpMethod = {_js_string(http_method)};")
    w.write_line("const routeParams = " + json.dumps(route_params, ensure_ascii=False) + ";")
    w.write_line("const defaultApiBase = 'http://127.0.0.1:5000';")
    w.write_line("const apiBaseUrl = (document.documentElement.dataset.apiBase || defaultApiBase).replace(/\\/$/, '');")
    w.write_line()
    w.write_line("formElement.addEventListener('submit', async function (event) {")
    w.indent()
    w.write_line("event.preventDefault();")
    w.write_line("if (!formElement.reportValidity()) return;")
    w.write_line("outputDiv.style.display = 'none';")
    w.write_line("submitButton.disabled = true;")
    w.write_line("try {")
    w.indent()
    w.write_line("const formData = new FormData(formElement);")
    w.write_line("for (const element of formElement.elements) {")
    w.indent()
    w.write_line("if (element.type === 'checkbox' && element.name && !element.checked) formData.set(element.name, 'false');")
    w.dedent()
    w.write_line("}")
    w.write_line("let targetPath = routeTemplate;")
    w.write_line("for (const paramName of routeParams) {")
    w.indent()
    w.write_line("const paramValue = formData.get(paramName);")
    w.write_line("if (paramValue === null || paramValue === '') throw new Error('Informe o campo usado na rota: ' + paramName);")
    w.write_line("if (paramValue instanceof File) throw new Error('Arquivo não pode ser usado como parâmetro de rota.');")
    w.write_line("targetPath = targetPath.replace('{' + paramName + '}', encodeURIComponent(String(paramValue)));")
    w.write_line("if (httpMethod !== 'POST') formData.delete(paramName);")
    w.dedent()
    w.write_line("}")
    w.write_line("const headers = {};")
    w.write_line("const options = { method: httpMethod, headers: headers };")
    w.write_line("let targetUrl = apiBaseUrl + targetPath;")
    w.write_line("if (httpMethod === 'GET') {")
    w.indent()
    w.write_line("const query = new URLSearchParams();")
    w.write_line("for (const [key, value] of formData.entries()) {")
    w.indent()
    w.write_line("if (value instanceof File) continue;")
    w.write_line("query.append(key, String(value));")
    w.dedent()
    w.write_line("}")
    w.write_line("const queryString = query.toString();")
    w.write_line("if (queryString) targetUrl += (targetUrl.includes('?') ? '&' : '?') + queryString;")
    w.dedent()
    w.write_line("} else if (httpMethod !== 'DELETE') {")
    w.indent()
    w.write_line("options.body = formData;")
    w.dedent()
    w.write_line("}")
    w.write_line("const response = await fetch(targetUrl, options);")
    w.write_line("const responseText = await response.text();")
    w.write_line("let responseData;")
    w.write_line("try { responseData = responseText ? JSON.parse(responseText) : {}; }")
    w.write_line("catch (_parseError) { throw new Error('O servidor retornou uma resposta que não é JSON válido.'); }")
    w.write_line("outputDiv.style.display = 'block';")
    w.write_line("if (response.ok) {")
    w.indent()
    w.write_line("outputDiv.className = 'response-output response-success';")
    w.write_line("outputDiv.textContent = JSON.stringify(responseData, null, 2);")
    w.dedent()
    w.write_line("} else {")
    w.indent()
    w.write_line("outputDiv.className = 'response-output response-error';")
    w.write_line("outputDiv.textContent = 'Erro ' + response.status + ': ' + (responseData.message || 'Não foi possível concluir a solicitação.');")
    w.dedent()
    w.write_line("}")
    w.dedent()
    w.write_line("} catch (error) {")
    w.indent()
    w.write_line("outputDiv.style.display = 'block';")
    w.write_line("outputDiv.className = 'response-output response-error';")
    w.write_line("outputDiv.textContent = 'Falha na solicitação: ' + error.message;")
    w.dedent()
    w.write_line("} finally {")
    w.indent()
    w.write_line("submitButton.disabled = false;")
    w.dedent()
    w.write_line("}")
    w.dedent()
    w.write_line("});")
    w.dedent()
    w.write_line("</script>")
    w.dedent()
    w.write_line("</body>")
    w.write_line("</html>")
    return w.get_code()


def generate_html(ast: ProgramNode, output_dir: str = "dist"):
    """Gera um arquivo HTML por formulário e retorna os caminhos criados."""
    os.makedirs(output_dir, exist_ok=True)
    generated_files = []
    for form_name, form in ast.forms.items():
        _identifier(form_name, "Nome de formulário")
        filename = f"{form_name.lower()}.html"
        filepath = os.path.join(output_dir, filename)
        rendered = _render_form_html(form, ast)
        with open(filepath, "w", encoding="utf-8", newline="\n") as output_file:
            output_file.write(rendered)
        generated_files.append(filepath)
        print(f"[SUCESSO] Formulário HTML gerado: {filepath}")
    return generated_files
