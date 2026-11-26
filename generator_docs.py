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
MODIFICADO (documentação): gerador de documentação da API (dist/API.md e
dist/openapi.json).

Não acrescenta produção à gramática nem ação semântica: é só mais um gerador
(fase 3), que lê a AST já validada. Toda a informação de endpoints/campos vem de
`generator_flask.montar_endpoints` (a MESMA função que gera o app.py), então a
documentação não diverge do servidor.
"""
import itertools
import json
import os
import re
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import quote

from expressions import Escopo, avaliar_json, para_json, para_texto
from flow_graph import FlowGraph
from generator_flask import montar_endpoints
from symbol_table import ProgramNode

_MAX_COMBINACOES = 5000
_ID_EXEMPLO_UUID = "123e4567-e89b-42d3-a456-426614174000"


# ---------------------------------------------------------------------------
# Valores de exemplo (sempre válidos para as regras do campo)
# ---------------------------------------------------------------------------

def _candidatos_padrao(padrao: str) -> List[str]:
    """Candidatos para um `pattern`: expande grupos `(a|b)` simples e tenta textos comuns."""
    lista: List[str] = []
    m = re.search(r"\(([^()|]+(?:\|[^()|]+)+)\)", padrao)
    if m:
        for alt in m.group(1).split("|"):
            lista.append(alt)
    for n in re.findall(r"(?:\[0-9\]|\\d)\{(\d+)\}", padrao):
        lista.append(("1234567890" * 5)[: int(n)])
    lista += ["abc", "a", "A", "1", "123", "12345678900", "a@b.com", "exemplo", "Exemplo 1",
              "2026-01-01", "(11) 91234-5678", "12.345.678/0001-90", "123.456.789-00", "ABC-1234"]
    return lista


def _tamanho_ok(valor: str, spec: Dict[str, Any]) -> bool:
    minimo, maximo = spec.get("min"), spec.get("max")
    if minimo is not None and len(valor) < minimo:
        return False
    if maximo is not None and len(valor) > maximo:
        return False
    return True


def _escalar_exemplo(nome: str, spec: Dict[str, Any]) -> Any:
    tipo = spec["type"]
    minimo, maximo = spec.get("min"), spec.get("max")
    if tipo == "integer":
        valor = 1
        if minimo is not None and valor < minimo:
            valor = int(minimo)
        if maximo is not None and valor > maximo:
            valor = int(maximo)
        return valor
    if tipo == "float":
        valor = 1.5
        if minimo is not None and valor < minimo:
            valor = float(minimo)
        if maximo is not None and valor > maximo:
            valor = float(maximo)
        return valor
    if tipo == "boolean":
        return True
    if tipo == "date":
        return "2026-01-15"
    if tipo == "uuid":
        return _ID_EXEMPLO_UUID
    if tipo == "file":
        return "arquivo.pdf"
    # string
    padrao = spec.get("pattern")
    if padrao:
        for candidato in _candidatos_padrao(padrao):
            try:
                if re.fullmatch(padrao, candidato) and _tamanho_ok(candidato, spec):
                    return candidato
            except re.error:
                break
        return "valor-de-exemplo"          # não foi possível gerar: o texto avisa
    base = nome if nome else "texto"
    if minimo is not None and len(base) < minimo:
        base = (base + "x" * int(minimo))[: max(int(minimo), len(base))]
    if maximo is not None and len(base) > maximo:
        base = base[: int(maximo)]
    return base


def _exemplo_campo(nome: str, spec: Dict[str, Any]) -> Any:
    if spec.get("default") is not None and not spec.get("is_array"):
        pass                                # o exemplo mostra um valor real, não o default
    valor = _escalar_exemplo(nome, spec)
    return [valor] if spec.get("is_array") else valor


def _exemplo_corpo(campos: Dict[str, Dict[str, Any]], so_obrigatorios: bool = False,
                   sobrescreve: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    corpo = {}
    for nome, spec in campos.items():
        if spec["type"] == "file":
            continue                        # arquivo vai por multipart; fica fora do JSON
        if so_obrigatorios and not spec.get("required"):
            continue
        corpo[nome] = _exemplo_campo(nome, spec)
    if sobrescreve:
        corpo.update(sobrescreve)
    return corpo


# ---------------------------------------------------------------------------
# Flow: caminhos possíveis e um exemplo válido por caminho
# ---------------------------------------------------------------------------

def _percorrer(runtime: Dict[str, Any], valores: Dict[str, Any]) -> Tuple[List[str], Dict[str, Any]]:
    """Mesma regra do servidor (`_walk_flow`): a primeira transição cuja condição vale decide."""
    etapa = runtime["start"]
    visitadas: List[str] = []
    busca = lambda _etapa, nome: valores.get(nome)
    while True:
        visitadas.append(etapa)
        if len(visitadas) > len(runtime["steps"]):
            raise ValueError("flow inválido")
        escolhida = None
        for t in runtime["steps"][etapa]["transitions"]:
            if t["when"] is None or avaliar_json(t["when"], busca):
                escolhida = t
                break
        if escolhida is None:
            raise ValueError("sem caminho")
        if escolhida["submit"] is not None:
            return visitadas, escolhida["submit"]
        etapa = escolhida["goto"]


def _campos_da_condicao(no: Dict[str, Any], saida: Dict[str, List[Any]]) -> None:
    k = no["k"]
    if k in ("or", "and"):
        _campos_da_condicao(no["l"], saida)
        _campos_da_condicao(no["r"], saida)
    elif k == "not":
        _campos_da_condicao(no["e"], saida)
    elif k == "field":
        saida.setdefault(no["name"], []).extend([True, False])
    elif k == "cmp":
        for lado, outro in (("l", "r"), ("r", "l")):
            if no[lado]["k"] == "field":
                lit = no[outro]
                saida.setdefault(no[lado]["name"], [])
                if lit["k"] == "lit":
                    v = lit["v"]
                    saida[no[lado]["name"]].append(v)
                    if isinstance(v, (int, float)) and not isinstance(v, bool):
                        saida[no[lado]["name"]].extend([v - 1, v + 1])
                    elif isinstance(v, str):
                        saida[no[lado]["name"]].append(v + "-x")
                elif lit["k"] == "field":
                    saida[no[lado]["name"]].extend([1, 2, 3, "a", "b"])
    elif k == "in":
        nome = no["f"]["name"]
        saida.setdefault(nome, [])
        saida[nome].extend(no["v"])
        saida[nome].append("fora-da-lista")
        saida[nome].extend([v + 1 for v in no["v"] if isinstance(v, (int, float)) and not isinstance(v, bool)])
    elif k == "empty":
        saida.setdefault(no["f"]["name"], []).extend([None, "preenchido"])


def _todos_caminhos(runtime: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Todos os caminhos (etapas + transição final) do início até um envio (grafo acíclico)."""
    resultado: List[Dict[str, Any]] = []

    def rec(etapa: str, passos: List[str], idxs: List[Tuple[str, int]]):
        for i, t in enumerate(runtime["steps"][etapa]["transitions"]):
            marca = idxs + [(etapa, i)]
            if t["submit"] is not None:
                resultado.append({"steps": passos, "last": marca, "submit": t["submit"]})
            elif t["goto"] not in passos:
                rec(t["goto"], passos + [t["goto"]], marca)

    rec(runtime["start"], [runtime["start"]], [])
    return resultado


