"""
Flask Backend Router Generator module for Askform with SQLite Persistence, File Uploads, and GET Retrieval.
"""
import os
import re
from symbol_table import ProgramNode

class CodeWriter:
    def __init__(self, indent_size: int = 4):
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

def _render_flask_app(ast: ProgramNode) -> str:
    w = CodeWriter()
    w.write_line("import os")
    w.write_line("import sqlite3")
    w.write_line("from flask import Flask, request, jsonify")
    w.write_line()
    w.write_line("app = Flask(__name__)")
    w.write_line("UPLOAD_FOLDER = 'uploads'")
    w.write_line("DB_NAME = 'database.db'")
    w.write_line("os.makedirs(UPLOAD_FOLDER, exist_ok=True)")
    w.write_line()
    
    w.write_line("def init_db():")
    w.indent()
    w.write_line("conn = sqlite3.connect(DB_NAME)")
    w.write_line("cursor = conn.cursor()")
    
    form_to_endpoint = {}
    for api in ast.apis.values():
        for ep in api.endpoints:
            if ep.consumes:
                flask_route = re.sub(r'\{([a-zA-Z_][a-zA-Z0-9_]*)\}', r'<\1>', ep.route)
                form_to_endpoint[ep.consumes] = (flask_route, ep.method)

    for form_name, form in ast.forms.items():
        table_name = form_name.lower()
        cols = ["id INTEGER PRIMARY KEY AUTOINCREMENT"]
        for f_name, f_field in form.fields.items():
            sql_type = "TEXT"
            if f_field.field_type == 'integer':
                sql_type = "INTEGER"
            elif f_field.field_type == 'float':
                sql_type = "REAL"
            elif f_field.field_type == 'boolean':
                sql_type = "INTEGER"
            cols.append(f"\"{f_name}\" {sql_type}")
        
        cols_str = ", ".join(cols)
        w.write_line(f"cursor.execute('''CREATE TABLE IF NOT EXISTS {table_name} ({cols_str})''')")

    w.write_line("conn.commit()")
    w.write_line("conn.close()")
    w.dedent()
    w.write_line()
    w.write_line("init_db()")
    w.write_line()

    for form_name, form in ast.forms.items():
        table_name = form_name.lower()
        route, method = form_to_endpoint.get(form_name, (f"/api/{table_name}/submit", "POST"))
        field_names = list(form.fields.keys())
        
        # Endpoint POST (Submissão e Gravação)
        w.write_line(f"# --- Endpoint POST para {form_name} ---")
        w.write_line(f"@app.route('{route}', methods=['{method}'])")
        w.write_line(f"def submit_{table_name}(**kwargs):")
        w.indent()
        w.write_line("data = request.form.to_dict()")
        w.write_line("data.update(kwargs)")
        w.write_line("saved_files = []")
        w.write_line()
        w.write_line("for f_key, file_obj in request.files.items():")
        w.indent()
        w.write_line("if file_obj and file_obj.filename:")
        w.indent()
        w.write_line("filepath = os.path.join(UPLOAD_FOLDER, file_obj.filename)")
        w.write_line("file_obj.save(filepath)")
        w.write_line("saved_files.append(file_obj.filename)")
        w.write_line("data[f_key] = filepath")
        w.dedent()
        w.dedent()
        w.write_line()
        w.write_line("errors = []")
        for f_name, f_field in form.fields.items():
            if f_field.properties.get('required'):
                w.write_line(f"if not data.get('{f_name}'):")
                w.indent()
                w.write_line(f"errors.append('O campo obrigatório \"{f_name}\" não foi preenchido.')")
                w.dedent()
        w.write_line()
        w.write_line("if errors:")
        w.indent()
        w.write_line("return jsonify({'status': 'error', 'errors': errors}), 400")
        w.dedent()
        w.write_line()
        w.write_line("try:")
        w.indent()
        w.write_line("conn = sqlite3.connect(DB_NAME)")
        w.write_line("cursor = conn.cursor()")
        col_names = [f"\"{f}\"" for f in field_names]
        placeholders = [":" + f for f in field_names]
        cols_insert = ", ".join(col_names)
        vals_insert = ", ".join(placeholders)
        w.write_line(f"cursor.execute('''INSERT INTO {table_name} ({cols_insert}) VALUES ({vals_insert})''', data)")
        w.write_line("conn.commit()")
        w.write_line("record_id = cursor.lastrowid")
        w.write_line("conn.close()")
        w.dedent()
        w.write_line("except Exception as e:")
        w.indent()
        w.write_line("return jsonify({'status': 'error', 'message': str(e)}), 500")
        w.dedent()
        w.write_line()
        w.write_line("return jsonify({")
        w.indent()
        w.write_line("'status': 'success',")
        w.write_line(f"'message': 'Dados de {form_name} salvos com sucesso!',")
        w.write_line("'record_id': record_id,")
        w.write_line("'data': data")
        w.dedent()
        w.write_line("}), 200")
        w.dedent()
        w.write_line()

        # Endpoint GET (Consulta limpa e direta)
        w.write_line(f"# --- Endpoint GET para consultar respostas de {form_name} ---")
        w.write_line(f"@app.route('/api/v1/{table_name}/records', methods=['GET'])")
        w.write_line(f"def get_{table_name}_records():")
        w.indent()
        w.write_line("conn = sqlite3.connect(DB_NAME)")
        w.write_line("conn.row_factory = sqlite3.Row")
        w.write_line("cursor = conn.cursor()")
        w.write_line(f"cursor.execute('SELECT * FROM {table_name}')")
        w.write_line("rows = cursor.fetchall()")
        w.write_line("conn.close()")
        w.write_line("result = [dict(row) for row in rows]")
        w.write_line("return jsonify({'status': 'success', 'count': len(result), 'records': result}), 200")
        w.dedent()
        w.write_line()

    w.write_line("if __name__ == '__main__':")
    w.indent()
    w.write_line("app.run(debug=True, port=5000)")
    w.dedent()
    return w.get_code()

def generate_flask(ast: ProgramNode, output_dir: str = "dist"):
    os.makedirs(output_dir, exist_ok=True)
    filepath = os.path.join(output_dir, "app.py")
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(_render_flask_app(ast))
    print(f"[SUCESSO] Aplicação Flask com suporte a GET/POST e SQLite gerada em: {filepath}")
