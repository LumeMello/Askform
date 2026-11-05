"""
HTML Generator module for Askform.
Resolves dynamic API routes and applies theme properties.
"""
import os
import re
from symbol_table import ProgramNode, FormNode

class CodeWriter:
    def __init__(self, indent_size: int = 2):
        self.indent_size = indent_size
        self._indent_level = 0
        self.lines = []

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
        return "\n".join(self.lines)

def _resolve_form_endpoint(form_name: str, ast: ProgramNode):
    # Procura nos fluxos ou nas APIs qual a rota associada a este formulário
    target_route = f"/api/{form_name.lower()}/submit"
    target_method = "POST"
    
    for flow in ast.flows.values():
        if flow.source_form == form_name and flow.target_api in ast.apis:
            api = ast.apis[flow.target_api]
            for ep in api.endpoints:
                if ep.consumes == form_name:
                    return ep.route, flow.target_verb
                    
    for api in ast.apis.values():
        for ep in api.endpoints:
            if ep.consumes == form_name:
                return ep.route, ep.method
                
    return target_route, target_method

def _render_form_html(form: FormNode, ast: ProgramNode) -> str:
    route_template, http_method = _resolve_form_endpoint(form.name, ast)

    theme_props = {}
    if ast.themes:
        first_theme = list(ast.themes.values())[0]
        theme_props = first_theme.properties

    bg_color = theme_props.get('background', '#f8fafc')
    card_bg = theme_props.get('card_background', '#ffffff')
    text_color = theme_props.get('text_color', '#1e293b')
    accent = theme_props.get('accent_color', '#2563eb')
    font = theme_props.get('font_family', "-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif")
    radius = theme_props.get('border_radius', '8px')

    w = CodeWriter(indent_size=2)
    w.write_line("<!DOCTYPE html>")
    w.write_line("<html lang=\"pt-br\">")
    w.write_line("<head>")
    w.indent()
    w.write_line("<meta charset=\"UTF-8\">")
    w.write_line("<meta name=\"viewport\" content=\"width=device-width, initial-scale=1.0\">")
    w.write_line(f"<title>{form.name}</title>")
    w.write_line("<style>")
    w.indent()
    w.write_line(f"body {{ font-family: {font}; margin: 2rem; background: {bg_color}; color: {text_color}; }}")
    w.write_line(f".card {{ max-width: 520px; margin: 0 auto; background: {card_bg}; padding: 2rem; border-radius: {radius}; box-shadow: 0 4px 6px -1px rgb(0 0 0 / 0.1); }}")
    w.write_line(".form-group { margin-bottom: 1.25rem; }")
    w.write_line("label { display: block; margin-bottom: 0.375rem; font-weight: 600; font-size: 0.875rem; }")
    w.write_line("input[type=\"text\"], input[type=\"number\"], input[type=\"date\"], input[type=\"file\"] { width: 100%; box-sizing: border-box; padding: 0.5rem 0.75rem; border: 1px solid #cbd5e1; border-radius: 4px; font-size: 0.875rem; }")
    w.write_line(f"button {{ width: 100%; padding: 0.75rem; font-weight: 600; border-radius: {radius}; cursor: pointer; border: none; background: {accent}; color: #fff; margin-top: 1rem; }}")
    w.write_line(".response-output { margin-top: 1rem; padding: 0.75rem; border-radius: 4px; font-family: monospace; font-size: 0.75rem; display: none; white-space: pre-wrap; word-break: break-all; }")
    w.write_line(".response-success { background: #f0fdf4; border: 1px solid #bbf7d0; color: #166534; }")
    w.write_line(".response-error { background: #fef2f2; border: 1px solid #fecaca; color: #991b1b; }")
    w.dedent()
    w.write_line("</style>")
    w.dedent()
    w.write_line("</head>")
    w.write_line("<body>")
    w.indent()
    w.write_line("<div class=\"card\">")
    w.indent()
    w.write_line(f"<h2>{form.name}</h2>")
    w.write_line(f"<form id=\"{form.name}\" enctype=\"multipart/form-data\">")
    w.indent()
    for f_name, f_field in form.fields.items():
        label = f_field.properties.get('label', f_name)
        req = " required" if f_field.properties.get('required') else ""
        if f_field.field_type == 'file':
            inp_t = "file"
            accept = " accept=\"image/*\""
        elif f_field.field_type in ('integer', 'float'):
            inp_t = "number"
            accept = ""
        elif f_field.field_type == 'date':
            inp_t = "date"
            accept = ""
        else:
            inp_t = "text"
            accept = ""
        w.write_line("<div class=\"form-group\">")
        w.indent()
        w.write_line(f"<label for=\"{f_name}\">{label}</label>")
        w.write_line(f"<input type=\"{inp_t}\" id=\"{f_name}\" name=\"{f_name}\"{accept}{req}>")
        w.dedent()
        w.write_line("</div>")
    w.write_line("<button type=\"submit\">Enviar Dados</button>")
    w.dedent()
    w.write_line("</form>")
    w.write_line("<div id=\"responseOutput\" class=\"response-output\"></div>")
    w.dedent()
    w.write_line("</div>")
    w.write_line("<script>")
    w.indent()
    w.write_line(f"document.getElementById('{form.name}').addEventListener('submit', async function(e) {{")
    w.indent()
    w.write_line("e.preventDefault();")
    w.write_line("const outputDiv = document.getElementById('responseOutput');")
    w.write_line("outputDiv.style.display = 'none';")
    w.write_line("try {")
    w.indent()
    w.write_line("const formData = new FormData(this);")
    w.write_line("let urlTemplate = '" + route_template + "';")
    w.write_line("// Substitui parâmetros de rota (ex: {userId}) pelos valores preenchidos no formulário")
    w.write_line("for (let [key, value] of formData.entries()) {")
    w.indent()
    w.write_line("if (urlTemplate.includes(`{${key}}`)) {")
    w.indent()
    w.write_line("urlTemplate = urlTemplate.replace(`{${key}}`, encodeURIComponent(value));")
    w.dedent()
    w.write_line("}")
    w.dedent()
    w.write_line("}")
    w.write_line(f"const targetUrl = 'http://127.0.0.1:5000' + urlTemplate;")
    w.write_line(f"const res = await fetch(targetUrl, {{ method: '{http_method}', body: formData }});")
    w.write_line("const textResponse = await res.text();")
    w.write_line("let data;")
    w.write_line("try {")
    w.indent()
    w.write_line("data = JSON.parse(textResponse);")
    w.dedent()
    w.write_line("} catch (err) {")
    w.indent()
    w.write_line("throw new Error('Resposta inválida do servidor: ' + textResponse);")
    w.dedent()
    w.write_line("}")
    w.write_line("outputDiv.style.display = 'block';")
    w.write_line("if (res.ok) {")
    w.indent()
    w.write_line("outputDiv.className = 'response-output response-success';")
    w.write_line("outputDiv.textContent = JSON.stringify(data, null, 2);")
    w.dedent()
    w.write_line("} else {")
    w.indent()
    w.write_line("outputDiv.className = 'response-output response-error';")
    w.write_line("outputDiv.textContent = 'Erro no servidor: ' + JSON.stringify(data, null, 2);")
    w.dedent()
    w.write_line("}")
    w.dedent()
    w.write_line("} catch (err) {")
    w.indent()
    w.write_line("outputDiv.style.display = 'block';")
    w.write_line("outputDiv.className = 'response-output response-error';")
    w.write_line("outputDiv.textContent = 'Falha na submissão: ' + err.message;")
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
    os.makedirs(output_dir, exist_ok=True)
    for form_name, form in ast.forms.items():
        filepath = os.path.join(output_dir, f"{form_name.lower()}.html")
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(_render_form_html(form, ast))
        print(f"[SUCESSO] Formulário gerado com rota dinâmica e entregue em: {filepath}")
