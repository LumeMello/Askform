"""
HTML and Wizard Generator module for Forms and APIs DSL.
Generates multi-step form wizard layouts with inter-step data propagation and client-side validation.
"""
import os
import json
from symbol_table import ProgramNode, FormNode, WizardNode, FieldRefNode

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

def _resolve_wizard_action(wizard: WizardNode, ast: ProgramNode):
    if wizard.target_api and wizard.target_verb and wizard.target_api in ast.apis:
        for ep in ast.apis[wizard.target_api].endpoints:
            if ep.method == wizard.target_verb:
                return ep.route, ep.method
    for flow in ast.flows.values():
        if flow.source_form == wizard.name and flow.target_api in ast.apis:
            for ep in ast.apis[flow.target_api].endpoints:
                if ep.method == flow.target_verb:
                    return ep.route, ep.method
    return f"/api/{wizard.name.lower()}/submit", "POST"

def _render_wizard_html(wizard: WizardNode, ast: ProgramNode) -> str:
    action_route, action_method = _resolve_wizard_action(wizard, ast)
    backend_target = f"http://127.0.0.1:5000{action_route}"
    w = CodeWriter(indent_size=2)
    w.write_line("<!DOCTYPE html>")
    w.write_line("<html lang=\"pt-br\">")
    w.write_line("<head>")
    w.indent()
    w.write_line("<meta charset=\"UTF-8\">")
    w.write_line("<meta name=\"viewport\" content=\"width=device-width, initial-scale=1.0\">")
    w.write_line(f"<title>{wizard.name} - Wizard</title>")
    w.write_line("<style>")
    w.indent()
    w.write_line("body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; margin: 2rem; background: #f8fafc; color: #1e293b; }")
    w.write_line(".wizard-container { max-width: 520px; margin: 0 auto; background: #ffffff; padding: 2rem; border-radius: 8px; box-shadow: 0 4px 6px -1px rgb(0 0 0 / 0.1); }")
    w.write_line(".step-nav { display: flex; gap: 8px; margin-bottom: 1.5rem; }")
    w.write_line(".step-indicator { flex: 1; height: 6px; background: #e2e8f0; border-radius: 3px; }")
    w.write_line(".step-indicator.active { background: #2563eb; }")
    w.write_line(".step-indicator.completed { background: #16a34a; }")
    w.write_line(".wizard-step { display: none; }")
    w.write_line(".wizard-step.active { display: block; }")
    w.write_line(".form-group { margin-bottom: 1.25rem; }")
    w.write_line("label { display: block; margin-bottom: 0.375rem; font-weight: 600; font-size: 0.875rem; }")
    w.write_line("input[type=\"text\"], input[type=\"number\"], input[type=\"date\"] { width: 100%; box-sizing: border-box; padding: 0.5rem 0.75rem; border: 1px solid #cbd5e1; border-radius: 4px; font-size: 0.875rem; }")
    w.write_line(".btn-row { display: flex; justify-content: space-between; gap: 12px; margin-top: 1.5rem; }")
    w.write_line("button { padding: 0.625rem 1.25rem; font-weight: 600; border-radius: 4px; cursor: pointer; border: none; }")
    w.write_line(".btn-primary { background: #2563eb; color: #fff; }")
    w.write_line(".btn-secondary { background: #e2e8f0; color: #334155; }")
    w.write_line(".response-output { margin-top: 1rem; padding: 0.75rem; border-radius: 4px; font-family: monospace; font-size: 0.75rem; display: none; }")
    w.write_line(".response-success { background: #f0fdf4; border: 1px solid #bbf7d0; color: #166534; }")
    w.dedent()
    w.write_line("</style>")
    w.dedent()
    w.write_line("</head>")
    w.write_line("<body>")
    w.indent()
    w.write_line("<div class=\"wizard-container\">")
    w.indent()
    w.write_line(f"<h2>{wizard.name}</h2>")
    w.write_line("<div class=\"step-nav\">")
    for idx in range(len(wizard.steps)):
        w.write_line(f"  <div class=\"step-indicator {'active' if idx == 0 else ''}\" id=\"indicator-{idx}\"></div>")
    w.write_line("</div>")
    w.write_line(f"<form id=\"{wizard.name}\">")
    w.indent()
    for idx, step_name in enumerate(wizard.steps):
        form = ast.forms[step_name]
        w.write_line(f"<div class=\"wizard-step {'active' if idx == 0 else ''}\" data-step=\"{idx}\" id=\"step-{step_name}\">")
        w.indent()
        w.write_line(f"<h3>Etapa {idx + 1}: {form.name}</h3>")
        for f_name, f_field in form.fields.items():
            label = f_field.properties.get('label', f_name)
            req = " required" if f_field.properties.get('required') else ""
            prop_data = ""
            def_val = f_field.properties.get('default')
            if isinstance(def_val, FieldRefNode):
                prop_data = f" data-propagate-from=\"{def_val.form_name}.{def_val.field_name}\""
                init_val = ""
            elif def_val is not None:
                init_val = f" value=\"{def_val}\""
            else:
                init_val = ""
            inp_t = "number" if f_field.field_type in ('integer', 'float') else ("date" if f_field.field_type == 'date' else "text")
            w.write_line("<div class=\"form-group\">")
            w.indent()
            w.write_line(f"<label for=\"{step_name}_{f_name}\">{label}</label>")
            w.write_line(f"<input type=\"{inp_t}\" id=\"{step_name}_{f_name}\" name=\"{f_name}\" data-form=\"{step_name}\"{init_val}{req}{prop_data}>")
            w.dedent()
            w.write_line("</div>")
        w.write_line("<div class=\"btn-row\">")
        if idx > 0:
            w.write_line(f"  <button type=\"button\" class=\"btn-secondary\" onclick=\"prevStep({idx})\">Voltar</button>")
        else:
            w.write_line("  <span></span>")
        if idx < len(wizard.steps) - 1:
            w.write_line(f"  <button type=\"button\" class=\"btn-primary\" onclick=\"nextStep({idx})\">Avançar</button>")
        else:
            w.write_line("  <button type=\"submit\" class=\"btn-primary\">Finalizar Cadastro</button>")
        w.write_line("</div>")
        w.dedent()
        w.write_line("</div>")
    w.dedent()
    w.write_line("</form>")
    w.write_line("<div id=\"responseOutput\" class=\"response-output\"></div>")
    w.dedent()
    w.write_line("</div>")
    w.write_line("<script>")
    w.indent()
    w.write_line("const wizardStore = {};")
    w.write_line("function syncPropagations() {")
    w.indent()
    w.write_line("document.querySelectorAll('[data-propagate-from]').forEach(el => {")
    w.indent()
    w.write_line("const [srcForm, srcField] = el.dataset.propagateFrom.split('.');")
    w.write_line("if (wizardStore[srcForm] && wizardStore[srcForm][srcField] !== undefined) {")
    w.write_line("  if (!el.value || el.dataset.autoFilled === 'true') {")
    w.write_line("    el.value = wizardStore[srcForm][srcField];")
    w.write_line("    el.dataset.autoFilled = 'true';")
    w.write_line("  }")
    w.write_line("}")
    w.dedent()
    w.write_line("});")
    w.dedent()
    w.write_line("}")
    w.write_line("function saveStepData(stepIdx) {")
    w.indent()
    w.write_line("const stepEl = document.querySelector(`.wizard-step[data-step=\"${stepIdx}\"]`);")
    w.write_line("stepEl.querySelectorAll('input').forEach(i => {")
    w.write_line("  wizardStore[i.dataset.form] = wizardStore[i.dataset.form] || {};")
    w.write_line("  wizardStore[i.dataset.form][i.name] = i.type === 'number' ? Number(i.value) : i.value;")
    w.write_line("});")
    w.dedent()
    w.write_line("}")
    w.write_line("function nextStep(currentIdx) {")
    w.indent()
    w.write_line("saveStepData(currentIdx);")
    w.write_line("syncPropagations();")
    w.write_line("document.querySelectorAll('.wizard-step')[currentIdx].classList.remove('active');")
    w.write_line("document.querySelectorAll('.wizard-step')[currentIdx + 1].classList.add('active');")
    w.write_line("document.getElementById(`indicator-${currentIdx}`).classList.add('completed');")
    w.write_line("document.getElementById(`indicator-${currentIdx + 1}`).classList.add('active');")
    w.dedent()
    w.write_line("}")
    w.write_line("function prevStep(currentIdx) {")
    w.indent()
    w.write_line("document.querySelectorAll('.wizard-step')[currentIdx].classList.remove('active');")
    w.write_line("document.querySelectorAll('.wizard-step')[currentIdx - 1].classList.add('active');")
    w.write_line("document.getElementById(`indicator-${currentIdx}`).classList.remove('active');")
    w.dedent()
    w.write_line("}")
    w.write_line(f"document.getElementById('{wizard.name}').addEventListener('submit', async function(e) {{")
    w.indent()
    w.write_line("e.preventDefault();")
    w.write_line(f"saveStepData({len(wizard.steps) - 1});")
    w.write_line(f"const res = await fetch('{backend_target}', {{ method: '{action_method}', headers: {{ 'Content-Type': 'application/json' }}, body: JSON.stringify(wizardStore) }});")
    w.write_line("const data = await res.json();")
    w.write_line("const out = document.getElementById('responseOutput');")
    w.write_line("out.style.display = 'block';")
    w.write_line("out.className = 'response-output response-success';")
    w.write_line("out.textContent = JSON.stringify(data, null, 2);")
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
    for wizard_name, wizard in ast.wizards.items():
        filepath = os.path.join(output_dir, f"{wizard_name.lower()}_wizard.html")
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(_render_wizard_html(wizard, ast))
        print(f"Generated Wizard HTML: {filepath}")
