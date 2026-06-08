"""Content management commands — thin layer over app.services.contents."""
import asyncio
from pathlib import Path

import typer

from app.db import SessionLocal
from app.services import contents as content_service
from app.services import pools as pool_service

cli = typer.Typer(help="Content commands", no_args_is_help=True)


@cli.command("add")
def add(
    pool_id: int = typer.Argument(..., help="ID of the pool this content belongs to"),
    name: str = typer.Option(..., "--name", "-n", help="Human-readable content name"),
    html_file: Path = typer.Option(
        ...,
        "--html-file",
        "-f",
        exists=True,
        file_okay=True,
        dir_okay=False,
        readable=True,
        help="Path to the HTML snippet file",
    ),
    description: str = typer.Option(
        "",
        "--description",
        "-d",
        help="What the content is for (audience/context hint for the selector)",
    ),
) -> None:
    """Add a content (HTML snippet) to a pool."""

    async def _run() -> None:
        html = html_file.read_text(encoding="utf-8")
        async with SessionLocal() as session:
            pool = await pool_service.get_pool(session, pool_id)
            if pool is None:
                typer.echo(f"pool #{pool_id} not found", err=True)
                raise typer.Exit(code=1)
            content = await content_service.add_content(
                session,
                pool_id=pool_id,
                name=name,
                html=html,
                description=description,
            )
            typer.echo(f"✓ added content #{content.id} ({content.name}) to pool #{pool_id}")

    asyncio.run(_run())


@cli.command("list")
def list_(pool_id: int) -> None:
    """List contents of a pool."""

    async def _run() -> None:
        async with SessionLocal() as session:
            items = await content_service.list_for_pool(session, pool_id)
            if not items:
                typer.echo("(no contents)")
                return
            for c in items:
                typer.echo(f"#{c.id}\t{c.name}")

    asyncio.run(_run())


@cli.command("show")
def show(content_id: int) -> None:
    """Print a content's HTML."""

    async def _run() -> None:
        async with SessionLocal() as session:
            content = await content_service.get_content(session, content_id)
            if content is None:
                typer.echo(f"content #{content_id} not found", err=True)
                raise typer.Exit(code=1)
            html = await content_service.read_html(content)
            typer.echo(f"# content #{content.id} ({content.name}) in pool #{content.pool_id}")
            if content.description:
                typer.echo(f"# description: {content.description}")
            typer.echo(html)

    asyncio.run(_run())


@cli.command("delete")
def delete(content_id: int) -> None:
    """Delete a content."""

    async def _run() -> None:
        async with SessionLocal() as session:
            ok = await content_service.delete_content(session, content_id)
            if not ok:
                typer.echo(f"content #{content_id} not found", err=True)
                raise typer.Exit(code=1)
            typer.echo(f"✓ deleted content #{content_id}")

    asyncio.run(_run())
