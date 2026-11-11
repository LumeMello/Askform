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

Um flow de uma linha (`Form -> Api.VERBO;`) gera a página do próprio
formulário, como antes. Um flow com várias etapas ou com caminhos (`when`)
gera uma única página multi-etapas (<flow>.html) com navegação Voltar/Próximo.
"""
import html
import json
import os
import re
from typing import Any, Dict, List, Tuple

from flow_graph import FlowGraph
from symbol_table import ProgramNode, FormNode, FieldRefNode
from expressions import Escopo, para_json


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
    simple = flow.transitions[0] if flow is not None and FlowGraph(flow).is_simple() else None
    if (
        simple is not None
        and simple.source_form == form_name
        and simple.target_api in ast.apis
    ):
        api = ast.apis[simple.target_api]
        desired_method = str(simple.target_verb).upper()
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


def _theme_values(ast: ProgramNode) -> Dict[str, str]:
    theme_props: Dict[str, Any] = ast.theme.properties if ast.theme else {}
    return {
        "bg_color": _safe_css_value(theme_props.get("background", "#f8fafc"), "color", "#f8fafc"),
        "card_bg": _safe_css_value(theme_props.get("card_background", "#ffffff"), "color", "#ffffff"),
        "text_color": _safe_css_value(theme_props.get("text_color", "#1e293b"), "color", "#1e293b"),
        "accent": _safe_css_value(theme_props.get("accent_color", "#2563eb"), "color", "#2563eb"),
        "font": _safe_css_value(
            theme_props.get("font_family", "Arial, sans-serif"), "font", "Arial, sans-serif"
        ),
        "radius": _safe_css_value(theme_props.get("border_radius", "8px"), "length", "8px"),
    }


def _write_head(w: CodeWriter, title: str, t: Dict[str, str], extra_css: Tuple[str, ...] = ()) -> None:
    bg_color, card_bg, text_color = t["bg_color"], t["card_bg"], t["text_color"]
    accent, font, radius = t["accent"], t["font"], t["radius"]
    w.write_line("<!DOCTYPE html>")
    w.write_line('<html lang="pt-BR">')
    w.write_line("<head>")
    w.indent()
    w.write_line('<meta charset="UTF-8">')
    w.write_line('<meta name="viewport" content="width=device-width, initial-scale=1.0">')
    w.write_line(f"<title>{_escape(title)}</title>")
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
    for css_line in extra_css:
        w.write_line(css_line)
    w.dedent()
    w.write_line("</style>")
    w.dedent()
    w.write_line("</head>")


def _write_field(w: CodeWriter, form: FormNode, field_name: str, field: Any, field_id: str) -> None:
    properties = getattr(field, "properties", {}) or {}
    label = _escape(properties.get("label", field_name))
    field_id = _escape(field_id)
    field_type = _field_type(field)
    required = bool(properties.get("required", False))
    required_attr = " required" if required else ""
    default = properties.get("default")
    if isinstance(default, FieldRefNode):
        # Herança entre etapas: o valor é copiado em tempo de execução (página do flow).
        default = None
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
        f'<input type="{input_type}" id="{field_id}" name="{_escape(field_name)}"'
        f'{accept_attr}{required_attr}{min_attr}{max_attr}{pattern_attr}{default_attr}{checked_attr}>'
    )
    w.dedent()
    w.write_line("</div>")


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

    t = _theme_values(ast)
    form_id = f"askform-{form.name}"
    w = CodeWriter(indent_size=2)
    _write_head(w, form.name, t)
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
        _write_field(w, form, field_name, field, field_name)

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


_FLOW_CSS = (
    "[hidden] { display: none !important; }",
    ".progress { margin: 0 0 0.25rem; font-size: 0.75rem; text-transform: uppercase; letter-spacing: .05em; opacity: .7; }",
    ".actions { display: flex; gap: 0.75rem; }",
    ".actions button.secondary { background: transparent; color: inherit; border: 1px solid #cbd5e1; }",
)

# MODIFICADO (expressões): avaliador PURO das condições (sem DOM), com a mesma
# semântica de expressions.avaliar_json. `get(etapa, campo, tipo)` devolve o
# valor ou null (vazio). Fica em constante própria para ser testado sem página.
_EVAL_JS = r"""
function evalExpr(n, get) {
  function val(op) { return op.k === 'lit' ? op.v : get(op.step, op.name, op.type); }
  switch (n.k) {
    case 'or': return evalExpr(n.l, get) || evalExpr(n.r, get);
    case 'and': return evalExpr(n.l, get) && evalExpr(n.r, get);
    case 'not': return !evalExpr(n.e, get);
    case 'lit': return n.v === true;
    case 'field': return get(n.step, n.name, n.type) === true;
    case 'cmp': {
      const a = val(n.l), b = val(n.r);
      if (a === null || b === null) return false;
      switch (n.op) {
        case '==': return a === b;
        case '!=': return a !== b;
        case '<': return a < b;
        case '<=': return a <= b;
        case '>': return a > b;
        default: return a >= b;
      }
    }
    case 'in': {
      const v = val(n.f);
      if (v === null) return false;
      const found = n.v.includes(v);
      return n.neg ? !found : found;
    }
    case 'empty': {
      const empty = val(n.f) === null;
      return n.neg ? !empty : empty;
    }
    default: throw new Error('nó de expressão desconhecido: ' + n.k);
  }
}
"""

# Script da página multi-etapas. `flow` é injetado antes deste trecho.
_FLOW_SCRIPT = r"""
const outputDiv = document.getElementById('responseOutput');
const nextButton = document.getElementById('askform-next');
const backButton = document.getElementById('askform-back');
const titleElement = document.getElementById('askform-title');
const progressElement = document.getElementById('askform-progress');
const defaultApiBase = 'http://127.0.0.1:5000';
const apiBaseUrl = (document.documentElement.dataset.apiBase || defaultApiBase).replace(/\/$/, '');
const stepForms = {};
for (const element of document.querySelectorAll('form[data-step]')) stepForms[element.dataset.step] = element;
// Caminho percorrido até a etapa atual; "Voltar" desfaz a última escolha.
const path = [flow.start];

