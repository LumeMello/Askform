"""
Testes do flow multi-etapas (páginas e caminhos condicionais).

Uso (na raiz do repositório):
    python tests/test_flow.py
    python -m pytest tests/
"""
import importlib.util
import os
import re
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from lexer import build_lexer            # noqa: E402
from parser import build_parser          # noqa: E402
from generator_html import generate_html  # noqa: E402
from generator_flask import generate_flask  # noqa: E402

_PARSER = build_parser()


def parse(source):
    return _PARSER.parse(source, lexer=build_lexer())


def erros(source):
    return [e.msg for e in parse(source).errors]


def ler(nome):
    with open(os.path.join(ROOT, nome), "r", encoding="utf-8-sig") as fh:
        return fh.read()


# ---------------------------------------------------------------------------
# Sintaxe
# ---------------------------------------------------------------------------

def test_exemplos_compilam_sem_erros():
    for nome in ("teste_multipagina.fad", "teste_caminhos.fad"):
        assert erros(ler(nome)) == [], nome


def test_wizard_nao_existe_mais():
    try:
        parse("form A { a: string; } wizard W { steps = [A]; }")
    except SyntaxError as exc:
        assert "wizard" in str(exc)
    else:
        raise AssertionError("wizard deveria ser erro de sintaxe")


def test_flow_vazio_e_erro_de_sintaxe():
    try:
        parse("form A { a: string; } flow F { }")
    except SyntaxError:
        return
    raise AssertionError("flow sem transições deveria ser erro de sintaxe")


def test_ast_das_transicoes():
    ast = parse('''
form A { tipo: string; n: integer; }
form B { b: string; }
api X { POST "/x" { consumes = F; produces = uuid; } }
flow F {
  A -> B when tipo != "x";
  A -> X.POST;
  B -> X.POST when A.n >= 10;
  B -> X.POST;
}''')
    t = ast.flow.transitions
    assert [x.source_form for x in t] == ["A", "A", "B", "B"]
    assert t[0].target_form == "B" and t[0].condition.operator == "!="
    assert t[1].target_api == "X" and t[1].target_verb == "POST" and t[1].condition is None
    c = t[2].condition
    assert (c.form_name, c.field_name, c.operator, c.value) == ("A", "n", ">=", 10)


# ---------------------------------------------------------------------------
# Semântica
# ---------------------------------------------------------------------------

BASE = '''
form A { x: string; n: integer; b: boolean; d: date; f: file; l: string[]; }
form B { y: string; }
form C { z: string; }
api Api { POST "/a" { consumes = F; produces = uuid; } }
'''


def test_referencias_inexistentes():
    assert erros(BASE + "flow F { A -> Nope; A -> Api.PUT; Ghost -> Fake.POST; }") == [
        "Flow 'F' referencia etapa inexistente 'Nope'.",
        "API destino 'Api' não suporta o verbo 'PUT' no flow.",
        "Flow 'F' referencia origem inexistente 'Ghost'.",
        "Flow 'F' referencia API inexistente 'Fake'.",
    ]


def test_condicoes_invalidas():
    assert erros(BASE + '''flow F {
 A -> B when x < "a";
 A -> B when n == "1";
 A -> B when f == "a";
 A -> B when l == "a";
 A -> B when d >= "2024-13-01";
 A -> B when zz == 1;
 A -> B when Nope.x == 1;
 A -> B;
 B -> Api.POST;
}''') == [
        "Operador '<' não pode ser usado com o campo 'x' do tipo 'string'.",
        "Valor '1' é incompatível com o tipo 'integer' do campo 'n' na condição.",
        "Campo 'f' do tipo 'file' não pode ser usado em condição.",
        "Campo 'l' é uma lista e não pode ser usado em condição.",
        "Valor '2024-13-01' não é uma data válida (use AAAA-MM-DD) na condição.",
        "Condição do flow 'F' referencia campo inexistente 'zz' na etapa 'A'.",
        "Condição do flow 'F' referencia formulário inexistente 'Nope'.",
    ]


def test_condicoes_validas():
    assert erros(BASE + '''flow F {
 A -> B when n >= 18;
 A -> B when d < "2000-01-01";
 A -> B when b == true;
 A -> C;
 B -> Api.POST when A.x == "ok";
 B -> Api.POST;
 C -> Api.POST;
}''') == []


def test_caminho_padrao():
    assert erros(BASE + '''flow F {
 A -> B;
 A -> C when x == "a";
 B -> C when y == "1";
 C -> Api.POST;
}''') == [
        "Transição de 'A' nunca é usada: a transição sem 'when' da linha 7 já é o caminho padrão.",
        "Etapa 'B' do flow 'F' só tem transições com 'when'; adicione uma transição sem 'when' como caminho padrão.",
    ]


def test_ciclo():
    assert erros(BASE + "flow F { A -> B; B -> C; C -> B; A -> Api.POST; }")[-1] == (
        "Flow 'F' tem um ciclo entre as etapas: B -> C -> B."
    )


def test_sem_saida_inalcancavel_e_campo_repetido():
    assert erros('''
form A { x: string; } form B { x: string; } form C { k: string; }
api Api { POST "/a" { consumes = F; produces = uuid; } }
flow F { A -> B; C -> Api.POST; }''') == [
        "Etapa 'B' do flow 'F' não tem transição de saída.",
        "Etapa 'C' do flow 'F' não é alcançável a partir da etapa inicial 'A'.",
        "Campo 'x' aparece nas etapas 'A' e 'B' do flow 'F'; os nomes de campo precisam ser únicos no flow.",
    ]


