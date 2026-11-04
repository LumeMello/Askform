


# Forms and APIs DSL Compiler (FAD-Compiler)

A robust domain-specific language (DSL) compiler and code generation engine designed to unify declarative user interface schemas, multi-step wizards, and REST API ingestion contracts. 

FAD-Compiler translates high-level domain definitions into production-ready artifacts, including interactive HTML5 multi-step wizard applications with client-side state propagation and type-safe Python/Flask backend routers.

---

## Architecture & Compilation Pipeline

The compilation workflow consists of three primary phases managed by the compiler driver (`main.py`):

1. **Syntactic Analysis (Lexer & Parser):** Employs PLY (Python Lex-Yacc) to tokenize source files (`.fad`), construct an Abstract Syntax Tree (AST), and enforce strict grammar rules.
2. **Semantic Analysis:** Validates scope uniqueness, type consistency, cross-reference integrity (such as inter-step field binding), and route parameter mappings.
3. **Code Generation:** Emits target code artifacts into the `dist/` directory:
   - Interactive, multi-step HTML5 form wizards with client-side state preservation and validation.
   - A fully typed Flask backend application (`app.py`) to handle payload ingestion.

---

## Project Structure

```text
├── lexer.py             # Lexical analyzer and token definitions
├── parser.py            # LALR(1) syntactic parser and AST builder
├── symbol_table.py      # Scope management, types, and AST node definitions
├── semantic.py          # Static semantic checker and cross-reference validator
├── generator_html.py    # Multi-step wizard UI generator
├── generator_flask.py   # REST API backend router generator
├── main.py              # CLI compiler driver and orchestrator
└── dist/                # Output directory for generated code artifacts
```

---

## Prerequisites & Dependencies

The project relies strictly on **Python 3** and **PLY (Python Lex-Yacc)** for lexical and syntactic analysis. No additional external frameworks are required to run the compiler core.

To install the required parser generator dependency:

```bash
pip install ply==3.11
```

---

## Getting Started & Execution

Compile and run a sample DSL definition file using the compiler driver:

```bash
python main.py seu_programa.fad
```

This will output the compiled artifacts into the `dist/` folder. To spin up the generated backend server:

```bash
python dist/app.py
```

---

## Configuring Data Persistence Targets

By default, the generated backend router (`dist/app.py`) accepts and validates incoming payloads from wizards or API endpoints, returning a success response with the structured JSON data. 

To connect the generated API endpoints to your preferred persistence layer (such as PostgreSQL, MongoDB, SQLAlchemy, or an external microservice):

1. **Locate the generated route handler** inside `generator_flask.py` (or directly modify the generated `dist/app.py` file if you prefer manual wiring).
2. Find the submission route block corresponding to your wizard or API endpoint:
   ```python
   @app.route('/api/seudominio/submit', methods=['POST'])
   def submit_wizard_seudominio():
       payload = request.get_json(silent=True) or {}
       # ... validation logic ...
   ```
3. **Inject your persistence logic** right before the return statement:
   ```python
   # Exemplo com SQLAlchemy / Banco de Dados Relacional
   # novo_registro = MeuModeloTabela(dados=payload)
   # db.session.add(novo_registro)
   # db.session.commit()
   ```

By centralizing schema definitions in your `.fad` source files, any updates to field types or validation constraints propagate consistently across both the frontend forms and the backend ingestion contracts.
