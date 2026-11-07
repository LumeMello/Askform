"""
Teste diferencial: pipeline ANTIGO (oráculo) x pipeline NOVO (SDD).

NÃO COMMITAR. Este arquivo e o resto da pasta oracle/ servem só para provar,
localmente, que a migração da análise semântica para a tabela de produções
manteve o comportamento.

  oracle/parser_old.py    cópia do parser.py original (git HEAD)
  oracle/semantic_old.py  cópia do semantic.py original (git HEAD)

Para cada programa-fonte, compara:
  1. resultado sintático (aceita/rejeita e a mensagem do erro);
  2. AST (dataclasses; os atributos novos `checks`/`symtab`/`errors` ficam
     fora da comparação);
  3. lista de erros semânticos: mesmo texto, mesma linha, MESMA ORDEM.

Uso (na raiz do repositório):
    python oracle/test_oracle.py            # roda tudo
    python oracle/test_oracle.py 5000       # fuzz com 5000 programas
    python -m pytest oracle/test_oracle.py  # alternativa com pytest
"""
import glob
import os
import random
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ORACLE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ORACLE)
sys.path.insert(0, ROOT)

from lexer import build_lexer                        # noqa: E402
import parser as parser_new                           # noqa: E402  (versão nova)
import semantic as semantic_new                       # noqa: E402  (versão nova)
import parser_old                                     # noqa: E402  (oráculo)
import semantic_old                                   # noqa: E402  (oráculo)

_PARSER_NEW = parser_new.build_parser()
_PARSER_OLD = parser_old.build_parser()


def _parse(parser, source):
    """Devolve ('ok', ast) | ('none', None) | ('erro', mensagem)."""
    try:
        ast = parser.parse(source, lexer=build_lexer())
    except Exception as exc:  # mesmo tratamento do main.py
        return ("erro", f"{type(exc).__name__}: {exc}")
    if not ast:
        return ("none", None)
    return ("ok", ast)


def run_old(source):
    status, value = _parse(_PARSER_OLD, source)
    if status != "ok":
        return status, value, None
    analyzer = semantic_old.SemanticAnalyzer()
    analyzer.analyze(value)
    return status, value, list(analyzer.errors)


def run_new(source):
    status, value = _parse(_PARSER_NEW, source)
    if status != "ok":
        return status, value, None
    analyzer = semantic_new.SemanticAnalyzer()
    analyzer.analyze(value)
    return status, value, list(analyzer.errors)


def compare(source):
    """Retorna None se igual; senão uma descrição da divergência."""
    old_status, old_val, old_errs = run_old(source)
    new_status, new_val, new_errs = run_new(source)
    if old_status != new_status:
        return f"status sintático diferente: antigo={old_status!r} novo={new_status!r}"
    if old_status != "ok":
        if old_val != new_val:
            return f"mensagem sintática diferente:\n  antigo: {old_val}\n  novo:   {new_val}"
        return None
    if old_val != new_val:
        return "AST diferente"
    if old_errs != new_errs:
        return (
            "erros semânticos diferentes:\n  antigo: "
            + "\n          ".join(old_errs)
            + "\n  novo:   "
            + "\n          ".join(new_errs)
        )
    # O resumo usado pelo main.py também deve ser igual.
    return None


# ---------------------------------------------------------------------------
# Casos fixos (um por regra e por comportamento notável)
# ---------------------------------------------------------------------------