function fieldOf(step, fieldName) {
  const form = stepForms[step];
  return form ? form.elements.namedItem(fieldName) : null;
}

// Leitura do valor de um campo no DOM: null = vazio; boolean nunca é vazio.
function domValue(step, name, type) {
  const element = fieldOf(step, name);
  if (!element) return null;
  if (type === 'boolean') return element.checked;
  if (element.value === '') return null;
  if (type === 'integer' || type === 'float') {
    const number = Number(element.value);
    return Number.isNaN(number) ? null : number;
  }
  if (type === 'uuid') return element.value.trim().toLowerCase();
  return element.value;
}

function matches(condition) {
  if (!condition) return true;
  return evalExpr(condition, domValue);
}

function applyInheritance(step) {
  for (const [fieldName, sourceStep, sourceField] of (flow.inherit[step] || [])) {
    const target = fieldOf(step, fieldName);
    const source = fieldOf(sourceStep, sourceField);
    if (!target || !source || target.type === 'file' || target.dataset.edited === 'true') continue;
    if (target.type === 'checkbox') target.checked = source.checked;
    else target.value = source.value;
  }
}

function showStep(step) {
  for (const [name, form] of Object.entries(stepForms)) form.hidden = name !== step;
  applyInheritance(step);
  titleElement.textContent = flow.steps[step].title;
  progressElement.textContent = 'Etapa ' + path.length;
  backButton.disabled = path.length === 1;
  nextButton.textContent = flow.steps[step].transitions.every(t => t.submit) ? 'Enviar dados' : 'Próximo';
}

function showResult(ok, text) {
  outputDiv.style.display = 'block';
  outputDiv.className = 'response-output ' + (ok ? 'response-success' : 'response-error');
  outputDiv.textContent = text;
}

