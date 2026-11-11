<img width="2000" height="1125" alt="Askform Logo" src="https://github.com/user-attachments/assets/7f3ed612-9a36-4edf-a9d3-862fee92b10f" />


# 🛠️ Askform DSL

O **Askform** é uma linguagem de domínio específico (DSL) e compilador construído em Python (utilizando a biblioteca `PLY` — *Python Lex-Yacc*). O objetivo do Askform é permitir a especificação declarativa de formulários web, validações de campos, abstração de temas visuais e mapeamento de endpoints REST de forma rápida e segura.

O compilador lê arquivos de especificação (`.fad` / `.askform`), realiza análise léxica, sintática e semântica estrita, e gera automaticamente como artefatos finalizados:
1. **Página HTML5 responsiva** (`dist/<form_name>.html`) com suporte nativo a `FormData`, validações no lado do cliente, suporte a envio de arquivos e fallback automático de comunicação via `fetch` HTTP.
2. **Servidor backend em Flask** (`dist/app.py`) dinâmico com persistência automática em banco de dados SQLite (`database.db`), middleware com suporte total a CORS, sanitização de identificadores SQL e tratamento de uploads de arquivos.

📖 **[Acesse a Documentação Completa no Google Drive](https://docs.google.com/document/d/1LmWLQvcHF1gwP22vvsaTMDQxMBQqgxs6z66bm8NaOCc/edit?usp=sharing)**

---

## 📐 Estrutura da Linguagem (Comandos e Blocos da DSL)

A DSL é composta por 4 blocos estruturais de declaração: `theme`, `form`, `api` e `flow`.

### 1. Bloco `theme` (Estilização da Interface)
Define as variáveis visuais para renderização do CSS do formulário HTML gerado.

```dsl
theme NomeDoTema {
  background = "#0f172a";
  card_background = "#1e293b";
  text_color = "#f8fafc";
  accent_color = "#38bdf8";
  font_family = "Courier New, monospace";
  border_radius = "12px";
}
```

* **Propriedades suportadas:** `background`, `card_background`, `text_color`, `accent_color`, `font_family`, `border_radius`.

---

### 2. Bloco `form` (Estruturação de Dados e Validações)
Define os campos do formulário, tipos de dados, regras obrigatórias e restrições de validação.

```dsl
form ProfileForm {
  userId: integer {
    label = "Código do Usuário";
    required = true;
  };
  displayName: string {
    label = "Nome de Exibição";
    default = "Desenvolvedor";
  };
  avatar: file {
    label = "Foto de Perfil";
    required = false;
  };

  validate displayName {
    min = 3;
    max = 20;
    pattern = "^[a-zA-Z0-9_]+$";
    message = "O nome deve conter entre 3 e 20 caracteres alfanuméricos.";
  }
}
```

#### Tipos Primitivos de Campos (`field_type`)
* `string`: Texto simples.
* `integer`: Números inteiros.
* `float`: Números decimais.
* `boolean`: Campo lógico (renderizado como checkbox no HTML).
* `date`: Data (formato ISO `YYYY-MM-DD`).
* `uuid`: Identificador único no padrão UUID v4.
* `file`: Upload de arquivos (armazenado de forma segura no backend em `uploads/`).

#### Propriedades de Campo
* `label = "Texto"`: Rótulo exibido na interface gráfica.
* `required = true/false`: Define se o preenchimento é obrigatório.
* `default = valor`: Define o valor padrão inicial do campo.

#### Bloco de Validação (`validate <nome_do_campo>`)
* `min = <número>`: Tamanho mínimo para `string` ou valor mínimo para `integer`/`float`.
* `max = <número>`: Tamanho máximo para `string` ou valor máximo para `integer`/`float`.
* `pattern = "expressão_regular"`: Expressão regular (Regex) para validação contextual de strings.
* `message = "Mensagem de erro"`: Mensagem customizada a ser exibida em caso de violação da regra.

---

### 3. Bloco `api` (Endpoints REST)
Declara os serviços web e mapeia a rota HTTP associada ao formulário. Suporta todos os verbos REST (`GET`, `POST`, `PUT`, `PATCH`, `DELETE`).

```dsl
api UserApi {
  POST "/api/v1/user/{userId}" {
    consumes = ProfileForm;
    produces = uuid;
  }
  GET "/api/v1/user/{userId}" {
    consumes = ProfileForm;
    produces = string;
  }
  PUT "/api/v1/user/{userId}" {
    consumes = ProfileForm;
    produces = boolean;
  }
  PATCH "/api/v1/user/{userId}" {
    consumes = ProfileForm;
    produces = string;
  }
  DELETE "/api/v1/user/{userId}" {
    consumes = ProfileForm;
    produces = boolean;
  }
}
```

* **Verbos HTTP suportados:** `GET`, `POST`, `PUT`, `PATCH`, `DELETE`.
* **Parâmetros de Rota:** Declarações entre chaves (ex: `{userId}`) capturam parâmetros dinâmicos vinculados aos campos do formulário.
* **`consumes`:** nome de um `form` ou do `flow`. Um endpoint com `consumes = NomeDoFlow` recebe os campos de todas as etapas do flow (veja abaixo).

---

### 4. Bloco `flow` (Navegação, Formulários Multi-Página e Caminhos)
Liga os formulários entre si e à API. Cada linha é uma **transição** `Origem -> Destino;`, onde o destino é outra etapa (outra página) ou o envio `Api.VERBO`.

**Formulário de uma página** (igual às versões anteriores):

```dsl
flow UserRegistrationFlow {
  ProfileForm -> UserApi.POST;
}
```

**Formulário multi-página:** cada `form` vira uma etapa. A etapa inicial é a origem da primeira transição. Um campo pode herdar o valor de uma etapa anterior com `default = Etapa.campo;`.

```dsl
api ClienteApi {
  POST "/api/v1/clientes" {
    consumes = CadastroClienteFlow;   // recebe os campos de todas as etapas
    produces = uuid;
  }
}

flow CadastroClienteFlow {
  ResponsavelLegalStep -> DadosCobrancaStep;
  DadosCobrancaStep -> ClienteApi.POST;
}
```

**Caminhos (desvios condicionais):** use `when <condição>` para escolher a próxima etapa. As transições de uma etapa são testadas na ordem em que aparecem; a primeira que casar decide o caminho. A transição sem `when` é o caminho padrão e deve ser a última.

```dsl
flow CadastroFlow {
  TipoClienteStep -> PessoaJuridicaStep when tipo == "PJ";
  TipoClienteStep -> PessoaFisicaStep;

  PessoaFisicaStep -> ResponsavelMenorStep when idade < 18;
  PessoaFisicaStep -> ContatoStep when TipoClienteStep.possuiIndicacao == false;
  PessoaFisicaStep -> IndicacaoStep;

  ResponsavelMenorStep -> ContatoStep;
  PessoaJuridicaStep -> ContatoStep;
  IndicacaoStep -> ContatoStep;

  ContatoStep -> ClienteApi.POST;
}
```

* **Comparações:** `==`, `!=` (todos os tipos) e `<`, `<=`, `>`, `>=` (`integer`, `float` e `date`). Os dois lados podem ser campo ou literal (`idade >= 18`, `18 <= idade`, `idade >= idadeMinima`); campos de tipos incompatíveis não se comparam.
* **Lógica:** `and`, `or`, `not` e parênteses. Precedência, da mais forte para a mais fraca: comparação, `not`, `and`, `or`; `and` e `or` associam à esquerda. Exemplo: `when idade >= 18 and (uf in ("SP", "RJ") or not possuiDocumento)`.
* **Booleano sozinho:** um campo `boolean` (ou `true`/`false`) já é uma condição: `when possuiDocumento and not menor`.
* **Lista e vazio:** `campo in ("a", "b")`, `campo not in (...)`, `campo is empty`, `campo is not empty`. As palavras `and or not in is empty` agora são reservadas e não servem como nome de campo.
* **Campo da condição:** `campo` (da própria etapa de origem) ou `Etapa.campo` (de uma etapa que vem antes em todos os caminhos). Campos `file` e listas (`tipo[]`) não podem ser usados.
* **Valor:** literal do mesmo tipo do campo (`"texto"`, `10`, `1.5`, `true`/`false`; datas como `"2024-01-31"`; `uuid` precisa ser um UUID válido).
* **Campo vazio:** a lógica é de dois valores. Comparação, `in` e `not in` com campo vazio dão falso; `not` apenas inverte; `boolean` ausente vale falso. Para tratar o vazio use `is empty`.
* **Avisos** (não impedem a compilação nem mudam o código de saída): campo opcional usado na condição (sem `is empty` na mesma condição), condição sempre verdadeira ou falsa, valor repetido em `in (...)`, `is empty` em campo booleano.
* **Envio:** o envio para a API (`Etapa -> Api.VERBO`) pode acontecer em qualquer etapa e mandar para APIs diferentes em cada caminho. Só os dados das etapas do caminho percorrido são enviados. Depois de mais de uma etapa, o endpoint precisa ter `consumes = NomeDoFlow`.
* **Backend:** o endpoint que consome o flow grava os campos de todas as etapas na mesma tabela. O servidor **recalcula o caminho** a partir dos dados recebidos: campos de etapas fora do caminho dão erro 400, `required` só vale para as etapas percorridas, e o destino do caminho precisa ser o endpoint chamado. O `PATCH` continua parcial e não recalcula o caminho.

**Regras verificadas pelo compilador:** etapas e APIs existentes; verbo suportado pela API; tipos e operadores das condições (inclusive entre campos); toda etapa com saída e com um caminho padrão (sem `when`), que deve ser o último; nenhuma transição inalcançável depois do caminho padrão; nenhum ciclo; todas as etapas alcançáveis a partir da inicial; nomes de campo únicos entre as etapas; herança (`default = Etapa.campo`) e condições `Etapa.campo` só de etapas que vêm antes em todos os caminhos; e o nome do flow diferente do nome de qualquer formulário.

**Saída gerada:** um flow de uma linha gera a página do formulário (`dist/<form>.html`), como antes. Um flow com várias etapas ou com `when` gera uma única página `dist/<flow>.html` com botões **Voltar** e **Próximo** (o último vira **Enviar dados**).

> O antigo bloco `wizard` foi removido: o que ele fazia (etapas em sequência, herança entre etapas e envio para a API) agora é escrito no `flow`.

---

## 🚀 Guia de Uso e Execução

### Pré-requisitos
* Python 3.9 ou superior instalado.
* Bibliotecas `PLY` (Python Lex-Yacc) e `Flask`:

```bash
pip install ply flask werkzeug
```

---

### 1. Compilando o arquivo DSL

Para compilar seu arquivo de especificação Askform (ex: `exemplo.fad`). Exemplos prontos: `teste.fad` (uma página), `teste_multipagina.fad` (duas páginas com herança) e `teste_caminhos.fad` (caminhos condicionais).

```bash
python main.py exemplo.fad
```

#### Saída esperada no terminal:
```text
Phase 1: Syntactic Parse (Building AST)...
Phase 2: Semantic Analysis...
Compilation Successful! Emitting Artifact Summary...
{
  "forms_compiled": [
    "FeedbackForm"
  ],
  "apis_compiled": [
    "FeedbackApi"
  ],
  "flows_linked": [
    "FeedbackFlow"
  ]
}
Phase 3: Code Generation...
[SUCESSO] Formulário HTML gerado: dist\feedbackform.html
[SUCESSO] Aplicação Flask dinâmica gerada em: dist\app.py
Artifacts generated successfully.
```

Os arquivos gerados são salvos automaticamente no diretório `dist/`.

---

### 2. Iniciando o Servidor Backend

Execute o servidor Flask gerado para habilitar os endpoints e o banco de dados SQLite:

```bash
python dist/app.py
```

O servidor será iniciado por padrão em `http://127.0.0.1:5000`. O banco de dados SQLite `database.db` e o repositório de uploads `uploads/` serão criados na mesma pasta automaticamente.

---

### 3. Executando a Interface Web (HTML)

Abra o arquivo HTML gerado (ex: `dist/feedbackform.html`) diretamente no seu navegador de preferência.

Ao preencher os campos e clicar em **Enviar dados**:
1. As validações nativas e os tipos de dados serão checados no lado do cliente.
2. O script disparará uma requisição `fetch` via HTTP enviando os dados em formato `FormData` para o backend Flask em `http://127.0.0.1:5000`.
3. O Flask responderá com os dados inseridos e a confirmação em JSON:

```json
{
  "status": "success",
  "message": "Registro criado com sucesso",
  "record_id": 1,
  "data": {
    "userId": 1,
    "comments": "Excelente compilador!",
    "attachment": "uploads/a1b2c3d4e5f6.jpg"
  }
}
```

---

### 4. Rodando os testes

```bash
python tests/test_flow.py
```

```bash
python tests/test_expressions.py
python tests/test_compat_preE.py
python oracle/test_oracle.py
```

O primeiro cobre o flow multi-etapas; `test_expressions.py` cobre a gramática das condições (0 conflitos, árvore do `teste.fad` inalterada), precedência, mensagens, avisos, o avaliador (JS×Python via `node`) e o servidor/navegador (precisam de Flask e Playwright; pulados se faltarem); `test_compat_preE.py` compara condições simples com `oracle/main_preE`; o último compara o compilador com a versão anterior em programas que não usam os recursos novos.

---

## 🔒 Segurança e Robustez Integradas

* **Prevenção de SQL Injection:** Todas as operações no banco SQLite utilizam consultas parametrizadas com placeholders (`?`) e identificadores sanitizados.
* **Tratamento de Uploads de Arquivos:** Nomes de arquivos são limpos via `secure_filename()` e renomeados com hashes UUID v4 para evitar sobreposição ou ataques de *Path Traversal*.
* **Suporte a CORS:** O backend possui tratamento de preflight `OPTIONS` e cabeçalhos de *Cross-Origin Resource Sharing* liberados para chamadas locais.
* **Validação em Camadas Duplas:** Regras de tamanho, limites de números e padrões Regex são validados obrigatoriamente tanto no cliente (HTML5) quanto no servidor (Python/Flask).

---

## 📄 License

This project is licensed under the GNU General Public License v3.0 - see the [LICENSE](LICENSE) file for details.