def _resolver_caminho(runtime: Dict[str, Any], caminho: Dict[str, Any],
                      campos: Dict[str, Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """Valores dos campos de condição que fazem o servidor seguir exatamente este caminho."""
    candidatos: Dict[str, List[Any]] = {}
    for etapa, i in caminho["last"]:
        cond = runtime["steps"][etapa]["transitions"][i]["when"]
        if cond is not None:
            _campos_da_condicao(cond, candidatos)
    # as transições anteriores da mesma etapa também influenciam o resultado
    for etapa in caminho["steps"]:
        for t in runtime["steps"][etapa]["transitions"]:
            if t["when"] is not None:
                _campos_da_condicao(t["when"], candidatos)
    nomes = sorted(candidatos)
    listas = []
    for nome in nomes:
        base = _escalar_exemplo(nome, campos[nome]) if nome in campos else "x"
        unicos: List[Any] = []
        for v in [base] + candidatos[nome]:
            if v not in unicos or (isinstance(v, bool) and not any(isinstance(u, bool) and u == v for u in unicos)):
                unicos.append(v)
        listas.append(unicos)
    total = 1
    for lista in listas:
        total *= len(lista)
    combos = itertools.islice(itertools.product(*listas), _MAX_COMBINACOES) if nomes else [()]
    for combo in combos:
        valores = dict(zip(nomes, combo))
        # campos de condição vazios (None) não entram no corpo
        try:
            visitadas, enviado = _percorrer(runtime, {k: v for k, v in valores.items()})
        except ValueError:
            continue
        if visitadas == caminho["steps"] and enviado == caminho["submit"]:
            return valores
    return None


def _flow_info(ast: ProgramNode, montagem: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    if ast.flow is None:
        return None
    graph = FlowGraph(ast.flow)
    runtime = None
    for c in montagem["configs"]:
        if "flow" in c:
            runtime = c["flow"]
            break
    if runtime is None:
        from generator_flask import _flow_runtime_config
        runtime = _flow_runtime_config(ast)
    transicoes = []
    for t in graph.transitions:
        cond = None
        if t.condition is not None:
            cond = para_texto(para_json(t.condition, Escopo(ast.flow.name, t.source_form), ast.forms), t.source_form)
        transicoes.append({
            "origem": t.source_form,
            "destino": t.target_form if t.target_form is not None else f"{t.target_api}.{str(t.target_verb).upper()}",
            "envio": t.is_submit,
            "api": t.target_api,
            "verbo": str(t.target_verb).upper() if t.is_submit else None,
            "condicao": cond,
        })
    return {"nome": ast.flow.name, "inicio": graph.start, "etapas": list(graph.steps),
            "transicoes": transicoes, "runtime": runtime}


def _caminhos_do_flow(flow: Dict[str, Any], ast: ProgramNode,
                      campos: Dict[str, Dict[str, Any]]) -> List[Dict[str, Any]]:
    runtime = flow["runtime"]
    saida = []
    vistos = set()
    for caminho in _todos_caminhos(runtime):
        # transições diferentes que levam às MESMAS etapas e ao mesmo envio são o mesmo
        # caminho para quem chama a API (os campos aceitos são os mesmos): uma entrada só
        chave = (tuple(caminho["steps"]), json.dumps(caminho["submit"], sort_keys=True, default=str))
        if chave in vistos:
            continue
        vistos.add(chave)
        condicoes = []
        for etapa, i in caminho["last"]:
            transicoes = runtime["steps"][etapa]["transitions"]
            escolhida = transicoes[i]
            if sum(1 for t in transicoes if (t["goto"], t["submit"]) == (escolhida["goto"], escolhida["submit"])) > 1:
                continue        # várias transições levam ao mesmo destino: a condição não decide o caminho
            # texto das condições: as anteriores falsas, a escolhida verdadeira
            for j, t in enumerate(transicoes[: i + 1]):
                if t["when"] is None:
                    continue
                txt = para_texto(t["when"], etapa)
                condicoes.append(txt if j == i else f"not ({txt})")
        valores = _resolver_caminho(runtime, caminho, campos)
        campos_do_caminho: Dict[str, Dict[str, Any]] = {}
        for etapa in caminho["steps"]:
            for nome in runtime["steps"][etapa]["fields"]:
                campos_do_caminho[nome] = campos[nome]
        corpo = None
        if valores is not None:
            corpo = _exemplo_corpo(campos_do_caminho, sobrescreve={
                k: v for k, v in valores.items() if k in campos_do_caminho and v is not None})
            for k, v in valores.items():
                if v is None:
                    corpo.pop(k, None)
        saida.append({
            "etapas": caminho["steps"],
            "envio": caminho["submit"],
            "condicoes": condicoes,
            "campos": campos_do_caminho,
            "exemplo": corpo,
        })
    return saida


# ---------------------------------------------------------------------------
# Modelo
# ---------------------------------------------------------------------------

def _status_do(metodo: str, tem_param: bool, unico: bool, flow: bool, upload: bool) -> List[Tuple[int, str]]:
    if metodo == "POST":
        lista = [(201, "Registro criado"), (400, "Dados inválidos")]
        if unico:
            lista.append((409, "Já existe registro com a mesma chave"))
    elif metodo == "GET":
        lista = [(200, "Registro" if tem_param else "Lista de registros")]
        if tem_param:
            lista.append((404, "Registro não encontrado"))
    elif metodo in ("PUT", "PATCH"):
        lista = [(200, "Registro atualizado"), (400, "Dados inválidos"), (404, "Registro não encontrado")]
        if unico:
            lista.append((409, "Já existe registro com a mesma chave"))
    else:
        lista = [(200, "Registro excluído"), (404, "Registro não encontrado")]
    if upload and metodo in ("POST", "PUT", "PATCH"):
        lista.append((413, "Corpo ou arquivo acima do limite"))
    lista.append((500, "Erro interno"))
    return lista


def construir_modelo(ast: ProgramNode, avisos: Optional[List[str]] = None) -> Dict[str, Any]:
    montagem = montar_endpoints(ast)
    configs = montagem["configs"]
    flow = _flow_info(ast, montagem)

    endpoints: List[Dict[str, Any]] = []
    cache_caminhos: Dict[str, List[Dict[str, Any]]] = {}
    for rota in montagem["routes"]:
        cfg = configs[rota["config_id"]]
        campos = cfg["fields"]
        ep = rota["endpoint"]
        metodo = rota["method"]
        params = cfg["route_params"]
        eh_flow = "flow" in cfg
        caminhos = None
        if eh_flow:
            chave = f'{cfg["api"]}.{metodo}'
            if chave not in cache_caminhos:
                cache_caminhos[chave] = [
                    c for c in _caminhos_do_flow(flow, ast, campos)
                    if c["envio"]["api"] == cfg["api"] and c["envio"]["verb"] == metodo]
            caminhos = cache_caminhos[chave]
        # exemplo de corpo
        if eh_flow:
            ex = next((c["exemplo"] for c in caminhos if c["exemplo"] is not None), None)
        else:
            ex = _exemplo_corpo(campos)
        if metodo == "PATCH":
            ex_patch = None
            for nome, spec in campos.items():
                if spec["type"] != "file" and nome not in params:
                    ex_patch = {nome: _exemplo_campo(nome, spec)}
                    break
            ex = ex_patch if ex_patch is not None else ex
        upload = any(s["type"] == "file" for s in campos.values())
        valores_param = {p: _exemplo_campo(p, campos[p]) for p in params}
        endpoints.append({
            "metodo": metodo,
            "rota": rota["template"],
            "rota_flask": rota["route"],
            "api": rota["api"],
            "form": cfg["form"],
            "tabela": cfg["table"],
            "params": params,
            "valores_param": valores_param,
            "campos": campos,
            "unicos": cfg["unique"],
            "eh_flow": eh_flow,
            "caminhos": caminhos,
            "exemplo": ex,
            "upload": upload,
            "produces": ep.produces,
            "headers": dict(ep.headers or {}),
            "status": _status_do(metodo, bool(params), bool(cfg["unique"]), eh_flow, upload),
            "config_id": rota["config_id"],
        })
    return {
        "tema": ast.theme.name if ast.theme else None,
        "formularios": {n: f for n, f in ast.forms.items()},
        "endpoints": endpoints,
        "flow": flow,
        "tabelas": montagem["sql_tables"],
        "schema_sql": montagem["schema_sql"],
        "banco": montagem["database_config"],
        "avisos": list(avisos or []),
    }


# ---------------------------------------------------------------------------
# API.md
# ---------------------------------------------------------------------------

def _json(v: Any, indent: Optional[int] = None) -> str:
    return json.dumps(v, ensure_ascii=False, indent=indent)


def _sh(texto: str) -> str:
    return "'" + texto.replace("'", "'\\''") + "'"


def _url_exemplo(ep: Dict[str, Any]) -> str:
    rota = ep["rota"]
    for p, v in ep["valores_param"].items():
        rota = rota.replace("{" + p + "}", quote(str(v), safe=""))
    return "http://localhost:5000" + rota


def _valor_form(v: Any) -> str:
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, list):
        return str(v[0]) if v else ""
    return str(v)


def exemplo_curl(ep: Dict[str, Any], corpo: Optional[Dict[str, Any]] = None) -> str:
    metodo = ep["metodo"]
    url = _url_exemplo(ep)
    corpo = ep["exemplo"] if corpo is None else corpo
    if metodo in ("POST", "PUT", "PATCH") and corpo is not None:
        arquivos = [n for n, s in ep["campos"].items() if s["type"] == "file"]
        if arquivos and not ep["eh_flow"]:
            # campo `file` exige multipart (o servidor guarda o arquivo enviado)
            partes = [f"curl -X {metodo} {_sh(url)}"]
            for nome, valor in corpo.items():
                partes.append(f"  -F {_sh(nome + '=' + _valor_form(valor))}")
            for nome in arquivos:
                if metodo == "PATCH" and nome not in corpo and len(arquivos) > 0 and not ep["campos"][nome].get("required"):
                    continue
                partes.append(f"  -F {_sh(nome + '=@./arquivo.pdf')}")
            return " \\\n".join(partes)
        return (f"curl -X {metodo} {_sh(url)} \\\n  -H 'Content-Type: application/json' \\\n"
                f"  -d {_sh(_json(corpo))}")
    return f"curl -X {metodo} {_sh(url)}"


def _tipo_texto(spec: Dict[str, Any]) -> str:
    t = spec["type"]
    return f"lista de {t}" if spec.get("is_array") else t


def _regras_texto(spec: Dict[str, Any]) -> str:
    partes = []
    if spec.get("min") is not None:
        partes.append(f"mín. {spec['min']}")
    if spec.get("max") is not None:
        partes.append(f"máx. {spec['max']}")
    if spec.get("pattern"):
        partes.append(f"formato (regex) `{spec['pattern']}`")
    if spec.get("default") is not None:
        partes.append(f"valor padrão: `{_json(spec['default'])}`")
    if spec.get("message"):
        partes.append(f"mensagem: \"{spec['message']}\"")
    return "; ".join(partes) or "—"


def _tabela_campos(campos: Dict[str, Dict[str, Any]], obrigatorio_sempre: bool = True) -> List[str]:
    linhas = ["| Campo | Tipo | Obrigatório | Regras |", "|---|---|---|---|"]
    for nome, spec in campos.items():
        obr = "sim" if spec.get("required") else "não"
        linhas.append(f"| `{nome}` | {_tipo_texto(spec)} | {obr} | {_regras_texto(spec)} |")
    return linhas


def _mermaid(flow: Dict[str, Any]) -> List[str]:
    linhas = ["```mermaid", "flowchart TD"]
    ids = {e: f"E{i}" for i, e in enumerate(flow["etapas"])}
    for e, i in ids.items():
        linhas.append(f'  {i}["{e}"]')
    envios = {}
    for t in flow["transicoes"]:
        if t["envio"]:
            envios.setdefault(t["destino"], f"S{len(envios)}")
    for d, i in envios.items():
        linhas.append(f'  {i}(["{d}"])')
    for t in flow["transicoes"]:
        a = ids[t["origem"]]
        b = envios[t["destino"]] if t["envio"] else ids[t["destino"]]
        if t["condicao"]:
            rot = t["condicao"].replace('"', "#quot;")
            linhas.append(f'  {a} -->|"{rot}"| {b}')
        else:
            linhas.append(f"  {a} --> {b}")
    linhas.append("```")
    return linhas


def render_markdown(modelo: Dict[str, Any]) -> str:
    L: List[str] = []
    eps = modelo["endpoints"]
    L += ["# Documentação da API", "",
          "> Gerada automaticamente pelo Askform a partir do arquivo `.fad`. "
          "Não edite à mão: compile de novo para atualizar.", ""]
    L += ["## Visão geral", ""]
    L.append(f"- Formulários: {', '.join(f'`{n}`' for n in modelo['formularios']) or '—'}")
    apis = []
    for e in eps:
        if e["api"] not in apis:
            apis.append(e["api"])
    L.append(f"- APIs: {', '.join(f'`{a}`' for a in apis) or '—'}")
    L.append(f"- Endpoints que gravam dados: {len(eps)}")
    if modelo["flow"]:
        L.append(f"- Flow: `{modelo['flow']['nome']}` ({len(modelo['flow']['etapas'])} etapa(s))")
    L += ["- Como subir: `python main.py arquivo.fad` e depois `python dist/app.py` (porta 5000; "
          "`ASKFORM_HOST` e `ASKFORM_PORT` mudam endereço e porta)", ""]

    banco = modelo["banco"]
    L += ["## Banco de dados", ""]
    L.append(f"- Engine: `{banco['engine']}`" + (" (dados somem ao parar o servidor)" if banco["engine"] == "memory" else ""))
    if banco["engine"] != "memory":
        L.append(f"- Arquivo: `data/{banco['path'] or 'database.db'}` (variável `ASKFORM_DATABASE` troca)")
    L.append(f"- Esquema: `{banco['schema']}`" +
             (" (o servidor cria/atualiza as tabelas)" if banco["schema"] == "auto"
              else " (você aplica `dist/schema.sql`; o servidor só avisa o que falta)"))
    L.append("")
    for t in modelo["tabelas"]:
        L += [f"### Tabela `{t['name']}`", "",
              "| Coluna | Tipo SQL | Restrições |", "|---|---|---|",
              "| `id` | INTEGER | chave primária, automática |"]
        for c in t["columns"]:
            rest = []
            if c["not_null"]:
                rest.append("NOT NULL")
            if c["default"] is not None:
                rest.append(f"DEFAULT {c['default']}")
            rest += c["checks"]
            if c["name"] in t["unique"]:
                rest.append("único")
            L.append(f"| `{c['name']}` | {c['sql_type']} | {', '.join(rest) or '—'} |")
        L.append("")
    L += ["O SQL completo está em `dist/schema.sql`.", ""]

    L += ["## Formulários", ""]
    for nome, form in modelo["formularios"].items():
        L += [f"### `{nome}`", ""]
        L += ["| Campo | Tipo | Rótulo | Obrigatório | Regras |", "|---|---|---|---|---|"]
        for fn, f in form.fields.items():
            props = getattr(f, "properties", {}) or {}
            rules = getattr(form.validations.get(fn), "rules", {}) if form.validations.get(fn) else {}
            spec = {"min": rules.get("min"), "max": rules.get("max"), "pattern": rules.get("pattern"),
                    "message": rules.get("message"), "default": props.get("default") if not hasattr(props.get("default"), "form_name") else None}
            tipo = ("lista de " if f.is_array else "") + str(f.field_type).lower()
            L.append(f"| `{fn}` | {tipo} | {props.get('label', '—')} | "
                     f"{'sim' if props.get('required') else 'não'} | {_regras_texto(spec)} |")
        L.append("")

    if modelo["flow"]:
        fl = modelo["flow"]
        L += [f"## Flow `{fl['nome']}`", "", f"Etapa inicial: `{fl['inicio']}`.", ""]
        L += _mermaid(fl)
        L += ["", "As transições de cada etapa são testadas na ordem; a primeira cuja condição vale decide. "
              "O servidor recalcula o caminho a partir dos dados enviados (não confia no navegador).", ""]
        L += ["| De | Para | Condição |", "|---|---|---|"]
        for t in fl["transicoes"]:
            L.append(f"| `{t['origem']}` | `{t['destino']}` | {('`' + t['condicao'] + '`') if t['condicao'] else 'sempre'} |")
        L.append("")

    L += ["## Endpoints", ""]
    for ep in eps:
        L += [f"### `{ep['metodo']} {ep['rota']}`", ""]
        L.append(f"- API: `{ep['api']}` · consome: `{ep['form']}` · tabela: `{ep['tabela']}`")
        L.append(f"- `produces = {ep['produces']}` no .fad (informativo: o servidor responde sempre o formato abaixo)")
        if ep["headers"]:
            hs = ", ".join(f"`{k}: {v}`" for k, v in ep["headers"].items())
            L.append(f"- Cabeçalhos declarados no .fad: {hs} (informativos; o servidor não os exige)")
        if ep["params"]:
            L.append("- Parâmetro de rota: " + ", ".join(f"`{p}` (chave única)" for p in ep["params"]))
        L.append("")
        if ep["metodo"] in ("POST", "PUT", "PATCH"):
            if ep["eh_flow"]:
                L += ["**Caminhos aceitos** (o corpo precisa corresponder a exatamente um):", ""]
                if not ep["caminhos"]:
                    L += ["_Nenhum caminho do flow termina neste endpoint._", ""]
                for i, c in enumerate(ep["caminhos"], 1):
                    L.append(f"{i}. {' → '.join(c['etapas'])}")
                    if c["condicoes"]:
                        L.append("   - quando: " + "; ".join(f"`{x}`" for x in c["condicoes"]))
                    obrig = [n for n, s in c["campos"].items() if s["required"]]
                    L.append("   - campos: " + (", ".join(f"`{n}`" for n in c["campos"]) or "—") +
                             (f" (obrigatórios: {', '.join(f'`{n}`' for n in obrig)})" if obrig else ""))
                    if c["exemplo"] is not None and ep["metodo"] == "POST":
                        L += ["", "   ```bash", "   " + exemplo_curl(ep, c["exemplo"]).replace("\n", "\n   "), "   ```"]
                    elif ep["metodo"] == "POST":
                        L.append("   - (exemplo não gerado automaticamente: condição complexa demais)")
                L.append("")
            else:
                if ep["metodo"] == "PATCH":
                    L += ["Corpo (JSON ou formulário): qualquer subconjunto dos campos abaixo; "
                          "nenhum é obrigatório em PATCH.", ""]
                else:
                    L += ["Corpo (JSON, `application/x-www-form-urlencoded` ou `multipart/form-data`):", ""]
                L += _tabela_campos(ep["campos"]) + [""]
                if ep["upload"]:
                    L += ["Campos `file` são enviados como `multipart/form-data`; a resposta guarda o caminho salvo.", ""]
        if not (ep["eh_flow"] and ep["metodo"] == "POST"):
            L += ["```bash", exemplo_curl(ep), "```", ""]
        L += ["Respostas:", "", "| Status | Significado |", "|---|---|"]
        for st, txt in ep["status"]:
            L.append(f"| {st} | {txt} |")
        L.append("")
        if ep["metodo"] == "GET" and not ep["params"]:
            L += ["Parâmetros de consulta: `limit` (1–500, padrão 100) e `offset` (padrão 0).", ""]

    L += ["## Convenções das respostas", "",
          "Sucesso: `{\"status\": \"success\", ...}`; erro: `{\"status\": \"error\", \"message\": \"...\"}`.", "",
          "| Operação | Corpo da resposta de sucesso |", "|---|---|",
          "| POST | `{status, message, record_id, data}` (HTTP 201) |",
          "| GET por chave | `{status, record}` |",
          "| GET lista | `{status, count, records, limit, offset}` |",
          "| PUT / PATCH | `{status, message, updated_fields}` |",
          "| DELETE | `{status, message}` |", "",
          "Valores gravados: `boolean` vira 0/1, listas viram texto JSON, `date` vira `AAAA-MM-DD`, "
          "`integer` é inteiro de 64 bits com sinal. Todas as respostas permitem CORS (`*`).", ""]

    if modelo["avisos"]:
        L += ["## Avisos do compilador", ""] + [f"- {a}" for a in modelo["avisos"]] + [""]
    return "\n".join(L).rstrip("\n") + "\n"


# ---------------------------------------------------------------------------
# OpenAPI 3.0.3
# ---------------------------------------------------------------------------

_TIPO_OPENAPI = {
    "string": {"type": "string"},
    "integer": {"type": "integer", "format": "int64"},
    "float": {"type": "number", "format": "double"},
    "boolean": {"type": "boolean"},
    "date": {"type": "string", "format": "date"},
    "uuid": {"type": "string", "format": "uuid"},
    "file": {"type": "string", "format": "binary"},
}


def _schema_campo(spec: Dict[str, Any]) -> Dict[str, Any]:
    base = dict(_TIPO_OPENAPI.get(spec["type"], {"type": "string"}))
    tipo = spec["type"]
    minimo, maximo = spec.get("min"), spec.get("max")
    if tipo == "string":
        if minimo is not None:
            base["minLength"] = int(minimo)
        if maximo is not None:
            base["maxLength"] = int(maximo)
        if spec.get("pattern"):
            base["pattern"] = "^(?:" + spec["pattern"] + ")$"   # o servidor usa fullmatch
    elif tipo in ("integer", "float"):
        if minimo is not None:
            base["minimum"] = minimo
        if maximo is not None:
            base["maximum"] = maximo
    if spec.get("default") is not None and not spec.get("is_array"):
        base["default"] = spec["default"]
    if spec.get("message"):
        base["x-askform-mensagem"] = spec["message"]
    if spec.get("is_array"):
        return {"type": "array", "items": base}
    return base


def _schema_form(campos: Dict[str, Dict[str, Any]], obrigatorios: bool = True,
                 nomes: Optional[List[str]] = None) -> Dict[str, Any]:
    nomes = list(campos) if nomes is None else nomes
    esquema: Dict[str, Any] = {
        "type": "object",
        "properties": {n: _schema_campo(campos[n]) for n in nomes},
        "additionalProperties": False,
    }
    if obrigatorios:
        req = [n for n in nomes if campos[n].get("required") and campos[n].get("default") is None]
        if req:
            esquema["required"] = req
    return esquema


def _schema_registro(tabela: Dict[str, Any]) -> Dict[str, Any]:
    props: Dict[str, Any] = {"id": {"type": "integer"}}
    for c in tabela["columns"]:
        tipo = c["sql_type"]
        props[c["name"]] = {"type": "integer"} if tipo in ("INTEGER",) else (
            {"type": "number"} if tipo == "REAL" else {"type": "string"})
        props[c["name"]]["nullable"] = True
    return {"type": "object", "properties": props}


def _resp(descricao: str, ref: str) -> Dict[str, Any]:
    return {"description": descricao,
            "content": {"application/json": {"schema": {"$ref": f"#/components/schemas/{ref}"}}}}


def _nome_schema(texto: str) -> str:
    return re.sub(r"[^A-Za-z0-9_]", "", texto)


def render_openapi(modelo: Dict[str, Any]) -> Dict[str, Any]:
    tabelas = {t["name"]: t for t in modelo["tabelas"]}
    schemas: Dict[str, Any] = {
        "Erro": {"type": "object", "required": ["status", "message"], "properties": {
            "status": {"type": "string", "enum": ["error"]}, "message": {"type": "string"}}},
        "Criado": {"type": "object", "properties": {
            "status": {"type": "string"}, "message": {"type": "string"},
            "record_id": {"type": "integer"}, "data": {"type": "object"}}},
        "Registro": {"type": "object", "properties": {
            "status": {"type": "string"}, "record": {"type": "object"}}},
        "Lista": {"type": "object", "properties": {
            "status": {"type": "string"}, "count": {"type": "integer"},
            "records": {"type": "array", "items": {"type": "object"}},
            "limit": {"type": "integer"}, "offset": {"type": "integer"}}},
        "Atualizado": {"type": "object", "properties": {
            "status": {"type": "string"}, "message": {"type": "string"},
            "updated_fields": {"type": "array", "items": {"type": "string"}}}},
        "Excluido": {"type": "object", "properties": {
            "status": {"type": "string"}, "message": {"type": "string"}}},
    }
    for t in modelo["tabelas"]:
        schemas[f"Registro_{_nome_schema(t['name'])}"] = _schema_registro(t)

    paths: Dict[str, Dict[str, Any]] = {}
    for ep in modelo["endpoints"]:
        op: Dict[str, Any] = {
            "tags": [ep["api"]],
            "summary": f"{ep['metodo']} {ep['rota']}",
            "operationId": f"{ep['api']}_{ep['metodo'].lower()}_{ep['config_id']}",
            "x-askform-produces": ep["produces"],
        }
        if ep["headers"]:
            op["x-askform-headers"] = ep["headers"]
        parametros = []
        for p in ep["params"]:
            parametros.append({"name": p, "in": "path", "required": True,
                               "schema": _schema_campo({**ep["campos"][p], "default": None})})
        if ep["metodo"] == "GET" and not ep["params"]:
            parametros += [
                {"name": "limit", "in": "query", "required": False,
                 "schema": {"type": "integer", "minimum": 1, "maximum": 500, "default": 100}},
                {"name": "offset", "in": "query", "required": False,
                 "schema": {"type": "integer", "minimum": 0, "default": 0}}]
        if parametros:
            op["parameters"] = parametros

        if ep["metodo"] in ("POST", "PUT", "PATCH"):
            if ep["eh_flow"]:
                alternativas = []
                for c in ep["caminhos"] or []:
                    s = _schema_form(c["campos"])
                    s["title"] = " → ".join(c["etapas"])
                    if c["condicoes"]:
                        s["x-askform-condicoes"] = c["condicoes"]
                    alternativas.append(s)
                corpo_schema: Dict[str, Any] = {"oneOf": alternativas} if alternativas else {"type": "object"}
            elif ep["metodo"] == "PATCH":
                corpo_schema = _schema_form(ep["campos"], obrigatorios=False)
            else:
                corpo_schema = _schema_form(ep["campos"])
            conteudo = {"application/json": {"schema": corpo_schema}}
            if ep["upload"] and not ep["eh_flow"]:
                conteudo["multipart/form-data"] = {"schema": corpo_schema}
            op["requestBody"] = {"required": True, "content": conteudo}

        respostas: Dict[str, Any] = {}
        ok_ref = {"POST": "Criado", "PUT": "Atualizado", "PATCH": "Atualizado", "DELETE": "Excluido"}.get(
            ep["metodo"], "Registro" if ep["params"] else "Lista")
        for st, txt in ep["status"]:
            if st == 200 or st == 201:
                resp = _resp(txt, ok_ref)
                if ep["metodo"] == "GET" and ep["params"]:
                    resp["content"]["application/json"]["schema"] = {
                        "type": "object", "properties": {
                            "status": {"type": "string"},
                            "record": {"$ref": f"#/components/schemas/Registro_{_nome_schema(ep['tabela'])}"}}}
                respostas[str(st)] = resp
            else:
                respostas[str(st)] = _resp(txt, "Erro")
        op["responses"] = respostas
        paths.setdefault(ep["rota"], {})[ep["metodo"].lower()] = op

    return {
        "openapi": "3.0.3",
        "info": {"title": "API gerada pelo Askform", "version": "1.0.0",
                 "description": "Documentação gerada automaticamente a partir do arquivo .fad."},
        "servers": [{"url": "http://localhost:5000"}],
        "paths": paths,
        "components": {"schemas": schemas},
    }


# ---------------------------------------------------------------------------
# Saída
# ---------------------------------------------------------------------------

def generate_docs(ast: ProgramNode, output_dir: str = "dist", avisos: Optional[List[str]] = None) -> List[str]:
    """Gera dist/API.md e dist/openapi.json; devolve os caminhos."""
    os.makedirs(output_dir, exist_ok=True)
    modelo = construir_modelo(ast, avisos)
    md_path = os.path.join(output_dir, "API.md")
    with open(md_path, "w", encoding="utf-8", newline="\n") as f:
        f.write(render_markdown(modelo))
    oa_path = os.path.join(output_dir, "openapi.json")
    with open(oa_path, "w", encoding="utf-8", newline="\n") as f:
        f.write(json.dumps(render_openapi(modelo), ensure_ascii=False, indent=2) + "\n")
    print(f"[SUCESSO] Documentação gerada em: {md_path} e {oa_path}")
    return [md_path, oa_path]