FIXED_CASES = {
    "default date/uuid/file sempre erro + float aceita bool + array": '''
form F {
  d: date { default = "2024-01-01"; };
  u: uuid { default = "abc"; };
  f: float { default = true; };
  b: boolean { default = "x"; };
  s: string[] { default = 3; };
  fl: file { default = "x"; };
  n: boolean;
  validate n { min = 1; }
  validate d { pattern = "(["; }
}''',
    "validate inexistente e regras": '''
form F { a: integer; validate zzz { min = 1; } validate a { pattern = "x"; max = 3; } }''',
    "referencias, wizard, api e flow quebrados": '''
api A { POST "/a/{x}" { consumes = Nope; produces = uuid; } }
form G { z: string { default = H.k; }; }
wizard W { steps = [G, Missing]; submit = A.GET; }
flow Fl { Nada -> Ghost.POST; }''',
    "heranca ok": '''
form A { n: string; }
form B { c: string { default = A.n; }; }
wizard W { steps = [A, B]; }''',
    "heranca tipo errado e campo inexistente": '''
form A { n: integer; }
form B { c: string { default = A.n; }; d: string { default = A.zz; }; }
wizard W { steps = [B, A]; }''',
    "heranca para etapa posterior": '''
form A { n: string; }
form B { c: string { default = A.n; }; }
wizard W { steps = [B, A]; }''',
    "api consome wizard": '''
form A { n: string; }
wizard W { steps = [A]; }
api X { POST "/w/{q}" { consumes = W; produces = uuid; } GET "/g" { produces = string; } }
flow F { W -> X.POST; }''',
    "api param ok e param faltando": '''
form P { pid: integer; }
api A { GET "/p/{pid}" { consumes = P; produces = string; } GET "/q/{pid}/{outro}" { consumes = P; produces = string; } }
flow F { P -> A.GET; }''',
    "flow verbo inexistente": '''
form P { pid: integer; }
api A { GET "/p" { consumes = P; produces = string; } }
flow F { P -> A.DELETE; }''',
    "ordem: tudo declarado depois": '''
api A { POST "/a/{x}" { consumes = P; produces = uuid; } }
wizard W { steps = [P, Q]; submit = A.POST; }
form Q { r: string { default = P.n; }; }
form P { n: string; }''',
    "duplicidades sintaticas": '''
form F { a: integer; a: string; }''',
    "endpoint duplicado": '''
form F { a: integer; }
api A { POST "/x" { consumes = F; produces = uuid; } POST "/x" { consumes = F; produces = uuid; } }''',
    "form duplicado": '''
form F { a: integer; }
form F { b: integer; }''',
    "nomes iguais em tipos diferentes passam": '''
form X { a: integer; }
api X { POST "/x" { consumes = X; produces = uuid; } }
wizard X { steps = [X]; }''',
    "erro de sintaxe": '''
form F { a integer; }''',
    "tema e flow ok": '''
theme T { background = "#fff"; }
form F { a: integer { required = true; label = "A"; }; }
api A { POST "/f" { consumes = F; produces = uuid; headers { "X-A": "1"; }; } }
flow Fl { F -> A.POST; }''',
}


def test_casos_fixos():
    falhas = []
    for nome, src in FIXED_CASES.items():
        diff = compare(src)
        if diff:
            falhas.append(f"[{nome}] {diff}")
    assert not falhas, "\n".join(falhas)


def test_arquivos_fad_do_repositorio():
    arquivos = sorted(glob.glob(os.path.join(ROOT, "*.fad")))
    assert arquivos, "nenhum .fad encontrado na raiz"
    falhas = []
    for caminho in arquivos:
        with open(caminho, "r", encoding="utf-8-sig") as fh:
            diff = compare(fh.read())
        if diff:
            falhas.append(f"[{os.path.basename(caminho)}] {diff}")
    assert not falhas, "\n".join(falhas)


# ---------------------------------------------------------------------------
# Fuzz: programas aleatórios (válidos, com erros semânticos e com erros
# sintáticos), semente fixa para reproduzir.
# ---------------------------------------------------------------------------

TYPES = ["string", "integer", "float", "boolean", "date", "uuid", "file"]
FORMS = ["F0", "F1", "F2"]
FIELDS = ["a", "b", "c"]
VERBS = ["GET", "POST", "PUT", "PATCH", "DELETE"]


def _default_literal(rng):
    kind = rng.choice(["str", "int", "float", "true", "false", "ref", "ref", "none"])
    if kind == "str":
        return '"s"'
    if kind == "int":
        return str(rng.randint(0, 9))
    if kind == "float":
        return "1.5"
    if kind in ("true", "false"):
        return kind
    if kind == "ref":
        return f"{rng.choice(FORMS + ['Zz'])}.{rng.choice(FIELDS + ['q'])}"
    return None


