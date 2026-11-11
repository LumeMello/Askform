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
Grafo de navegação de um `flow`.

Cada formulário citado no flow é uma etapa (página). As transições
`A -> B` ligam etapas; as transições `A -> Api.VERBO` encerram o fluxo
enviando os dados. A primeira transição declarada define a etapa inicial.

Usado pela análise semântica (ciclos, etapas inalcançáveis, herança em
ordem) e pelos geradores (montagem da página multi-etapas e dos campos
obrigatórios no backend).
"""
from typing import Dict, List, Optional, Set

from symbol_table import FlowNode, TransitionNode


class FlowGraph:
    def __init__(self, flow: FlowNode):
        self.flow = flow
        self.transitions: List[TransitionNode] = list(flow.transitions)
        self.start: Optional[str] = (
            self.transitions[0].source_form if self.transitions else None
        )

        # Etapas na ordem em que aparecem pela primeira vez no flow.
        self.steps: List[str] = []
        self.outgoing: Dict[str, List[TransitionNode]] = {}
        for t in self.transitions:
            self._add_step(t.source_form)
            self.outgoing.setdefault(t.source_form, []).append(t)
            if t.target_form is not None:
                self._add_step(t.target_form)

        self.successors: Dict[str, List[str]] = {s: [] for s in self.steps}
        self.predecessors: Dict[str, List[str]] = {s: [] for s in self.steps}
        for t in self.transitions:
            if t.target_form is None:
                continue
            if t.target_form not in self.successors[t.source_form]:
                self.successors[t.source_form].append(t.target_form)
            if t.source_form not in self.predecessors[t.target_form]:
                self.predecessors[t.target_form].append(t.source_form)

    def _add_step(self, name: str) -> None:
        if name not in self.steps:
            self.steps.append(name)

    # ------------------------------------------------------------------
    # Consultas simples
    # ------------------------------------------------------------------

    def is_simple(self) -> bool:
        """Flow de uma linha só (`Form -> Api.VERBO;`), como antes do multi-etapas."""
        return (
            len(self.transitions) == 1
            and self.transitions[0].is_submit
            and self.transitions[0].condition is None
        )

    def submits(self) -> List[TransitionNode]:
        return [t for t in self.transitions if t.is_submit]

    def reachable(self) -> Set[str]:
        if self.start is None:
            return set()
        seen = {self.start}
        stack = [self.start]
        while stack:
            node = stack.pop()
            for nxt in self.successors.get(node, []):
                if nxt not in seen:
                    seen.add(nxt)
                    stack.append(nxt)
        return seen

    def find_cycle(self) -> Optional[List[str]]:
        """Devolve um ciclo como [A, B, ..., A] ou None se o grafo é acíclico."""
        WHITE, GRAY, BLACK = 0, 1, 2
        color = {s: WHITE for s in self.steps}
        path: List[str] = []

        def visit(node: str) -> Optional[List[str]]:
            color[node] = GRAY
            path.append(node)
            for nxt in self.successors.get(node, []):
                if color[nxt] == GRAY:
                    return path[path.index(nxt):] + [nxt]
                if color[nxt] == WHITE:
                    found = visit(nxt)
                    if found:
                        return found
            path.pop()
            color[node] = BLACK
            return None

        for step in self.steps:
            if color[step] == WHITE:
                found = visit(step)
                if found:
                    return found
        return None

    # ------------------------------------------------------------------
    # Dominadores: etapas visitadas antes de X em TODOS os caminhos
    # ------------------------------------------------------------------

    def dominators(self) -> Dict[str, Set[str]]:
        """
        Para cada etapa alcançável X, o conjunto de etapas que aparecem antes
        de X em todos os caminhos a partir da etapa inicial (X fora do
        conjunto). Requer grafo acíclico.
        """
        reach = self.reachable()
        indegree = {
            s: sum(1 for p in self.predecessors[s] if p in reach) for s in reach
        }
        order: List[str] = []
        queue = [s for s in self.steps if s in reach and indegree[s] == 0]
        while queue:
            node = queue.pop(0)
            order.append(node)
            for nxt in self.successors.get(node, []):
                indegree[nxt] -= 1
                if indegree[nxt] == 0:
                    queue.append(nxt)

        dom: Dict[str, Set[str]] = {}
        for node in order:
            preds = [p for p in self.predecessors[node] if p in dom]
            if node == self.start or not preds:
                dom[node] = set()
                continue
            common = None
            for p in preds:
                candidate = dom[p] | {p}
                common = candidate if common is None else common & candidate
            dom[node] = common or set()
        return dom

    def ancestors(self, step: str) -> Set[str]:
        """Etapas alcançáveis que podem vir antes de `step` em algum caminho."""
        reach = self.reachable()
        seen: Set[str] = set()
        stack = [p for p in self.predecessors.get(step, []) if p in reach]
        while stack:
            node = stack.pop()
            if node in seen:
                continue
            seen.add(node)
            stack.extend(p for p in self.predecessors.get(node, []) if p in reach)
        seen.discard(step)
        return seen
