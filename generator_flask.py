"""
Gerador de Servidor Flask com suporte a validação de Wizards Multi-Etapas.
"""
import os
from symbol_table import ProgramNode, FieldRefNode

class FlaskGenerator:
    def generate(self, ast: ProgramNode, output_dir: str = "dist") -> str:
        os.makedirs(output_dir, exist_ok=True)
        filepath = os.path.join(output_dir, "app.py")
        
        lines = [
            "from flask import Flask, request, jsonify",
            "from flask_cors import CORS",
            "",
            "app = Flask(__name__)",
            "CORS(app)",
            ""
        ]

        for wizard_name, wizard in ast.wizards.items():
            lines.append(f"# --- Endpoint do Wizard: {wizard_name} ---")
            lines.append(f"@app.route('/api/{wizard_name.lower()}/submit', methods=['POST'])")
            lines.append(f"def submit_{wizard_name.lower()}():")
            lines.append("    payload = request.get_json(silent=True) or {}")
            lines.append("    errors = []")
            lines.append("")

            for step in wizard.steps:
                form = ast.forms[step]
                lines.append(f"    # Validação da Etapa: {step}")
                lines.append(f"    step_data = payload.get('{step}', {{}})")

                for f_name, f_field in form.fields.items():
                    def_val = f_field.properties.get('default')
                    if isinstance(def_val, FieldRefNode):
                        lines.append(f"    if '{f_name}' not in step_data or not step_data['{f_name}']:")
                        lines.append(f"        step_data['{f_name}'] = payload.get('{def_val.form_name}', {{}}).get('{def_val.field_name}')")

                    if f_field.properties.get('required'):
                        lines.append(f"    if '{f_name}' not in step_data or step_data['{f_name}'] == '':")
                        lines.append(f"        errors.append('Etapa {step}: Campo obrigatório ausente: {f_name}')")

            lines.append("    if errors:")
            lines.append("        return jsonify({'status': 'erro', 'erros': errors}), 400")
            lines.append("")
            lines.append("    return jsonify({'status': 'sucesso', 'mensagem': 'Wizard processado com sucesso', 'dados': payload}), 200")
            lines.append("")

        lines.append("if __name__ == '__main__':")
        lines.append("    app.run(debug=True, port=5000)")

        code = "\n".join(lines)
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(code)
        print(f" [OK] Servidor Flask gerado em: {filepath}")
        return code

def generate_flask(ast: ProgramNode, output_dir: str = "dist"):
    return FlaskGenerator().generate(ast, output_dir)