def test_heranca_e_condicao_exigem_etapa_anterior_em_todos_os_caminhos():
    assert erros('''
form A { x: string; }
form B { y: string { default = C.z; }; }
form C { z: string; }
api Api { POST "/a" { consumes = F; produces = uuid; } }
flow F {
 A -> B when x == "1";
 A -> C;
 C -> B when A.x == "2";
 C -> Api.POST when B.y == "k";
 C -> Api.POST;
 B -> Api.POST;
}''') == [
        "A etapa 'B' tenta herdar o valor de 'C', mas 'C' não vem antes dela em todos os caminhos do flow 'F'.",
        "A condição da transição de 'C' usa 'B.y', mas 'B' não vem antes de 'C' em todos os caminhos do flow 'F'.",
    ]


def test_envio_de_varias_etapas_exige_endpoint_que_consome_o_flow():
    assert erros('''
form A { x: string; } form B { y: string; }
api Api { POST "/a" { consumes = B; produces = uuid; } }
flow F { A -> B; B -> Api.POST; }''') == [
        "A transição de 'B' envia os dados de várias etapas para 'Api.POST', mas nenhum endpoint POST de 'Api' consome o flow (use consumes = F;).",
    ]


def test_endpoint_que_consome_o_flow():
    fonte = '''
form A { id: integer; } form B { b: string; }
api Api {
  PUT "/a/{id}" { consumes = F; produces = boolean; }
  GET "/a/{nada}" { consumes = F; produces = string; }
  POST "/x" { consumes = Nada; produces = uuid; }
}
flow F { A -> B; B -> Api.PUT; }'''
    assert erros(fonte) == [
        "Parâmetro de rota '{nada}' não declarado em nenhuma etapa do flow 'F'.",
        "Endpoint 'POST /x' consome formulário ou flow inexistente 'Nada'.",
    ]


def test_flow_com_nome_de_formulario():
    assert erros('''form F { a: string; }
api Api { POST "/a" { consumes = F; produces = uuid; } }
flow f { F -> Api.POST; }''') == ["Flow 'f' tem o mesmo nome do formulário 'F'."]


# ---------------------------------------------------------------------------
# Geração de código
# ---------------------------------------------------------------------------

def _gerar(nome_fad, out_dir):
    ast = parse(ler(nome_fad))
    assert ast.errors == []
    arquivos = generate_html(ast, out_dir)
    generate_flask(ast, out_dir)
    return ast, arquivos


def _carregar_app(out_dir):
    os.environ["ASKFORM_DATABASE"] = os.path.join(out_dir, "test.db")
    os.environ["ASKFORM_UPLOAD_FOLDER"] = os.path.join(out_dir, "uploads")
    spec = importlib.util.spec_from_file_location(
        f"askform_app_{abs(hash(out_dir))}", os.path.join(out_dir, "app.py")
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_html_multietapas_substitui_paginas_das_etapas():
    with tempfile.TemporaryDirectory() as out:
        _, arquivos = _gerar("teste_caminhos.fad", out)
        assert [os.path.basename(a) for a in arquivos] == ["cadastroflow.html"]
        with open(arquivos[0], encoding="utf-8") as fh:
            html = fh.read()
        assert len(re.findall(r'<form id="askform-\w+" data-step=', html)) == 6
        assert '"start": "TipoClienteStep"' in html
        assert '"op": "<", "value": 18' in html
        assert 'id="askform-back"' in html and 'id="askform-next"' in html


def test_html_flow_simples_continua_igual():
    with tempfile.TemporaryDirectory() as out:
        _, arquivos = _gerar("teste.fad", out)
        assert [os.path.basename(a) for a in arquivos] == ["produtoform.html"]


def test_heranca_vai_para_o_script_e_nao_para_o_value():
    with tempfile.TemporaryDirectory() as out:
        _, arquivos = _gerar("teste_multipagina.fad", out)
        with open(arquivos[0], encoding="utf-8") as fh:
            html = fh.read()
        assert '"DadosCobrancaStep": [["nomeCobranca", "ResponsavelLegalStep", "nomeResponsavel"]' in html
        assert "FieldRefNode" not in html


def test_backend_recebe_o_flow_inteiro():
    try:
        import flask  # noqa: F401
    except ImportError:
        print("  (flask não instalado: teste do backend pulado)")
        return
    with tempfile.TemporaryDirectory() as out:
        _gerar("teste_caminhos.fad", out)
        app = _carregar_app(out)
        campos = app.ENDPOINT_CONFIGS[0]["fields"]
        obrigatorios = sorted(k for k, v in campos.items() if v["required"])
        # Só as etapas presentes em todos os caminhos até o envio.
        assert obrigatorios == ["email", "tipo"]
        client = app.app.test_client()
        ok = client.post("/api/v1/clientes", data={
            "tipo": "PJ", "razaoSocial": "ACME", "cnpj": "1", "email": "a@b.c",
        })
        assert ok.status_code == 201, ok.get_json()
        falta = client.post("/api/v1/clientes", data={"tipo": "PJ"})
        assert falta.status_code == 400
        assert "email" in falta.get_json()["message"]


if __name__ == "__main__":
    testes = [(n, f) for n, f in sorted(globals().items()) if n.startswith("test_")]
    for nome, funcao in testes:
        funcao()
        print(f"OK  {nome}")
    print(f"{len(testes)} testes passaram.")
