# FastAPI Service (`api/`) — Architektur

Doku der gewählten Architektur für das Python-Teilprojekt `api/`. Gilt als
Referenz für Erweiterungen — neue Features sollen diesem Muster folgen.

## Monorepo-Aufteilung

Das Repo enthält zwei unabhängige Projekte:

```
ARDU-DigSig-Prototype/
├── arduino/    # Arduino UNO Q App Lab App (wird per rsync.sh aufs Board gesynct)
└── api/        # FastAPI-Service (eigene venv, NICHT aufs Board gesynct)
```

`rsync.sh` synct bewusst nur `arduino/`. Die beiden Teile sind getrennt, damit
Board-Deployment und Python-Service unterschiedliche Lebenszyklen haben.

## Leitprinzip: dünne Layer über gemeinsamem Kern

Web-Routen **und** CLI-Befehle sind dünne Hüllen. Die eigentliche Logik lebt
einmalig in `services/`. Beide Einstiegspunkte rufen denselben Service auf →
keine Duplizierung, beide testbar.

```
HTTP-Route ─┐
            ├─► services/  ─►  models / db        (eine Quelle für Logik)
CLI-Befehl ─┘
```

## Verzeichnisstruktur

```
api/
├── pyproject.toml          # Metadaten, Dependencies, `digsig` Entry Point
├── alembic.ini             # Alembic-Config
├── migrations/             # Alembic env.py + versions/ (committet)
└── app/                    # importierbares Code-Paket (versioniert, read-only)
    ├── config.py           # Settings (env/.env), abgeleitete Pfade
    ├── db.py               # async Engine, Session, SQLite-PRAGMAs, init_db
    ├── storage.py          # ensure_dirs() für storage/-Layout
    ├── models.py           # SQLModel-Tabellen: Item, StoredFile
    ├── services/           # ← gemeinsame Geschäftslogik (API + CLI)
    │   ├── items.py
    │   └── files.py
    ├── api/                # Web-Layer (dünn)
    │   ├── main.py         # FastAPI-App + lifespan (ensure_dirs + init_db)
    │   └── routers/        # ein Router pro Domäne
    │       ├── items.py
    │       └── files.py
    └── cli/                # Konsolen-Layer (dünn)
        ├── __init__.py     # Typer-Haupt-App → `digsig`
        └── commands/       # ein Modul pro Befehlsgruppe
            ├── db.py
            ├── items.py
            └── files.py
```

## Entscheidungen & Begründungen

### Code-Layer trennen (web / cli / services)
Routen und Befehle enthalten keine Logik, nur Ein-/Ausgabe-Übersetzung. Neue
Domäne = neues `services/<x>.py` + dünner Router + dünne Befehlsgruppe.

### CLI über Entry Point (Typer)
`pyproject.toml` → `[project.scripts] digsig = "app.cli:cli"`. Nach
`pip install -e .` ist `digsig` ein echtes Kommando im PATH (best practice statt
`manage.py`). Subgruppen via `cli.add_typer(...)`. Typer-Befehle sind synchron →
async-DB-Code wird mit `asyncio.run(...)` gekapselt.

### Persistenz: SQLite via SQLModel + SQLAlchemy async (aiosqlite)
Modelle sind **SQLModel**-Klassen (Pydantic + SQLAlchemy vereint); die Engine ist
SQLAlchemys async Engine, Sessions sind SQLModels `AsyncSession` (`session.exec`).
`db.py` setzt per Connection-Event diese PRAGMAs (entscheidend für Effizienz):
- `journal_mode=WAL` — Leser blockieren Schreiber nicht
- `busy_timeout=5000` — kein sofortiges „database is locked"
- `synchronous=NORMAL` — mit WAL sicher und schnell
- `foreign_keys=ON` — FK-Constraints aktiv

Session pro Request via `Depends(get_session)`; CLI nutzt `SessionLocal`.

### Schema-Migrationen: Alembic
Das Schema wird von **Alembic** verwaltet, **nicht** beim App-Start angelegt
(`lifespan` macht nur `ensure_dirs()`). Migrationen laufen als eigener Schritt
(Best Practice, kein Auto-Migrate beim Boot mit mehreren Workern).
- `migrations/env.py` ist async, zieht die DB-URL aus `settings` und nutzt
  `SQLModel.metadata` für Autogenerate; `render_as_batch=True` (SQLite kann
  kaum `ALTER` in place); `script.py.mako` importiert `sqlmodel` für die
  generierten `AutoString`-Typen.
- Bedient über die `digsig db`-Befehle (dünner Wrapper um Alembic):
  `digsig db revision "msg"` (autogenerate) → Datei in `migrations/versions/`
  prüfen → `digsig db upgrade` / `downgrade` / `current`. Das rohe `alembic`-CLI
  geht ebenso.

### `storage/` außerhalb des Code-Pakets
Veränderlicher Laufzeit-Zustand (DB-Datei + Content-HTML-Dateien) liegt in
`api/storage/`, **neben** `app/`, nicht darin. Gründe:
- **Code vs. Daten**: `app/` ist versioniert, paketiert, read-only; `storage/`
  ist veränderlich.