def _gen_form(rng, name):
    lines = [f"form {name} {{"]
    for fname in rng.sample(FIELDS, rng.randint(0, 3)):
        props = []
        default = _default_literal(rng)
        if default is not None:
            props.append(f"default = {default};")
        if rng.random() < 0.3:
            props.append("required = true;")
        if rng.random() < 0.2:
            props.append('label = "L";')
        ftype = rng.choice(TYPES) + ("[]" if rng.random() < 0.15 else "")
        body = (" { " + " ".join(props) + " }") if props else ""
        lines.append(f"  {fname}: {ftype}{body};")
    for _ in range(rng.randint(0, 2)):
        target = rng.choice(FIELDS + ["zz"])
        rules = []
        for rule in rng.sample(["min", "max", "pattern", "message"], rng.randint(0, 3)):
            if rule in ("min", "max"):
                rules.append(f"{rule} = {rng.randint(0, 9)};")
            elif rule == "pattern":
                rules.append(f'pattern = "{rng.choice(["^a+$", "([", "x"])}";')
            else:
                rules.append('message = "m";')
        lines.append(f"  validate {target} {{ {' '.join(rules)} }}")
    lines.append("}")
    return "\n".join(lines)


def _gen_wizard(rng, name):
    steps = [rng.choice(FORMS + ["Zz"]) for _ in range(rng.randint(1, 3))]
    lines = [f"wizard {name} {{", f"  steps = [{', '.join(steps)}];"]
    if rng.random() < 0.6:
        lines.append(f"  submit = {rng.choice(['A0', 'A1', 'Nope'])}.{rng.choice(VERBS)};")
    lines.append("}")
    return "\n".join(lines)


def _gen_api(rng, name, wizards):
    lines = [f"api {name} {{"]
    for i in range(rng.randint(0, 3)):
        route = rng.choice(["/x", "/x/{a}", "/y/{a}/{zz}", f"/r{i}/{{b}}"])
        consumes = rng.choice(FORMS + wizards + ["Nope", None])
        props = []
        if consumes:
            props.append(f"consumes = {consumes};")
        props.append(f"produces = {rng.choice(TYPES)};")
        lines.append(f'  {rng.choice(VERBS)} "{route}" {{ {" ".join(props)} }}')
    lines.append("}")
    return "\n".join(lines)


def gen_program(rng):
    decls = []
    forms = rng.sample(FORMS, rng.randint(1, 3))
    wizards = [f"W{i}" for i in range(rng.randint(0, 2))]
    apis = [f"A{i}" for i in range(rng.randint(0, 2))]
    for f in forms:
        decls.append(_gen_form(rng, f))
    for w in wizards:
        decls.append(_gen_wizard(rng, w))
    for a in apis:
        decls.append(_gen_api(rng, a, wizards))
    if rng.random() < 0.1 and decls:           # duplicata sintática ocasional
        decls.append(rng.choice(decls))
    rng.shuffle(decls)                          # referências para frente
    parts = []
    if rng.random() < 0.2:
        parts.append('theme T { background = "#fff"; }')
    parts.extend(decls)
    if rng.random() < 0.5:
        source = rng.choice(forms + wizards + ["Nada"])
        parts.append(
            f"flow Fl {{ {source} -> {rng.choice(apis + ['Ghost'])}.{rng.choice(VERBS)}; }}"
        )
    src = "\n".join(parts)
    if rng.random() < 0.03:                     # erro sintático ocasional
        pos = rng.randrange(len(src))
        src = src[:pos] + src[pos + 1:]
    return src


def fuzz(n=1500, seed=20261107):
    rng = random.Random(seed)
    cobertura = {"ok": 0, "com_erros": 0, "sintatico": 0}
    for i in range(n):
        src = gen_program(rng)
        diff = compare(src)
        if diff:
            raise AssertionError(f"Divergência no programa #{i} (seed={seed}):\n{src}\n---\n{diff}")
        status, _, errs = run_new(src)
        if status != "ok":
            cobertura["sintatico"] += 1
        elif errs:
            cobertura["com_erros"] += 1
        else:
            cobertura["ok"] += 1
    return cobertura


def test_fuzz():
    cobertura = fuzz()
    # Garante que o fuzz exercitou os três cenários.
    assert all(v > 0 for v in cobertura.values()), cobertura


if __name__ == "__main__":
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 1500
    test_casos_fixos()
    print(f"OK  casos fixos ({len(FIXED_CASES)})")
    test_arquivos_fad_do_repositorio()
    print(f"OK  arquivos .fad do repositório ({len(glob.glob(os.path.join(ROOT, '*.fad')))})")
    cobertura = fuzz(n)
    print(f"OK  fuzz com {n} programas: {cobertura}")
