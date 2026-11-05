"""
Flask Backend Router Generator module for Askform with Full Dynamic REST Routing and SQLite Persistence.
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
    
    # Criação das tabelas baseadas nos formulários
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

    # Processa todas as APIs e os seus endpoints declarados na DSL
    endpoint_counter = 0
    for api_name, api_node in ast.apis.items():
        for ep in api_node.endpoints:
            if not ep.consumes:
                continue
            
            form = ast.forms.get(ep.consumes)
            if not form:
                continue
                
            table_name = form.name.lower()
            field_names = list(form.fields.keys())
            
            # Converte a rota da DSL (ex: /produtos/{idProduto}) para a sintaxe do Flask (/produtos/<idProduto>)
            flask_route = re.sub(r'\{([a-zA-Z_][a-zA-Z0-9_]*)\}', r'<\1>', ep.route)
            method = ep.method.upper()
            func_name = f"endpoint_{endpoint_counter}_{table_name}_{method.lower()}"
            endpoint_counter += 1

            w.write_line(f"# --- Endpoint {method} {ep.route} para {form.name} ---")
            w.write_line(f"@app.route('{flask_route}', methods=['{method}'])")
            w.write_line(f"def {func_name}(**kwargs):")
            w.indent()
            
            if method == 'POST':
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
                w.write_line(f"'message': 'Registo criado com sucesso na tabela {table_name}!',")
                w.write_line("'record_id': record_id,")
                w.write_line("'data': data")
                w.dedent()
                w.write_line("}), 201")
                
            elif method == 'GET':
                # Verifica se a rota tem parâmetros (ex: <idProduto>)
                param_match = re.search(r'<([a-zA-Z_][a-zA-Z0-9_]*)>', flask_route)
                if param_match:
                    param_name = param_match.group(1)
                    w.write_line(f"conn = sqlite3.connect(DB_NAME)")
                    w.write_line("conn.row_factory = sqlite3.Row")
                    w.write_line("cursor = conn.cursor()")
                    w.write_line(f"cursor.execute('SELECT * FROM {table_name} WHERE \"{param_name}\" = ?', ({param_name},))")
                    w.write_line("row = cursor.fetchone()")
                    w.write_line("conn.close()")
                    w.write_line("if row:")
                    w.indent()
                    w.write_line("return jsonify({'status': 'success', 'record': dict(row)}), 200")
                    w.dedent()
                    w.write_line("else:")
                    w.indent()
                    w.write_line("return jsonify({'status': 'error', 'message': 'Registo não encontrado'}), 404")
                    w.dedent()
                else:
                    w.write_line(f"conn = sqlite3.connect(DB_NAME)")
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
    print(f"[SUCESSO] Aplicação Flask dinâmica gerada em: {filepath}")
