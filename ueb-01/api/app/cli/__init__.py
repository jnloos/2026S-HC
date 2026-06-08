"""Console entry point. Exposes the `digsig` command (see pyproject.toml)."""
import typer

from app.cli.commands import contents as contents_cmd
from app.cli.commands import db as db_cmd
from app.cli.commands import pools as pools_cmd
from app.cli.commands import seed as seed_cmd

cli = typer.Typer(help="DigSig management CLI", no_args_is_help=True)
cli.add_typer(db_cmd.cli, name="db")
cli.add_typer(pools_cmd.cli, name="pool")
cli.add_typer(contents_cmd.cli, name="content")
cli.add_typer(seed_cmd.cli, name="seed")


if __name__ == "__main__":
    cli()
