"""Seed example data for demos.

Currently ships one ready-made scenario — a bakery shop window — whose HTML
snippets live as files under ``api/fixtures/bakery/`` so they can be edited
and previewed in a browser directly.
"""
import asyncio
from dataclasses import dataclass

import typer

from app.config import BASE_DIR
from app.db import SessionLocal
from app.services import contents as content_service
from app.services import pools as pool_service

cli = typer.Typer(help="Seed example data", no_args_is_help=True)

BAKERY_FIXTURES_DIR = BASE_DIR / "fixtures" / "bakery"
BAKERY_POOL_NAME = "Bäckerei-Schaufenster"
BAKERY_POOL_DESCRIPTION = (
    "Schaufenster-Inhalte einer Bäckerei — Frühstück, Snacks und "
    "Kuchen-Angebote für verschiedene Zielgruppen, Tageszeiten und Wetter."
)


@dataclass(frozen=True)
class _Fixture:
    file: str
    name: str
    description: str


# The descriptions are the primary signal the LLM uses to pick a snippet, so
# spell out audience + weather + time-of-day cues explicitly. Image-heavy
# snippets (Variant 3) rely on them too because the image is the camera frame,
# not the snippet content.
BAKERY_FIXTURES: list[_Fixture] = [
    _Fixture(
        file="01-fruehstueck-to-go.html",
        name="Frühstück to go",
        description=(
            "Croissant + Kaffee zum Mitnehmen. Für Pendler und Berufstätige am "
            "frühen Morgen (vor 10 Uhr); wetterunabhängig."
        ),
    ),
    _Fixture(
        file="02-heisse-schokolade.html",
        name="Heiße Schokolade & Apfelstrudel",
        description=(
            "Gemütliches Heißgetränk mit warmem Apfelstrudel. Für kaltes oder "
            "regnerisches Wetter; passt für Familien und Senioren am Nachmittag."
        ),
    ),
    _Fixture(
        file="03-eiskaffee.html",
        name="Eiskaffee & Beerenkuchen",
        description=(
            "Erfrischendes Sommer-Angebot mit Eiskaffee und kaltem Kuchen. "
            "Für heißes, sonniges Wetter; bevorzugt jüngere bis mittelalte "
            "Erwachsene am Nachmittag."
        ),
    ),
    _Fixture(
        file="04-kinder-naschstation.html",
        name="Kinder-Naschstation",
        description=(
            "Buntes Süßwaren-Angebot mit Donut/Muffin/Keks. NUR anzeigen, "
            "wenn Kinder oder Familien mit Kindern erkannt werden. "
            "Wetterunabhängig, ganztägig."
        ),
    ),
    _Fixture(
        file="05-kaffeeklatsch.html",
        name="Kaffeeklatsch (Kaffee + Kuchen)",
        description=(
            "Klassisches Nachmittagsangebot Kaffee und Kuchen. Besonders "
            "passend für Seniorinnen und Senioren oder kleine Erwachsenen-"
            "Gruppen am Nachmittag; wetterunabhängig."
        ),
    ),
    _Fixture(
        file="06-suppe-broetchen.html",
        name="Suppe & Brötchen Mittagsmenü",
        description=(
            "Herzhafte Suppe mit frischem Brötchen. Für die Mittagszeit "
            "(11–14 Uhr); besonders bei kaltem, regnerischem oder "
            "winterlichem Wetter."
        ),
    ),
]


@cli.command("bakery")
def bakery(
    reset: bool = typer.Option(
        False, "--reset", help=f"If a '{BAKERY_POOL_NAME}' pool exists, delete it first."
    ),
) -> None:
    """Seed the demo bakery shop-window pool."""

    async def _run() -> None:
        async with SessionLocal() as session:
            existing = await pool_service.find_pool_by_name(session, BAKERY_POOL_NAME)
            if existing is not None:
                if not reset:
                    typer.echo(
                        f"pool '{BAKERY_POOL_NAME}' already exists (#{existing.id}); "
                        "pass --reset to recreate it.",
                        err=True,
                    )
                    raise typer.Exit(code=1)
                await pool_service.delete_pool(session, existing.id)
                typer.echo(f"✗ deleted existing pool #{existing.id}")

            pool = await pool_service.create_pool(
                session, name=BAKERY_POOL_NAME, description=BAKERY_POOL_DESCRIPTION
            )
            typer.echo(f"✓ created pool #{pool.id}: {pool.name}")

            for fx in BAKERY_FIXTURES:
                path = BAKERY_FIXTURES_DIR / fx.file
                if not path.exists():
                    typer.echo(f"  ! fixture missing: {path}", err=True)
                    raise typer.Exit(code=1)
                html = path.read_text(encoding="utf-8")
                content = await content_service.add_content(
                    session,
                    pool_id=pool.id,
                    name=fx.name,
                    html=html,
                    description=fx.description,
                )
                typer.echo(f"  ✓ added content #{content.id}: {fx.name}")

            typer.echo(
                f"\nDone. Try: curl http://localhost:8000/pools/{pool.id} | jq ."
            )

    asyncio.run(_run())