- **Packaging/Deployment**: `app/` wird zu einem Wheel/Image — Daten dürfen da
  nicht hineinwandern.
- **Read-only-Container**: in Prod ist nur ein gemountetes Volume beschreibbar →
  auf `storage/` gemountet.
- **Twelve-Factor**: unveränderliches Code-Artefakt, Zustand separat.

Pfade sind CWD-unabhängig aus `BASE_DIR` (= `api/`) abgeleitet, sodass Server
und CLI garantiert dieselbe DB/Dateien nutzen. `storage/`-Inhalt ist gitignored
(`storage/*`, nur `.gitkeep` bleibt). Dasselbe Muster wie Laravels `storage/`.

### Domäne: Pools und Contents (1:n)
- **`Pool`** (id, name, description) — benannter Eimer für HTML-Snippets.
- **`Content`** (id, pool_id FK, name) — ein HTML-Schnipsel, gehört zu genau
  einem Pool. Die HTML-Bytes liegen **auf Platte** unter
  `storage/pools/<pool_id>/<content_id>.html`, nur Metadaten in der DB.
- Cascade-Delete: Pool löschen entfernt alle Contents (DB) **und** das
  Pool-Verzeichnis (FS).

### Drei Runtime-Endpoints (= die drei Varianten)
- `GET /pools/{id}` → ganzer Pool inkl. aller Contents+HTML inline.
  Für **Variante 1** (Edge-only): Arduino zieht den Pool einmal, wählt lokal
  über den on-device `personal:llm` Brick (Custom-Brick in `arduino/bricks/personal_llm/`).
- `POST /pools/{id}/choose-by-context` (JSON-Body: offenes Dict, z.B.
  `{"audience": {"group": "young_adult"}, "weather": "rain"}`) → ein gewählter
  Content + `reasoning`. **Variante 2** (Hybrid, Claude textbasiert). Der Body
  ist absichtlich offen — beliebige Top-Level-Keys (`loudness`, `time_of_day`,
  …) fließen unverändert ins Prompt. Trade-off: keine 422 mehr für Tippfehler,
  dafür API-Vertrag bleibt stabil, wenn der Client neue Signale schickt.
- `POST /pools/{id}/choose-by-img` (multipart `image`, optional Form-Feld
  `context` = JSON-String, gleiche offene Form wie V2) → ein gewählter
  Content + `reasoning`. **Variante 3** (Cloud-only, Claude Vision).

Antwortform der Choose-Endpoints: `{pool_id, chosen_id, name, description, html, reasoning}`.
Claude wird mit einem JSON-Schema Output-Constraint aufgerufen, das Ergebnis
gegen Pydantic validiert; die `chosen_id` muss aus dem Pool stammen — sonst
HTTP 502.

### Claude-Integration (`services/selection.py`)
- Async via `anthropic.AsyncAnthropic`-Client, Modell `claude-haiku-4-5`
  (überschreibbar via `CLAUDE_MODEL`).
- Strukturierte Outputs: JSON-Schema mit `chosen_id` + `reasoning` als Pflichtfelder.
- Konfig per Env/.env: `ANTHROPIC_API_KEY` (Pflicht für V2 & V3),
  `CLAUDE_MODEL`, `CLAUDE_MAX_TOKENS`, `CLAUDE_TIMEOUT_SECONDS`.
- Fehlerklasse `SelectionError` → Routes übersetzen zu HTTP 502.

### Prompts als Jinja2-Templates
Prompts liegen **nicht** als Python-Strings in `selection.py`, sondern als
`.j2`-Dateien unter `app/templates/`, geladen via `PackageLoader` in
`app/prompts.py` (`StrictUndefined`, keine HTML-Autoescape, `trim_blocks`).
Templates:
- `selection_system.j2` — System-Prompt mit JSON-Output-Vertrag.
- `_candidates.j2` — Kandidatenliste, in beiden User-Templates included.
- `_context.j2` — generischer Kontext-Block (rendert beliebiges Dict via
  `| tojson`), in beiden User-Templates included.
- `choose_by_context_user.j2` — V2 User-Prompt (text-only).
- `choose_by_image_user.j2` — V3 User-Prompt (mit `<image>`-Block + Kontext).

Prompts ändern = `.j2` editieren; kein Python-Diff.

### Tests
`pytest` + `pytest-asyncio` (auto-mode). Fixtures in `tests/conftest.py`:
isoliertes `STORAGE_DIR` per Tempdir, DB-Tabellen werden zwischen Tests
gedroppt+neu angelegt (sync via `asyncio.run()`, damit auch CLI-Tests
funktionieren). Claude wird per `monkeypatch.setattr(selection, "_post_chat", ...)`
gemockt; Templates werden direkt gerendert getestet (`test_prompts.py`).

## Befehle (Kurzreferenz)

```bash
cd api && pip install -e ".[dev]"       # Deps + `digsig`-CLI + Test-Deps
digsig db upgrade                       # Migrationen anwenden (Schema anlegen)
uvicorn app.api.main:app --reload       # Server (http://localhost:8000/docs)
digsig pool create "rainy"
digsig content add 1 --name "umbrella" --html-file ./snippet.html
pytest                                  # Tests
```
