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
Expressões lógicas das condições `when` do flow.

MODIFICADO (expressões nas condições): módulo novo. Concentra tudo que é de
expressão e não depende do parser nem do ponto de uso:

  * checar_condicao  checagem de tipos (atributo `tipo`), erros e avisos;
  * para_json        árvore serializável usada pelos geradores (HTML e Flask);
  * avaliar_json     avaliador Python ÚNICO. É usado pelo compilador (condição
                     constante) e o gerador copia o seu código-fonte para o
                     app.py, então compilador e servidor avaliam igual;
  * referencias      campos usados, na ordem do código.

Semântica de avaliação (a mesma no navegador e no servidor):
  * campo vazio  -> toda comparação que o usa (==, !=, <, <=, >, >=, in,
    not in) dá falso; `is empty` / `is not empty` testam o vazio;
  * campo booleano nunca é vazio (desmarcado/ausente vale falso);
  * `not` apenas inverte o resultado.

Para o `visible_if` (Parte A) só muda o `Escopo`: aqui, nome sem qualificação é
o campo da etapa de origem; lá seria o campo do próprio formulário.
"""
import datetime
import uuid
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

from symbol_table import (
    CompareExpr, EmptyExpr, ExprNode, FieldRefExpr, InExpr, LiteralExpr,
    LogicExpr, NotExpr,
)

Diagnostico = Tuple[int, str]            # (linha, mensagem)

_ORDERED_TYPES = ('integer', 'float', 'date')
_EQUALITY_OPS = ('==', '!=')
_NUMERIC = ('integer', 'float')


@dataclass
class Escopo:
    """Onde a expressão aparece: define o que um nome sem qualificação significa."""
    flow_name: str
    source_form: str


def _condition_value_ok(field_type: str, val: Any) -> bool:
    if field_type in ('string', 'uuid', 'date'):
        return isinstance(val, str)
    if field_type == 'integer':
        return isinstance(val, int) and not isinstance(val, bool)
    if field_type == 'float':
        return isinstance(val, (int, float)) and not isinstance(val, bool)
    if field_type == 'boolean':
        return isinstance(val, bool)
    return False


def _show(val: Any) -> str:
    if isinstance(val, bool):
        return 'true' if val else 'false'
    return str(val)


def _literal_type(val: Any) -> str:
    if isinstance(val, bool):
        return 'boolean'
    if isinstance(val, int):
        return 'integer'
    if isinstance(val, float):
        return 'float'
    return 'string'


def _uuid_canonico(val: str) -> Optional[str]:
    try:
        return str(uuid.UUID(val))
    except (ValueError, AttributeError):
        return None


# ---------------------------------------------------------------------------
# Referências a campos
# ---------------------------------------------------------------------------

def referencias(expr: ExprNode) -> List[FieldRefExpr]:
    """Referências a campo na ordem do código-fonte (com repetições)."""
    if isinstance(expr, FieldRefExpr):
        return [expr]
    if isinstance(expr, (LogicExpr, CompareExpr)):
        return referencias(expr.left) + referencias(expr.right)
    if isinstance(expr, NotExpr):
        return referencias(expr.operand)
    if isinstance(expr, (InExpr, EmptyExpr)):
        return [expr.target]
    return []


# ---------------------------------------------------------------------------
# Checagem de tipos (atributo `tipo`, resolvido na raiz, pois precisa da
# tabela de símbolos) — gera erros e avisos
# ---------------------------------------------------------------------------

@dataclass
class _Operando:
    tipo: Optional[str]                  # None = operando inválido (erro já registrado)
    literal: bool = False
    valor: Any = None
    campo: Optional[str] = None
    obj: Any = None                      # FormFieldNode


class _Verificador:
    def __init__(self, escopo: Escopo, forms: Dict[str, Any]):
        self.escopo = escopo
        self.forms = forms
        self.erros: List[Diagnostico] = []
        self.avisos: List[Diagnostico] = []
        # (etapa, campo) usados em comparações (fora de `is empty`), p/ o aviso de campo opcional
        self.usos: List[Tuple[str, str]] = []
        # campos cujo vazio a própria expressão trata (`is empty` / `is not empty`)
        self.vazios: set = set()

    # -- operandos ---------------------------------------------------------

    def _campo(self, ref: FieldRefExpr) -> _Operando:
        form_name = ref.form_name or self.escopo.source_form
        if form_name not in self.forms:
            if ref.form_name is not None:
                self.erros.append((ref.lineno, f"Condição do flow '{self.escopo.flow_name}' referencia formulário inexistente '{form_name}'."))
            return _Operando(None)       # origem inexistente já foi informada
        form = self.forms[form_name]
        if ref.field_name not in form.fields:
            self.erros.append((ref.lineno, f"Condição do flow '{self.escopo.flow_name}' referencia campo inexistente '{ref.field_name}' na etapa '{form_name}'."))
            return _Operando(None)
        campo = form.fields[ref.field_name]
        if campo.field_type == 'file':
            self.erros.append((ref.lineno, f"Campo '{ref.field_name}' do tipo 'file' não pode ser usado em condição."))
            return _Operando(None)
        if campo.is_array:
            self.erros.append((ref.lineno, f"Campo '{ref.field_name}' é uma lista e não pode ser usado em condição."))
            return _Operando(None)
        return _Operando(campo.field_type, campo=ref.field_name, obj=campo)

    def _operando(self, expr: ExprNode) -> _Operando:
        if isinstance(expr, FieldRefExpr):
            return self._campo(expr)
        return _Operando(_literal_type(expr.value), literal=True, valor=expr.value)

    def _registrar_uso(self, ref: FieldRefExpr, op: _Operando) -> None:
        if op.tipo is not None:
            self.usos.append((ref.form_name or self.escopo.source_form, ref.field_name))

    # -- valor literal contra um campo -------------------------------------

    def _valor_contra_campo(self, linha: int, op: _Operando, valor: Any) -> bool:
        f_type = op.tipo
        if not _condition_value_ok(f_type, valor):
            self.erros.append((linha, f"Valor '{_show(valor)}' é incompatível com o tipo '{f_type}' do campo '{op.campo}' na condição."))
            return False
        if f_type == 'date':
            try:
                datetime.date.fromisoformat(valor)
            except ValueError:
                self.erros.append((linha, f"Valor '{valor}' não é uma data válida (use AAAA-MM-DD) na condição."))
                return False
        if f_type == 'uuid' and _uuid_canonico(valor) is None:
            self.erros.append((linha, f"Valor '{valor}' não é um UUID válido na condição."))
            return False
        return True

    # -- nós ----------------------------------------------------------------

    def booleano(self, expr: ExprNode) -> bool:
        """Verifica `expr` como condição booleana. Devolve False se houve erro."""
        if isinstance(expr, FieldRefExpr):
            op = self._campo(expr)
            if op.tipo is None:
                return False
            if op.tipo != 'boolean':
                self.erros.append((expr.lineno, f"A condição precisa ser verdadeira ou falsa, mas o campo '{expr.field_name}' é do tipo '{op.tipo}'."))
                return False
            return True
        if isinstance(expr, LiteralExpr):
            if not isinstance(expr.value, bool):
                self.erros.append((expr.lineno, f"A condição precisa ser verdadeira ou falsa, mas o valor '{_show(expr.value)}' não é booleano."))
                return False
            return True
        if isinstance(expr, LogicExpr):
            esq = self.booleano(expr.left)
            dir_ = self.booleano(expr.right)
            return esq and dir_
        if isinstance(expr, NotExpr):
            return self.booleano(expr.operand)
        if isinstance(expr, CompareExpr):
            return self.comparacao(expr)
        if isinstance(expr, InExpr):
            return self.em_lista(expr)
        if isinstance(expr, EmptyExpr):
            return self.vazio(expr)
        raise TypeError(f"nó de expressão desconhecido: {type(expr).__name__}")

    def comparacao(self, c: CompareExpr) -> bool:
        esq, dir_ = self._operando(c.left), self._operando(c.right)
        for ref, op in ((c.left, esq), (c.right, dir_)):
            if isinstance(ref, FieldRefExpr):
                self._registrar_uso(ref, op)
        if esq.tipo is None or dir_.tipo is None:
            return False
        ok = True
        if esq.literal and dir_.literal:
            ok = self._literal_literal(c, esq, dir_)
        elif esq.literal or dir_.literal:
            campo, lit = (dir_, esq) if esq.literal else (esq, dir_)
            if not self._valor_contra_campo(c.lineno, campo, lit.valor):
                ok = False
            elif c.op not in _EQUALITY_OPS and campo.tipo not in _ORDERED_TYPES:
                self.erros.append((c.lineno, f"Operador '{c.op}' não pode ser usado com o campo '{campo.campo}' do tipo '{campo.tipo}'."))
                ok = False
        else:
            ok = self._campo_campo(c, esq, dir_)
        return ok

    def _campo_campo(self, c: CompareExpr, a: _Operando, b: _Operando) -> bool:
        compativel = a.tipo == b.tipo or (a.tipo in _NUMERIC and b.tipo in _NUMERIC)
        if not compativel:
            self.erros.append((c.lineno, f"Não é possível comparar o campo '{a.campo}' ({a.tipo}) com o campo '{b.campo}' ({b.tipo}) na condição."))
            return False
        if c.op not in _EQUALITY_OPS and a.tipo not in _ORDERED_TYPES:
            self.erros.append((c.lineno, f"Operador '{c.op}' não pode ser usado com o campo '{a.campo}' do tipo '{a.tipo}'."))
            return False
        return True

    def _literal_literal(self, c: CompareExpr, a: _Operando, b: _Operando) -> bool:
        compativel = a.tipo == b.tipo or (a.tipo in _NUMERIC and b.tipo in _NUMERIC)
        if not compativel:
            self.erros.append((c.lineno, f"Não é possível comparar o valor '{_show(a.valor)}' ({a.tipo}) com o valor '{_show(b.valor)}' ({b.tipo}) na condição."))
            return False
        if c.op not in _EQUALITY_OPS and a.tipo not in _NUMERIC:
            self.erros.append((c.lineno, f"Operador '{c.op}' não pode ser usado com valores do tipo '{a.tipo}'."))
            return False
        return True

    def em_lista(self, e: InExpr) -> bool:
        op = self._campo(e.target)
        self._registrar_uso(e.target, op)
        if op.tipo is None:
            return False
        ok = True
        vistos = []
        for lit in e.values:
            if not self._valor_contra_campo(lit.lineno, op, lit.value):
                ok = False
                continue
            chave = _uuid_canonico(lit.value) if op.tipo == 'uuid' else lit.value
            if chave in vistos:
                self.avisos.append((lit.lineno, f"O valor '{_show(lit.value)}' aparece mais de uma vez na lista de 'in' do campo '{op.campo}'."))
            vistos.append(chave)
        return ok

    def vazio(self, e: EmptyExpr) -> bool:
        op = self._campo(e.target)
        if op.tipo is None:
            return False
        self.vazios.add((e.target.form_name or self.escopo.source_form, e.target.field_name))
        if op.tipo == 'boolean':
            sempre = 'verdadeiro' if e.negated else 'falso'
            self.avisos.append((e.lineno, f"O campo booleano '{op.campo}' nunca fica vazio; '{'is not empty' if e.negated else 'is empty'}' é sempre {sempre}."))
        return True


def checar_condicao(expr: ExprNode, escopo: Escopo, forms: Dict[str, Any]) -> Tuple[List[Diagnostico], List[Diagnostico]]:
    """
    Atributo `tipo` da condição (precisa ser booleana) + avisos.
    Devolve (erros, avisos); avisos só são gerados se não houve erro.
    """
    v = _Verificador(escopo, forms)
    v.booleano(expr)
    if v.erros:
        return v.erros, []
    avisos = list(v.avisos)

    # Aviso: campo opcional em comparação (decisão: lógica de dois valores).
    # Não avisa se a própria expressão trata o vazio com `is empty`.
    vistos = set()
    for form_name, field_name in v.usos:
        if (form_name, field_name) in vistos or (form_name, field_name) in v.vazios:
            continue
        vistos.add((form_name, field_name))
        campo = forms[form_name].fields[field_name]
        if campo.properties.get('required') is True or campo.field_type == 'boolean':
            continue
        avisos.append((expr.lineno,
            f"O campo opcional '{field_name}' é usado na condição da transição de '{escopo.source_form}'; "
            f"se ficar vazio, a comparação dá falso (use '{field_name} is empty' para tratar esse caso)."))

    # Aviso: condição constante (nenhum campo na expressão).
    if not expr.deps:
        valor = avaliar_json(para_json(expr, escopo, forms), lambda step, name: None)
        avisos.append((expr.lineno, f"A condição da transição de '{escopo.source_form}' é sempre {'verdadeira' if valor else 'falsa'}."))
    return [], avisos


# ---------------------------------------------------------------------------
# Serialização para os geradores
# ---------------------------------------------------------------------------

def _op_json(expr: ExprNode, escopo: Escopo, forms: Dict[str, Any]) -> Dict[str, Any]:
    if isinstance(expr, FieldRefExpr):
        step = expr.form_name or escopo.source_form
        return {"k": "field", "step": step, "name": expr.field_name,
                "type": forms[step].fields[expr.field_name].field_type}
    return {"k": "lit", "v": expr.value}


def _norm_uuid(no: Dict[str, Any], valor: Any) -> Any:
    if no.get("type") == "uuid" and isinstance(valor, str):
        return _uuid_canonico(valor) or valor
    return valor


def para_json(expr: ExprNode, escopo: Escopo, forms: Dict[str, Any]) -> Dict[str, Any]:
    """Árvore da expressão em dicionários/listas/valores simples (JSON-safe)."""
    if isinstance(expr, LogicExpr):
        return {"k": expr.op, "l": para_json(expr.left, escopo, forms), "r": para_json(expr.right, escopo, forms)}
    if isinstance(expr, NotExpr):
        return {"k": "not", "e": para_json(expr.operand, escopo, forms)}
    if isinstance(expr, CompareExpr):
        l, r = _op_json(expr.left, escopo, forms), _op_json(expr.right, escopo, forms)
        # literal comparado com campo `uuid`: normaliza para minúsculas
        if l["k"] == "lit" and r["k"] == "field":
            l["v"] = _norm_uuid(r, l["v"])
        if r["k"] == "lit" and l["k"] == "field":
            r["v"] = _norm_uuid(l, r["v"])
        return {"k": "cmp", "op": expr.op, "l": l, "r": r}
    if isinstance(expr, InExpr):
        f = _op_json(expr.target, escopo, forms)
        return {"k": "in", "f": f, "v": [_norm_uuid(f, lit.value) for lit in expr.values], "neg": expr.negated}
    if isinstance(expr, EmptyExpr):
        return {"k": "empty", "f": _op_json(expr.target, escopo, forms), "neg": expr.negated}
    return _op_json(expr, escopo, forms)    # campo booleano sozinho ou literal booleano


# ---------------------------------------------------------------------------
# Avaliador Python único (copiado como texto para o app.py gerado)
# ---------------------------------------------------------------------------

def avaliar_json(no, lookup):
    """Avalia a árvore de `para_json`. `lookup(etapa, campo)` -> valor ou None (vazio)."""
    k = no['k']
    if k == 'or':
        return avaliar_json(no['l'], lookup) or avaliar_json(no['r'], lookup)
    if k == 'and':
        return avaliar_json(no['l'], lookup) and avaliar_json(no['r'], lookup)
    if k == 'not':
        return not avaliar_json(no['e'], lookup)
    if k == 'lit':
        return no['v'] is True

    def valor(op):
        return op['v'] if op['k'] == 'lit' else lookup(op['step'], op['name'])

    if k == 'field':
        return lookup(no['step'], no['name']) is True
    if k == 'cmp':
        a, b, op = valor(no['l']), valor(no['r']), no['op']
        if a is None or b is None:
            return False
        if op == '==':
            return a == b
        if op == '!=':
            return a != b
        if op == '<':
            return a < b
        if op == '<=':
            return a <= b
        if op == '>':
            return a > b
        return a >= b
    if k == 'in':
        v = valor(no['f'])
        if v is None:
            return False
        achou = v in no['v']
        return (not achou) if no['neg'] else achou
    if k == 'empty':
        vazio = valor(no['f']) is None
        return (not vazio) if no['neg'] else vazio
    raise ValueError('nó de expressão desconhecido: ' + str(k))
