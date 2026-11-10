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
Main CLI compiler driver for Forms and APIs DSL.
Coordinates parsing, semantic analysis, and output generation.
"""
import sys
import json
from lexer import build_lexer
from parser import build_parser
from semantic import SemanticAnalyzer
from generator_html import generate_html
from generator_flask import generate_flask

def compile_dsl(source_code: str):
    lexer = build_lexer()
    parser = build_parser()

    print("Phase 1: Syntactic Parse (Building AST)...")
    try:
        ast = parser.parse(source_code, lexer=lexer)
        if not ast:
            print("Compilation halted: Failed to construct AST.")
            return False
    except Exception as e:
        print(f"Syntactic Analysis Failed: {str(e)}")
        return False

    print("Phase 2: Semantic Analysis...")
    analyzer = SemanticAnalyzer()
    is_valid = analyzer.analyze(ast)

    if not is_valid:
        print(f"Compilation Failed with {len(analyzer.errors)} semantic error(s):")
        for err in analyzer.errors:
            print(f"  - {err}")
        return False

    print("Compilation Successful! Emitting Artifact Summary...")
    summary = {
        "forms_compiled": list(analyzer.symbol_table.forms.keys()),
        "apis_compiled": list(analyzer.symbol_table.apis.keys()),
        "flows_linked": list(analyzer.symbol_table.flows.keys())
    }
    print(json.dumps(summary, indent=2))

    print("Phase 3: Code Generation...")
    try:
        generate_html(ast)
        generate_flask(ast)
    except ValueError as e:
        print(f"Code Generation Failed: {e}")
        return False
    print("Artifacts generated successfully.")
    return True

if __name__ == "__main__":
    sample_program = """
    form ProfileSetup {
        userId: integer {
            required = true;
        };
        displayName: string {
            label = "Screen Name";
            default = "User";
        };

        validate displayName {
            min = 3;
            max = 20;
            pattern = "^[a-zA-Z0-9_]+$";
        }
    }

    api UserServices {
        PUT "/users/{userId}/profile" {
            consumes = ProfileSetup;
            produces = boolean;
        }
    }

    flow SetupFlow {
        ProfileSetup -> UserServices.PUT;
    }
    """

    if len(sys.argv) > 1:
        with open(sys.argv[1], 'r', encoding='utf-8-sig') as f:
            code = f.read()
    else:
        code = sample_program

    success = compile_dsl(code)
    sys.exit(0 if success else 1)
