"""Pool management commands — thin layer over app.services.pools."""
import asyncio

import typer

from app.db import SessionLocal
from app.services import pools as pool_service

cli = typer.Typer(help="Pool commands", no_args_is_help=True)


@cli.command("create")
def create(name: str, description: str = "") -> None:
    """Create a pool."""

    async def _run() -> None:
        async with SessionLocal() as session:
            pool = await pool_service.create_pool(session, name=name, description=description)
            typer.echo(f"✓ created pool #{pool.id}: {pool.name}")

    asyncio.run(_run())


@cli.command("list")
def list_() -> None:
    """List all pools."""

    async def _run() -> None:
        async with SessionLocal() as session:
            pools = await pool_service.list_pools(session)
            if not pools:
                typer.echo("(no pools)")
                return
            for p in pools:
                typer.echo(f"#{p.id}\t{p.name}\t{p.description}")

    asyncio.run(_run())


@cli.command("show")
def show(pool_id: int) -> None:
    """Show a pool and its contents."""

    async def _run() -> None:
        async with SessionLocal() as session:
            pool = await pool_service.get_pool(session, pool_id)
            if pool is None:
                typer.echo(f"pool #{pool_id} not found", err=True)
                raise typer.Exit(code=1)
            typer.echo(f"#{pool.id}\t{pool.name}\t{pool.description}")
            # Force-load relationship — async session needs explicit refresh for collections.
            from app.services import contents as content_service
            items = await content_service.list_for_pool(session, pool_id)
            if not items:
                typer.echo("  (no contents)")
                return
            for c in items:
                typer.echo(f"  #{c.id}\t{c.name}")

    asyncio.run(_run())


@cli.command("delete")
def delete(pool_id: int) -> None:
    """Delete a pool (and all its contents)."""

    async def _run() -> None:
        async with SessionLocal() as session:
            ok = await pool_service.delete_pool(session, pool_id)
            if not ok:
                typer.echo(f"pool #{pool_id} not found", err=True)
                raise typer.Exit(code=1)
            typer.echo(f"✓ deleted pool #{pool_id}")

    asyncio.run(_run())