async function submitFlow(endpoint) {
  nextButton.disabled = true;
  backButton.disabled = true;
  try {
    // Só as etapas do caminho percorrido são enviadas.
    const formData = new FormData();
    for (const step of path) {
      const form = stepForms[step];
      for (const [key, value] of new FormData(form).entries()) formData.append(key, value);
      for (const element of form.elements) {
        if (element.type === 'checkbox' && element.name && !element.checked) formData.set(element.name, 'false');
      }
    }
    let targetPath = endpoint.route;
    for (const paramName of endpoint.params) {
      const paramValue = formData.get(paramName);
      if (paramValue === null || paramValue === '') throw new Error('Informe o campo usado na rota: ' + paramName);
      if (paramValue instanceof File) throw new Error('Arquivo não pode ser usado como parâmetro de rota.');
      targetPath = targetPath.replace('{' + paramName + '}', encodeURIComponent(String(paramValue)));
      if (endpoint.method !== 'POST') formData.delete(paramName);
    }
    const options = { method: endpoint.method, headers: {} };
    let targetUrl = apiBaseUrl + targetPath;
    if (endpoint.method === 'GET') {
      const query = new URLSearchParams();
      for (const [key, value] of formData.entries()) {
        if (value instanceof File) continue;
        query.append(key, String(value));
      }
      const queryString = query.toString();
      if (queryString) targetUrl += (targetUrl.includes('?') ? '&' : '?') + queryString;
    } else if (endpoint.method !== 'DELETE') {
      options.body = formData;
    }
    const response = await fetch(targetUrl, options);
    const responseText = await response.text();
    let responseData;
    try { responseData = responseText ? JSON.parse(responseText) : {}; }
    catch (_parseError) { throw new Error('O servidor retornou uma resposta que não é JSON válido.'); }
    if (response.ok) showResult(true, JSON.stringify(responseData, null, 2));
    else showResult(false, 'Erro ' + response.status + ': ' + (responseData.message || 'Não foi possível concluir a solicitação.'));
  } catch (error) {
    showResult(false, 'Falha na solicitação: ' + error.message);
  } finally {
    nextButton.disabled = false;
    backButton.disabled = path.length === 1;
  }
}

async function goNext() {
  const current = path[path.length - 1];
  if (!stepForms[current].reportValidity()) return;
  outputDiv.style.display = 'none';
  // As transições são testadas na ordem; a primeira que casa decide o caminho.
  const transition = flow.steps[current].transitions.find(t => matches(t.when));
  if (!transition) {
    showResult(false, 'Nenhum caminho disponível a partir desta etapa.');
    return;
  }
  if (transition.goto) {
    path.push(transition.goto);
    showStep(transition.goto);
  } else {
    await submitFlow(transition.submit);
  }
}

