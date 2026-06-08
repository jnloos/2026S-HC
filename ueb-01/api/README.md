# DigSig API (FastAPI)

Python/FastAPI service for the DigSig prototype — simulates a tiny CMS holding
HTML snippets in **pools** and exposes the three Digital-Signage variants the
prototype compares (edge-only / hybrid / cloud-only). See
[`.claude/knowledge/08-project-goal.md`](../.claude/knowledge/08-project-goal.md)
for the variant overview.

Separate project from the Arduino UNO Q app in [`../arduino/`](../arduino/).

## Setup

```bash
cd api
python -m venv .venv && source .venv/bin/activate   # fish: source .venv/bin/activate.fish
pip install -e ".[dev]"   # installs deps + the `digsig` CLI + test deps
digsig db upgrade         # apply migrations -> create the DB schema
```

Configure the Anthropic key (required for variants 2 & 3) in `api/.env`:

```dotenv
ANTHROPIC_API_KEY=sk-ant-...
# optional overrides
CLAUDE_MODEL=claude-haiku-4-5
CLAUDE_MAX_TOKENS=1024
CLAUDE_TIMEOUT_SECONDS=30
# optional debug UI
DEBUG_UI_ENABLED=false
DEBUG_TOKEN=
```

## Run the API

```bash
uvicorn app.api.main:app --reload --host 0.0.0.0 --port 8000
```

- Health check: <http://localhost:8000/health>
- Interactive docs: <http://localhost:8000/docs>

## Tests

```bash
pytest
```

Claude calls are mocked; tests use an isolated tmp `STORAGE_DIR`.

## The three runtime endpoints

| Variant | Endpoint | Body | Returns |
|---------|----------|------|---------|
| 1 (edge-only) | `GET /pools/{id}` | — | `{id, name, description, contents: [{id, name, description, html}]}` |
| 2 (hybrid) | `POST /pools/{id}/choose-by-context` | open JSON object, e.g. `{"audience": {"group": "young_adult"}, "weather": "rain"}` | `{pool_id, chosen_id, name, description, html, reasoning}` |
| 3 (cloud-only) | `POST /pools/{id}/choose-by-img` | `image` (multipart) + optional `context` (form, JSON string) | same as variant 2 |

Variants 2 and 3 go through Claude (`claude-haiku-4-5` by default) with a JSON
Schema output constraint and a validation pass that rejects ids the model
invents. The V2 body is **intentionally open-shaped**: any top-level key flows
into the prompt, so new context signals (loudness, time-of-day, …) don't
require an API change.

## Console commands (`digsig`)

Pools and contents are managed via CLI. Each content's HTML is stored on disk
under `storage/pools/<pool_id>/<content_id>.html`; only metadata lives in the DB.

```bash
digsig --help
digsig db upgrade                                                    # apply migrations
digsig pool create "rainy" --description "wet-weather screens"
digsig pool list
digsig pool show 1                                                   # pool + its contents
digsig content add 1 --name "umbrella ad" --html-file ./snippet.html
digsig content list 1
digsig content show 5
digsig pool delete 1                                                 # cascades to contents
```

(Equivalent without install: `python -m app.cli ...`.)

## Database migrations (Alembic)

The schema is managed by Alembic, not auto-created on startup.

```bash
digsig db revision "add foo column"   # autogenerate from model diff
digsig db upgrade                      # apply
digsig db downgrade                    # revert one step
digsig db current                      # show applied revision
```

## Architecture

Web routes and console commands are **thin layers** over a shared `services/`
core. Claude prompts live as Jinja2 templates under `app/templates/` so
they can be tuned without touching Python.

```
api/
├── pyproject.toml          # metadata, dependencies, `digsig` entry point
├── alembic.ini             # Alembic config
├── migrations/             # Alembic env + version scripts
└── app/
    ├── config.py           # settings (env / .env, incl. ANTHROPIC_*)
    ├── db.py               # async engine, session, SQLite PRAGMAs
    ├── storage.py          # storage/ layout, pool_dir(), content_path()
    ├── models.py           # Pool, Content (1:n)
    ├── prompts.py          # tiny Jinja2 wrapper
    ├── templates/          # prompt templates (.j2)
    │   ├── selection_system.j2
    │   ├── _candidates.j2          # shared candidate-list include
    │   ├── _context.j2             # shared open-context include (V2 + V3)
    │   ├── choose_by_context_user.j2  # V2 user prompt (text)
    │   └── choose_by_image_user.j2    # V3 user prompt (image + context)
    ├── services/           # ← shared business logic (API + CLI)
    │   ├── pools.py
    │   ├── contents.py
    │   └── selection.py    # Claude integration (anthropic AsyncClient)
    ├── api/                # web layer (thin)
    │   ├── main.py
    │   └── routers/pools.py
    └── cli/                # console layer (thin)
        ├── __init__.py     # Typer app -> `digsig`
        └── commands/
            ├── db.py
            ├── pools.py
            └── contents.py
```

## Storage layout

```
storage/
├── db/digsig.db
└── pools/
    └── <pool_id>/
        └── <content_id>.html
```
