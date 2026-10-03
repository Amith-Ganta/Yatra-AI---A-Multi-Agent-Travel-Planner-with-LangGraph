"""main.py must load .env before anything reads the settings.

Only the root Settings class has an env_file. The nested sections (database, llm, mcp) and the
tools read os.environ, so a DATABASE_URL that lives only in .env made the app fail at import
until main.py called load_dotenv. The test pins that order, because it is easy to undo by moving
an import.
"""

import ast
from pathlib import Path

MAIN = Path(__file__).resolve().parents[2] / "main.py"


def _first_line(tree: ast.Module, match: "type[ast.AST]", name: str) -> int:
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and match is ast.ImportFrom and node.module == name:
            return node.lineno
        if isinstance(node, ast.Call) and match is ast.Call:
            func = node.func
            if isinstance(func, ast.Name) and func.id == name:
                return node.lineno
    raise AssertionError(f"{name} not found in main.py")


def test_main_loads_dotenv_before_importing_the_app():
    tree = ast.parse(MAIN.read_text(encoding="utf-8"))

    load_call = _first_line(tree, ast.Call, "load_dotenv")
    app_import = _first_line(tree, ast.ImportFrom, "src.api")

    assert load_call < app_import


def test_main_does_not_let_the_file_override_real_environment_variables():
    # Render and Docker set real variables; a stray .env in the image must not beat them.
    source = MAIN.read_text(encoding="utf-8")

    assert "load_dotenv(override=False)" in source