for (const form of Object.values(stepForms)) {
  form.addEventListener('submit', function (event) { event.preventDefault(); goNext(); });
  // Campo alterado pelo usuário deixa de receber o valor herdado.
  form.addEventListener('input', function (event) { if (event.target.name) event.target.dataset.edited = 'true'; });
}
nextButton.addEventListener('click', goNext);
backButton.addEventListener('click', function () {
  if (path.length === 1) return;
  path.pop();
  outputDiv.style.display = 'none';
  showStep(path[path.length - 1]);
});
showStep(flow.start);
"""


def _flow_steps(ast: ProgramNode) -> set:
    """Formulários renderizados pela página multi-etapas (flow não simples)."""
    flow = ast.flow
    if flow is None:
        return set()
    graph = FlowGraph(flow)
    return set() if graph.is_simple() else set(graph.steps)


def _resolve_submit_endpoint(transition: Any, flow_name: str, ast: ProgramNode):
    """Endpoint do envio `Origem -> Api.VERBO`: prefere o que consome o flow."""
    api = ast.apis[transition.target_api]
    method = str(transition.target_verb).upper()
    candidates = [ep for ep in api.endpoints if str(ep.method).upper() == method]
    for wanted in (flow_name, transition.source_form):
        for endpoint in candidates:
            if endpoint.consumes == wanted:
                return endpoint.route, method
    return candidates[0].route, method


def _render_flow_html(ast: ProgramNode) -> str:
    flow = ast.flow
    graph = FlowGraph(flow)
    _identifier(flow.name, "Nome de flow")

    field_names = set()
    for step in graph.steps:
        _identifier(step, "Nome de formulário")
        for field_name in ast.forms[step].fields:
            _identifier(field_name, "Nome de campo")
            field_names.add(field_name)

    steps_config: Dict[str, Any] = {}
    inherit: Dict[str, List[List[str]]] = {}
    for step in graph.steps:
        form = ast.forms[step]
        transitions = []
        for t in graph.outgoing.get(step, []):
            item: Dict[str, Any] = {"when": None}
            if t.condition is not None:
                # MODIFICADO (expressões): árvore da expressão (and/or/not/in...).
                item["when"] = para_json(t.condition, Escopo(flow.name, t.source_form), ast.forms)
            if t.target_form is not None:
                item["goto"] = t.target_form
            else:
                route, method = _resolve_submit_endpoint(t, flow.name, ast)
                if method not in _ALLOWED_METHODS:
                    raise ValueError(f"Método HTTP não suportado no flow {flow.name}: {method}")
                route, params = _validate_route(route, method, field_names)
                item["submit"] = {"method": method, "route": route, "params": params}
            transitions.append(item)
        steps_config[step] = {
            "title": step,
            "transitions": transitions,
        }
        for field_name, field in form.fields.items():
            ref = (getattr(field, "properties", {}) or {}).get("default")
            if isinstance(ref, FieldRefNode):
                inherit.setdefault(step, []).append([field_name, ref.form_name, ref.field_name])

    config = {"start": graph.start, "steps": steps_config, "inherit": inherit}

    w = CodeWriter(indent_size=2)
    _write_head(w, flow.name, _theme_values(ast), _FLOW_CSS)
    w.write_line("<body>")
    w.indent()
    w.write_line('<main class="card">')
    w.indent()
    w.write_line('<p id="askform-progress" class="progress">Etapa 1</p>')
    w.write_line(f'<h2 id="askform-title">{_escape(graph.start)}</h2>')
    for step in graph.steps:
        form = ast.forms[step]
        hidden_attr = "" if step == graph.start else " hidden"
        w.write_line(
            f'<form id="askform-{_escape(step)}" data-step="{_escape(step)}" '
            f'enctype="multipart/form-data" novalidate{hidden_attr}>'
        )
        w.indent()
        for field_name, field in form.fields.items():
            _write_field(w, form, field_name, field, f"{step}__{field_name}")
        # Permite avançar com Enter sem um botão visível dentro de cada etapa.
        w.write_line('<button type="submit" hidden></button>')
        w.dedent()
        w.write_line("</form>")
    w.write_line('<div class="actions">')
    w.indent()
    w.write_line('<button id="askform-back" type="button" class="secondary" disabled>Voltar</button>')
    w.write_line('<button id="askform-next" type="button">Próximo</button>')
    w.dedent()
    w.write_line("</div>")
    w.write_line('<div id="responseOutput" class="response-output" role="status" aria-live="polite"></div>')
    w.dedent()
    w.write_line("</main>")
    w.write_line("<script>")
    w.indent()
    w.write_line("'use strict';")
    config_json = json.dumps(config, ensure_ascii=False).replace("</", "<\\/")
    w.write_line(f"const flow = {config_json};")
    for line in (_EVAL_JS.strip("\n") + "\n" + _FLOW_SCRIPT.strip("\n")).split("\n"):
        w.write_line(line)
    w.dedent()
    w.write_line("</script>")
    w.dedent()
    w.write_line("</body>")
    w.write_line("</html>")
    return w.get_code()


def generate_html(ast: ProgramNode, output_dir: str = "dist"):
    """
    Gera um arquivo HTML por formulário e, se o flow tiver várias etapas ou
    caminhos, uma página multi-etapas <flow>.html no lugar das páginas
    avulsas dessas etapas. Retorna os caminhos criados.
    """
    os.makedirs(output_dir, exist_ok=True)
    generated_files = []
    flow_steps = _flow_steps(ast)
    for form_name, form in ast.forms.items():
        _identifier(form_name, "Nome de formulário")
        if form_name in flow_steps:
            continue
        filename = f"{form_name.lower()}.html"
        filepath = os.path.join(output_dir, filename)
        rendered = _render_form_html(form, ast)
        with open(filepath, "w", encoding="utf-8", newline="\n") as output_file:
            output_file.write(rendered)
        generated_files.append(filepath)
        print(f"[SUCESSO] Formulário HTML gerado: {filepath}")
    if flow_steps:
        _identifier(ast.flow.name, "Nome de flow")
        filepath = os.path.join(output_dir, f"{ast.flow.name.lower()}.html")
        rendered = _render_flow_html(ast)
        with open(filepath, "w", encoding="utf-8", newline="\n") as output_file:
            output_file.write(rendered)
        generated_files.append(filepath)
        print(f"[SUCESSO] Formulário multi-etapas gerado: {filepath}")
    return generated_files
