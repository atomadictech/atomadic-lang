"""``python -m atomadic_lang`` — dispatch to the Typer CLI."""

from .a4_sy_orchestration.cli import app

if __name__ == "__main__":
    app()
