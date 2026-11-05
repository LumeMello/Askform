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
Gerador de backend Flask para o Askform.

Gera endpoints REST com persistência SQLite, validação no servidor,
armazenamento seguro de arquivos enviados e suporte a CORS.
"""
from __future__ import annotations

import os
import re
from typing import Any, Dict, List

from symbol_table import ProgramNode


class CodeWriter:
    """Construtor simples de código Python com controle de indentação."""

    def __init__(self, indent_size: int = 4):
        self.indent_size = indent_size
        self._indent_level = 0
        self.lines: List[str] = []

    def indent(self) -> None:
        self._indent_level += 1

    def dedent(self) -> None:
        if self._indent_level > 0:
            self._indent_level -= 1

    def write_line(self, line: str = "") -> None:
        if line:
            self.lines.append(
                f"{' ' * (self._indent_level * self.indent_size)}{line}"
            )
        else:
            self.lines.append("")

    def get_code(self) -> str:
        return "\n".join(self.lines) + "\n"


_SUPPORTED_METHODS = {"GET", "POST", "PUT", "PATCH", "DELETE"}
_IDENTIFIER_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_ROUTE_PARAM_RE = re.compile(r"\{([A-Za-z_][A-Za-z0-9_]*)\}")


def _safe_identifier(value: str, description: str) -> str:
    """Valida nomes usados como identificadores SQL."""
    if not isinstance(value, str) or not _IDENTIFIER_RE.fullmatch(value):
        raise ValueError(f"{description} inválido: {value!r}")
    return value


def _field_config(form: Any) -> Dict[str, Dict[str, Any]]:
    """Converte os campos e validações do AST em configuração serializável."""
    result: Dict[str, Dict[str, Any]] = {}

    for field_name, field in form.fields.items():
        _safe_identifier(field_name, "Nome de campo")
        properties = getattr(field, "properties", {}) or {}
        validation = getattr(form, "validations", {}).get(field_name)
        rules = getattr(validation, "rules", {}) if validation else {}

        result[field_name] = {
            "type": str(getattr(field, "field_type", "string")).lower(),
            "is_array": bool(getattr(field, "is_array", False)),
            "required": bool(properties.get("required", False)),
            "default": properties.get("default"),
            "min": rules.get("min"),
            "max": rules.get("max"),
            "pattern": rules.get("pattern"),
            "message": rules.get("message"),
        }

    return result


def _render_flask_app(ast: ProgramNode) -> str:
    """Renderiza a aplicação Flask com middleware CORS e endpoints CRUD."""
    endpoint_configs: List[Dict[str, Any]] = []
    routes: List[Dict[str, Any]] = []

    for api_name, api_node in ast.apis.items():
        for endpoint in api_node.endpoints:
            method = str(endpoint.method).upper()
            if method not in _SUPPORTED_METHODS:
                raise ValueError(
                    f"Método HTTP não suportado no endpoint "
                    f"{api_name}: {method!r}"
                )

            if not endpoint.consumes:
                continue

            form = ast.forms.get(endpoint.consumes)
            if form is None:
                continue

            form_name = _safe_identifier(form.name, "Nome de formulário")
            table_name = form_name.lower()
            _safe_identifier(table_name, "Nome de tabela")

            route = getattr(endpoint, "route", "")
            if not isinstance(route, str) or not route.startswith("/"):
                raise ValueError(f"Rota inválida no endpoint {api_name}: {route!r}")

            flask_route = _ROUTE_PARAM_RE.sub(r"<\1>", route)
            if "{" in flask_route or "}" in flask_route:
                raise ValueError(f"Parâmetro de rota inválido: {route!r}")

            route_params = _ROUTE_PARAM_RE.findall(route)
            fields = _field_config(form)

            for param_name in route_params:
                if param_name not in fields:
                    raise ValueError(
                        f"Parâmetro de rota {param_name!r} não existe "
                        f"no formulário {form_name!r}"
                    )

            config_id = len(endpoint_configs)
            endpoint_configs.append({
                "table": table_name,
                "form": form_name,
                "fields": fields,
                "route_params": route_params,
            })
            routes.append({
                "route": flask_route,
                "method": method,
                "config_id": config_id,
                "function": f"endpoint_{config_id}_{method.lower()}",
            })

    w = CodeWriter()
    w.write_line('"""Aplicação Flask gerada automaticamente pelo Askform."""')
    w.write_line("import datetime")
    w.write_line("import json")
    w.write_line("import logging")
    w.write_line("import os")
    w.write_line("import re")
    w.write_line("import sqlite3")
    w.write_line("import uuid")
    w.write_line("from pathlib import Path")
    w.write_line("from werkzeug.utils import secure_filename")
    w.write_line("from flask import Flask, jsonify, request")
    w.write_line()
    w.write_line("app = Flask(__name__)")
    w.write_line("BASE_DIR = Path(__file__).resolve().parent")
    w.write_line("UPLOAD_FOLDER = Path(os.environ.get('ASKFORM_UPLOAD_FOLDER', BASE_DIR / 'uploads'))")
    w.write_line("DB_NAME = os.environ.get('ASKFORM_DATABASE', str(BASE_DIR / 'database.db'))")
    w.write_line("MAX_CONTENT_LENGTH = int(os.environ.get('ASKFORM_MAX_CONTENT_LENGTH', 16 * 1024 * 1024))")
    w.write_line("app.config['MAX_CONTENT_LENGTH'] = MAX_CONTENT_LENGTH")
    w.write_line("UPLOAD_FOLDER.mkdir(parents=True, exist_ok=True)")
    w.write_line("logging.basicConfig(level=os.environ.get('LOG_LEVEL', 'INFO'))")
    w.write_line("logger = logging.getLogger('askform.generated')")
    w.write_line()
    w.write_line("@app.after_request")
    w.write_line("def _add_cors_headers(response):")
    w.indent()
    w.write_line("response.headers['Access-Control-Allow-Origin'] = '*'")
    w.write_line("response.headers['Access-Control-Allow-Methods'] = 'GET, POST, PUT, PATCH, DELETE, OPTIONS'")
    w.write_line("response.headers['Access-Control-Allow-Headers'] = 'Content-Type, Authorization'")
    w.write_line("return response")
    w.dedent()
    w.write_line()
    w.write_line("@app.route('/', defaults={'path': ''}, methods=['OPTIONS'])")
    w.write_line("@app.route('/<path:path>', methods=['OPTIONS'])")
    w.write_line("def _options_handler(path):")
    w.indent()
    w.write_line("return '', 200")
    w.dedent()
    w.write_line()
    w.write_line(f"ENDPOINT_CONFIGS = {endpoint_configs!r}")
    w.write_line()

    w.write_line("def quote_identifier(identifier):")
    w.indent()
    w.write_line("if not isinstance(identifier, str) or not re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]*', identifier):")
    w.indent()
    w.write_line("raise ValueError('Identificador SQL inválido')")
    w.dedent()
    w.write_line("return '\"' + identifier.replace('\"', '\"\"') + '\"'")
    w.dedent()
    w.write_line()

    w.write_line("def get_connection():")
    w.indent()
    w.write_line("connection = sqlite3.connect(DB_NAME, timeout=10)")
    w.write_line("connection.row_factory = sqlite3.Row")
    w.write_line("return connection")
    w.dedent()
    w.write_line()

    w.write_line("def init_db():")
    w.indent()
    w.write_line("with get_connection() as connection:")
    w.indent()
    w.write_line("for config in ENDPOINT_CONFIGS:")
    w.indent()
    w.write_line("columns = ['\"id\" INTEGER PRIMARY KEY AUTOINCREMENT']")
    w.write_line("for field_name, spec in config['fields'].items():")
    w.indent()
    w.write_line("field_type = spec['type']")
    w.write_line("sql_type = 'INTEGER' if field_type in ('integer', 'boolean') else ('REAL' if field_type == 'float' else 'TEXT')")
    w.write_line("columns.append(f'{quote_identifier(field_name)} {sql_type}')")
    w.dedent()
    w.write_line("table = quote_identifier(config['table'])")
    w.write_line("connection.execute(f'CREATE TABLE IF NOT EXISTS {table} ({\", \".join(columns)})')")
    w.dedent()
    w.dedent()
    w.dedent()
    w.write_line()

    w.write_line("def _json_error(message, status):")
    w.indent()
    w.write_line("return jsonify({'status': 'error', 'message': message}), status")
    w.dedent()
    w.write_line()

    w.write_line("def _parse_bool(value):")
    w.indent()
    w.write_line("if isinstance(value, bool):")
    w.indent()
    w.write_line("return value")
    w.dedent()
    w.write_line("if isinstance(value, int) and value in (0, 1):")
    w.indent()
    w.write_line("return bool(value)")
    w.dedent()
    w.write_line("if isinstance(value, str):")
    w.indent()
    w.write_line("normalized = value.strip().lower()")
    w.write_line("if normalized in ('true', '1', 'yes', 'on', 'sim'): return True")
    w.write_line("if normalized in ('false', '0', 'no', 'off', 'não', 'nao'): return False")
    w.dedent()
    w.write_line("raise ValueError('valor booleano inválido')")
    w.dedent()
    w.write_line()

    w.write_line("def _convert_scalar(value, field_type):")
    w.indent()
    w.write_line("if value is None:")
    w.indent()
    w.write_line("return None")
    w.dedent()
    w.write_line("if field_type == 'string': return str(value)")
    w.write_line("if field_type == 'integer':")
    w.indent()
    w.write_line("if isinstance(value, bool): raise ValueError('inteiro inválido')")
    w.write_line("return int(value)")
    w.dedent()
    w.write_line("if field_type == 'float':")
    w.indent()
    w.write_line("number = float(value)")
    w.write_line("if number != number or number in (float('inf'), float('-inf')): raise ValueError('número inválido')")
    w.write_line("return number")
    w.dedent()
    w.write_line("if field_type == 'boolean': return int(_parse_bool(value))")
    w.write_line("if field_type == 'date':")
    w.indent()
    w.write_line("return datetime.date.fromisoformat(str(value)).isoformat()")
    w.dedent()
    w.write_line("if field_type == 'uuid':")
    w.indent()
    w.write_line("return str(uuid.UUID(str(value)))")
    w.dedent()
    w.write_line("if field_type == 'file':")
    w.indent()
    w.write_line("return str(value)")
    w.dedent()
    w.write_line("raise ValueError(f'tipo de campo não suportado: {field_type}')")
    w.dedent()
    w.write_line()

    w.write_line("def _validate_value(field_name, value, spec):")
    w.indent()
    w.write_line("if value is None or value == '':")
    w.indent()
    w.write_line("if spec.get('required'): raise ValueError(f'Campo obrigatório: {field_name}')")
    w.write_line("return None")
    w.dedent()
    w.write_line("field_type = spec['type']")
    w.write_line("if spec.get('is_array'):")
    w.indent()
    w.write_line("if not isinstance(value, list): value = [value]")
    w.write_line("converted = [_convert_scalar(item, field_type) for item in value]")
    w.write_line("checked_value = converted")
    w.dedent()
    w.write_line("else:")
    w.indent()
    w.write_line("converted = _convert_scalar(value, field_type)")
    w.write_line("checked_value = converted")
    w.dedent()
    w.write_line("minimum, maximum = spec.get('min'), spec.get('max')")
    w.write_line("values = checked_value if isinstance(checked_value, list) else [checked_value]")
    w.write_line("for item in values:")
    w.indent()
    w.write_line("if item is None: continue")
    w.write_line("if minimum is not None:")
    w.indent()
    w.write_line("measure = len(item) if isinstance(item, str) else item")
    w.write_line("if measure < minimum: raise ValueError(spec.get('message') or f'Valor mínimo não atendido em {field_name}')")
    w.dedent()
    w.write_line("if maximum is not None:")
    w.indent()
    w.write_line("measure = len(item) if isinstance(item, str) else item")
    w.write_line("if measure > maximum: raise ValueError(spec.get('message') or f'Valor máximo excedido em {field_name}')")
    w.dedent()
    w.write_line("pattern = spec.get('pattern')")
    w.write_line("if pattern and isinstance(item, str) and not re.fullmatch(pattern, item):")
    w.indent()
    w.write_line("raise ValueError(spec.get('message') or f'Formato inválido em {field_name}')")
    w.dedent()
    w.dedent()
    w.write_line("return json.dumps(converted, ensure_ascii=False) if spec.get('is_array') else converted")
    w.dedent()
    w.write_line()

    w.write_line("def _read_payload():")
    w.indent()
    w.write_line("json_data = request.get_json(silent=True)")
    w.write_line("if json_data is not None:")
    w.indent()
    w.write_line("if not isinstance(json_data, dict): raise ValueError('O corpo JSON deve ser um objeto')")
    w.write_line("return dict(json_data)")
    w.dedent()
    w.write_line("data = request.form.to_dict(flat=True)")
    w.write_line("for key in request.files:")
    w.indent()
    w.write_line("uploaded = request.files.getlist(key)")
    w.write_line("data[key] = uploaded if len(uploaded) > 1 else uploaded[0]")
    w.dedent()
    w.write_line("return data")
    w.dedent()
    w.write_line()

    w.write_line("def _save_upload(field_name, file_storage, saved_paths):")
    w.indent()
    w.write_line("if not file_storage or not getattr(file_storage, 'filename', ''):")
    w.indent()
    w.write_line("return None")
    w.dedent()
    w.write_line("original_name = secure_filename(file_storage.filename)")
    w.write_line("if not original_name: raise ValueError(f'Nome de arquivo inválido: {field_name}')")
    w.write_line("extension = Path(original_name).suffix.lower()")
    w.write_line("stored_name = f'{uuid.uuid4().hex}{extension}'")
    w.write_line("destination = (UPLOAD_FOLDER / stored_name).resolve()")
    w.write_line("if destination.parent != UPLOAD_FOLDER.resolve(): raise ValueError('Caminho de upload inválido')")
    w.write_line("file_storage.save(destination)")
    w.write_line("saved_paths.append(destination)")
    w.write_line("return str(Path('uploads') / stored_name)")
    w.dedent()
    w.write_line()

    w.write_line("def _prepare_data(config, payload, partial=False):")
    w.indent()
    w.write_line("fields = config['fields']")
    w.write_line("unknown = set(payload) - set(fields)")
    w.write_line("if unknown: raise ValueError('Campos não reconhecidos: ' + ', '.join(sorted(unknown)))")
    w.write_line("prepared = {}")
    w.write_line("saved_paths = []")
    w.write_line("try:")
    w.indent()
    w.write_line("for field_name, spec in fields.items():")
    w.indent()
    w.write_line("if field_name not in payload:")
    w.indent()
    w.write_line("if partial: continue")
    w.write_line("if spec.get('default') is not None: raw_value = spec['default']")
    w.write_line("elif spec.get('required'): raise ValueError(f'Campo obrigatório: {field_name}')")
    w.write_line("else: continue")
    w.dedent()
    w.write_line("else:")
    w.indent()
    w.write_line("raw_value = payload[field_name]")
    w.dedent()
    w.write_line("if spec['type'] == 'file':")
    w.indent()
    w.write_line("if isinstance(raw_value, list):")
    w.indent()
    w.write_line("paths = [_save_upload(field_name, item, saved_paths) for item in raw_value]")
    w.write_line("raw_value = [path for path in paths if path is not None]")
    w.dedent()
    w.write_line("else:")
    w.indent()
    w.write_line("raw_value = _save_upload(field_name, raw_value, saved_paths)")
    w.dedent()
    w.write_line("if raw_value is None and spec.get('required'): raise ValueError(f'Arquivo obrigatório: {field_name}')")
    w.dedent()
    w.write_line("prepared[field_name] = _validate_value(field_name, raw_value, spec)")
    w.dedent()
    w.write_line("return prepared, saved_paths")
    w.dedent()
    w.write_line("except Exception:")
    w.indent()
    w.write_line("for path in saved_paths:")
    w.indent()
    w.write_line("try: path.unlink(missing_ok=True)")
    w.write_line("except OSError: logger.exception('Falha ao remover upload temporário')")
    w.dedent()
    w.write_line("raise")
    w.dedent()
    w.dedent()
    w.write_line()

    w.write_line("def _cleanup_saved_files(saved_paths):")
    w.indent()
    w.write_line("for path in saved_paths:")
    w.indent()
    w.write_line("try: path.unlink(missing_ok=True)")
    w.write_line("except OSError: logger.exception('Falha ao remover arquivo enviado após erro')")
    w.dedent()
    w.dedent()
    w.write_line()

    w.write_line("def _handle_request(config, route_values):")
    w.indent()
    w.write_line("table = quote_identifier(config['table'])")
    w.write_line("route_params = config['route_params']")
    w.write_line("method = request.method.upper()")
    w.write_line("saved_paths = []")
    w.write_line("try:")
    w.indent()
    w.write_line("if method == 'POST':")
    w.indent()
    w.write_line("payload = _read_payload()")
    w.write_line("prepared, saved_paths = _prepare_data(config, payload)")
    w.write_line("if not prepared:")
    w.indent()
    w.write_line("return _json_error('Nenhum dado válido foi informado', 400)")
    w.dedent()
    w.write_line("columns = ', '.join(quote_identifier(name) for name in prepared)")
    w.write_line("placeholders = ', '.join('?' for _ in prepared)")
    w.write_line("with get_connection() as connection:")
    w.indent()
    w.write_line("cursor = connection.execute(f'INSERT INTO {table} ({columns}) VALUES ({placeholders})', tuple(prepared.values()))")
    w.write_line("record_id = cursor.lastrowid")
    w.dedent()
    w.write_line("return jsonify({'status': 'success', 'message': 'Registro criado com sucesso', 'record_id': record_id, 'data': prepared}), 201")
    w.dedent()
    w.write_line("if method == 'GET':")
    w.indent()
    w.write_line("with get_connection() as connection:")
    w.indent()
    w.write_line("if route_params:")
    w.indent()
    w.write_line("param = route_params[0]")
    w.write_line("row = connection.execute(f'SELECT * FROM {table} WHERE {quote_identifier(param)} = ?', (route_values[param],)).fetchone()")
    w.write_line("if row is None: return _json_error('Registro não encontrado', 404)")
    w.write_line("return jsonify({'status': 'success', 'record': dict(row)}), 200")
    w.dedent()
    w.write_line("limit = request.args.get('limit', default=100, type=int)")
    w.write_line("limit = max(1, min(limit or 100, 500))")
    w.write_line("offset = request.args.get('offset', default=0, type=int)")
    w.write_line("offset = max(0, offset or 0)")
    w.write_line("rows = connection.execute(f'SELECT * FROM {table} LIMIT ? OFFSET ?', (limit, offset)).fetchall()")
    w.write_line("records = [dict(row) for row in rows]")
    w.dedent()
    w.write_line("return jsonify({'status': 'success', 'count': len(records), 'records': records, 'limit': limit, 'offset': offset}), 200")
    w.dedent()
    w.write_line("if method in ('PUT', 'PATCH'):")
    w.indent()
    w.write_line("if not route_params: return _json_error('A rota de atualização precisa de um parâmetro de identificação', 400)")
    w.write_line("param = route_params[0]")
    w.write_line("payload = _read_payload()")
    w.write_line("prepared, saved_paths = _prepare_data(config, payload, partial=(method == 'PATCH'))")
    w.write_line("if not prepared: return _json_error('Nenhum campo para atualizar foi informado', 400)")
    w.write_line("assignments = ', '.join(f'{quote_identifier(name)} = ?' for name in prepared)")
    w.write_line("values = list(prepared.values()) + [route_values[param]]")
    w.write_line("with get_connection() as connection:")
    w.indent()
    w.write_line("cursor = connection.execute(f'UPDATE {table} SET {assignments} WHERE {quote_identifier(param)} = ?', values)")
    w.write_line("if cursor.rowcount == 0:")
    w.indent()
    w.write_line("_cleanup_saved_files(saved_paths)")
    w.write_line("return _json_error('Registro não encontrado', 404)")
    w.dedent()
    w.dedent()
    w.write_line("return jsonify({'status': 'success', 'message': 'Registro atualizado', 'updated_fields': list(prepared)}), 200")
    w.dedent()
    w.write_line("if method == 'DELETE':")
    w.indent()
    w.write_line("if not route_params: return _json_error('A rota de exclusão precisa de um parâmetro de identificação', 400)")
    w.write_line("param = route_params[0]")
    w.write_line("with get_connection() as connection:")
    w.indent()
    w.write_line("cursor = connection.execute(f'DELETE FROM {table} WHERE {quote_identifier(param)} = ?', (route_values[param],))")
    w.write_line("if cursor.rowcount == 0:")
    w.indent()
    w.write_line("_cleanup_saved_files(saved_paths)")
    w.write_line("return _json_error('Registro não encontrado', 404)")
    w.dedent()
    w.dedent()
    w.write_line("return jsonify({'status': 'success', 'message': 'Registro excluído'}), 200")
    w.dedent()
    w.write_line("return _json_error('Método não permitido', 405)")
    w.dedent()
    w.write_line("except ValueError as exc:")
    w.indent()
    w.write_line("_cleanup_saved_files(saved_paths)")
    w.write_line("return _json_error(str(exc), 400)")
    w.dedent()
    w.write_line("except sqlite3.Error:")
    w.indent()
    w.write_line("_cleanup_saved_files(saved_paths)")
    w.write_line("logger.exception('Erro de banco de dados no endpoint %s', config['form'])")
    w.write_line("return _json_error('Não foi possível concluir a operação no banco de dados', 500)")
    w.dedent()
    w.write_line("except Exception:")
    w.indent()
    w.write_line("_cleanup_saved_files(saved_paths)")
    w.write_line("logger.exception('Erro inesperado no endpoint %s', config['form'])")
    w.write_line("return _json_error('Erro interno do servidor', 500)")
    w.dedent()
    w.dedent()
    w.write_line()

    for route in routes:
        config_id = route["config_id"]
        w.write_line(
            f"@app.route({route['route']!r}, methods={[route['method']]!r}, "
            f"endpoint={route['function']!r})"
        )
        w.write_line(f"def {route['function']}(**kwargs):")
        w.indent()
        w.write_line(f"return _handle_request(ENDPOINT_CONFIGS[{config_id}], kwargs)")
        w.dedent()
        w.write_line()

    w.write_line("@app.errorhandler(413)")
    w.write_line("def request_too_large(_error):")
    w.indent()
    w.write_line("return _json_error('O arquivo ou corpo enviado excede o limite permitido', 413)")
    w.dedent()
    w.write_line()
    w.write_line("init_db()")
    w.write_line()
    w.write_line("if __name__ == '__main__':")
    w.indent()
    w.write_line("host = os.environ.get('ASKFORM_HOST', '127.0.0.1')")
    w.write_line("port = int(os.environ.get('ASKFORM_PORT', '5000'))")
    w.write_line("# Debug permanece desativado; use um servidor WSGI em produção.")
    w.write_line("app.run(host=host, port=port, debug=False)")
    w.dedent()

    return w.get_code()


def generate_flask(ast: ProgramNode, output_dir: str = "dist") -> str:
    """Gera dist/app.py e retorna o caminho do arquivo criado."""
    os.makedirs(output_dir, exist_ok=True)
    filepath = os.path.join(output_dir, "app.py")
    generated_code = _render_flask_app(ast)

    compile(generated_code, filepath, "exec")

    with open(filepath, "w", encoding="utf-8", newline="\n") as output_file:
        output_file.write(generated_code)

    print(f"[SUCESSO] Aplicação Flask dinâmica gerada em: {filepath}")
    return filepath
