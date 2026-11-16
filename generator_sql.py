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
MODIFICADO (persistência, fase 1): gerador do esquema SQL (SQLite).

Recebe as mesmas configurações de endpoint que o gerador do Flask usa (campos
com tipo, required, default, min e max) e produz:

  * `dist/schema.sql`: CREATE TABLE + CREATE UNIQUE INDEX, para ler/rodar à mão;
  * a estrutura `TABLES` embutida no app.py, com o MESMO texto do schema.sql e,
    para cada coluna, a definição usada na migração (`ALTER TABLE ADD COLUMN`).

Regras de tradução (alinhadas com a validação do app.py, para o banco nunca
rejeitar o que a aplicação aceita):
  * NOT NULL        campo `required` de endpoint que consome um FORM; num flow o
                    servidor decide por caminho, então as colunas ficam anuláveis;
  * DEFAULT         string/integer/float/boolean escalares com literal compatível;
  * CHECK min/max   integer/float: o valor; string: length(); arrays ficam de fora;
  * UNIQUE          índice nos campos usados como {param} de rota (a chave);
  * pattern         só na aplicação (regex de Python não é portátil para CHECK).
"""
from typing import Any, Dict, List, Optional

_SQL_TYPES = {"integer": "INTEGER", "boolean": "INTEGER", "float": "REAL"}
_CHECKABLE = ("integer", "float", "string")


def _q(identifier: str) -> str:
    return '"' + identifier.replace('"', '""') + '"'


def _number(value: Any) -> Optional[str]:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return repr(value)


def _default_sql(spec: Dict[str, Any]) -> Optional[str]:
    default = spec.get("default")
    if default is None or spec.get("is_array") or spec["type"] == "file":
        return None
    kind = spec["type"]
    if kind == "string" and isinstance(default, str):
        return "'" + default.replace("'", "''") + "'"
    if kind == "integer" and isinstance(default, (int, bool)):
        return str(int(default))
    if kind == "float" and isinstance(default, (int, float, bool)):
        return repr(float(default))
    if kind == "boolean" and isinstance(default, bool):
        return "1" if default else "0"
    return None


def _checks(name: str, spec: Dict[str, Any]) -> List[str]:
    if spec.get("is_array") or spec["type"] not in _CHECKABLE:
        return []
    target = f"length({_q(name)})" if spec["type"] == "string" else _q(name)
    checks = []
    minimum, maximum = _number(spec.get("min")), _number(spec.get("max"))
    if minimum is not None:
        checks.append(f"CHECK ({target} >= {minimum})")
    if maximum is not None:
        checks.append(f"CHECK ({target} <= {maximum})")
    return checks


def tabelas(endpoint_configs: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Uma entrada por tabela (várias rotas do mesmo form compartilham a tabela).

    Cada coluna: {name, create (definição no CREATE TABLE), add (definição na
    migração: anulável e sem CHECK, porque o SQLite não acrescenta coluna
    NOT NULL sem valor padrão e não valida CHECK em linhas antigas)}.
    """
    resultado: Dict[str, Dict[str, Any]] = {}
    for config in endpoint_configs:
        nome = config["table"]
        tabela = resultado.get(nome)
        if tabela is None:
            estrito = "flow" not in config
            colunas = []
            for campo, spec in config["fields"].items():
                tipo = _SQL_TYPES.get(spec["type"], "TEXT")
                default = _default_sql(spec)
                parte_default = f" DEFAULT {default}" if default is not None else ""
                not_null = " NOT NULL" if estrito and spec.get("required") else ""
                checks = "".join(" " + c for c in _checks(campo, spec))
                colunas.append({
                    "name": campo,
                    "create": f"{_q(campo)} {tipo}{not_null}{parte_default}{checks}",
                    "add": f"{_q(campo)} {tipo}{parte_default}",
                })
            tabela = resultado[nome] = {"name": nome, "columns": colunas, "unique": []}
        for param in config["route_params"]:
            if param not in tabela["unique"]:
                tabela["unique"].append(param)

    saida = []
    for tabela in resultado.values():
        nome = tabela["name"]
        linhas = ['"id" INTEGER PRIMARY KEY AUTOINCREMENT'] + [c["create"] for c in tabela["columns"]]
        tabela["create"] = f"CREATE TABLE IF NOT EXISTS {_q(nome)} (\n  " + ",\n  ".join(linhas) + "\n);"
        tabela["indexes"] = [
            {
                "column": coluna,
                "name": f"ux_{nome}_{coluna}",
                "create": f"CREATE UNIQUE INDEX IF NOT EXISTS {_q(f'ux_{nome}_{coluna}')} "
                          f"ON {_q(nome)} ({_q(coluna)});",
            }
            for coluna in tabela["unique"]
        ]
        saida.append(tabela)
    return saida


def render_schema_sql(lista: List[Dict[str, Any]]) -> str:
    """Texto do schema.sql (o mesmo que o app.py embute e executa)."""
    partes = ["-- Gerado pelo Askform. Pode ser executado em um banco SQLite vazio.",
              "-- O app.py aplica este mesmo esquema ao subir e só ACRESCENTA colunas",
              "-- (nunca apaga coluna nem dado)."]
    for tabela in lista:
        partes.append("")
        partes.append(tabela["create"])
        partes.extend(i["create"] for i in tabela["indexes"])
    return "\n".join(partes) + "\n"
